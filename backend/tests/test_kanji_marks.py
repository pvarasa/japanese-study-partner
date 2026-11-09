"""Marked kanji: per-user marks, the Kanji page listing, and the marked drill."""
import json

from app.database import get_db
from app.main import app
from app.models import KanjiInfo


def _add(client, japanese, reading, type="word", meaning="m"):
    r = client.post("/api/items/", json={
        "type": type, "japanese": japanese, "reading": reading, "meaning": meaning,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _db():
    return next(app.dependency_overrides[get_db]())


def _cache_info(kanji, meaning):
    db = _db()
    db.add(KanjiInfo(
        kanji=kanji, meaning=meaning, onyomi=json.dumps(["ダン"]), kunyomi=json.dumps(["ことわ.る"]),
        components="[]", mnemonic="", origin="", example_words="[]",
    ))
    db.commit()


def test_mark_list_and_unmark(client):
    assert client.get("/api/kanji/marks").json() == []

    r = client.put("/api/kanji/marks/断")
    assert r.status_code == 200, r.text
    assert r.json()["kanji"] == "断"
    assert [m["kanji"] for m in client.get("/api/kanji/marks").json()] == ["断"]

    assert client.delete("/api/kanji/marks/断").status_code == 200
    assert client.get("/api/kanji/marks").json() == []
    # Unmarking twice is harmless.
    assert client.delete("/api/kanji/marks/断").status_code == 200


def test_marking_twice_keeps_the_note(client):
    client.put("/api/kanji/marks/断", json={"note": "  not 継  "})
    r = client.put("/api/kanji/marks/断")  # re-marked from the drill, no body
    assert r.json()["note"] == "not 継"
    assert len(client.get("/api/kanji/marks").json()) == 1

    client.put("/api/kanji/marks/断", json={"note": ""})
    assert client.get("/api/kanji/marks").json()[0]["note"] == ""


def test_only_a_single_kanji_can_be_marked(client):
    for bad in ("決断", "か", "a", "々"):
        assert client.put(f"/api/kanji/marks/{bad}").status_code == 422, bad


def test_marks_are_per_user(client):
    client.put("/api/kanji/marks/断")
    assert client.get("/api/kanji/marks", headers={"X-User-ID": "other"}).json() == []
    client.delete("/api/kanji/marks/断", headers={"X-User-ID": "other"})
    assert len(client.get("/api/kanji/marks").json()) == 1


def test_listing_carries_cached_details_and_library_words(client):
    _add(client, "決断", "けつだん")
    _add(client, "断る", "ことわる")
    _add(client, "解決", "かいけつ")
    _cache_info("断", "decide; refuse")

    client.put("/api/kanji/marks/断")
    client.put("/api/kanji/marks/思")  # details never generated

    marks = {m["kanji"]: m for m in client.get("/api/kanji/marks").json()}
    assert marks["断"]["detail"]["meaning"] == "decide; refuse"
    assert marks["断"]["detail"]["kunyomi"] == ["ことわ.る"]
    assert sorted(w["japanese"] for w in marks["断"]["words"]) == ["断る", "決断"]
    assert marks["断"]["word_count"] == 2
    assert marks["思"]["detail"] is None
    assert marks["思"]["words"] == []


def test_marked_practice_serves_words_containing_marked_kanji(client):
    a = _add(client, "決断", "けつだん")
    b = _add(client, "断る", "ことわる")
    _add(client, "解決", "かいけつ")
    _add(client, "印象", "いんしょう")

    # Nothing marked yet: nothing to drill.
    assert client.get("/api/study/reading/practice?marked=true").json() == []

    client.put("/api/kanji/marks/断")
    ids = {i["id"] for i in client.get("/api/study/reading/practice?marked=true").json()}
    assert ids == {a, b}
    # Without the flag, the whole library is in play.
    assert len(client.get("/api/study/reading/practice").json()) == 4


def test_dashboard_counts_marked_kanji(client):
    assert client.get("/api/study/dashboard").json()["marked_kanji"] == 0
    client.put("/api/kanji/marks/断")
    client.put("/api/kanji/marks/決")
    assert client.get("/api/study/dashboard").json()["marked_kanji"] == 2
