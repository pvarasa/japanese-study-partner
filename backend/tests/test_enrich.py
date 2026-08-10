"""Tests for note/example enrichment and its opt-in on item creation."""
import json
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import enrich as enrich_mod
from app.database import Base
from app.enrich import build_enrichment, build_example_sentence
from app.models import Item
from scripts import backfill_enrich as backfill_mod
from scripts.backfill_enrich import ENRICH, TOPUP, _gap


@pytest.fixture
def fake_model(monkeypatch):
    """Replace the Claude round-trip; returns the captured prompt list."""
    prompts = []

    def _install(reply):
        def fake_complete_json(content, **kwargs):
            prompts.append(content)
            if isinstance(reply, Exception):
                raise reply
            return reply
        monkeypatch.setattr(enrich_mod, "complete_json", fake_complete_json)
        return prompts

    return _install


GOOD_REPLY = {
    "notes": "Often paired with を with the transitive partner 変える",
    "example_sentences": [
        {"japanese": "天気が変化した。", "english": "The weather changed."},
        {"japanese": "考えに変化がある。", "english": "There is a change in thinking."},
    ],
}


def _build(**overrides):
    kwargs = {
        "item_type": "word", "japanese": "変化", "reading": "へんか",
        "meaning": "change", "level": "N3",
    }
    kwargs.update(overrides)
    return build_enrichment(**kwargs)


def test_returns_notes_and_serialised_examples(fake_model):
    fake_model(GOOD_REPLY)
    result = _build()
    assert result["notes"] == GOOD_REPLY["notes"]
    assert json.loads(result["example_sentences"]) == GOOD_REPLY["example_sentences"]


def test_examples_stay_readable_japanese(fake_model):
    """Matches how the ingest path writes the column (ensure_ascii=False)."""
    fake_model(GOOD_REPLY)
    assert "天気" in _build()["example_sentences"]


def test_trailing_period_stripped_to_match_house_style(fake_model):
    fake_model({**GOOD_REPLY, "notes": "Common in written Japanese。"})
    assert _build()["notes"] == "Common in written Japanese"


def test_malformed_example_entries_are_dropped(fake_model):
    fake_model({
        "notes": "ok",
        "example_sentences": [
            {"japanese": "良い例。", "english": "Good."},
            {"english": "missing japanese"},
            "not an object",
        ],
    })
    assert len(json.loads(_build()["example_sentences"])) == 1


def test_prompt_carries_level_descriptor(fake_model):
    prompts = fake_model(GOOD_REPLY)
    _build(level="N1")
    assert "JLPT N1" in prompts[0] and "advanced" in prompts[0]


def test_empty_reply_raises(fake_model):
    fake_model({"notes": "", "example_sentences": []})
    with pytest.raises(ValueError):
        _build()


def test_notes_only_reply_is_accepted(fake_model):
    fake_model({"notes": "Usually intransitive", "example_sentences": []})
    result = _build()
    assert result["notes"] == "Usually intransitive"
    assert result["example_sentences"] == ""


# ---- create_item enrichment opt-in ------------------------------------------

def _new_word(**overrides):
    base = {"type": "word", "japanese": "経験", "reading": "けいけん", "meaning": "experience"}
    base.update(overrides)
    return base


def test_create_does_not_enrich_by_default(client, monkeypatch):
    """The default path must stay free of AI calls."""
    def explode(**kwargs):
        raise AssertionError("enrichment should not run without ?enrich=true")
    monkeypatch.setattr("app.routers.items.build_enrichment", explode)

    body = client.post("/api/items/", json=_new_word()).json()
    assert body["notes"] is None


def test_create_with_enrich_fills_notes_and_examples(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.items.build_enrichment",
        lambda **kwargs: {
            "notes": "Frequently used with を積む (to gain experience)",
            "example_sentences": '[{"japanese": "経験を積む。", "english": "Gain experience."}]',
        },
    )
    body = client.post("/api/items/?enrich=true", json=_new_word()).json()
    assert body["notes"] == "Frequently used with を積む (to gain experience)"
    assert json.loads(body["example_sentences"])[0]["japanese"] == "経験を積む。"


def test_enrich_failure_still_saves_the_item(client, monkeypatch):
    """A model hiccup must never cost the user the word they saved."""
    def boom(**kwargs):
        raise RuntimeError("upstream down")
    monkeypatch.setattr("app.routers.items.build_enrichment", boom)

    r = client.post("/api/items/?enrich=true", json=_new_word())
    assert r.status_code == 200
    assert r.json()["japanese"] == "経験"
    assert r.json()["notes"] is None


def test_enrich_does_not_overwrite_supplied_values(client, monkeypatch):
    monkeypatch.setattr(
        "app.routers.items.build_enrichment",
        lambda **kwargs: {"notes": "generated", "example_sentences": "[]"},
    )
    body = client.post(
        "/api/items/?enrich=true", json=_new_word(notes="my own note")
    ).json()
    assert body["notes"] == "my own note"


def test_enrich_uses_item_level_when_present(client, monkeypatch):
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return {"notes": "n", "example_sentences": ""}

    monkeypatch.setattr("app.routers.items.build_enrichment", capture)
    client.post("/api/items/?enrich=true", json=_new_word(jlpt_level="N1"))
    assert seen["level"] == "N1"


def test_enrich_falls_back_to_user_level(client, monkeypatch):
    """An item with no/garbage level uses the learner's configured setting."""
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return {"notes": "n", "example_sentences": ""}

    monkeypatch.setattr("app.routers.items.build_enrichment", capture)
    client.put("/api/settings/", json={"jlpt_level": "N2"})
    client.post("/api/items/?enrich=true", json=_new_word(jlpt_level=None))
    assert seen["level"] == "N2"


