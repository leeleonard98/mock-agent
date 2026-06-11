"""Tests for itinerary feedback + regenerate (T8)."""

from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.agents.planner import PlannerAgent
from app.models import ChatSession, ItineraryFeedback


async def test_post_feedback_persists_rating_and_comment(
    client: httpx.AsyncClient,
) -> None:
    """POST /sessions/{id}/feedback persists rating and comment."""
    r = await client.post("/sessions", json={"user_id": "alice"})
    sid = r.json()["id"]

    r = await client.post(
        f"/sessions/{sid}/feedback",
        json={"rating": 2, "comment": "Too rushed; need more food stops."},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["rating"] == 2
    assert body["comment"] == "Too rushed; need more food stops."

    # GET returns the same feedback
    r = await client.get(f"/sessions/{sid}/feedback")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["rating"] == 2


async def test_feedback_invalid_rating_rejected(client: httpx.AsyncClient) -> None:
    """Rating outside 1..5 is 422."""
    r = await client.post("/sessions", json={"user_id": "bob"})
    sid = r.json()["id"]

    r = await client.post(f"/sessions/{sid}/feedback", json={"rating": 0})
    assert r.status_code == 422
    r = await client.post(f"/sessions/{sid}/feedback", json={"rating": 6})
    assert r.status_code == 422


def test_regenerate_includes_latest_feedback_in_prompt(db: Session, script_llm) -> None:
    """When regenerating, the planner must read the latest feedback into the goal/system prompt."""
    sess = ChatSession(user_id="carol")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    db.add(
        ItineraryFeedback(
            session_id=sess.id,
            rating=2,
            comment="Too rushed; want slower pacing and more food stops.",
        )
    )
    db.commit()

    script_llm.script = [{"content": "Updated plan.", "tool_calls": []}]
    PlannerAgent(db).regenerate(sess.id, original_goal="Plan Tokyo")

    sys_msg = script_llm.calls[0]["messages"][0]
    user_msg = script_llm.calls[0]["messages"][1]
    combined = sys_msg["content"] + "\n" + user_msg["content"]
    # Either system or user (we put it in user goal) should reference the feedback
    assert "Too rushed" in combined or "slower pacing" in combined


async def test_regenerate_endpoint_runs_planner_with_feedback(
    client: httpx.AsyncClient, script_llm
) -> None:
    """POST /sessions/{id}/regenerate dispatches a planner run that incorporates feedback."""
    r = await client.post("/sessions", json={"user_id": "dave"})
    sid = r.json()["id"]

    # Submit feedback first
    await client.post(
        f"/sessions/{sid}/feedback",
        json={"rating": 1, "comment": "Add more nature spots."},
    )

    script_llm.script = [{"content": "Regenerated.", "tool_calls": []}]
    r = await client.post(
        f"/sessions/{sid}/regenerate", json={"goal": "Plan Tokyo"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["final"] == "Regenerated."

    # The planner must have seen the feedback
    sys_msg = script_llm.calls[0]["messages"][0]
    user_msg = script_llm.calls[0]["messages"][1]
    combined = sys_msg["content"] + user_msg["content"]
    assert "nature" in combined.lower()
