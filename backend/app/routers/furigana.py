import json
import unicodedata

import fugashi
from fastapi import APIRouter
from pydantic import BaseModel

from ..llm import call_claude, get_anthropic_client, parse_json_response

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
        kana = w.feature.kana
        if kana and _has_kanji(w.surface):
            hira = _kata_to_hira(kana)
            if hira != w.surface:
                parts.append(f"<ruby>{w.surface}<rt>{hira}</rt></ruby>")
                continue
        parts.append(w.surface)
    return "".join(parts)


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


_lookup_cache: dict[tuple[str, bool], LookupResponse] = {}


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
    """Look up an English gloss/translation for a Japanese word or phrase, using Claude. Cached."""
    if not _is_lookupable(req.surface):
        return LookupResponse(meaning="")

    key = ((req.lemma or req.surface).strip(), req.is_phrase)
    if key in _lookup_cache:
        return _lookup_cache[key]

    client = get_anthropic_client()
    if req.is_phrase:
        prompt = f"""Translate this Japanese phrase or sentence fragment naturally into English, preserving its meaning as it appears in context.

Phrase: {req.surface}
Surrounding context: {req.context[:300]}

Return ONLY a JSON object with:
- "meaning": a natural English translation (concise, max ~20 words)
- "reading": the hiragana reading of the phrase (empty string if the phrase has no kanji)

Return ONLY valid JSON, no other text."""
    else:
        prompt = f"""Give a brief English gloss for this Japanese word as it appears in context.

Word (as it appears): {req.surface}
Dictionary form: {req.lemma or req.surface}
Context: {req.context[:300]}

Return ONLY a JSON object with:
- "meaning": a short English gloss (max 8 words, e.g. "to eat" or "quickly, rapidly")
- "reading": the hiragana reading of the dictionary form (empty string if the word has no kanji)

Return ONLY valid JSON, no other text."""

    message = call_claude(
        client,
        model="claude-sonnet-4-6",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = parse_json_response(message.content[0].text)
        resp = LookupResponse(
            meaning=data.get("meaning", "").strip(),
            reading=data.get("reading", "").strip(),
        )
    except (json.JSONDecodeError, AttributeError, IndexError):
        resp = LookupResponse(meaning="")

    _lookup_cache[key] = resp
    return resp
