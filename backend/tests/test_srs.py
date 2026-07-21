"""Unit tests for the SRS algorithm."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Item
from app.srs import HARD_INTERVAL, MIN_INTERVAL, process_review


def _new_item(interval: float = 0.0, ease: float = 2.5, reviews: int = 0, correct: int = 0) -> Item:
    return Item(
        type="word",
        japanese="猫",
        meaning="cat",
        srs_interval=interval,
        srs_ease=ease,
        srs_due=datetime.now(timezone.utc),
        srs_reviews=reviews,
        srs_correct=correct,
    )


def test_again_resets_and_drops_ease():
    item = _new_item(interval=5.0, ease=2.5, reviews=3, correct=3)
    process_review(item, "again")
    assert item.srs_interval == MIN_INTERVAL
    assert item.srs_ease == 2.3
    assert item.srs_reviews == 4
    assert item.srs_correct == 3  # not incremented on 'again'


def test_hard_on_new_item_jumps_to_one_hour():
    item = _new_item(interval=0.0)
    process_review(item, "hard")
    assert item.srs_interval == HARD_INTERVAL
    assert item.srs_correct == 1


def test_hard_on_mature_item_grows_interval_slightly():
    item = _new_item(interval=10.0, ease=2.5)
    process_review(item, "hard")
    assert item.srs_interval == 12.0  # 10 * 1.2
    assert item.srs_ease == 2.4


def test_good_on_new_item_sets_one_day():
    item = _new_item(interval=0.0, ease=2.5)
    process_review(item, "good")
    assert item.srs_interval == 1
    assert item.srs_ease == 2.55
    assert item.srs_correct == 1


def test_good_on_mature_item_multiplies_by_ease():
    item = _new_item(interval=4.0, ease=2.5)
    process_review(item, "good")
    assert item.srs_interval == 10.0  # 4 * 2.5
    assert item.srs_ease == 2.55


def test_ease_clamped_low():
    item = _new_item(ease=1.4)
    process_review(item, "again")
    assert item.srs_ease == 1.3
    process_review(item, "again")
    assert item.srs_ease == 1.3


def test_ease_clamped_high():
    item = _new_item(interval=5.0, ease=2.98)
    process_review(item, "good")
    assert item.srs_ease == 3.0


def test_srs_due_follows_interval():
    item = _new_item(interval=0.0)
    before = datetime.now(timezone.utc)
    process_review(item, "good")
    delta = item.srs_due - before
    # "good" on a new item → 1 day interval
    assert timedelta(hours=23) < delta < timedelta(hours=25)


def test_unknown_rating_raises():
    item = _new_item()
    with pytest.raises(ValueError, match="Unknown SRS rating"):
        process_review(item, "excellent")
