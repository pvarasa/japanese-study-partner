"""Tests for the shared ai_response guard and malformed-payload tolerance."""
import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.llm import BAD_RESPONSE_MSG, ai_response
from app.schemas import IngestItem, ItemOut

# ---- ai_response guard ------------------------------------------------------

def test_passes_through_on_success():
    with ai_response("op"):
        result = {"ok": True}
    assert result == {"ok": True}


def test_json_decode_error_becomes_502():
    with pytest.raises(HTTPException) as exc:
        with ai_response("op"):
            json.loads("not json")
    assert exc.value.status_code == 502
    assert exc.value.detail == BAD_RESPONSE_MSG


def test_missing_key_becomes_502():
    with pytest.raises(HTTPException) as exc:
        with ai_response("op", item_id=7):
            {"a": 1}["question"]
    assert exc.value.status_code == 502


def test_validation_error_becomes_502():
    with pytest.raises(HTTPException) as exc:
        with ai_response("op"):
            IngestItem(japanese="x")  # missing required fields
    assert exc.value.status_code == 502


def test_existing_http_exception_passes_through_unchanged():
    """call_claude's 503/504 mappings must not be flattened into a generic 502."""
    with pytest.raises(HTTPException) as exc:
        with ai_response("op"):
            raise HTTPException(status_code=503, detail="upstream busy")
    assert exc.value.status_code == 503
    assert exc.value.detail == "upstream busy"


def test_guard_logs_context(caplog):
    with pytest.raises(HTTPException):
        with ai_response("generate_question", item_id=42, mode="fill_blank"):
            raise KeyError("prompt")
    assert "item_id=42" in caplog.text
    assert "mode='fill_blank'" in caplog.text


# ---- IngestItem coercion ----------------------------------------------------

def _item(**overrides):
    base = {"type": "word", "japanese": "猫", "meaning": "cat"}
    base.update(overrides)
    return base


def test_example_sentences_accepts_json_string():
    raw = '[{"japanese": "猫が好き", "english": "I like cats"}]'
    assert IngestItem(**_item(example_sentences=raw)).example_sentences == raw


def test_example_sentences_accepts_real_array():
    """The model routinely returns an array where the prompt asked for a string."""
    parsed = IngestItem(**_item(
        example_sentences=[{"japanese": "猫が好き", "english": "I like cats"}]
    ))
    assert json.loads(parsed.example_sentences) == [
        {"japanese": "猫が好き", "english": "I like cats"}
    ]


def test_example_sentences_keeps_japanese_unescaped():
    parsed = IngestItem(**_item(example_sentences=[{"japanese": "猫", "english": "cat"}]))
    assert "猫" in parsed.example_sentences


def test_example_sentences_none_stays_none():
    assert IngestItem(**_item(example_sentences=None)).example_sentences is None


def test_still_rejects_genuinely_missing_fields():
    with pytest.raises(ValidationError):
        IngestItem(type="word", japanese="猫")  # no meaning


# ---- ItemOut serialisation --------------------------------------------------

def test_item_out_flattens_orm_tags():
    """model_validate replaced a hand-written 15-field mapper; tags still flatten."""
    from app.models import Item, Tag

    item = Item(
        id=1, user_id="u", type="word", japanese="猫", meaning="cat",
        srs_interval=0.0, srs_ease=2.5, srs_reviews=0, srs_correct=0,
        srs_hard=0, srs_lapses=0, suspended=False,
    )
    item.created_at = item.srs_due = __import__("datetime").datetime.now()
    item.tags = [Tag(name="animal"), Tag(name="noun")]

    out = ItemOut.model_validate(item)
    assert out.tags == ["animal", "noun"]
    assert out.japanese == "猫"
    # Derived on the model, not stored — None until the item has been reviewed.
    assert out.pass_rate is None
    assert out.recall_rate is None
    assert out.is_leech is False
