"""JLPT level configuration and per-level prompt tuning.

Lives outside ``routers/`` because ingest, generate, and converse all need the
level settings but have no business depending on the settings *router*.
"""
from sqlalchemy.orm import Session

from .models import Setting

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


def get_jlpt_level(db: Session, user_id: str = "default") -> str:
    row = db.query(Setting).filter(
        Setting.user_id == user_id, Setting.key == "jlpt_level"
    ).first()
    if row and row.value in VALID_LEVELS:
        return row.value
    return DEFAULT_LEVEL
