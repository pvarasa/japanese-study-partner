"""Shared data-access helpers.

Plain SQLAlchemy operations used by more than one router. Nothing here knows
about HTTP — the 404-on-missing behaviour lives in ``deps.py`` instead.
"""
from sqlalchemy.orm import Session

from .models import Item, Tag


def get_item_for_user(db: Session, item_id: int, user_id: str) -> Item | None:
    """Fetch an item scoped to its owner. Returns None if absent or not theirs."""
    return db.query(Item).filter(Item.id == item_id, Item.user_id == user_id).first()


def get_or_create_tags(db: Session, tag_names: list[str]) -> list[Tag]:
    """Resolve tag names to Tag rows, creating any that don't exist yet.

    Names are normalised to lowercase and blanks are dropped. Flushes so newly
    created tags have ids before the caller associates them with an item.
    """
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
