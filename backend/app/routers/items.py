from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_user_id
from ..models import Item, Tag
from ..schemas import ItemCreate, ItemOut, ItemUpdate

router = APIRouter(prefix="/api/items", tags=["items"])


def _item_to_out(item: Item) -> ItemOut:
    return ItemOut(
        id=item.id,
        type=item.type,
        japanese=item.japanese,
        reading=item.reading,
        meaning=item.meaning,
        notes=item.notes,
        example_sentences=item.example_sentences,
        jlpt_level=item.jlpt_level,
        source_id=item.source_id,
        created_at=item.created_at,
        srs_interval=item.srs_interval,
        srs_ease=item.srs_ease,
        srs_due=item.srs_due,
        srs_reviews=item.srs_reviews,
        srs_correct=item.srs_correct,
        tags=[t.name for t in item.tags],
    )


def _get_or_create_tags(db: Session, tag_names: list[str]) -> list[Tag]:
    tags = []
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        tags.append(tag)
    return tags


@router.get("/", response_model=list[ItemOut])
def list_items(
    type: str | None = None,
    search: str | None = None,
    tag: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
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
    q = q.order_by(Item.created_at.desc())
    items = q.offset(offset).limit(limit).all()
    return [_item_to_out(i) for i in items]


@router.post("/", response_model=ItemOut)
def create_item(
    data: ItemCreate,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    item = Item(
        user_id=user_id,
        type=data.type,
        japanese=data.japanese,
        reading=data.reading,
        meaning=data.meaning,
        notes=data.notes,
        example_sentences=data.example_sentences,
        jlpt_level=data.jlpt_level,
        source_id=data.source_id,
    )
    if data.tags:
        item.tags = _get_or_create_tags(db, data.tags)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _item_to_out(item)


@router.get("/{item_id}", response_model=ItemOut)
def get_item(
    item_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    item = db.query(Item).filter(Item.id == item_id, Item.user_id == user_id).first()
    if not item:
        raise HTTPException(404, "Item not found")
    return _item_to_out(item)


@router.put("/{item_id}", response_model=ItemOut)
def update_item(
    item_id: int,
    data: ItemUpdate,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    item = db.query(Item).filter(Item.id == item_id, Item.user_id == user_id).first()
    if not item:
        raise HTTPException(404, "Item not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "tags":
            item.tags = _get_or_create_tags(db, value)
        else:
            setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return _item_to_out(item)


@router.delete("/{item_id}")
def delete_item(
    item_id: int,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    item = db.query(Item).filter(Item.id == item_id, Item.user_id == user_id).first()
    if not item:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}
