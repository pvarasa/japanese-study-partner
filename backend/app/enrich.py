"""Fill in the usage notes and example sentences that only the ingest path produced.

Items created through ``POST /api/items/`` (the Reading page's "Add to library"
button, manual entry) used to be stored exactly as handed over, so they arrived
without the ``notes`` and ``example_sentences`` that make imported items useful.
This module is the shared generator used by both the create endpoint and the
``scripts/backfill_enrich.py`` one-off, so the two can't drift apart.
"""
import json
import logging

from .levels import LEVEL_DESCRIPTOR
from .llm import complete_json

log = logging.getLogger("app.enrich")

# How many example sentences an item is expected to ship with. The enrichment
# and extraction prompts both ask for exactly this many, and the backfill tops
# up anything that came in short — so raising it changes the contract in one
# place rather than in three prompts that can drift apart.
EXAMPLES_PER_ITEM = 2

# Matches the house style of the ingest-produced rows: a single practical line
# (no trailing period) plus EXAMPLES_PER_ITEM level-appropriate sentences.
ENRICH_PROMPT = """You are a Japanese language teaching assistant for a {descriptor} (JLPT {level}) learner.

Write a usage note and example sentences for this study item:
- Type: {type}
- Japanese: {japanese}
- Reading: {reading}
- Meaning: {meaning}

Return ONLY valid JSON with:
- "notes": ONE short line of practical usage guidance, roughly 8-20 words, no trailing period.
  Say something the meaning alone doesn't convey — a common collocation, the form it
  usually appears in, its transitive/intransitive partner, register, or a nuance that
  distinguishes it from a near-synonym. Do NOT restate the English meaning.
- "example_sentences": array of exactly {examples_per_item} objects, each {{"japanese": "...", "english": "..."}}.
  Natural sentences that use the item in context, at JLPT {level} difficulty.
  Vary the situation between them — don't rephrase one sentence {examples_per_item} ways.

Return ONLY valid JSON, no markdown fences."""


def build_enrichment(
    *,
    item_type: str,
    japanese: str,
    reading: str | None,
    meaning: str,
    level: str,
) -> dict[str, str]:
    """Generate ``{"notes": str, "example_sentences": str}`` for one item.

    ``example_sentences`` comes back as a JSON string because that's how the
    column stores it. Raises on an unusable model reply — callers decide whether
    that's fatal (the backfill skips the row) or not (item creation still saves).
    """
    data = complete_json(
        ENRICH_PROMPT.format(
            level=level,
            descriptor=LEVEL_DESCRIPTOR[level],
            type=item_type,
            japanese=japanese,
            reading=reading or "",
            meaning=meaning,
            examples_per_item=EXAMPLES_PER_ITEM,
        ),
        max_tokens=512,
    )

    notes = str(data.get("notes") or "").strip().rstrip("。.")

    examples = []
    for e in data.get("example_sentences") or []:
        if isinstance(e, dict) and e.get("japanese"):
            examples.append({
                "japanese": str(e["japanese"]),
                "english": str(e.get("english", "")),
            })

    if not notes and not examples:
        raise ValueError("model returned neither notes nor examples")

    return {
        "notes": notes,
        # ensure_ascii=False keeps the Japanese readable in the stored column,
        # matching the rows the ingest path writes.
        "example_sentences": json.dumps(examples, ensure_ascii=False) if examples else "",
    }


EXAMPLE_SENTENCE_PROMPT = """You are a Japanese language teaching assistant for a {descriptor} (JLPT {level}) learner.

Generate ONE natural example sentence using this item:
- Japanese: {japanese}
- Reading: {reading}
- Meaning: {meaning}
- Type: {type}

Requirements:
- The sentence must be natural and contextually appropriate
- Match grammar/vocabulary difficulty to JLPT {level}
- Use the word/grammar naturally in context
- Do NOT reuse any of these existing examples: {examples}

Return JSON with:
- "japanese": the example sentence in Japanese
- "english": natural English translation

Return ONLY valid JSON."""


def build_example_sentence(
    *,
    item_type: str,
    japanese: str,
    reading: str | None,
    meaning: str,
    level: str,
    existing: str | None = None,
) -> dict[str, str]:
    """Generate ONE example sentence that avoids the ones already stored.

    ``existing`` is the item's ``example_sentences`` column verbatim (a JSON
    string) — it goes into the prompt as the do-not-repeat list. Lives here
    rather than in the generate router so the backfill's top-up pass and the
    Study page's "Generate example" button share one prompt.

    Raises on an unusable reply: the endpoint's ``ai_response`` turns that into
    a 502, and the backfill counts the item as failed so a re-run retries it.
    """
    data = complete_json(
        EXAMPLE_SENTENCE_PROMPT.format(
            level=level,
            descriptor=LEVEL_DESCRIPTOR[level],
            type=item_type,
            japanese=japanese,
            reading=reading or "",
            meaning=meaning,
            examples=existing or "[]",
        ),
        max_tokens=256,
    )
    return {"japanese": str(data["japanese"]), "english": str(data["english"])}
