import unicodedata

from fastapi import APIRouter

from ..japanese import annotate, reading_for, tokenize
from ..schemas import (
    FuriganaRequest,
    FuriganaResponse,
    LookupRequest,
    LookupResponse,
    Token,
    TokenizeRequest,
    TokenizeResponse,
)
from ..translation import get_model, get_provider, translate_lookup

router = APIRouter(prefix="/api/furigana", tags=["furigana"])


@router.post("/annotate", response_model=FuriganaResponse)
def annotate_texts(req: FuriganaRequest):
    """Annotate multiple Japanese texts with furigana ruby HTML.

    Plain ``def`` so FastAPI runs the CPU-bound fugashi tokenization in a
    threadpool rather than on the event loop, where it would stall every
    other request — same convention as the other blocking routes.
    """
    return FuriganaResponse(results=[annotate(t) for t in req.texts])


@router.post("/tokenize", response_model=TokenizeResponse)
def tokenize_text(req: TokenizeRequest):
    """Segment text into tokens with furigana and word meanings for hover.

    A token takes the meaning of the library word matching its surface form,
    falling back to its lemma so conjugated verbs still find their entry.
    """
    meanings = {w.japanese: w.meaning for w in req.words}
    return TokenizeResponse(tokens=[
        Token(
            surface=t["surface"],
            reading=t["reading"],
            meaning=meanings.get(t["surface"]) or meanings.get(t["lemma"], ""),
            lemma=t["lemma"],
        )
        for t in tokenize(req.text)
    ])


_lookup_cache: dict[tuple[str, str, str, bool], LookupResponse] = {}


def _is_lookupable(text: str) -> bool:
    """Skip punctuation and pure ASCII/whitespace."""
    return any(
        script in unicodedata.name(c, "")
        for c in text
        for script in ("CJK", "HIRAGANA", "KATAKANA")
    )


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
    # An empty meaning is an unparseable reply, not an answer — caching it would
    # pin "No meaning found" on the word until the server restarts.
    if resp.meaning:
        _lookup_cache[key] = resp
    return resp
