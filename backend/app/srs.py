"""Simple spaced repetition logic."""
from datetime import datetime, timedelta, timezone
from .models import Item

MIN_INTERVAL = 0.00694  # ~10 minutes (in fractional days)


def process_review(item: Item, rating: str) -> Item:
    """Update an item's SRS fields based on review rating."""
    now = datetime.now(timezone.utc)
    item.srs_reviews += 1

    if rating == "again":
        # Reset — item needs more work
        item.srs_interval = MIN_INTERVAL
        item.srs_ease = max(1.3, item.srs_ease - 0.2)
    elif rating == "hard":
        item.srs_correct += 1
        if item.srs_interval < 1:
            item.srs_interval = 0.0416  # 1 hour
        else:
            item.srs_interval = item.srs_interval * 1.2
        item.srs_ease = max(1.3, item.srs_ease - 0.1)
    elif rating == "good":
        item.srs_correct += 1
        if item.srs_interval < 1:
            item.srs_interval = 1  # 1 day
        else:
            item.srs_interval = item.srs_interval * item.srs_ease
        item.srs_ease = min(3.0, item.srs_ease + 0.05)

    item.srs_due = now + timedelta(days=item.srs_interval)
    return item
