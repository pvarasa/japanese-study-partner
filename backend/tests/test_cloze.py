"""Tests for building cloze questions out of stored example sentences."""
import json
import random

from app.cloze import BLANK, build_cloze, target_forms
from app.models import Item


def _item(japanese, examples, reading=None, item_type="word", meaning="x"):
    return Item(
        type=item_type,
        japanese=japanese,
        reading=reading,
        meaning=meaning,
        example_sentences=json.dumps(examples, ensure_ascii=False) if examples is not None else None,
    )


def _fixed_rng():
    return random.Random(0)


# --- locating the word -----------------------------------------------------

def test_blanks_an_exact_match():
    item = _item("環境", [{"japanese": "環境が変わりました。", "english": "The environment changed."}])
    q = build_cloze(item, _fixed_rng())
    assert q["prompt"] == f"{BLANK}が変わりました。"
    assert q["answer"] == "環境"
    assert q["translation"] == "The environment changed."


def test_finds_a_conjugated_verb_via_lemma():
    """済む appears as 済みました — substring matching alone would miss it."""
    item = _item("済む", [{"japanese": "宿題は済みました。", "english": "The homework is done."}])
    q = build_cloze(item, _fixed_rng())
    assert BLANK in q["prompt"]
    assert "済" not in q["prompt"]
    assert q["answer"] == "済み"


def test_finds_a_suru_verb_stem():
    """把握する conjugates the する away from the stem."""
    item = _item("把握する", [{"japanese": "状況を把握している。", "english": "I grasp the situation."}])
    q = build_cloze(item, _fixed_rng())
    assert q["answer"] == "把握"
    assert q["prompt"] == f"状況を{BLANK}している。"


def test_grammar_placeholder_is_stripped_before_matching():
    item = _item(
        "〜次第",
        [{"japanese": "着き次第連絡します。", "english": "I'll contact you as soon as I arrive."}],
        item_type="grammar",
    )
    q = build_cloze(item, _fixed_rng())
    assert BLANK in q["prompt"]
    assert q["answer"] == "次第"


def test_longest_form_wins_over_the_stem():
    item = _item("検討する", [{"japanese": "検討するつもりです。", "english": "I intend to consider it."}])
    q = build_cloze(item, _fixed_rng())
    assert q["answer"] == "検討する"


def test_finds_a_phrase_that_conjugates_internally():
    """手に入れる spans three tokens and inflects on the last one."""
    item = _item(
        "手に入れる",
        [{"japanese": "やっと切符を手に入れた。", "english": "I finally got a ticket."}],
        item_type="expression",
    )
    q = build_cloze(item, _fixed_rng())
    assert q["answer"] == "手に入れ"
    assert q["prompt"] == f"やっと切符を{BLANK}た。"


def test_matches_either_side_of_an_interpunct_pair():
    """増える・減る is two targets stored in one field."""
    item = _item("増える・減る", [{"japanese": "人口が減っている。", "english": "The population is shrinking."}])
    q = build_cloze(item, _fixed_rng())
    assert BLANK in q["prompt"]
    assert q["answer"] == "減っ"


def test_matches_either_side_of_a_slash_pair_with_placeholders():
    item = _item(
        "～どころではない/～どころじゃない",
        [{"japanese": "旅行どころではない。", "english": "This is no time for a trip."}],
        item_type="grammar",
    )
    q = build_cloze(item, _fixed_rng())
    assert q["answer"] == "どころではない"


def test_target_forms_splits_alternatives():
    forms = target_forms(_item("上がる・下がる", []))
    assert "上がる" in forms
    assert "下がる" in forms
    assert "上がる・下がる" not in forms


def test_only_the_first_occurrence_is_blanked():
    item = _item("本", [{"japanese": "本を読む。本は good。", "english": "..."}])
    q = build_cloze(item, _fixed_rng())
    assert q["prompt"].count(BLANK) == 1


# --- accepted answers ------------------------------------------------------

def test_kana_reading_is_accepted_alongside_the_kanji():
    item = _item(
        "環境",
        [{"japanese": "環境が変わりました。", "english": "..."}],
        reading="かんきょう",
    )
    q = build_cloze(item, _fixed_rng())
    assert "環境" in q["accepted"]
    assert "かんきょう" in q["accepted"]


def test_accepted_answers_are_deduped():
    item = _item("ゆっくり", [{"japanese": "ゆっくり歩く。", "english": "..."}], reading="ゆっくり")
    q = build_cloze(item, _fixed_rng())
    assert q["accepted"] == ["ゆっくり"]


# --- degrading rather than raising -----------------------------------------

def test_returns_none_when_no_example_contains_the_word():
    item = _item("環境", [{"japanese": "全然関係ない文です。", "english": "Unrelated."}])
    assert build_cloze(item, _fixed_rng()) is None


def test_returns_none_without_examples():
    assert build_cloze(_item("環境", None), _fixed_rng()) is None
    assert build_cloze(_item("環境", []), _fixed_rng()) is None


def test_malformed_example_json_degrades_to_none():
    """The column is LLM-authored with no DB-level validation."""
    item = _item("環境", None)
    item.example_sentences = "{not json at all"
    assert build_cloze(item, _fixed_rng()) is None


def test_non_array_example_json_degrades_to_none():
    item = _item("環境", None)
    item.example_sentences = json.dumps({"japanese": "環境です。"}, ensure_ascii=False)
    assert build_cloze(item, _fixed_rng()) is None


def test_skips_malformed_entries_but_uses_good_ones():
    item = _item("環境", None)
    item.example_sentences = json.dumps(
        [
            "a bare string",
            {"english": "no japanese key"},
            {"japanese": "", "english": "empty"},
            {"japanese": "環境が変わりました。", "english": "ok"},
        ],
        ensure_ascii=False,
    )
    q = build_cloze(item, _fixed_rng())
    assert q is not None
    assert q["translation"] == "ok"


def test_example_without_translation_still_works():
    item = _item("環境", [{"japanese": "環境が変わりました。"}])
    q = build_cloze(item, _fixed_rng())
    assert q["translation"] == ""


# --- variety ---------------------------------------------------------------

def test_picks_among_all_matching_examples():
    """Repeat reviews shouldn't always show the same sentence."""
    item = _item("環境", [
        {"japanese": "環境が変わりました。", "english": "one"},
        {"japanese": "環境を守る。", "english": "two"},
        {"japanese": "この環境は静かだ。", "english": "three"},
    ])
    seen = {build_cloze(item, random.Random(seed))["translation"] for seed in range(30)}
    assert seen == {"one", "two", "three"}


def test_target_forms_are_longest_first():
    item = _item("検討する", [], reading="けんとうする")
    forms = target_forms(item)
    assert forms == sorted(forms, key=len, reverse=True)
    assert "検討" in forms
