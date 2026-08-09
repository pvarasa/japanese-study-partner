"""Additive column migrations for the SQLite dev database.

``Base.metadata.create_all()`` creates missing *tables* but never alters
existing ones, so a column added to a model is silently absent from a
``nihongo.db`` that predates it and every query against it fails. PostgreSQL
gets this from Alembic; SQLite has no migration runner, so new columns are
declared here and applied idempotently at startup.

Additive only — ``ADD COLUMN`` is the one schema change SQLite does cheaply and
without a table rewrite. Anything else (drops, type changes, constraints) needs
a real migration.
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

log = logging.getLogger("app.sqlite_migrate")

# table -> [(column, full SQL type + default)]
# Defaults are required: SQLite rejects ADD COLUMN ... NOT NULL without one.
ADDED_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "items": [
        ("srs_hard", "INTEGER NOT NULL DEFAULT 0"),
        ("srs_lapses", "INTEGER NOT NULL DEFAULT 0"),
        ("suspended", "BOOLEAN NOT NULL DEFAULT 0"),
    ],
    "study_sessions": [
        ("items_hard", "INTEGER NOT NULL DEFAULT 0"),
    ],
}


def ensure_columns(engine: Engine) -> list[str]:
    """Add any missing columns. Returns the ``table.column`` names added."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []

    with engine.begin() as conn:
        for table, columns in ADDED_COLUMNS.items():
            if table not in existing_tables:
                continue  # create_all will build it complete
            present = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns:
                if name in present:
                    continue
                # Identifiers are module constants, never user input.
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                added.append(f"{table}.{name}")

    if added:
        log.info("SQLite schema updated: added %s", ", ".join(added))
    return added
