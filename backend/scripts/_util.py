"""Helpers shared by the one-off maintenance scripts in this package."""
import os
import shutil
from datetime import datetime
from pathlib import Path

from app.database import engine


def backup_sqlite() -> Path | None:
    """Copy the SQLite file before writing. No-op on PostgreSQL."""
    if os.environ.get("DATABASE_URL"):
        return None
    db_path = Path(engine.url.database)
    if not db_path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db_path.with_name(f"{db_path.stem}.backup-{stamp}{db_path.suffix}")
    shutil.copy2(db_path, backup)
    return backup
