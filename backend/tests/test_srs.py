"""Unit tests for the SRS algorithm."""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Item
from app.srs import (
    HARD_INTERVAL,
    LEECH_MIN_REVIEWS,
    MIN_INTERVAL,
    is_leech,
    pass_rate,
    process_review,
    recall_rate,
)


def _new_item(
    interval: float = 0.0,
    ease: float = 2.5,
    reviews: int = 0,
    correct: int = 0,
    hard: int = 0,
    lapses: int = 0,
) -> Item:
    return Item(
        type="word",
        japanese="猫",
        meaning="cat",
        srs_interval=interval,
        srs_ease=ease,
        srs_due=datetime.now(timezone.utc),
        srs_reviews=reviews,
        srs_correct=correct,
        srs_hard=hard,
        srs_lapses=lapses,
        suspended=False,
    )


def test_again_resets_and_drops_ease():
    item = _new_item(interval=5.0, ease=2.5, reviews=3, correct=3)
    process_review(item, "again")
    assert item.srs_interval == MIN_INTERVAL
    assert item.srs_ease == 2.3
    assert item.srs_reviews == 4
    assert item.srs_correct == 3  # not incremented on 'again'
    assert item.srs_lapses == 1


def test_hard_on_new_item_jumps_to_one_hour():
    item = _new_item(interval=0.0)
    process_review(item, "hard")
    assert item.srs_interval == HARD_INTERVAL
    # "hard" is tracked separately — folding it into srs_correct made a barely
    # recalled card indistinguishable from a known one.
    assert item.srs_correct == 0
    assert item.srs_hard == 1


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


# --- rates -----------------------------------------------------------------

def test_rates_are_none_when_unreviewed():
    item = _new_item()
    assert pass_rate(item) is None
    assert recall_rate(item) is None
    assert is_leech(item) is False


def test_pass_rate_counts_hard_but_recall_rate_does_not():
    item = _new_item(reviews=10, correct=4, hard=3)
    assert pass_rate(item) == 0.7   # only 3 lapses
    assert recall_rate(item) == 0.4  # only 4 clean recalls


def test_pass_rate_handles_legacy_null_hard():
    """Rows written before srs_hard existed read back as NULL, not 0."""
    item = _new_item(reviews=4, correct=3)
    item.srs_hard = None
    assert pass_rate(item) == 0.75


# --- leeches ---------------------------------------------------------------

def test_leech_needs_both_volume_and_failure():
    # Failing badly but barely reviewed — not yet a leech.
    assert is_leech(_new_item(reviews=3, correct=0)) is False
    # Heavily reviewed and passing — not a leech.
    assert is_leech(_new_item(reviews=20, correct=18)) is False
    # Heavily reviewed and failing — leech.
    assert is_leech(_new_item(reviews=20, correct=4)) is True


def test_hard_ratings_keep_an_item_out_of_leech_territory():
    """"Hard" means recalled-but-slowly, so it shouldn't count as failure."""
    item = _new_item(reviews=10, correct=2, hard=6)
    assert pass_rate(item) == 0.8
    assert is_leech(item) is False


def test_lapse_crossing_threshold_auto_suspends():
    item = _new_item(reviews=LEECH_MIN_REVIEWS - 1, correct=1, lapses=6)
    assert item.suspended is False
    process_review(item, "again")
    assert item.srs_reviews == LEECH_MIN_REVIEWS
    assert item.suspended is True


def test_good_review_never_auto_suspends():
    """Crossing the threshold on a correct answer would read as a bug."""
    item = _new_item(reviews=LEECH_MIN_REVIEWS - 1, correct=1, lapses=6)
    process_review(item, "good")
    assert is_leech(item) is True  # still a bad card by the numbers…
    assert item.suspended is False  # …but not yanked mid-success


def test_healthy_item_is_not_suspended_by_a_single_lapse():
    item = _new_item(interval=20.0, reviews=30, correct=28)
    process_review(item, "again")
    assert item.suspended is False
