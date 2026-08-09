"""Simple spaced repetition logic."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # importing models at runtime would cycle — models imports this
    from .models import Item

MIN_INTERVAL = 0.00694   # ~10 minutes in fractional days
HARD_INTERVAL = 0.0416   # ~1 hour in fractional days (used when interval < 1 day)

# A card the learner keeps failing is a "leech": it comes back every session,
# never matures, and crowds out items that would actually stick. Past these
# thresholds the item is suspended so it stops consuming reviews until the card
# itself is reworked (see routers/items.py suspend/unsuspend).
LEECH_MIN_REVIEWS = 8
LEECH_MAX_PASS_RATE = 0.6


def pass_rate(item: Item) -> float | None:
    """Share of reviews the learner did NOT lapse on ("hard" counts as a pass).

    This is the lenient measure, and the one leech detection uses: "hard" means
    the item *was* recalled, just slowly. Returns None for unreviewed items.

    Items reviewed before the hard/correct split have their hards folded into
    ``srs_correct`` and a zero ``srs_hard``, which lands on the same number.
    """
    if not item.srs_reviews:
        return None
    return ((item.srs_correct or 0) + (item.srs_hard or 0)) / item.srs_reviews


def recall_rate(item: Item) -> float | None:
    """Share of reviews rated "good" — the strict measure. None if unreviewed."""
    if not item.srs_reviews:
        return None
    return (item.srs_correct or 0) / item.srs_reviews


def is_leech(item: Item) -> bool:
    """Whether the item has failed often enough to be worth reworking."""
    rate = pass_rate(item)
    return (
        rate is not None
        and item.srs_reviews >= LEECH_MIN_REVIEWS
        and rate < LEECH_MAX_PASS_RATE
    )


def process_review(item: Item, rating: str) -> Item:
    """Update an item's SRS fields based on review rating (again/hard/good)."""
    now = datetime.now(timezone.utc)
    item.srs_reviews += 1

    if rating == "again":
        item.srs_lapses = (item.srs_lapses or 0) + 1
        item.srs_interval = MIN_INTERVAL
        item.srs_ease = max(1.3, item.srs_ease - 0.2)
    elif rating == "hard":
        # Counted separately from "good": folding it into srs_correct made a
        # card the learner barely dredged up look identical to one they knew.
        item.srs_hard = (item.srs_hard or 0) + 1
        item.srs_interval = HARD_INTERVAL if item.srs_interval < 1 else item.srs_interval * 1.2
        item.srs_ease = max(1.3, item.srs_ease - 0.1)
    elif rating == "good":
        item.srs_correct += 1
        item.srs_interval = 1 if item.srs_interval < 1 else item.srs_interval * item.srs_ease
        item.srs_ease = min(3.0, item.srs_ease + 0.05)
    else:
        raise ValueError(f"Unknown SRS rating: {rating!r}")

    item.srs_due = now + timedelta(days=item.srs_interval)

    # Only ever auto-suspend on a lapse. Crossing the threshold on a "good"
    # would yank a card the learner just got right, which reads as a bug.
    if rating == "again" and is_leech(item):
        item.suspended = True

    return item
