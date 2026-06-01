import unicodedata

import fugashi
from fastapi import APIRouter
from pydantic import BaseModel

from ..translation import get_model, get_provider, translate_lookup

router = APIRouter(prefix="/api/furigana", tags=["furigana"])

_tagger = None


def _get_tagger():
    global _tagger
    if _tagger is None:
        _tagger = fugashi.Tagger()
    return _tagger


def _kata_to_hira(text: str) -> str:
    return "".join(
        chr(ord(c) - 0x60) if "KATAKANA" in unicodedata.name(c, "") else c
        for c in text
    )


def _has_kanji(text: str) -> bool:
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
        if kana and _has_kanji(w.surface):
            hira = _kata_to_hira(kana)
            if hira != w.surface:
                parts.append(f"<ruby>{w.surface}<rt>{hira}</rt></ruby>")
                continue
        parts.append(w.surface)
    return "".join(parts)


def reading_for(text: str) -> str:
    """Hiragana reading for a kanji-bearing word/phrase via fugashi.

    Returns "" for kana-only or unrecognized input. Used as a fallback when
    the LLM omits the reading field.
    """
    if not _has_kanji(text):
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
        if kana and _has_kanji(w.surface):
            hira = _kata_to_hira(kana)
            if hira != w.surface:
                reading = hira
        lemma = w.feature.lemma or w.surface
        tokens.append({"surface": w.surface, "reading": reading, "lemma": lemma})
    return tokens


class FuriganaRequest(BaseModel):
    texts: list[str]


class FuriganaResponse(BaseModel):
    results: list[str]


class TokenizeWord(BaseModel):
    japanese: str
    reading: str
    meaning: str


class TokenizeRequest(BaseModel):
    text: str
    words: list[TokenizeWord] = []


class Token(BaseModel):
    surface: str
    reading: str
    meaning: str
    lemma: str = ""


class TokenizeResponse(BaseModel):
    tokens: list[Token]


@router.post("/annotate", response_model=FuriganaResponse)
async def annotate_texts(req: FuriganaRequest):
    """Annotate multiple Japanese texts with furigana ruby HTML."""
    return FuriganaResponse(results=[annotate(t) for t in req.texts])


@router.post("/tokenize", response_model=TokenizeResponse)
async def tokenize_text(req: TokenizeRequest):
    """Segment text into tokens with furigana and word meanings for hover."""
    raw_tokens = tokenize(req.text)

    # Build lookup from word list: map surface and lemma forms to meaning
    meaning_map: dict[str, str] = {}
    for w in req.words:
        meaning_map[w.japanese] = w.meaning

    result = []
    for t in raw_tokens:
        meaning = meaning_map.get(t["surface"], "")
        if not meaning:
            meaning = meaning_map.get(t["lemma"], "")
        result.append(Token(surface=t["surface"], reading=t["reading"], meaning=meaning, lemma=t["lemma"]))
    return TokenizeResponse(tokens=result)


class LookupRequest(BaseModel):
    surface: str
    lemma: str = ""
    context: str = ""
    is_phrase: bool = False


class LookupResponse(BaseModel):
    meaning: str
    reading: str = ""


_lookup_cache: dict[tuple[str, str, str, bool], LookupResponse] = {}


def _is_lookupable(text: str) -> bool:
    """Skip punctuation and pure ASCII/whitespace."""
    if not text or not text.strip():
        return False
    for c in text:
        try:
            name = unicodedata.name(c, "")
        except ValueError:
            continue
        if "CJK" in name or "HIRAGANA" in name or "KATAKANA" in name:
            return True
    return False


@router.post("/lookup", response_model=LookupResponse)
async def lookup_word(req: LookupRequest):
    """Look up an English gloss/translation for a Japanese word or phrase. Cached."""
    if not _is_lookupable(req.surface):
        return LookupResponse(meaning="")

    key = (
        get_provider(),
        get_model(),
        (req.lemma or req.surface).strip(),
        req.is_phrase,
    )
    if key in _lookup_cache:
        return _lookup_cache[key]

    data = await translate_lookup(req.surface, req.lemma, req.context, req.is_phrase)
    reading = (data.get("reading") or "").strip()
    if not reading:
        reading = reading_for(req.lemma or req.surface)
    resp = LookupResponse(
        meaning=(data.get("meaning") or "").strip(),
        reading=reading,
    )
    _lookup_cache[key] = resp
    return resp
