"""JP→EN translation backend with pluggable provider (Anthropic Claude or local Ollama).

Selected via TRANSLATION_PROVIDER env var ("anthropic" by default, or "ollama").
Ollama configuration: OLLAMA_BASE_URL, OLLAMA_TRANSLATION_MODEL.
"""
import logging
import os

import httpx
from fastapi import HTTPException

from .llm import call_claude, get_anthropic_client, parse_json_response

log = logging.getLogger("app.translation")

DEFAULT_OLLAMA_URL = "http://host.docker.internal:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"

_BUSY_MSG = "The translation service is busy right now. Please try again in a moment."
_TIMEOUT_MSG = "The translation service did not respond in time. Please try again."
_UNAVAILABLE_MSG = "The local translation model is not reachable. Check that Ollama is running."


def get_provider() -> str:
    return os.environ.get("TRANSLATION_PROVIDER", "anthropic").strip().lower() or "anthropic"


def get_model() -> str:
    """Identifier for the active model — used as a cache-key component."""
    if get_provider() == "ollama":
        return os.environ.get("OLLAMA_TRANSLATION_MODEL", DEFAULT_OLLAMA_MODEL)
    return "claude-sonnet-4-6"


def _build_prompt(surface: str, lemma: str, context: str, is_phrase: bool) -> str:
    if is_phrase:
        return f"""Translate this Japanese phrase or sentence fragment naturally into English, preserving its meaning as it appears in context.

Phrase: {surface}
Surrounding context: {context[:300]}

Return ONLY a JSON object with:
- "meaning": a natural English translation (concise, max ~20 words)
- "reading": the hiragana reading of the phrase (empty string if the phrase has no kanji)

Return ONLY valid JSON, no other text."""
    return f"""Give a brief English gloss for this Japanese word as it appears in context.

Word (as it appears): {surface}
Dictionary form: {lemma or surface}
Context: {context[:300]}

Return ONLY a JSON object with:
- "meaning": a short English gloss (max 8 words, e.g. "to eat" or "quickly, rapidly")
- "reading": the hiragana reading of the dictionary form (empty string if the word has no kanji)

Return ONLY valid JSON, no other text."""


async def translate_lookup(
    surface: str, lemma: str, context: str, is_phrase: bool
) -> dict:
    """Return ``{"meaning": str, "reading": str}`` (either may be empty on parse failure)."""
    prompt = _build_prompt(surface, lemma, context, is_phrase)
    if get_provider() == "ollama":
        return await _translate_ollama(prompt)
    return _translate_anthropic(prompt)


def _translate_anthropic(prompt: str) -> dict:
    client = get_anthropic_client()
    message = call_claude(
        client,
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        return parse_json_response(message.content[0].text)
    except Exception:
        return {}


async def _translate_ollama(prompt: str) -> dict:
    base = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL).rstrip("/")
    model = os.environ.get("OLLAMA_TRANSLATION_MODEL", DEFAULT_OLLAMA_MODEL)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "format": "json",
        "stream": False,
        # keep_alive pins the model in VRAM between requests so we don't pay the
        # cold-load tax (~10–30s on a 7B Q4) every time the user idles past Ollama's
        # 5-minute default eviction window.
        "keep_alive": "30m",
        "options": {"temperature": 0.2, "num_predict": 200},
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{base}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.ConnectError as e:
        log.warning("Ollama unreachable at %s: %s", base, e)
        raise HTTPException(status_code=503, detail=_UNAVAILABLE_MSG) from e
    except httpx.TimeoutException as e:
        log.warning("Ollama timeout at %s", base)
        raise HTTPException(status_code=504, detail=_TIMEOUT_MSG) from e
    except httpx.HTTPStatusError as e:
        body = e.response.text[:300] if e.response is not None else ""
        log.error("Ollama HTTP %s: %s", e.response.status_code, body)
        raise HTTPException(status_code=502, detail=_BUSY_MSG) from e

    content = (data.get("message") or {}).get("content", "")
    try:
        return parse_json_response(content)
    except Exception:
        log.warning("Ollama returned non-JSON content: %.200s", content)
        return {}
