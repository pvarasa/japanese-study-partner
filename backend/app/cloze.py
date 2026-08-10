"""Build fill-in-the-blank questions from an item's stored example sentences.

Unlike the other study modes this costs no AI call — every item already carries
LLM-authored ``example_sentences`` from the ingest/enrich path, so the target
word can simply be blanked out of one of them.

The hard part is *locating* the word: it appears conjugated (済む → 済みます),
as a suru-verb stem (把握する → 把握し), or with the ~ placeholder stripped
(〜次第 → 次第). Plain substring matching misses all three, so fall back to
fugashi lemmas, which normalise conjugation back to dictionary form.
"""
import json
import random
from typing import Optional

from .japanese import reading_for, tokenize
from .models import Item

BLANK = "＿＿＿"


def parse_examples(raw: Optional[str]) -> list[dict]:
    """Tolerant parse of the example_sentences JSON-string column.

    Mirrors the frontend's ``parseExamples``: the column is LLM-authored with no
    DB-level validation, so malformed values degrade to "no examples" rather
    than raising. Public because the enrichment backfill counts stored examples
    with it — the column has exactly one reader worth trusting.
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [
        e for e in parsed
        if isinstance(e, dict) and isinstance(e.get("japanese"), str) and e["japanese"].strip()
    ]


def _strip_placeholder(text: str) -> str:
    """Drop the ~ markers grammar items are stored with (〜次第 → 次第)."""
    return text.strip().strip("〜～").strip()


# Items are sometimes stored as a pair of alternatives rather than one word:
# 増える・減る, ～どころではない/～どころじゃない. Each side is a target in its
# own right, and neither matches the combined string.
_ALTERNATIVE_SEPARATORS = ("・", "/", "／")


def _split_alternatives(text: str) -> list[str]:
    parts = [text]
    for sep in _ALTERNATIVE_SEPARATORS:
        parts = [piece for part in parts for piece in part.split(sep)]
    return [p for p in (_strip_placeholder(p) for p in parts) if p]


def target_forms(item: Item) -> list[str]:
    """Surface forms of the item worth searching a sentence for, longest first."""
    forms: list[str] = []
    for base in _split_alternatives(item.japanese):
        forms.append(base)
        # 把握する rarely appears intact — the する conjugates off the stem.
        if base.endswith("する") and len(base) > 2:
            forms.append(base[:-2])
    forms.extend(_split_alternatives(item.reading or ""))
    # fromkeys dedupes in insertion order (a set would order by hash, which is
    # randomised per process); the sort is stable, so ties stay deterministic.
    return sorted(dict.fromkeys(f for f in forms if f), key=len, reverse=True)


def _token_spans(text: str) -> list[tuple[int, int, str, str]]:
    """(start, end, surface, lemma) per token, with offsets into ``text``.

    fugashi doesn't hand back character offsets, so they're recovered by
    scanning forward for each surface — MeCab drops inter-token whitespace, so
    the surfaces don't simply concatenate back into the original string.
    """
    spans = []
    cursor = 0
    for token in tokenize(text):
        surface = token["surface"]
        if not surface:
            continue
        idx = text.find(surface, cursor)
        if idx < 0:
            continue
        cursor = idx + len(surface)
        spans.append((idx, cursor, surface, token["lemma"]))
    return spans


def _find_span(sentence: str, forms: list[str]) -> Optional[tuple[int, int]]:
    """Locate a target form in the sentence, returning (start, end) or None."""
    # Exact match first, longest form wins so 把握する beats 把握.
    for form in forms:
        idx = sentence.find(form)
        if idx >= 0:
            return idx, idx + len(form)

    # Nothing matched literally — the word is conjugated (済む → 済みました) or
    # is a phrase that inflects internally (手に入れる → 手に入れた). Compare
    # dictionary forms token-for-token, which normalises both cases.
    sentence_spans = _token_spans(sentence)
    for form in forms:
        wanted = _token_spans(form)
        if not wanted or len(wanted) > len(sentence_spans):
            continue
        for i in range(len(sentence_spans) - len(wanted) + 1):
            run = sentence_spans[i:i + len(wanted)]
            # Match on either form, since the last token of a phrase is the one
            # that conjugates while the earlier ones appear verbatim.
            if all(
                got_lemma == want_lemma or got_surface == want_surface
                for (_, _, got_surface, got_lemma), (_, _, want_surface, want_lemma)
                in zip(run, wanted)
            ):
                return run[0][0], run[-1][1]
    return None


def accepted_answers(removed: str, item: Item) -> list[str]:
    """Answers to count as correct for a blank that removed ``removed``.

    The kana reading is accepted alongside the kanji so the mode is playable
    without switching to a Japanese IME — it tests recall of the word, not the
    learner's input method.
    """
    answers = [removed]
    kana = reading_for(removed)
    if kana:
        answers.append(kana)
    item_reading = _strip_placeholder(item.reading or "")
    if item_reading:
        answers.append(item_reading)
    return list(dict.fromkeys(a for a in answers if a))


def build_cloze(item: Item, rng: Optional[random.Random] = None) -> Optional[dict]:
    """Blank the item out of one of its example sentences.

    Returns None when no stored example contains the word in any recognisable
    form, which is the caller's cue to skip this item rather than 500.
    """
    forms = target_forms(item)
    if not forms:
        return None

    matches = []
    for example in parse_examples(item.example_sentences):
        sentence = example["japanese"]
        span = _find_span(sentence, forms)
        if span:
            matches.append((sentence, span, example.get("english") or ""))

    if not matches:
        return None

    # Pick at random so repeat reviews of the same item aren't identical.
    sentence, (start, end), english = (rng or random).choice(matches)
    return {
        "prompt": sentence[:start] + BLANK + sentence[end:],
        "answer": sentence[start:end],
        "accepted": accepted_answers(sentence[start:end], item),
        "translation": english,
    }
