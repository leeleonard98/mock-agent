"""Tests for agent trace events (T7 bonus)."""

from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.agents.planner import PlannerAgent
from app.models import ChatSession, TraceEvent


def test_trace_events_persisted_in_order_during_planning(db: Session, script_llm) -> None:
    """A planning run records trace events in the order they happened."""
    sess = ChatSession(user_id="alice")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    script_llm.script = [
        {
            "content": "",
            "tool_calls": [
                {"name": "search_attractions", "arguments": {"city": "Tokyo", "limit": 1}}
            ],
        },
        {"content": "Done.", "tool_calls": []},
    ]
    PlannerAgent(db).plan(sess.id, goal="plan")

    events = (
        db.query(TraceEvent)
        .filter(TraceEvent.session_id == sess.id)
        .order_by(TraceEvent.id)
        .all()
    )
    types = [e.event_type for e in events]
    # We expect at minimum: thinking → tool_call → tool_result → thinking → complete
    assert types[0] == "thinking"
    assert "tool_call" in types
    assert "tool_result" in types
    assert types[-1] == "complete"


def test_trace_tool_call_event_includes_arguments(db: Session, script_llm) -> None:
    """A tool_call event must record the arguments the model passed."""
    sess = ChatSession(user_id="bob")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    script_llm.script = [
        {
            "content": "",
            "tool_calls": [
                {
                    "name": "calculate_budget",
                    "arguments": {
                        "days": 5,
                        "accommodation_per_night": 100,
                        "transport_total": 200,
                        "activities_per_day": 50,
                    },
                }
            ],
        },
        {"content": "Done.", "tool_calls": []},
    ]
    PlannerAgent(db).plan(sess.id, goal="plan")

    tool_call_events = (
        db.query(TraceEvent)
        .filter(TraceEvent.session_id == sess.id, TraceEvent.event_type == "tool_call")
        .all()
    )
    assert len(tool_call_events) == 1
    payload = tool_call_events[0].payload
    assert payload["name"] == "calculate_budget"
    assert payload["arguments"]["days"] == 5
    assert payload["arguments"]["transport_total"] == 200


async def test_get_trace_returns_persisted_events(
    client: httpx.AsyncClient, script_llm
) -> None:
    """GET /sessions/{id}/trace returns the events in order."""
    r = await client.post("/sessions", json={"user_id": "carol"})
    sid = r.json()["id"]

    script_llm.script = [
        {
            "content": "",
            "tool_calls": [
                {"name": "search_attractions", "arguments": {"city": "Osaka"}}
            ],
        },
        {"content": "All set.", "tool_calls": []},
    ]
    await client.post(f"/sessions/{sid}/plan", json={"goal": "Osaka"})

    r = await client.get(f"/sessions/{sid}/trace")
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) >= 3
    types = [e["event_type"] for e in events]
    assert types[0] == "thinking"
    assert "tool_call" in types
    assert types[-1] == "complete"

    # Final event payload should record the truncated flag from the planner result
    last = events[-1]
    assert last["payload"]["truncated"] is False
