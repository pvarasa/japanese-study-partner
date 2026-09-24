import random
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from ..crud import get_item_for_user
from ..deps import Db, UserId
from ..kanji import READING_TYPES, is_reading_candidate, kanji_families
from ..models import Item, ReadingCard, StudySession
from ..schemas import (
    DashboardStats,
    DayStat,
    ItemOut,
    KanjiFamily,
    ReadingItemOut,
    SessionProgress,
    SRSReview,
)
from ..srs import process_review

router = APIRouter(prefix="/api/study", tags=["study"])

# Modes where the learner's answer is graded right/wrong, so items_correct is
# meaningful. Conversation practice records turns for streak/activity purposes
# but has no notion of a correct answer — including it would pin accuracy at
# 100% regardless of how the learner actually did.
GRADED_MODES = {
    "flashcard_jp",
    "flashcard_en",
    "cloze",
    "fill_blank",
    "sentence_build",
    "grammar_drill",
    "kanji_reading",
}


def _local_midnight(day_offset: int = 0) -> datetime:
    """Local calendar midnight, ``day_offset`` days from today (tz-aware local).

    Timestamps are stored in UTC but "today" and the streak follow the server's
    local calendar, so callers convert this with ``.astimezone(timezone.utc)``
    to compare against stored values.
    """
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return start + timedelta(days=day_offset)


def _active_items(db: Db, user_id: str, type: str | None):
    """Base query shared by every study-queue endpoint: this user's own,
    non-suspended items, optionally narrowed to one type."""
    q = db.query(Item).filter(Item.user_id == user_id, Item.suspended.is_(False))
    if type:
        q = q.filter(Item.type == type)
    return q


def _serve(items: list[Item]) -> list[ItemOut]:
    return [ItemOut.model_validate(i) for i in items]


