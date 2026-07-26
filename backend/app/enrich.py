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

# Matches the house style of the ingest-produced rows: a single practical line
# (no trailing period) plus exactly two level-appropriate sentences.
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
- "example_sentences": array of exactly 2 objects, each {{"japanese": "...", "english": "..."}}.
  Natural sentences that use the item in context, at JLPT {level} difficulty.

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
