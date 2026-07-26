import logging

from fastapi import APIRouter, Query
from sqlalchemy import Float, cast, func, or_

from ..crud import get_or_create_tags
from ..deps import Db, OwnedItem, UserId
from ..enrich import build_enrichment
from ..levels import LEVEL_DESCRIPTOR, get_jlpt_level
from ..models import Item, Tag
from ..schemas import ItemCreate, ItemOut, ItemUpdate

router = APIRouter(prefix="/api/items", tags=["items"])

log = logging.getLogger("app.items")


@router.get("/", response_model=list[ItemOut])
def list_items(
    user_id: UserId,
    db: Db,
    type: str | None = None,
    search: str | None = None,
    tag: str | None = None,
    jlpt_level: str | None = None,
    accuracy: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
):
    q = db.query(Item).filter(Item.user_id == user_id)
    if type:
        q = q.filter(Item.type == type)
    if search:
        pattern = f"%{search}%"
        q = q.filter(or_(
            Item.japanese.ilike(pattern),
            Item.reading.ilike(pattern),
            Item.meaning.ilike(pattern),
        ))
    if tag:
        q = q.join(Item.tags).filter(Tag.name == tag.lower())
    if jlpt_level:
        q = q.filter(Item.jlpt_level == jlpt_level)
    if accuracy:
        # nullif() makes the divisor NULL (not 0) for never-reviewed items, so
        # the division yields NULL instead of raising division_by_zero on
        # PostgreSQL, which doesn't guarantee the srs_reviews > 0 clause is
        # evaluated first.
        acc = cast(Item.srs_correct, Float) / func.nullif(Item.srs_reviews, 0)
        if accuracy == "new":
            q = q.filter(Item.srs_reviews == 0)
        elif accuracy == "struggling":
            q = q.filter(Item.srs_reviews > 0, acc < 0.6)
        elif accuracy == "learning":
            q = q.filter(Item.srs_reviews > 0, acc >= 0.6, acc < 0.85)
        elif accuracy == "strong":
            q = q.filter(Item.srs_reviews > 0, acc >= 0.85)
    q = q.order_by(Item.created_at.desc())
    items = q.offset(offset).limit(limit).all()
    return [ItemOut.model_validate(i) for i in items]


@router.post("/", response_model=ItemOut)
def create_item(data: ItemCreate, user_id: UserId, db: Db, enrich: bool = False):
    """Create a study item.

    Plain ``def`` so the optional Claude enrichment runs in a threadpool rather
    than on the event loop. With ``enrich=true`` the missing usage note and
    example sentences are generated at save time, so items added from the
    Reading page match the ones the import flow produces.
    """
    notes = data.notes
    example_sentences = data.example_sentences

    if enrich and not (notes and example_sentences):
        level = data.jlpt_level if data.jlpt_level in LEVEL_DESCRIPTOR else get_jlpt_level(db, user_id)
        try:
            generated = build_enrichment(
                item_type=data.type,
                japanese=data.japanese,
                reading=data.reading,
                meaning=data.meaning,
                level=level,
            )
            notes = notes or generated["notes"] or None
            example_sentences = example_sentences or generated["example_sentences"] or None
        except Exception:
            # Never lose the user's word because the model hiccuped — save the
            # bare item and let the backfill script pick it up later.
            log.warning("Enrichment failed for %r; saving without notes", data.japanese, exc_info=True)

    item = Item(
        user_id=user_id,
        type=data.type,
        japanese=data.japanese,
        reading=data.reading,
        meaning=data.meaning,
        notes=notes,
        example_sentences=example_sentences,
        jlpt_level=data.jlpt_level,
        source_id=data.source_id,
    )
    if data.tags:
        item.tags = get_or_create_tags(db, data.tags)
    db.add(item)
    db.commit()
    db.refresh(item)
    return ItemOut.model_validate(item)


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item: OwnedItem):
    return ItemOut.model_validate(item)


@router.put("/{item_id}", response_model=ItemOut)
def update_item(item: OwnedItem, data: ItemUpdate, db: Db):
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "tags":
            item.tags = get_or_create_tags(db, value)
        else:
            setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return ItemOut.model_validate(item)


@router.delete("/{item_id}")
def delete_item(item: OwnedItem, db: Db):
    db.delete(item)
    db.commit()
    return {"ok": True}
