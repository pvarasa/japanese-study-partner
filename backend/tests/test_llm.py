"""Tests for the shared LLM JSON-response parser."""
import json

import pytest

from app.llm import parse_json_response


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
