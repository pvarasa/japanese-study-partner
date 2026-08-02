"""Tests for the shared LLM JSON-response parser."""
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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


def _reply(text, *, stop_reason="end_turn", block_type="text"):
    """Stand-in for the SDK's Message, carrying only what complete_json reads."""
    return SimpleNamespace(
        stop_reason=stop_reason,
        usage=SimpleNamespace(output_tokens=len(text)),
        content=[SimpleNamespace(type=block_type, text=text)],
    )


def test_complete_json_builds_request_and_parses(monkeypatch):
    """complete_json wraps the content in a single user message and decodes the reply."""
    captured = {}

    def fake_call_claude(client, **kwargs):
        captured.update(kwargs)
        return _reply('{"ok": true}')

    monkeypatch.setattr(llm, "get_anthropic_client", lambda: object())
    monkeypatch.setattr(llm, "call_claude", fake_call_claude)

    result = complete_json("hello", max_tokens=128)

    assert result == {"ok": True}
    assert captured["model"] == DEFAULT_MODEL
    assert captured["max_tokens"] == 128
    assert captured["messages"] == [{"role": "user", "content": "hello"}]


def test_truncated_reply_reports_truncation(monkeypatch):
    """A reply cut off at max_tokens gets its own message, not the generic one.

    The half-written JSON would otherwise surface as "unexpected response",
    which sends the user to retry the same request and hit the same wall.
    """
    monkeypatch.setattr(llm, "get_anthropic_client", lambda: object())
    monkeypatch.setattr(
        llm, "call_claude",
        lambda client, **kw: _reply('{"items": [{"japanese": "勉', stop_reason="max_tokens"),
    )

    with pytest.raises(HTTPException) as exc:
        complete_json("hello", max_tokens=128)

    assert exc.value.status_code == 502
    assert exc.value.detail == llm.TRUNCATED_MSG


def test_reply_without_text_block_is_rejected(monkeypatch):
    """A reply carrying no text block fails as a bad response, not an IndexError."""
    monkeypatch.setattr(llm, "get_anthropic_client", lambda: object())
    monkeypatch.setattr(
        llm, "call_claude",
        lambda client, **kw: SimpleNamespace(
            stop_reason="refusal", usage=SimpleNamespace(output_tokens=0), content=[]
        ),
    )

    with pytest.raises(HTTPException) as exc:
        complete_json("hello", max_tokens=128)

    assert exc.value.status_code == 502
    assert exc.value.detail == llm.BAD_RESPONSE_MSG
