"""Per-kanji details for the reading drill (see app.kanji_details)."""
from fastapi import APIRouter

from ..deps import Db, OwnedItem
from ..kanji import kanji_in, readings_in_word
from ..kanji_details import kanji_info_for, serialise
from ..llm import ai_response
from ..schemas import KanjiDetail

router = APIRouter(prefix="/api/kanji", tags=["kanji"])


@router.get("/item/{item_id}", response_model=list[KanjiDetail])
def get_item_kanji(item: OwnedItem, db: Db):
    """Details for each kanji in an item's word, in the order they appear.

    Cached kanji return instantly; the first word to contain an uncached one
    pays a single Claude call for all of its missing kanji. Each entry also
    says which of its readings this word uses, so the reveal can point at it.
    """
    with ai_response("kanji_details", item_id=item.id):
        rows = kanji_info_for(db, item.japanese, item.reading or "")
    details = {k: serialise(rows[k]) for k in kanji_in(item.japanese) if k in rows}
    used = readings_in_word(item.japanese, item.reading or "", details)
    return [
        KanjiDetail(
            **d,
            reading_in_word=used.get(k, {}).get("reading"),
            reading_kind=used.get(k, {}).get("kind"),
        )
        for k, d in details.items()
    ]
