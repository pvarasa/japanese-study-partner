import unicodedata

from fastapi import APIRouter
from pydantic import BaseModel

from ..japanese import annotate, reading_for, tokenize
from ..translation import get_model, get_provider, translate_lookup

router = APIRouter(prefix="/api/furigana", tags=["furigana"])


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
