"""Tests for the pluggable translation module (Ollama path)."""
import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app import translation


@pytest.fixture
def use_ollama(monkeypatch):
    monkeypatch.setenv("TRANSLATION_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://test-ollama:11434")
    monkeypatch.setenv("OLLAMA_TRANSLATION_MODEL", "qwen2.5:7b")


def _patch_httpx_post(monkeypatch, handler):
    """Replace AsyncClient.post with a coroutine that calls ``handler(url, json)``."""

    async def fake_post(self, url, json=None, **kwargs):
        return handler(url, json)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


def _ok_response(body: dict) -> httpx.Response:
    return httpx.Response(200, json=body, request=httpx.Request("POST", "http://x"))


def test_provider_defaults_to_anthropic(monkeypatch):
    monkeypatch.delenv("TRANSLATION_PROVIDER", raising=False)
    assert translation.get_provider() == "anthropic"
    assert translation.get_model() == "claude-sonnet-5"


def test_ollama_word_lookup_parses_json(use_ollama, monkeypatch):
    captured = {}

    def handler(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return _ok_response({
            "message": {"content": '{"meaning": "to eat", "reading": "たべる"}'}
        })

    _patch_httpx_post(monkeypatch, handler)

    result = asyncio.run(
        translation.translate_lookup(
            surface="食べる", lemma="食べる", context="毎日ご飯を食べる。", is_phrase=False
        )
    )

    assert result == {"meaning": "to eat", "reading": "たべる"}
    assert captured["url"] == "http://test-ollama:11434/api/chat"
    assert captured["payload"]["model"] == "qwen2.5:7b"
    assert captured["payload"]["format"] == "json"
    assert captured["payload"]["stream"] is False
    assert "食べる" in captured["payload"]["messages"][0]["content"]


def test_ollama_phrase_uses_phrase_prompt(use_ollama, monkeypatch):
    captured = {}

    def handler(url, payload):
        captured["payload"] = payload
        return _ok_response({"message": {"content": '{"meaning": "to make do", "reading": ""}'}})

    _patch_httpx_post(monkeypatch, handler)

    asyncio.run(
        translation.translate_lookup(
            surface="間に合わせる", lemma="", context="時間がないので", is_phrase=True
        )
    )

    prompt = captured["payload"]["messages"][0]["content"]
    assert "phrase or sentence fragment" in prompt


def test_ollama_non_json_returns_empty_dict(use_ollama, monkeypatch):
    def handler(url, payload):
        return _ok_response({"message": {"content": "I'm sorry, I can't comply."}})

    _patch_httpx_post(monkeypatch, handler)

    result = asyncio.run(
        translation.translate_lookup(surface="x", lemma="", context="", is_phrase=False)
    )
    assert result == {}


def test_ollama_connection_error_raises_503(use_ollama, monkeypatch):
    def handler(url, payload):
        raise httpx.ConnectError("connection refused")

    _patch_httpx_post(monkeypatch, handler)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            translation.translate_lookup(surface="x", lemma="", context="", is_phrase=False)
        )
    assert exc.value.status_code == 503


def test_ollama_timeout_raises_504(use_ollama, monkeypatch):
    def handler(url, payload):
        raise httpx.ReadTimeout("slow")

    _patch_httpx_post(monkeypatch, handler)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            translation.translate_lookup(surface="x", lemma="", context="", is_phrase=False)
        )
    assert exc.value.status_code == 504
