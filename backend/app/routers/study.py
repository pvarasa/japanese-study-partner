from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone, timedelta
from ..database import get_db
from ..models import Item, StudySession
from ..schemas import SRSReview, ItemOut, DashboardStats
from ..srs import process_review
from .items import _item_to_out

router = APIRouter(prefix="/api/study", tags=["study"])


@router.get("/due", response_model=list[ItemOut])
def get_due_items(
    limit: int = 20,
    type: str | None = None,
    db: Session = Depends(get_db),
):
    """Get items due for review, ordered by most overdue first."""
    now = datetime.now(timezone.utc)
    q = db.query(Item).filter(Item.srs_due <= now)
    if type:
        q = q.filter(Item.type == type)
    items = q.order_by(Item.srs_due.asc()).limit(limit).all()
    return [_item_to_out(i) for i in items]


@router.post("/review")
def review_item(data: SRSReview, db: Session = Depends(get_db)):
    """Submit a review rating for an item."""
    item = db.query(Item).filter(Item.id == data.item_id).first()
    if not item:
        raise HTTPException(404, "Item not found")
    item = process_review(item, data.rating)
    db.commit()
    return {
        "ok": True,
        "next_due": item.srs_due.isoformat(),
        "interval_days": round(item.srs_interval, 2),
    }


@router.get("/dashboard", response_model=DashboardStats)
def get_dashboard(db: Session = Depends(get_db)):
    """Get dashboard stats."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_items = db.query(func.count(Item.id)).scalar()
    due_today = db.query(func.count(Item.id)).filter(Item.srs_due <= now).scalar()

    # Today's sessions
    sessions_today = db.query(StudySession).filter(
        StudySession.started_at >= today_start
    ).all()
    studied_today = sum(s.items_reviewed for s in sessions_today)
    correct_today = sum(s.items_correct for s in sessions_today)
    accuracy_today = (correct_today / studied_today * 100) if studied_today > 0 else 0

    # Weak items: lowest accuracy with at least 2 reviews
    weak_items = (
        db.query(Item)
        .filter(Item.srs_reviews >= 2)
        .order_by((Item.srs_correct * 1.0 / Item.srs_reviews).asc())
        .limit(10)
        .all()
    )

    # Recent items
    recent_items = db.query(Item).order_by(Item.created_at.desc()).limit(10).all()

    # Streak: consecutive days with at least one session
    streak = 0
    check_date = today_start
    while True:
        day_sessions = db.query(StudySession).filter(
            StudySession.started_at >= check_date,
            StudySession.started_at < check_date + timedelta(days=1),
            StudySession.items_reviewed > 0,
        ).first()
        if day_sessions:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    return DashboardStats(
        total_items=total_items,
        due_today=due_today,
        studied_today=studied_today,
        accuracy_today=round(accuracy_today, 1),
        weak_items=[_item_to_out(i) for i in weak_items],
        recent_items=[_item_to_out(i) for i in recent_items],
        streak_days=streak,
    )


@router.post("/session/start")
def start_session(mode: str, db: Session = Depends(get_db)):
    session = StudySession(mode=mode)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"session_id": session.id}


@router.post("/session/{session_id}/end")
def end_session(
    session_id: int,
    items_reviewed: int,
    items_correct: int,
    db: Session = Depends(get_db),
):
    session = db.query(StudySession).filter(StudySession.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    session.ended_at = datetime.now(timezone.utc)
    session.items_reviewed = items_reviewed
    session.items_correct = items_correct
    db.commit()
    return {"ok": True}
