"""Per-kanji details for the reading drill (see app.kanji_details), and the
learner's marked kanji."""
from fastapi import APIRouter, HTTPException

from ..deps import Db, OwnedItem, UserId
from ..kanji import (
    READING_TYPES,
    as_sibling,
    is_single_kanji,
    kanji_in,
    readings_in_word,
    words_with_kanji,
)
from ..kanji_details import kanji_info_for, serialise
from ..llm import ai_response
from ..models import Item, KanjiInfo, KanjiMark
from ..schemas import KanjiDetail, KanjiMarkIn, MarkedKanji

router = APIRouter(prefix="/api/kanji", tags=["kanji"])

# Library words listed per marked kanji. More than the drill's reveal shows,
# since this page is where the learner goes to look at a kanji properly.
MAX_MARK_WORDS = 12


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


def _marked_out(db: Db, user_id: str, marks: list[KanjiMark]) -> list[MarkedKanji]:
    """Attach cached kanji facts and the library words containing each kanji.

    Never generates anything: a mark is made from a reveal, which already paid
    for the details, so this page costs no AI calls.
    """
    if not marks:
        return []
    info = {r.kanji: r for r in db.query(KanjiInfo).filter(KanjiInfo.kanji.in_([m.kanji for m in marks]))}
    # Suspended items included, as on the reveal: they're still words the learner has met.
    library = db.query(Item).filter(Item.user_id == user_id, Item.type.in_(READING_TYPES)).all()
    out = []
    for m in marks:
        words = words_with_kanji(m.kanji, library)
        out.append(MarkedKanji(
            kanji=m.kanji,
            note=m.note or "",
            created_at=m.created_at,
            detail=KanjiDetail(**serialise(info[m.kanji])) if m.kanji in info else None,
            words=[as_sibling(w) for w in words[:MAX_MARK_WORDS]],
            word_count=len(words),
        ))
    return out


def _require_kanji(kanji: str) -> None:
    if not is_single_kanji(kanji):
        raise HTTPException(422, "Only a single kanji can be marked")


@router.get("/marks", response_model=list[MarkedKanji])
def list_marks(user_id: UserId, db: Db):
    """The learner's marked kanji, most recently marked first."""
    marks = (
        db.query(KanjiMark)
        .filter(KanjiMark.user_id == user_id)
        .order_by(KanjiMark.created_at.desc(), KanjiMark.kanji)
        .all()
    )
    return _marked_out(db, user_id, marks)


@router.put("/marks/{kanji}", response_model=MarkedKanji)
def put_mark(kanji: str, user_id: UserId, db: Db, data: KanjiMarkIn | None = None):
    """Mark a kanji, or update its note. Idempotent: marking an already
    marked kanji without a note leaves the stored note alone."""
    _require_kanji(kanji)
    mark = db.get(KanjiMark, (user_id, kanji))
    if mark is None:
        mark = KanjiMark(user_id=user_id, kanji=kanji, note="")
        db.add(mark)
    if data is not None and data.note is not None:
        mark.note = data.note.strip()
    db.commit()
    db.refresh(mark)
    return _marked_out(db, user_id, [mark])[0]


@router.delete("/marks/{kanji}")
def delete_mark(kanji: str, user_id: UserId, db: Db):
    """Unmark a kanji. Unmarking one that isn't marked is not an error."""
    _require_kanji(kanji)
    db.query(KanjiMark).filter(KanjiMark.user_id == user_id, KanjiMark.kanji == kanji).delete()
    db.commit()
    return {"ok": True}
