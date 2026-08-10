"""Backfill usage notes and example sentences for items that came in short.

Items created through POST /api/items/ (Reading page "Add to library", manual
entry) were stored exactly as handed over, so they lack the notes and example
sentences the import flow generates. Older rows also predate the
``EXAMPLES_PER_ITEM`` contract and may carry fewer sentences than a card now
shows. This walks both kinds of gap using the same generators the live
endpoints use.

Two passes, picked per item:

* **enrich**  — notes and/or examples missing outright: one Claude call fills
  both, via the generator ``POST /api/items/?enrich=true`` uses.
* **top-up**  — has examples but fewer than ``EXAMPLES_PER_ITEM``: one Claude
  call per missing sentence, appended to what's already there. The existing
  sentences are kept and passed to the model as a do-not-repeat list, so a
  reviewed card doesn't lose text it already had.

Usage (from backend/):

    uv run python -m scripts.backfill_enrich --dry-run     # preview, no writes
    uv run python -m scripts.backfill_enrich               # apply
    uv run python -m scripts.backfill_enrich --limit 5     # try a few first

Safe to re-run: gaps are recomputed from the current rows every run, so an
interrupted run resumes where it stopped and a partly-filled item is picked up
by whichever pass still applies. Note that --dry-run still makes the Claude
calls (that's what lets it show the text it would write); it only skips writes.
"""
import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# .env lives at the project root, two levels up from backend/scripts/
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from app.cloze import parse_examples  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.enrich import EXAMPLES_PER_ITEM, build_enrichment, build_example_sentence  # noqa: E402
from app.levels import LEVEL_DESCRIPTOR, get_jlpt_level  # noqa: E402
from app.models import Item  # noqa: E402

ENRICH = "enrich"  # notes and/or examples absent
TOPUP = "topup"    # has examples, but fewer than EXAMPLES_PER_ITEM


def _gap(item: Item) -> str | None:
    """Classify what an item is missing, or None if it's complete.

    Counting stored examples means parsing the JSON column, which SQL can't do
    portably across SQLite and PostgreSQL — so this is a Python-side filter over
    every row rather than a WHERE clause. Fine at library scale.
    """
    examples = parse_examples(item.example_sentences)
    if not item.notes or not examples:
        return ENRICH
    if len(examples) < EXAMPLES_PER_ITEM:
        return TOPUP
    return None


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

        candidates = []
        for item in q.order_by(Item.id).all():
            gap = _gap(item)
            if gap:
                candidates.append((item, gap))

        if args.limit:
            candidates = candidates[: args.limit]

        if not candidates:
            print(
                f"Nothing to do - every item has notes and at least "
                f"{EXAMPLES_PER_ITEM} example sentences."
            )
            return 0

        n_topup = sum(1 for _, gap in candidates if gap == TOPUP)
        print(
            f"{len(candidates)} item(s) need work "
            f"({len(candidates) - n_topup} to enrich, {n_topup} to top up)"
            f"{' (dry run)' if args.dry_run else ''}."
        )

        backup = None
        if not args.dry_run:
            backup = _backup_sqlite()
            if backup:
                print(f"Database backed up to {backup.name}")

        # get_jlpt_level hits the settings table per user; cache it per run.
        level_cache: dict[str, str] = {}
        filled = skipped = failed = 0

        for n, (item, gap) in enumerate(candidates, 1):
            if item.jlpt_level in LEVEL_DESCRIPTOR:
                level = item.jlpt_level
            else:
                if item.user_id not in level_cache:
                    level_cache[item.user_id] = get_jlpt_level(db, item.user_id)
                level = level_cache[item.user_id]

            label = f"[{n}/{len(candidates)}] {item.japanese}"

            if gap == TOPUP:
                # Append to what's there instead of regenerating the set, so a
                # sentence the learner has already seen on the card survives.
                kept = parse_examples(item.example_sentences)
                added: list[dict] = []
                try:
                    while len(kept) + len(added) < EXAMPLES_PER_ITEM:
                        added.append(build_example_sentence(
                            item_type=item.type,
                            japanese=item.japanese,
                            reading=item.reading,
                            meaning=item.meaning,
                            level=level,
                            # Feed back everything so far, so call two doesn't
                            # repeat call one.
                            existing=json.dumps(kept + added, ensure_ascii=False),
                        ))
                except Exception as e:
                    print(f"  {label}: FAILED ({type(e).__name__}: {e})")
                    failed += 1
                    continue

                filled += 1
                print(f"  {label}: had {len(kept)}, +{len(added)} example(s)")
                if args.verbose or args.dry_run:
                    for ex in added:
                        print(f"      {ex['japanese']}  -  {ex['english']}")
                if not args.dry_run:
                    item.example_sentences = json.dumps(kept + added, ensure_ascii=False)
                    db.commit()
                continue

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
            # parse_examples rather than a blank-string check: a row whose column
            # holds unparseable JSON is just as example-less as an empty one.
            # If the model returns fewer than EXAMPLES_PER_ITEM here, the row
            # simply reappears in the top-up pass on the next run.
            if not parse_examples(item.example_sentences) and generated["example_sentences"]:
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
