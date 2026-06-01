"""Tests for the shared LLM JSON-response parser."""
import json
from types import SimpleNamespace

import pytest

from app import llm
from app.llm import DEFAULT_MODEL, complete_json, parse_json_response


def test_plain_json():
    assert parse_json_response('{"a": 1}') == {"a": 1}


def test_whitespace_is_ignored():
    assert parse_json_response('\n\n  {"a": 1}\n  ') == {"a": 1}


def test_json_fence_stripped():
    raw = '```json\n{"a": 1, "b": [2, 3]}\n```'
    assert parse_json_response(raw) == {"a": 1, "b": [2, 3]}


def test_bare_triple_backtick_fence():
    raw = '```\n{"ok": true}\n```'
    assert parse_json_response(raw) == {"ok": True}


def test_fence_without_closing_backticks():
    raw = '```json\n{"a": 1}'
    assert parse_json_response(raw) == {"a": 1}


def test_trailing_whitespace_before_close_fence():
    raw = '```json\n{"a": 1}\n   \n```'
    assert parse_json_response(raw) == {"a": 1}


def test_invalid_json_raises():
    with pytest.raises(json.JSONDecodeError):
        parse_json_response("not json")


def test_complete_json_builds_request_and_parses(monkeypatch):
    """complete_json wraps the content in a single user message and decodes the reply."""
    captured = {}

    def fake_call_claude(client, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(text='{"ok": true}')])

    monkeypatch.setattr(llm, "get_anthropic_client", lambda: object())
    monkeypatch.setattr(llm, "call_claude", fake_call_claude)

    result = complete_json("hello", max_tokens=128)

    assert result == {"ok": True}
    assert captured["model"] == DEFAULT_MODEL
    assert captured["max_tokens"] == 128
    assert captured["messages"] == [{"role": "user", "content": "hello"}]
