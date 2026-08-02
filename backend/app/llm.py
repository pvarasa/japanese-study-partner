"""Shared helpers for LLM response handling and error translation."""
import json
import logging
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
)
from fastapi import HTTPException

log = logging.getLogger("app.llm")

DEFAULT_MODEL = "claude-sonnet-5"

_BUSY_MSG = "The AI service is busy right now. Please try again in a moment."
_TIMEOUT_MSG = "The AI service did not respond in time. Please try again."
_API_ERROR_MSG = "The AI service returned an error. Please try again later."

# Shown when the model call succeeds but the reply can't be parsed or shaped
# into what the endpoint needs (bad JSON, missing keys, wrong value types).
# call_claude already maps upstream API failures to messages of their own.
BAD_RESPONSE_MSG = "Couldn't generate this — the AI returned an unexpected response. Please try again."

# Truncation gets its own message. It reads as "bad JSON" to the parser, but the
# cause and the fix are completely different — the reply was fine, it just ran
# past max_tokens — and retrying unchanged reproduces it every time.
TRUNCATED_MSG = "The AI's reply was cut off before it finished. Please try again with a shorter piece of text."


@contextmanager
def ai_response(operation: str, **context: Any) -> Iterator[None]:
    """Translate a malformed/unusable model reply into a friendly HTTP 502.

    Wrap the parse-and-build block of any endpoint that consumes model output::

        with ai_response("generate_question", item_id=item_id):
            data = complete_json(prompt, max_tokens=1024)
            return StudyQuestion(prompt=data["prompt"], ...)

    HTTPExceptions raised inside (including the ones call_claude produces for
    upstream failures) pass through untouched; anything else — JSONDecodeError,
    KeyError, ValidationError — is logged with a traceback and reported as 502
    so the caller never sees a bare 500.
    """
    try:
        yield
    except HTTPException:
        raise
    except Exception:
        details = ", ".join(f"{k}={v!r}" for k, v in context.items())
        log.exception("%s failed%s", operation, f" ({details})" if details else "")
        raise HTTPException(status_code=502, detail=BAD_RESPONSE_MSG) from None


def get_anthropic_client() -> Anthropic:
    """Return a configured Anthropic client, raising HTTP 500 if the API key is missing."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
    return Anthropic(api_key=api_key)


def parse_json_response(raw: str) -> dict:
    """Parse a JSON object from a Claude response.

    Strips optional ```json / ``` markdown fences and surrounding whitespace.
    Raises json.JSONDecodeError if the stripped payload isn't valid JSON.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        if "\n" in raw:
            raw = raw.split("\n", 1)[1]
        else:
            raw = raw[3:]
        raw = raw.rstrip()
        if raw.endswith("```"):
            raw = raw[:-3].rstrip()
    return json.loads(raw)


def complete_json(content: str, *, max_tokens: int, model: str = DEFAULT_MODEL) -> dict:
    """Send a single user message to Claude and return its parsed JSON reply.

    Collapses the round-trip shared by every router: build the request, run it
    through ``call_claude`` (which maps upstream API errors to HTTPExceptions),
    and decode the JSON body. Raises ``json.JSONDecodeError`` if the reply isn't
    valid JSON — callers that build a response from the result should guard it.

    A reply that hit ``max_tokens`` is reported as its own 502 rather than being
    left to fail as malformed JSON: the parse error it produces points at the
    JSON, but the actual fix is a bigger budget or a smaller request.
    """
    message = call_claude(
        get_anthropic_client(),
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": content}],
    )
    if message.stop_reason == "max_tokens":
        log.error(
            "Reply truncated at max_tokens=%d (model=%s, output_tokens=%s)",
            max_tokens, model, getattr(message.usage, "output_tokens", "?"),
        )
        raise HTTPException(status_code=502, detail=TRUNCATED_MSG)
    text = next((b.text for b in message.content if b.type == "text"), None)
    if text is None:
        log.error("No text block in reply (stop_reason=%s)", message.stop_reason)
        raise HTTPException(status_code=502, detail=BAD_RESPONSE_MSG)
    return parse_json_response(text)


def call_claude(client: Anthropic, *, retry_on_overload: bool = True, **kwargs) -> Any:
    """Call ``client.messages.create`` with friendly error translation.

    Anthropic SDK exceptions are converted to ``HTTPException`` with a concise
    user-facing ``detail`` and a compact log line — no stack trace for transient
    upstream issues. Overload (HTTP 529) gets a single retry by default.
    """
    # Sonnet 5 runs adaptive thinking by default when `thinking` is omitted. These
    # are all small, structured-JSON calls where thinking only adds latency and
    # cost (and eats into max_tokens), so disable it unless a caller opts in.
    kwargs.setdefault("thinking", {"type": "disabled"})
    attempts = 2 if retry_on_overload else 1
    for attempt in range(1, attempts + 1):
        try:
            return client.messages.create(**kwargs)
        except RateLimitError as e:
            log.warning("Anthropic rate limit (request_id=%s)", getattr(e, "request_id", "?"))
            raise HTTPException(status_code=503, detail=_BUSY_MSG) from e
        except APIStatusError as e:
            if e.status_code == 529:
                log.warning(
                    "Anthropic overloaded (attempt %d/%d, request_id=%s)",
                    attempt, attempts, getattr(e, "request_id", "?"),
                )
                if attempt < attempts:
                    time.sleep(1.0)
                    continue
                raise HTTPException(status_code=503, detail=_BUSY_MSG) from e
            log.error(
                "Anthropic API error %s (request_id=%s): %s",
                e.status_code, getattr(e, "request_id", "?"), e.message,
            )
            raise HTTPException(status_code=502, detail=_API_ERROR_MSG) from e
        except APITimeoutError as e:
            log.warning("Anthropic timeout")
            raise HTTPException(status_code=504, detail=_TIMEOUT_MSG) from e
        except APIConnectionError as e:
            log.warning("Anthropic connection error: %s", e)
            raise HTTPException(status_code=504, detail=_TIMEOUT_MSG) from e
