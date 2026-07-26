"""Backfill usage notes and example sentences for items that never got them.

Items created through POST /api/items/ (Reading page "Add to library", manual
entry) were stored exactly as handed over, so they lack the notes and example
sentences the import flow generates. This walks those rows and fills the gaps
using the same generator the create endpoint now uses.

Usage (from backend/):

    uv run python -m scripts.backfill_enrich --dry-run     # preview, no writes
    uv run python -m scripts.backfill_enrich               # apply
    uv run python -m scripts.backfill_enrich --limit 5     # try a few first

Safe to re-run: it only selects rows still missing the fields, so an interrupted
run resumes where it stopped. Costs one Claude call per item.
"""
import argparse
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import or_

# .env lives at the project root, two levels up from backend/scripts/
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from app.database import SessionLocal, engine  # noqa: E402
from app.enrich import build_enrichment  # noqa: E402
from app.levels import LEVEL_DESCRIPTOR, get_jlpt_level  # noqa: E402
from app.models import Item  # noqa: E402

BLANK_EXAMPLES = ("", "[]")


def _needs_enrichment(q):
    """Rows missing a usage note or an example-sentence array."""
    return q.filter(
        or_(
            Item.notes.is_(None),
            Item.notes == "",
            Item.example_sentences.is_(None),
            Item.example_sentences.in_(BLANK_EXAMPLES),
        )
    )


def _backup_sqlite() -> Path | None:
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    parser.add_argument("--limit", type=int, default=None, help="process at most N items")
    parser.add_argument("--user-id", default=None, help="restrict to one user (default: all)")
    parser.add_argument("--verbose", action="store_true", help="log the generated text")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    db = SessionLocal()
    try:
        q = db.query(Item)
        if args.user_id:
            q = q.filter(Item.user_id == args.user_id)
        items = _needs_enrichment(q).order_by(Item.id).all()

        if args.limit:
            items = items[: args.limit]

        if not items:
            print("Nothing to do - every item already has notes and examples.")
            return 0

        print(f"{len(items)} item(s) need enrichment{' (dry run)' if args.dry_run else ''}.")

        backup = None
        if not args.dry_run:
            backup = _backup_sqlite()
            if backup:
                print(f"Database backed up to {backup.name}")

        # get_jlpt_level hits the settings table per user; cache it per run.
        level_cache: dict[str, str] = {}
        filled = skipped = failed = 0

        for n, item in enumerate(items, 1):
            if item.jlpt_level in LEVEL_DESCRIPTOR:
                level = item.jlpt_level
            else:
                if item.user_id not in level_cache:
                    level_cache[item.user_id] = get_jlpt_level(db, item.user_id)
                level = level_cache[item.user_id]

            label = f"[{n}/{len(items)}] {item.japanese}"
            try:
                generated = build_enrichment(
                    item_type=item.type,
                    japanese=item.japanese,
                    reading=item.reading,
                    meaning=item.meaning,
                    level=level,
                )
            except Exception as e:
                print(f"  {label}: FAILED ({type(e).__name__}: {e})")
                failed += 1
                continue

            changes = []
            if not item.notes and generated["notes"]:
                changes.append("notes")
                if not args.dry_run:
                    item.notes = generated["notes"]
            if (item.example_sentences or "") in BLANK_EXAMPLES and generated["example_sentences"]:
                changes.append("examples")
                if not args.dry_run:
                    item.example_sentences = generated["example_sentences"]

            if not changes:
                print(f"  {label}: nothing generated, skipped")
                skipped += 1
                continue

            filled += 1
            print(f"  {label}: +{', +'.join(changes)}")
            if args.verbose or args.dry_run:
                if "notes" in changes:
                    print(f"      notes: {generated['notes']}")
                if "examples" in changes:
                    print(f"      examples: {generated['example_sentences'][:160]}")

            # Commit per item so an interruption keeps the work already done.
            if not args.dry_run:
                db.commit()

        verb = "would fill" if args.dry_run else "filled"
        print(f"\nDone: {verb} {filled}, skipped {skipped}, failed {failed}.")
        if failed and not args.dry_run:
            print("Re-run to retry the failures (already-filled items are skipped).")
        return 1 if failed else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
