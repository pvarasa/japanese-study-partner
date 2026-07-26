from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .crud import get_item_for_user
from .database import get_db
from .models import Item


def get_user_id(x_user_id: str = Header(default="default")) -> str:
    return x_user_id


UserId = Annotated[str, Depends(get_user_id)]
Db = Annotated[Session, Depends(get_db)]


def require_item(item_id: int, user_id: UserId, db: Db) -> Item:
    """Resolve ``item_id`` to an item owned by the caller, or raise 404.

    FastAPI binds ``item_id`` from the path when the route declares one
    (``/items/{item_id}``) and from the query string otherwise
    (``/generate/question?item_id=``), so both call styles share this dependency.
    Returning 404 rather than 403 for another user's item keeps ids unenumerable.
    """
    item = get_item_for_user(db, item_id, user_id)
    if not item:
        raise HTTPException(404, "Item not found")
    return item


OwnedItem = Annotated[Item, Depends(require_item)]
