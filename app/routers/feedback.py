"""Itinerary feedback (T8)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ChatSession, ItineraryFeedback

router = APIRouter(tags=["feedback"])


class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: int
    rating: int
    comment: str | None
    created_at: datetime


class FeedbackList(BaseModel):
    session_id: int
    items: list[FeedbackOut]


def _ensure_session(session_id: int, db: Session) -> None:
    if db.get(ChatSession, session_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="session not found"
        )


@router.post(
    "/sessions/{session_id}/feedback",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
)
def post_feedback(
    session_id: int, payload: FeedbackCreate, db: Session = Depends(get_db)
) -> FeedbackOut:
    _ensure_session(session_id, db)
    fb = ItineraryFeedback(
        session_id=session_id, rating=payload.rating, comment=payload.comment
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return FeedbackOut.model_validate(fb)


@router.get("/sessions/{session_id}/feedback", response_model=FeedbackList)
def list_feedback(session_id: int, db: Session = Depends(get_db)) -> FeedbackList:
    _ensure_session(session_id, db)
    rows = (
        db.execute(
            select(ItineraryFeedback)
            .where(ItineraryFeedback.session_id == session_id)
            .order_by(ItineraryFeedback.id.desc())
        )
        .scalars()
        .all()
    )
    return FeedbackList(
        session_id=session_id,
        items=[FeedbackOut.model_validate(r) for r in rows],
    )
