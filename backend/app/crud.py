"""Shared data-access helpers.

Plain SQLAlchemy operations used by more than one router. Nothing here knows
about HTTP — the 404-on-missing behaviour lives in ``deps.py`` instead.
"""
from sqlalchemy.orm import Session

from .models import Item, Tag


def format_library_lines(items: list[Item]) -> str:
    """Render items as the "- japanese (reading): meaning" lines several AI
    prompts (reading passages, conversation starters) use to show library context."""
    return "\n".join(f"- {it.japanese} ({it.reading}): {it.meaning}" for it in items)


def get_item_for_user(db: Session, item_id: int, user_id: str) -> Item | None:
    """Fetch an item scoped to its owner. Returns None if absent or not theirs."""
    return db.query(Item).filter(Item.id == item_id, Item.user_id == user_id).first()


def get_existing_japanese(db: Session, user_id: str, texts: list[str]) -> set[str]:
    """Which of these japanese strings are already items in the user's library."""
    if not texts:
        return set()
    rows = (
        db.query(Item.japanese)
        .filter(Item.user_id == user_id, Item.japanese.in_(texts))
        .all()
    )
    return {r[0] for r in rows}


def get_or_create_tags(db: Session, tag_names: list[str]) -> list[Tag]:
    """Resolve tag names to Tag rows, creating any that don't exist yet.

    Names are normalised to lowercase, blanks dropped, and duplicates within the
    same call collapse to one Tag (otherwise a caller submitting the same name
    twice would produce duplicate item-tag association rows). Existing tags are
    fetched in one batched query rather than one round-trip per name. Flushes
    once so newly created tags have ids before the caller associates them with
    an item.
    """
    names = list(dict.fromkeys(n.strip().lower() for n in tag_names if n.strip()))
    if not names:
        return []

    by_name = {t.name: t for t in db.query(Tag).filter(Tag.name.in_(names)).all()}
    for name in names:
        if name not in by_name:
            tag = Tag(name=name)
            db.add(tag)
            by_name[name] = tag

    db.flush()
    return [by_name[name] for name in names]
