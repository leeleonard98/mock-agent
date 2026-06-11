"""Chat sessions and messages (T1)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import ChatSession, Message

router = APIRouter(tags=["chat"])

# Roles we accept on inbound messages. tool/assistant come from agent code, not users,
# but we let them through for testability — the router itself doesn't trust input.
Role = Literal["user", "assistant", "system", "tool"]


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    role: str
    content: str
    created_at: datetime


class SessionCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=255)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    title: str | None
    created_at: datetime


class SessionWithMessages(SessionOut):
    messages: list[MessageOut]


class MessageCreate(BaseModel):
    role: Role
    content: str = Field(min_length=1, max_length=10_000)


def _get_session_or_404(session_id: int, db: Session, user_id: str | None = None) -> ChatSession:
    obj = db.get(ChatSession, session_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    # Tenancy: when caller asserts a user_id, the session must belong to them.
    # We deliberately return 404 (not 403) so we don't leak existence.
    if user_id is not None and obj.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return obj


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)) -> SessionOut:
    obj = ChatSession(user_id=payload.user_id, title=payload.title)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return SessionOut.model_validate(obj)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(user_id: str, db: Session = Depends(get_db)) -> list[SessionOut]:
    """List sessions for a user. user_id is REQUIRED — no global dump."""
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.id.desc())
    )
    rows = db.execute(stmt).scalars().all()
    return [SessionOut.model_validate(r) for r in rows]


@router.get("/sessions/{session_id}", response_model=SessionWithMessages)
def get_session(
    session_id: int,
    user_id: str | None = None,
    db: Session = Depends(get_db),
) -> SessionWithMessages:
    """Fetch a session with its messages.

    If `user_id` is supplied, the session must belong to that user; otherwise
    return 404 (don't leak existence). Without `user_id` the endpoint is open
    — that's an acceptable simplification for this prototype, not for prod.
    """
    stmt = (
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.messages))
    )
    obj = db.execute(stmt).scalar_one_or_none()
    if obj is None or (user_id is not None and obj.user_id != user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    return SessionWithMessages(
        id=obj.id,
        user_id=obj.user_id,
        title=obj.title,
        created_at=obj.created_at,
        messages=[MessageOut.model_validate(m) for m in obj.messages],
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
def add_message(
    session_id: int,
    payload: MessageCreate,
    user_id: str | None = None,
    db: Session = Depends(get_db),
) -> MessageOut:
    _get_session_or_404(session_id, db, user_id=user_id)
    msg = Message(session_id=session_id, role=payload.role, content=payload.content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return MessageOut.model_validate(msg)


class PlanRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)


class PlanToolCall(BaseModel):
    name: str
    arguments: dict
    result: object


class PlanResponse(BaseModel):
    plan: list[str]
    tool_calls: list[PlanToolCall]
    final: str
    truncated: bool


@router.post("/sessions/{session_id}/plan", response_model=PlanResponse)
def run_planner(
    session_id: int,
    payload: PlanRequest,
    user_id: str | None = None,
    db: Session = Depends(get_db),
) -> PlanResponse:
    """Run the planner agent against a session. Persists turns; returns structured result."""
    from app.agents.planner import PlannerAgent  # avoid eager OpenAI import

    _get_session_or_404(session_id, db, user_id=user_id)
    agent = PlannerAgent(db)
    result = agent.plan(session_id, goal=payload.goal)
    return PlanResponse(**result)


@router.post("/sessions/{session_id}/plan/stream")
def run_planner_stream(
    session_id: int,
    payload: PlanRequest,
    user_id: str | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream the planner's events as Server-Sent Events (T6)."""
    import json as _json

    from app.agents.planner import PlannerAgent

    _get_session_or_404(session_id, db, user_id=user_id)

    def _sse() -> "Iterator[bytes]":  # type: ignore[name-defined]
        agent = PlannerAgent(db)
        for event in agent.plan_stream(session_id, goal=payload.goal):
            yield f"data: {_json.dumps(event)}\n\n".encode()

    return StreamingResponse(_sse(), media_type="text/event-stream")


class TraceEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    session_id: int
    event_type: str
    payload: dict
    created_at: datetime


class TraceOut(BaseModel):
    session_id: int
    events: list[TraceEventOut]


@router.get("/sessions/{session_id}/trace", response_model=TraceOut)
def get_trace(
    session_id: int,
    user_id: str | None = None,
    db: Session = Depends(get_db),
) -> TraceOut:
    """Return the agent's trace events for a session in execution order (T7)."""
    from app.models import TraceEvent

    _get_session_or_404(session_id, db, user_id=user_id)
    rows = (
        db.execute(
            select(TraceEvent)
            .where(TraceEvent.session_id == session_id)
            .order_by(TraceEvent.id)
        )
        .scalars()
        .all()
    )
    return TraceOut(
        session_id=session_id,
        events=[TraceEventOut.model_validate(r) for r in rows],
    )
