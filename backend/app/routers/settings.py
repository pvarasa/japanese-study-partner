from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import get_user_id
from ..models import Setting

router = APIRouter(prefix="/api/settings", tags=["settings"])

VALID_LEVELS = {"N1", "N2", "N3", "N4", "N5"}
DEFAULT_LEVEL = "N3"

LEVEL_DESCRIPTOR = {
    "N5": "beginner",
    "N4": "elementary",
    "N3": "intermediate",
    "N2": "upper-intermediate",
    "N1": "advanced",
}

# Target character range for generated reading passages.
READING_LENGTH = {
    "N5": "80-120",
    "N4": "120-180",
    "N3": "150-250",
    "N2": "250-350",
    "N1": "350-450",
}

# Tier for new vocabulary to introduce in reading passages: the current level
# and one step harder (capped at N1).
NEW_WORD_TIER = {
    "N5": "N5-N4",
    "N4": "N4-N3",
    "N3": "N3-N2",
    "N2": "N2-N1",
    "N1": "N1",
}


class SettingsOut(BaseModel):
    jlpt_level: str


class SettingsUpdate(BaseModel):
    jlpt_level: str | None = None


def get_jlpt_level(db: Session, user_id: str = "default") -> str:
    row = db.query(Setting).filter(
        Setting.user_id == user_id, Setting.key == "jlpt_level"
    ).first()
    if row and row.value in VALID_LEVELS:
        return row.value
    return DEFAULT_LEVEL


@router.get("", response_model=SettingsOut)
@router.get("/", response_model=SettingsOut)
def read_settings(
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    return SettingsOut(jlpt_level=get_jlpt_level(db, user_id))


@router.put("", response_model=SettingsOut)
@router.put("/", response_model=SettingsOut)
def update_settings(
    data: SettingsUpdate,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
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
