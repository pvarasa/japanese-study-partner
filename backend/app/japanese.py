"""Japanese text processing: tokenization, readings, and furigana markup.

Lives outside ``routers/`` because cloze generation and the furigana endpoints
both need the fugashi tagger, and a shared helper has no business depending on
a *router* — same reasoning as ``levels.py``.
"""
import html
import threading
import unicodedata

import fugashi

_tagger = None
# One MeCab tagger is shared by every threadpool worker, and MeCab's node
# parsing isn't documented as thread-safe — so parses are serialised, and each
# token's fields are copied out before the lock is released.
_tagger_lock = threading.Lock()


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


def tokenize(text: str) -> list[dict]:
    """Segment text into tokens with surface, reading, lemma, and the
    whitespace that preceded each token.

    ``reading`` is hiragana, and only set for kanji-bearing tokens whose
    reading differs from the surface — i.e. exactly where furigana belongs.
    """
    global _tagger
    with _tagger_lock:
        if _tagger is None:
            _tagger = fugashi.Tagger()
        # MeCab drops inter-token whitespace from the surface; white_space holds
        # the run that preceded the token, so annotate() can re-emit it.
        words = [
            (w.surface, w.feature.kana, w.feature.lemma, getattr(w, "white_space", "") or "")
            for w in _tagger(text)
        ]

    tokens = []
    for surface, kana, lemma, white_space in words:
        reading = ""
        if kana and has_kanji(surface):
            hira = kata_to_hira(kana)
            if hira != surface:
                reading = hira
        tokens.append({
            "surface": surface,
            "reading": reading,
            "lemma": lemma or surface,
            "white_space": white_space,
        })
    return tokens


def annotate(text: str) -> str:
    """Convert Japanese text to HTML with <ruby> tags for kanji."""
    parts = []
    for t in tokenize(text):
        parts.append(t["white_space"])
        # Escape token text before it goes into HTML that the frontend renders
        # via dangerouslySetInnerHTML — ingested pages can contain raw markup.
        surface = html.escape(t["surface"])
        if t["reading"]:
            parts.append(f"<ruby>{surface}<rt>{html.escape(t['reading'])}</rt></ruby>")
        else:
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
