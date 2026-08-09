"""Suspend items that already meet the leech threshold.

Auto-suspension in ``app.srs`` only fires when an item *lapses*, so cards that
were already leeches before the feature existed stay in rotation until they
happen to fail once more. This sweeps the existing backlog in one go.

Usage (from backend/):

    uv run python -m scripts.suspend_leeches --dry-run    # preview, no writes
    uv run python -m scripts.suspend_leeches              # apply
    uv run python -m scripts.suspend_leeches --min-reviews 12 --max-pass-rate 0.5

Safe to re-run: already-suspended items are skipped. Costs nothing — no AI
calls, it's a pure database sweep. Unsuspend anything you'd rather keep from
the Library page or the dashboard's "Needs rework" list.
"""
import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import func

# .env lives at the project root, two levels up from backend/scripts/
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from app.database import SessionLocal, engine  # noqa: E402
from app.models import Item  # noqa: E402
from app.srs import LEECH_MAX_PASS_RATE, LEECH_MIN_REVIEWS, pass_rate  # noqa: E402


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
    parser.add_argument("--user-id", default=None, help="restrict to one user (default: all)")
    parser.add_argument(
        "--min-reviews", type=int, default=LEECH_MIN_REVIEWS,
        help=f"reviews before an item can count as a leech (default: {LEECH_MIN_REVIEWS})",
    )
    parser.add_argument(
        "--max-pass-rate", type=float, default=LEECH_MAX_PASS_RATE,
        help=f"pass rate below which an item is a leech (default: {LEECH_MAX_PASS_RATE})",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        q = db.query(Item).filter(Item.suspended.is_(False))
        if args.user_id:
            q = q.filter(Item.user_id == args.user_id)

        candidates = []
        for item in q.order_by(Item.id).all():
            rate = pass_rate(item)
            if rate is None or item.srs_reviews < args.min_reviews:
                continue
            if rate < args.max_pass_rate:
                candidates.append((item, rate))

        if not candidates:
            print("Nothing to do - no unsuspended items meet the leech threshold.")
            return 0

        candidates.sort(key=lambda pair: pair[1])
        spent = sum(i.srs_reviews for i, _ in candidates)
        # Scoped the same way as the candidate query, so the percentage compares
        # like with like when --user-id narrows the sweep.
        overall_q = db.query(func.coalesce(func.sum(Item.srs_reviews), 0))
        if args.user_id:
            overall_q = overall_q.filter(Item.user_id == args.user_id)
        overall = overall_q.scalar()

        print(
            f"{len(candidates)} leech(es) at <{args.max_pass_rate:.0%} pass rate "
            f"over >={args.min_reviews} reviews{' (dry run)' if args.dry_run else ''}."
        )
        print(
            f"They account for {spent} of {overall} reviews "
            f"({spent / overall * 100:.0f}% of all review time).\n"
        )
        for item, rate in candidates:
            print(f"  {item.japanese:<12} {rate:>5.0%}  {item.srs_reviews:>3} reviews  {item.meaning[:44]}")

        if args.dry_run:
            print("\nDry run - nothing written.")
            return 0

        backup = _backup_sqlite()
        if backup:
            print(f"\nDatabase backed up to {backup.name}")

        for item, _ in candidates:
            item.suspended = True
        db.commit()

        print(f"Suspended {len(candidates)} item(s). Rework them from the dashboard's "
              '"Needs rework" list, then Restore.')
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
