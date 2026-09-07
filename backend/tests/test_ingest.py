"""Duplicate detection on the ingest/extraction path."""
import json

import app.routers.ingest as ingest_mod


def _fake_extract(items):
    def fake(text, level):
        return {"title": "Test Source", "items": items}
    return fake


def test_flags_item_already_in_library(client, monkeypatch):
    client.post("/api/items/", json={
        "type": "word", "japanese": "食べる", "meaning": "to eat",
    })
    monkeypatch.setattr(ingest_mod, "_extract_with_llm", _fake_extract([
        {"type": "word", "japanese": "食べる", "meaning": "to eat"},
        {"type": "word", "japanese": "飲む", "meaning": "to drink"},
    ]))

    res = client.post("/api/ingest/text", data={"content": "..."})
    assert res.status_code == 200
    by_japanese = {i["japanese"]: i for i in res.json()["items"]}
    assert by_japanese["食べる"]["duplicate"] is True
    assert by_japanese["飲む"]["duplicate"] is False


def test_flags_repeats_within_the_same_batch(client, monkeypatch):
    monkeypatch.setattr(ingest_mod, "_extract_with_llm", _fake_extract([
        {"type": "word", "japanese": "走る", "meaning": "to run"},
        {"type": "word", "japanese": "走る", "meaning": "to run (again)"},
    ]))

    res = client.post("/api/ingest/text", data={"content": "..."})
    items = res.json()["items"]
    assert items[0]["duplicate"] is False
    assert items[1]["duplicate"] is True


def test_save_does_not_require_the_duplicate_field(client, monkeypatch):
    """The review UI round-trips whatever the extraction response gave it."""
    monkeypatch.setattr(ingest_mod, "_extract_with_llm", _fake_extract([
        {"type": "word", "japanese": "泳ぐ", "meaning": "to swim", "duplicate": False},
    ]))
    extracted = client.post("/api/ingest/text", data={"content": "..."}).json()

    res = client.post("/api/ingest/save", data={
        "source_title": extracted["source_title"],
        "source_type": "text",
        "items_json": json.dumps(extracted["items"]),
    })
    assert res.status_code == 200
    assert res.json()["saved_count"] == 1
