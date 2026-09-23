"""Tests for model-output checks in the generate router and the lookup cache."""
import pytest

from app.routers import furigana, generate
from app.routers.generate import _checked_options


def test_checked_options_keeps_every_choice():
    opts = ["食べる", "飲む", "見る", "行く"]
    assert sorted(_checked_options(opts, "飲む")) == sorted(opts)


def test_checked_options_rejects_answer_missing_from_options():
    """Exact-match grading would mark every choice wrong and record a lapse."""
    with pytest.raises(ValueError):
        _checked_options(["食べる (to eat)", "飲む"], "食べる")


def test_checked_options_allows_free_text_questions():
    assert _checked_options([], "anything") == []


def test_question_with_answer_outside_options_is_a_502(client, monkeypatch):
    item = client.post("/api/items/", json={"type": "word", "japanese": "食べる", "meaning": "eat"}).json()
    monkeypatch.setattr(generate, "complete_json", lambda *a, **k: {
        "prompt": "毎日ご飯を＿＿。", "answer": "食べる", "options": ["食べます", "飲む", "見る", "行く"],
    })
    r = client.post(f"/api/generate/question?item_id={item['id']}&mode=fill_blank")
    assert r.status_code == 502


def test_unknown_question_mode_is_rejected(client):
    item = client.post("/api/items/", json={"type": "word", "japanese": "食べる", "meaning": "eat"}).json()
    r = client.post(f"/api/generate/question?item_id={item['id']}&mode=essay")
    assert r.status_code == 422


def test_lookup_does_not_cache_an_empty_meaning(client, monkeypatch):
    replies = iter([{}, {"meaning": "to eat", "reading": "たべる"}])

    async def fake_lookup(*args):
        return next(replies)

    monkeypatch.setattr(furigana, "translate_lookup", fake_lookup)
    monkeypatch.setattr(furigana, "_lookup_cache", {})
    body = {"surface": "食べる", "lemma": "食べる"}
    assert client.post("/api/furigana/lookup", json=body).json()["meaning"] == ""
    # The failed reply wasn't cached, so the retry reaches the model again.
    assert client.post("/api/furigana/lookup", json=body).json()["meaning"] == "to eat"
