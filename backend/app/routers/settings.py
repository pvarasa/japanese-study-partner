from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..deps import Db, UserId
from ..levels import VALID_LEVELS, get_jlpt_level
from ..models import Setting

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsOut(BaseModel):
    jlpt_level: str


class SettingsUpdate(BaseModel):
    jlpt_level: str | None = None


@router.get("", response_model=SettingsOut)
@router.get("/", response_model=SettingsOut)
def read_settings(user_id: UserId, db: Db):
    return SettingsOut(jlpt_level=get_jlpt_level(db, user_id))


@router.put("", response_model=SettingsOut)
@router.put("/", response_model=SettingsOut)
def update_settings(data: SettingsUpdate, user_id: UserId, db: Db):
    if data.jlpt_level is not None:
        level = data.jlpt_level.upper()
        if level not in VALID_LEVELS:
            raise HTTPException(400, f"Invalid JLPT level: {data.jlpt_level}")
        row = db.query(Setting).filter(
            Setting.user_id == user_id, Setting.key == "jlpt_level"
        ).first()
        if row:
            row.value = level
        else:
            db.add(Setting(user_id=user_id, key="jlpt_level", value=level))
        db.commit()
    return SettingsOut(jlpt_level=get_jlpt_level(db, user_id))
