"""Japanese text processing: tokenization, readings, and furigana markup.

Lives outside ``routers/`` because cloze generation and the furigana endpoints
both need the fugashi tagger, and a shared helper has no business depending on
a *router* — same reasoning as ``levels.py``.
"""
import html
import unicodedata

import fugashi

_tagger = None


def _get_tagger():
    global _tagger
    if _tagger is None:
        _tagger = fugashi.Tagger()
    return _tagger


def kata_to_hira(text: str) -> str:
    # Only the U+30A1–U+30F6 block has 1:1 hiragana counterparts (offset 0x60).
    # Matching on "KATAKANA" in the char name would also catch ー (prolonged
    # sound mark) and ・ (middle dot), which have no hiragana form and would be
    # mangled into stray diacritics.
    return "".join(
        chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c
        for c in text
    )


def has_kanji(text: str) -> bool:
    return any("CJK" in unicodedata.name(c, "") for c in text)


def annotate(text: str) -> str:
    """Convert Japanese text to HTML with <ruby> tags for kanji."""
    tagger = _get_tagger()
    words = tagger(text)
    parts = []
    for w in words:
        # MeCab drops inter-token whitespace from the surface; w.white_space
        # holds the run that preceded this token, so re-emit it to keep
        # English/mixed prompts (e.g. sentence-build questions) readable.
        parts.append(getattr(w, "white_space", "") or "")
        kana = w.feature.kana
        # Escape token text before it goes into HTML that the frontend renders
        # via dangerouslySetInnerHTML — ingested pages can contain raw markup.
        surface = html.escape(w.surface)
        if kana and has_kanji(w.surface):
            hira = kata_to_hira(kana)
            if hira != w.surface:
                parts.append(f"<ruby>{surface}<rt>{html.escape(hira)}</rt></ruby>")
                continue
        parts.append(surface)
    return "".join(parts)


def reading_for(text: str) -> str:
    """Hiragana reading for a kanji-bearing word/phrase via fugashi.

    Returns "" for kana-only or unrecognized input. Used as a fallback when
    the LLM omits the reading field.
    """
    if not has_kanji(text):
        return ""
    parts = [t["reading"] or t["surface"] for t in tokenize(text)]
    out = "".join(parts)
    return out if out and out != text else ""


def tokenize(text: str) -> list[dict]:
    """Segment text into tokens with surface, reading, and lemma."""
    tagger = _get_tagger()
    words = tagger(text)
    tokens = []
    for w in words:
        kana = w.feature.kana
        reading = ""
        if kana and has_kanji(w.surface):
            hira = kata_to_hira(kana)
            if hira != w.surface:
                reading = hira
        lemma = w.feature.lemma or w.surface
        tokens.append({"surface": w.surface, "reading": reading, "lemma": lemma})
    return tokens
