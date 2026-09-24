"""Per-kanji details for the reading drill's reveal: readings, level, parts, a
mnemonic, and where the character comes from.

Seeing the kanji families from the learner's own library shows *that* a kanji
is read differently in different words; this is the "why" and the "how do I
remember it". One Claude call covers every kanji of a word that isn't cached
yet, and the result is stored in ``KanjiInfo`` for all users, so each kanji is
paid for once.
"""
import json
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .kanji import kanji_in
from .levels import VALID_LEVELS
from .llm import complete_json
from .models import KanjiInfo

log = logging.getLogger("app.kanji_details")

# Not tied to the user's JLPT setting, unlike the other prompts: the output is
# cached once for everyone, and facts about a kanji don't vary by level.
KANJI_PROMPT = """You are a Japanese kanji teacher writing study notes for an intermediate (around JLPT N3) learner
who remembers kanji best through vivid stories and real history.

Write notes for each of these kanji: {kanji_list}
(The learner met them in the word {word} ({reading}), but the notes are about the kanji in general.)

Return ONLY valid JSON: {{"kanji": [ ...one object per kanji, in the order given... ]}}
Each object has:
- "kanji": the character itself
- "meaning": 1-4 short English keywords, comma-separated (e.g. "think, feel")
- "onyomi": array of the common on'yomi in katakana, most common first, at most 4. [] if none
- "kunyomi": array of the common kun'yomi in hiragana, most common first, at most 4, with a "."
  before the okurigana in KANJIDIC style (e.g. "おも.う", "だ.す"). [] if none
- "jlpt_level": the level it's usually listed under in JLPT kanji study lists ("N5"-"N1"), or null
  if it isn't on them
- "strokes": stroke count as an integer
- "components": array of 1-4 visual building blocks, each {{"part": "<character>", "meaning": "<short English>"}}.
  Use the recognisable parts a learner would see (radicals or common components), not every stroke
- "mnemonic": 1-2 sentences, a vivid, concrete picture that ties the components to the meaning.
  Use the components you listed. Keep it memorable rather than clever
- "origin": 1-2 sentences of genuinely interesting, accurate background: the character's
  etymology (pictograph, phonetic component, what the original form depicted) or a notable
  fact about its use. Do NOT invent history; if the origin is disputed, say "traditionally
  explained as..."

Return ONLY valid JSON, no markdown fences."""

# Roughly 250 tokens per kanji, with headroom for the wrapper and long notes.
_TOKENS_PER_KANJI = 450


def _loads_list(raw: str | None) -> list:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _str_list(value, limit: int = 4) -> list[str]:
    if isinstance(value, str):
        value = [v for v in value.replace("、", ",").split(",")]
    if not isinstance(value, list):
        return []
    return [s for s in (str(v).strip() for v in value) if s][:limit]


def _row_from_reply(kanji: str, data: dict) -> KanjiInfo:
    """Shape one model-authored entry into a row, tolerating sloppy types.

    Raises KeyError/ValueError only when the entry is unusable (no meaning).
    """
    meaning = str(data["meaning"]).strip()
    if not meaning:
        raise ValueError(f"empty meaning for {kanji}")
    level = str(data.get("jlpt_level") or "").strip().upper()
    try:
        strokes = int(data.get("strokes")) or None
    except (TypeError, ValueError):
        strokes = None
    components = [
        {"part": str(c.get("part", "")).strip(), "meaning": str(c.get("meaning", "")).strip()}
        for c in data.get("components") or []
        if isinstance(c, dict) and str(c.get("part", "")).strip()
    ][:4]
    return KanjiInfo(
        kanji=kanji,
        meaning=meaning,
        onyomi=json.dumps(_str_list(data.get("onyomi")), ensure_ascii=False),
        kunyomi=json.dumps(_str_list(data.get("kunyomi")), ensure_ascii=False),
        jlpt_level=level if level in VALID_LEVELS else None,
        strokes=strokes,
        components=json.dumps(components, ensure_ascii=False),
        mnemonic=str(data.get("mnemonic") or "").strip(),
        origin=str(data.get("origin") or "").strip(),
    )


def generate_kanji_info(kanji: list[str], *, word: str, reading: str) -> list[KanjiInfo]:
    """One Claude call for all of ``kanji``. Returns unsaved rows for the ones
    the model answered usably; entries for characters that weren't asked for
    are dropped. Raises on an unparseable reply."""
    data = complete_json(
        KANJI_PROMPT.format(kanji_list="、".join(kanji), word=word, reading=reading or "?"),
        max_tokens=200 + _TOKENS_PER_KANJI * len(kanji),
    )
    wanted = set(kanji)
    rows = {}
    for entry in data["kanji"]:
        k = str(entry.get("kanji", "")).strip() if isinstance(entry, dict) else ""
        if k in wanted and k not in rows:
            try:
                rows[k] = _row_from_reply(k, entry)
            except (KeyError, ValueError):
                log.warning("Skipping unusable kanji entry for %s: %r", k, entry)
    return list(rows.values())


def kanji_info_for(db: Session, word: str, reading: str) -> dict[str, KanjiInfo]:
    """Details for every kanji in ``word``, generating whatever isn't cached.

    Two requests can race to generate the same kanji (the drill prefetches the
    next card while the current one loads). The loser's insert fails on the
    primary key; it rolls back and serves its own copy, which is equivalent.
    """
    chars = kanji_in(word)
    if not chars:
        return {}
    cached = {r.kanji: r for r in db.query(KanjiInfo).filter(KanjiInfo.kanji.in_(chars))}
    missing = [k for k in chars if k not in cached]
    if missing:
        fresh = generate_kanji_info(missing, word=word, reading=reading)
        db.add_all(fresh)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        cached.update({r.kanji: r for r in fresh})
    return cached


def serialise(row: KanjiInfo) -> dict:
    return {
        "kanji": row.kanji,
        "meaning": row.meaning,
        "onyomi": _loads_list(row.onyomi),
        "kunyomi": _loads_list(row.kunyomi),
        "jlpt_level": row.jlpt_level,
        "strokes": row.strokes,
        "components": [c for c in _loads_list(row.components) if isinstance(c, dict)],
        "mnemonic": row.mnemonic,
        "origin": row.origin,
    }