# ---- single example sentence -------------------------------------------------

ONE_EXAMPLE = '[{"japanese": "天気が変化した。", "english": "The weather changed."}]'
TWO_EXAMPLES = json.dumps(GOOD_REPLY["example_sentences"], ensure_ascii=False)


def _one_sentence(**overrides):
    kwargs = {
        "item_type": "word", "japanese": "変化", "reading": "へんか",
        "meaning": "change", "level": "N3",
    }
    kwargs.update(overrides)
    return build_example_sentence(**kwargs)


def test_example_sentence_returns_the_pair(fake_model):
    fake_model({"japanese": "急な変化。", "english": "A sudden change."})
    assert _one_sentence() == {"japanese": "急な変化。", "english": "A sudden change."}


def test_example_sentence_prompt_lists_what_not_to_repeat(fake_model):
    """The do-not-repeat list is what keeps a top-up from duplicating example one."""
    prompts = fake_model({"japanese": "急な変化。", "english": "A sudden change."})
    _one_sentence(existing=ONE_EXAMPLE)
    assert "天気が変化した。" in prompts[0]


# ---- backfill gap classification ---------------------------------------------

class _Row:
    """Duck-types the two Item columns _gap reads."""

    def __init__(self, notes, example_sentences):
        self.notes = notes
        self.example_sentences = example_sentences


@pytest.mark.parametrize("notes, examples, expected", [
    ("a note", TWO_EXAMPLES, None),        # complete
    ("a note", ONE_EXAMPLE, TOPUP),        # short by one
    ("a note", None, ENRICH),              # never enriched
    ("a note", "[]", ENRICH),
    ("a note", "{not json", ENRICH),       # unparseable reads as example-less
    ("", TWO_EXAMPLES, ENRICH),            # examples fine, note missing
    (None, ONE_EXAMPLE, ENRICH),           # both gaps -> the fuller pass wins
])
def test_gap_classification(notes, examples, expected):
    assert _gap(_Row(notes, examples)) == expected


# ---- backfill top-up ---------------------------------------------------------

@pytest.fixture
def backfill_db(tmp_path, monkeypatch):
    """Point the script's session factory at a throwaway DB.

    Also stubs the backup step — it reads app.database.engine, which on the
    default (no DATABASE_URL) path is the developer's real nihongo.db.
    """
    engine = create_engine(f"sqlite:///{(tmp_path / 'backfill.db').as_posix()}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    monkeypatch.setattr(backfill_mod, "SessionLocal", Session)
    monkeypatch.setattr(backfill_mod, "_backup_sqlite", lambda: None)
    monkeypatch.setattr(sys, "argv", ["backfill_enrich"])

    def seed(**overrides):
        fields = {
            "user_id": "default", "type": "word", "japanese": "変化",
            "reading": "へんか", "meaning": "change", "jlpt_level": "N3",
            "notes": "a note", "example_sentences": ONE_EXAMPLE,
        }
        fields.update(overrides)
        db = Session()
        db.add(Item(**fields))
        db.commit()
        db.close()

    def stored():
        db = Session()
        try:
            return json.loads(db.query(Item).one().example_sentences)
        finally:
            db.close()

    return seed, stored, Session


def test_topup_appends_and_keeps_the_existing_sentence(backfill_db, monkeypatch):
    """A card the learner has already seen must not lose the sentence it had."""
    seed, stored, _ = backfill_db
    seed()
    monkeypatch.setattr(
        backfill_mod, "build_example_sentence",
        lambda **kw: {"japanese": "急な変化。", "english": "A sudden change."},
    )

    assert backfill_mod.main() == 0

    examples = stored()
    assert len(examples) == 2
    assert examples[0]["japanese"] == "天気が変化した。"  # original, first
    assert examples[1]["japanese"] == "急な変化。"        # appended


def test_topup_does_not_run_the_full_enrichment(backfill_db, monkeypatch):
    """Topping up costs one cheap call, not a regeneration of notes + both examples."""
    seed, _, _ = backfill_db
    seed()
    monkeypatch.setattr(
        backfill_mod, "build_example_sentence",
        lambda **kw: {"japanese": "急な変化。", "english": "A sudden change."},
    )
    monkeypatch.setattr(backfill_mod, "build_enrichment", _explode)

    assert backfill_mod.main() == 0


def test_dry_run_leaves_the_column_alone(backfill_db, monkeypatch):
    seed, stored, _ = backfill_db
    seed()
    monkeypatch.setattr(
        backfill_mod, "build_example_sentence",
        lambda **kw: {"japanese": "急な変化。", "english": "A sudden change."},
    )
    monkeypatch.setattr(sys, "argv", ["backfill_enrich", "--dry-run"])

    assert backfill_mod.main() == 0
    assert len(stored()) == 1


def test_complete_items_cost_no_calls(backfill_db, monkeypatch):
    """The whole sweep is a no-op once every row satisfies the contract."""
    seed, stored, _ = backfill_db
    seed(example_sentences=TWO_EXAMPLES)
    monkeypatch.setattr(backfill_mod, "build_example_sentence", _explode)
    monkeypatch.setattr(backfill_mod, "build_enrichment", _explode)

    assert backfill_mod.main() == 0
    assert len(stored()) == 2


def test_topup_failure_is_reported_and_leaves_the_row_intact(backfill_db, monkeypatch):
    seed, stored, _ = backfill_db
    seed()

    def boom(**kwargs):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(backfill_mod, "build_example_sentence", boom)

    assert backfill_mod.main() == 1  # non-zero so a re-run is prompted
    assert len(stored()) == 1


def _explode(**kwargs):
    raise AssertionError(f"unexpected AI call: {kwargs}")