def _to_local_date(dt: datetime) -> date:
    """Convert a stored timestamp to the server's local calendar date.

    ``started_at`` is stored naive-UTC, so the zone has to be attached before
    converting to local — otherwise the day boundary drifts from what the
    dashboard and history chart consider "today".
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date()


# Items recalled at least this often are "strong" (the Library's top bucket) and
# don't belong on the dashboard's needs-practice list.
WEAK_RECALL_BELOW = 0.85

# No real streak runs longer than this, so bounding the window keeps the
# streak calculation to one query instead of one query per day of the streak.
STREAK_WINDOW_DAYS = 400


@router.get("/due", response_model=list[ItemOut])
def get_due_items(user_id: UserId, db: Db, limit: int = 20, type: str | None = None):
    """Get items due for review.

    Suspended leeches are excluded: they're due (their interval never grows
    past the 10-minute floor) but showing them just burns the session on cards
    that have already proven they don't work as written.

    Selection still favors the most overdue items (so a queue longer than
    ``limit`` doesn't starve the ones waiting longest), but the returned order
    is shuffled — always drilling the same sequence lets the learner memorize
    "what comes after X" instead of actually recalling X.
    """
    now = datetime.now(timezone.utc)
    q = _active_items(db, user_id, type).filter(Item.srs_due <= now)
    items = q.order_by(Item.srs_due.asc()).limit(limit).all()
    random.shuffle(items)
    return _serve(items)


@router.get("/practice", response_model=list[ItemOut])
def get_practice_items(user_id: UserId, db: Db, limit: int = 20, type: str | None = None):
    """Extra reps outside the SRS schedule — any active item, not just due ones.

    For learners who've cleared their due queue and want more drilling.
    Sampled uniformly at random (not just shuffled after an ordered fetch,
    the way /due is) since there's no due-date priority to preserve here.
    Reviewing these goes through /review with ``practice: true``, which skips
    ``process_review`` entirely, so it can't reschedule a card early or dodge
    leech suspension.
    """
    items = _active_items(db, user_id, type).order_by(func.random()).limit(limit).all()
    return _serve(items)


def _reading_pool(db: Db, user_id: str):
    """Active vocabulary that could carry a reading card, with cards preloaded.

    "Has kanji" can't be expressed in SQL portably, so callers still pass the
    rows through ``is_reading_candidate``.
    """
    return (
        _active_items(db, user_id, None)
        .filter(Item.type.in_(READING_TYPES), Item.reading.isnot(None))
        .options(joinedload(Item.reading_card))
    )


def _serve_reading(db: Db, user_id: str, items: list[Item]) -> list[ReadingItemOut]:
    """Serialise reading-drill items with their kanji families attached.

    Siblings come from the whole library (suspended items included — they're
    still words the learner has met), loaded once for the batch.
    """
    if not items:
        return []
    library = db.query(Item).filter(Item.user_id == user_id, Item.type.in_(READING_TYPES)).all()
    return [
        ReadingItemOut.model_validate(i).model_copy(update={
            "kanji": [KanjiFamily.model_validate(f) for f in kanji_families(i, library)],
        })
        for i in items
    ]


@router.get("/reading/due", response_model=list[ReadingItemOut])
def get_reading_due(user_id: UserId, db: Db, limit: int = 20):
    """Items due for the kanji-reading drill.

    Reading cards that are due come first, most overdue first. Any room left
    is filled with items that have never had a reading review, **best-known
    meaning first** (longest meaning interval): those are the words whose
    only gap is the kanji, which is what this drill is for. A card is created
    by the first review, so never-reviewed items stay "new" until then.
    """
    now = datetime.now(timezone.utc)
    due = [
        i for i in _reading_pool(db, user_id)
        .join(ReadingCard, ReadingCard.item_id == Item.id)
        .filter(ReadingCard.srs_due <= now)
        .order_by(ReadingCard.srs_due.asc())
        .limit(limit)
        if is_reading_candidate(i)
    ]
    if len(due) < limit:
        fresh = (
            _reading_pool(db, user_id)
            .outerjoin(ReadingCard, ReadingCard.item_id == Item.id)
            .filter(ReadingCard.item_id.is_(None))
            .order_by(Item.srs_interval.desc(), Item.id.asc())
        )
        due += [i for i in fresh if is_reading_candidate(i)][: limit - len(due)]
    random.shuffle(due)
    return _serve_reading(db, user_id, due)


@router.get("/reading/practice", response_model=list[ReadingItemOut])
def get_reading_practice(user_id: UserId, db: Db, limit: int = 20):
    """Random reading-drill items regardless of schedule (see /practice)."""
    pool = [i for i in _reading_pool(db, user_id) if is_reading_candidate(i)]
    return _serve_reading(db, user_id, random.sample(pool, min(limit, len(pool))))


def _review_reading(item: Item, rating: str) -> ReadingCard:
    """Apply a rating to the item's reading card, creating it on first review.

    SRS values are set explicitly: column defaults only fill in at flush,
    and ``process_review`` increments them before that.
    """
    card = item.reading_card
    if card is None:
        card = ReadingCard(
            user_id=item.user_id, srs_interval=0, srs_ease=2.5, srs_reviews=0,
            srs_correct=0, srs_hard=0, srs_lapses=0,
        )
        item.reading_card = card
    return process_review(card, rating, auto_suspend=False)


def _bump_session(db: Db, session_id: int, user_id: str, *, reviewed=0, correct=0, hard=0):
    """Fold counter deltas into a session, ignoring unknown/foreign sessions.

    Counters used to be written only when a session ran to completion, so
    abandoning one part-way recorded nothing at all — which is why every
    sentence_build, grammar_drill and converse session historically showed zero.
    """
    session = db.query(StudySession).filter(
        StudySession.id == session_id, StudySession.user_id == user_id
    ).first()
    if not session:
        return None
    session.items_reviewed = (session.items_reviewed or 0) + reviewed
    session.items_correct = (session.items_correct or 0) + correct
    session.items_hard = (session.items_hard or 0) + hard
    return session


@router.post("/review")
def review_item(data: SRSReview, user_id: UserId, db: Db):
    """Submit a review rating for an item.

    When ``session_id`` is supplied the session counters are advanced in the
    same transaction, so a session that's abandoned mid-way still keeps the
    reviews the learner actually did.
    """
    # item_id arrives in the JSON body, so the require_item dependency (which
    # binds from path/query) doesn't apply here.
    item = get_item_for_user(db, data.item_id, user_id)
    if not item:
        raise HTTPException(404, "Item not found")
    if data.card == "reading" and not is_reading_candidate(item):
        raise HTTPException(422, "This item has no kanji reading to review")
    scheduled = item
    if data.card == "reading":
        # Practice reps skip scheduling, so they don't create a card either.
        scheduled = item.reading_card
        if not data.practice:
            scheduled = _review_reading(item, data.rating)
    elif not data.practice:
        process_review(item, data.rating)
    if data.session_id is not None:
        _bump_session(
            db, data.session_id, user_id,
            reviewed=1,
            correct=1 if data.rating == "good" else 0,
            hard=1 if data.rating == "hard" else 0,
        )
    db.commit()
    return {
        "ok": True,
        "next_due": scheduled.srs_due.isoformat() if scheduled else None,
        "interval_days": round(scheduled.srs_interval, 2) if scheduled else None,
        "suspended": bool(item.suspended),
    }


@router.get("/dashboard", response_model=DashboardStats)
def get_dashboard(user_id: UserId, db: Db):
    """Get dashboard stats."""
    now = datetime.now(timezone.utc)
    today_start_local = _local_midnight()
    today_start = today_start_local.astimezone(timezone.utc)

    total_items = db.query(func.count(Item.id)).filter(Item.user_id == user_id).scalar()
    # Matches what /due will actually serve, so the "Study N due items" button
    # can't promise more cards than the session hands out.
    due_today = db.query(func.count(Item.id)).filter(
        Item.user_id == user_id, Item.srs_due <= now, Item.suspended.is_(False)
    ).scalar()

    sessions_today = db.query(StudySession).filter(
        StudySession.user_id == user_id,
        StudySession.started_at >= today_start,
    ).all()
    studied_today = sum(s.items_reviewed for s in sessions_today)
    graded = [s for s in sessions_today if s.mode in GRADED_MODES]
    graded_reviewed = sum(s.items_reviewed for s in graded)
    graded_correct = sum(s.items_correct for s in graded)
    accuracy_today = (graded_correct / graded_reviewed * 100) if graded_reviewed > 0 else 0

    recall = Item.srs_correct * 1.0 / func.nullif(Item.srs_reviews, 0)
    weak_items = (
        db.query(Item)
        .filter(
            Item.user_id == user_id, Item.srs_reviews >= 2, Item.suspended.is_(False),
            recall < WEAK_RECALL_BELOW,
        )
        .order_by(recall.asc())
        .limit(10)
        .all()
    )

    # Suspended cards, worst first — the rework queue. The list is capped, so
    # the total is counted separately.
    suspended = db.query(Item).filter(Item.user_id == user_id, Item.suspended.is_(True))
    suspended_count = suspended.with_entities(func.count(Item.id)).scalar()
    leeches = (
        suspended
        .order_by(
            ((Item.srs_correct + Item.srs_hard) * 1.0 / func.nullif(Item.srs_reviews, 0)).asc(),
            Item.srs_reviews.desc(),
        )
        .limit(20)
        .all()
    )

    recent_items = db.query(Item).filter(Item.user_id == user_id).order_by(
        Item.created_at.desc()
    ).limit(10).all()

    window_start = (today_start_local - timedelta(days=STREAK_WINDOW_DAYS)).astimezone(timezone.utc)
    streak_sessions = db.query(StudySession).filter(
        StudySession.user_id == user_id,
        StudySession.started_at >= window_start,
        StudySession.items_reviewed > 0,
    ).all()
    active_days = {_to_local_date(s.started_at) for s in streak_sessions}

    streak = 0
    day = today_start_local.date()
    while day in active_days:
        streak += 1
        day -= timedelta(days=1)

    return DashboardStats(
        total_items=total_items,
        due_today=due_today,
        studied_today=studied_today,
        accuracy_today=round(accuracy_today, 1),
        weak_items=[ItemOut.model_validate(i) for i in weak_items],
        recent_items=[ItemOut.model_validate(i) for i in recent_items],
        streak_days=streak,
        leeches=[ItemOut.model_validate(i) for i in leeches],
        suspended_count=suspended_count,
    )


@router.get("/history", response_model=list[DayStat])
def get_history(user_id: UserId, db: Db, days: int = 60):
    """Per-day graded review counts for the retention trend, oldest first.

    Only days with activity appear — the chart draws gaps rather than plotting
    a run of zero-accuracy days the learner simply didn't study.
    """
    days = max(1, min(days, 365))
    start = _local_midnight(-(days - 1)).astimezone(timezone.utc)
    sessions = db.query(StudySession).filter(
        StudySession.user_id == user_id,
        StudySession.started_at >= start,
        StudySession.items_reviewed > 0,
        StudySession.mode.in_(GRADED_MODES),
    ).all()

    by_day: dict[date, dict[str, int]] = {}
    for s in sessions:
        bucket = by_day.setdefault(
            _to_local_date(s.started_at), {"reviewed": 0, "correct": 0, "hard": 0}
        )
        bucket["reviewed"] += s.items_reviewed or 0
        bucket["correct"] += s.items_correct or 0
        bucket["hard"] += s.items_hard or 0

    return [
        DayStat(
            date=day.isoformat(),
            reviewed=v["reviewed"],
            correct=v["correct"],
            hard=v["hard"],
            accuracy=round(v["correct"] / v["reviewed"] * 100, 1) if v["reviewed"] else 0.0,
        )
        for day, v in sorted(by_day.items())
    ]


@router.post("/session/start")
def start_session(mode: str, user_id: UserId, db: Db):
    session = StudySession(user_id=user_id, mode=mode)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"session_id": session.id}


@router.post("/session/{session_id}/progress")
def record_progress(session_id: int, data: SessionProgress, user_id: UserId, db: Db):
    """Add to a session's counters as the learner goes.

    Used by modes that aren't item reviews (conversation turns). Item reviews
    pass ``session_id`` to /review instead, which keeps the counter bump in the
    same transaction as the SRS update.
    """
    session = _bump_session(
        db, session_id, user_id,
        reviewed=data.reviewed, correct=data.correct, hard=data.hard,
    )
    if not session:
        raise HTTPException(404, "Session not found")
    db.commit()
    return {"ok": True, "items_reviewed": session.items_reviewed}


@router.post("/session/{session_id}/end")
def end_session(session_id: int, user_id: UserId, db: Db):
    """Close a session by stamping ``ended_at``.

    Deliberately takes no counts: progress is accumulated per review, and
    letting the closing call also *set* totals gave an exit path — which may
    fire from an unmount handler, or not at all — the power to overwrite what
    actually happened. Counters only ever move through /review and /progress.
    """
    session = db.query(StudySession).filter(
        StudySession.id == session_id, StudySession.user_id == user_id
    ).first()
    if not session:
        raise HTTPException(404, "Session not found")
    session.ended_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}
