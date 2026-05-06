"""Shared helpers for LLM response handling and error translation."""
import json
import logging
import os
import time
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

_BUSY_MSG = "The AI service is busy right now. Please try again in a moment."
_TIMEOUT_MSG = "The AI service did not respond in time. Please try again."
_API_ERROR_MSG = "The AI service returned an error. Please try again later."


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


def call_claude(client: Anthropic, *, retry_on_overload: bool = True, **kwargs) -> Any:
    """Call ``client.messages.create`` with friendly error translation.

    Anthropic SDK exceptions are converted to ``HTTPException`` with a concise
    user-facing ``detail`` and a compact log line — no stack trace for transient
    upstream issues. Overload (HTTP 529) gets a single retry by default.
    """
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
