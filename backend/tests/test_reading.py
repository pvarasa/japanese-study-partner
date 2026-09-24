"""Kanji-reading drill: its own SRS track, queue selection, and kanji families."""
import pytest

from app import kanji_details as details_mod
from app.database import get_db
from app.kanji import readings_in_word
from app.main import app
from app.models import KanjiInfo, ReadingCard


def _add(client, japanese, reading, type="word", meaning="m"):
    r = client.post("/api/items/", json={
        "type": type, "japanese": japanese, "reading": reading, "meaning": meaning,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _review(client, item_id, rating, **extra):
    return client.post("/api/study/review", json={
        "item_id": item_id, "rating": rating, "card": "reading", **extra,
    })


def _db():
    return next(app.dependency_overrides[get_db]())


def test_due_serves_only_kanji_vocabulary(client):
    word = _add(client, "決断", "けつだん")
    expr = _add(client, "間に合う", "まにあう", type="expression")
    _add(client, "すでに", "すでに")                       # no kanji
    _add(client, "に対して", "にたいして", type="grammar")  # grammar isn't drilled
    _add(client, "関係", None)                              # nothing to check against

    ids = {i["id"] for i in client.get("/api/study/reading/due").json()}
    assert ids == {word, expr}


def test_kanji_families_list_other_words_sharing_a_kanji(client):
    target = _add(client, "決断", "けつだん")
    _add(client, "断る", "ことわる")
    _add(client, "解決", "かいけつ")

    item = next(i for i in client.get("/api/study/reading/due").json() if i["id"] == target)
    families = {f["kanji"]: [w["japanese"] for w in f["words"]] for f in item["kanji"]}
    assert families == {"決": ["解決"], "断": ["断る"]}


def test_new_cards_prefer_best_known_meaning(client):
    _add(client, "需要", "じゅよう")  # never reviewed, so should lose the tie
    known = _add(client, "関係", "かんけい")
    # A meaning review lengthens the item's own interval.
    client.post("/api/study/review", json={"item_id": known, "rating": "good"})

    served = client.get("/api/study/reading/due?limit=1").json()
    assert [i["id"] for i in served] == [known]


def test_reading_review_uses_its_own_track(client):
    item_id = _add(client, "印象", "いんしょう")
    r = _review(client, item_id, "good")
    assert r.status_code == 200
    assert r.json()["interval_days"] == 1

    item = client.get(f"/api/items/{item_id}").json()
    assert item["srs_reviews"] == 0  # meaning track untouched

    # Rated good, so it's scheduled for tomorrow and no longer due.
    assert client.get("/api/study/reading/due").json() == []
    # ...but the meaning card is still due.
    assert [i["id"] for i in client.get("/api/study/due").json()] == [item_id]


def test_reading_lapses_never_suspend_the_item(client):
    item_id = _add(client, "偶然", "ぐうぜん")
    for _ in range(10):
        assert _review(client, item_id, "again").status_code == 200

    item = client.get(f"/api/items/{item_id}").json()
    assert item["suspended"] is False
    # Lapsed cards come back in ~10 minutes, so read the card via practice.
    served = client.get("/api/study/reading/practice").json()
    assert served[0]["reading_card"]["srs_lapses"] == 10


def test_practice_reading_review_creates_no_card(client):
    item_id = _add(client, "効果", "こうか")
    r = _review(client, item_id, "good", practice=True)
    assert r.status_code == 200
    assert r.json()["next_due"] is None
    assert _db().query(ReadingCard).count() == 0


def test_reading_review_rejects_item_without_kanji(client):
    item_id = _add(client, "すでに", "すでに")
    assert _review(client, item_id, "good").status_code == 422


def test_deleting_item_removes_its_reading_card(client):
    item_id = _add(client, "態度", "たいど")
    _review(client, item_id, "good")
    assert _db().query(ReadingCard).count() == 1

    client.delete(f"/api/items/{item_id}")
    assert _db().query(ReadingCard).count() == 0


def test_reading_sessions_count_toward_graded_accuracy(client):
    item_id = _add(client, "正確", "せいかく")
    sid = client.post("/api/study/session/start?mode=kanji_reading").json()["session_id"]
    _review(client, item_id, "again", session_id=sid)

    stats = client.get("/api/study/dashboard").json()
    assert stats["studied_today"] == 1
    assert stats["accuracy_today"] == 0


# --- Kanji details ---------------------------------------------------------

def _entry(k, meaning, on=(), kun=(), **extra):
    return {
        "kanji": k, "meaning": meaning, "onyomi": list(on), "kunyomi": list(kun),
        "jlpt_level": "N3", "strokes": 9,
        "components": [{"part": "田", "meaning": "field"}],
        "mnemonic": "m", "origin": "o", **extra,
    }


@pytest.fixture
def fake_kanji_model(monkeypatch):
    calls = []

    def _install(entries):
        def fake(content, **kwargs):
            calls.append(content)
            return {"kanji": entries}
        monkeypatch.setattr(details_mod, "complete_json", fake)
        return calls
    return _install


def test_kanji_details_are_generated_once_and_cached(client, fake_kanji_model):
    calls = fake_kanji_model([
        _entry("思", "think", on=["シ"], kun=["おも.う"]),
        _entry("出", "exit", on=["シュツ", "スイ"], kun=["で.る", "だ.す"]),
    ])
    item_id = _add(client, "思い出す", "おもいだす")

    r = client.get(f"/api/kanji/item/{item_id}")
    assert r.status_code == 200, r.text
    got = {d["kanji"]: d for d in r.json()}
    assert list(got) == ["思", "出"]
    assert got["思"]["reading_in_word"] == "おも.う"
    assert got["出"]["reading_in_word"] == "だ.す"
    assert got["出"]["reading_kind"] == "kun"
    assert got["思"]["jlpt_level"] == "N3"

    # A second word sharing both kanji costs nothing.
    other = _add(client, "思い出", "おもいで")
    got = {d["kanji"]: d for d in client.get(f"/api/kanji/item/{other}").json()}
    assert got["出"]["reading_in_word"] == "で.る"
    assert len(calls) == 1


def test_kanji_details_only_ask_for_missing_kanji(client, fake_kanji_model):
    fake_kanji_model([_entry("断", "decline", on=["ダン"], kun=["ことわ.る"])])
    first = _add(client, "断る", "ことわる")
    client.get(f"/api/kanji/item/{first}")

    calls = fake_kanji_model([_entry("決", "decide", on=["ケツ"], kun=["き.める"])])
    second = _add(client, "決断", "けつだん")
    got = client.get(f"/api/kanji/item/{second}").json()
    assert [(d["kanji"], d["reading_in_word"]) for d in got] == [("決", "ケツ"), ("断", "ダン")]
    assert len(calls) == 2
    assert "these kanji: 決\n" in calls[-1]  # 断 was already cached


def test_kanji_details_sanitise_model_output(client, fake_kanji_model):
    fake_kanji_model([
        _entry("印", "stamp", onyomi="イン、ジン", jlpt_level="N9", strokes="lots"),
        _entry("象", "", on=["ショウ"]),  # no meaning: unusable, skipped
        _entry("猫", "cat"),              # not asked for
    ])
    item_id = _add(client, "印象", "いんしょう")
    got = client.get(f"/api/kanji/item/{item_id}").json()
    assert [d["kanji"] for d in got] == ["印"]
    assert got[0]["onyomi"] == ["イン", "ジン"]
    assert got[0]["jlpt_level"] is None
    assert got[0]["strokes"] is None
    assert _db().query(KanjiInfo).count() == 1


def test_kanji_details_bad_reply_is_a_502(client, monkeypatch):
    monkeypatch.setattr(details_mod, "complete_json", lambda *a, **k: {"nope": 1})
    item_id = _add(client, "印象", "いんしょう")
    assert client.get(f"/api/kanji/item/{item_id}").status_code == 502


def test_readings_in_word_handles_sound_changes():
    d = {
        "学": {"onyomi": ["ガク"], "kunyomi": ["まな.ぶ"]},
        "校": {"onyomi": ["コウ"], "kunyomi": []},
        "会": {"onyomi": ["カイ", "エ"], "kunyomi": ["あ.う"]},
        "社": {"onyomi": ["シャ"], "kunyomi": ["やしろ"]},
        "今": {"onyomi": ["コン", "キン"], "kunyomi": ["いま"]},
        "日": {"onyomi": ["ニチ", "ジツ"], "kunyomi": ["ひ", "-か"]},
    }
    assert readings_in_word("学校", "がっこう", d) == {
        "学": {"reading": "ガク", "kind": "on"}, "校": {"reading": "コウ", "kind": "on"},
    }
    assert readings_in_word("入社", "にゅうしゃ", d)["社"]["reading"] == "シャ"
    assert readings_in_word("会社", "かいしゃ", d)["会"]["reading"] == "カイ"
    # Jukujikun: nothing lines up, so nothing is claimed for 今.
    assert "今" not in readings_in_word("今日", "きょう", d)


def test_readings_in_word_uses_okurigana_to_break_stem_ties():
    d = {"立": {"onyomi": ["リツ", "リュウ"], "kunyomi": ["た.つ", "た.てる"]}}
    assert readings_in_word("計画を立てる", "けいかくをたてる", d)["立"]["reading"] == "た.てる"
    assert readings_in_word("立つ", "たつ", d)["立"]["reading"] == "た.つ"
