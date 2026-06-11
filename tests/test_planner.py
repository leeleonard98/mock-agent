"""Tests for the agent planner (T2)."""

from __future__ import annotations

import json

import httpx

from app.agents.planner import PlannerAgent
from app.models import ChatSession, Message
from sqlalchemy.orm import Session


# script_llm fixture comes from tests/conftest.py
# ---------------------------------------------------------------------------
# Direct PlannerAgent tests
# ---------------------------------------------------------------------------


def test_planner_decomposes_and_returns_subtasks(db: Session, script_llm) -> None:
    """First LLM turn returns a plan; planner exposes it on the result."""
    sess = ChatSession(user_id="alice", title="trip")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    script_llm.script = [
        # Turn 1: model returns a plan with no tool calls (just a textual plan)
        {
            "content": json.dumps(
                {"plan": ["Find attractions", "Estimate cost", "Build itinerary"]}
            ),
            "tool_calls": [],
        },
        # Turn 2: final
        {"content": "Here is your itinerary.", "tool_calls": []},
    ]

    agent = PlannerAgent(db)
    result = agent.plan(sess.id, goal="Plan a 5-day Japan trip under $2000")

    assert result["plan"] == ["Find attractions", "Estimate cost", "Build itinerary"]
    assert result["final"] == "Here is your itinerary."

    # User goal + assistant turns persisted on the session
    msgs = (
        db.query(Message).filter(Message.session_id == sess.id).order_by(Message.id).all()
    )
    roles_and_contents = [(m.role, m.content) for m in msgs]
    assert ("user", "Plan a 5-day Japan trip under $2000") in roles_and_contents
    assert any(r == "assistant" and "itinerary" in c.lower() for r, c in roles_and_contents)


def test_planner_dispatches_tool_calls_with_correct_args(db: Session, script_llm) -> None:
    """When LLM returns tool_calls, planner invokes them via the registry and feeds results back."""
    sess = ChatSession(user_id="bob")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    script_llm.script = [
        # Turn 1: model wants to search attractions
        {
            "content": "",
            "tool_calls": [
                {"name": "search_attractions", "arguments": {"city": "Tokyo", "limit": 2}}
            ],
        },
        # Turn 2: model wants to compute budget
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
        # Turn 3: model is done
        {"content": "All planned.", "tool_calls": []},
    ]

    agent = PlannerAgent(db)
    result = agent.plan(sess.id, goal="Plan Tokyo")

    # Two tool calls executed, results captured
    assert len(result["tool_calls"]) == 2
    names = [tc["name"] for tc in result["tool_calls"]]
    assert names == ["search_attractions", "calculate_budget"]

    # search_attractions returned 2 attractions for Tokyo (deterministic catalog)
    search_result = result["tool_calls"][0]["result"]
    assert isinstance(search_result, list) and len(search_result) == 2

    # budget total is correctly the result of the tool, not made up by the LLM
    budget_result = result["tool_calls"][1]["result"]
    assert budget_result["total"] == 4 * 100 + 200 + 5 * 50

    # Tool messages persisted with role="tool"
    tool_msgs = (
        db.query(Message)
        .filter(Message.session_id == sess.id, Message.role == "tool")
        .order_by(Message.id)
        .all()
    )
    assert len(tool_msgs) == 2
    assert "Tokyo" in tool_msgs[0].content  # search result mentions Tokyo attractions
    assert "total" in tool_msgs[1].content


def test_planner_passes_tool_schemas_to_llm(db: Session, script_llm) -> None:
    """Each LLM call must include the registry's tool schemas so the model can pick."""
    sess = ChatSession(user_id="carol")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    script_llm.script = [{"content": "ok", "tool_calls": []}]
    PlannerAgent(db).plan(sess.id, goal="hi")

    assert len(script_llm.calls) == 1
    tools = script_llm.calls[0]["tools"]
    names = {t["function"]["name"] for t in tools}
    assert names == {"search_attractions", "calculate_budget", "generate_itinerary"}
    # Schemas must be well-formed: each parameters block is an object schema
    for t in tools:
        params = t["function"]["parameters"]
        assert params["type"] == "object"
        assert "properties" in params


def test_planner_stops_at_max_steps_to_avoid_infinite_loops(
    db: Session, script_llm
) -> None:
    """If the LLM keeps requesting tool calls forever, we bail at max_steps."""
    sess = ChatSession(user_id="dave")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    # Model keeps requesting search_attractions in a loop. Without a cap, this
    # would run forever; with a cap, we should return a partial result.
    script_llm.script = [
        {
            "content": "",
            "tool_calls": [{"name": "search_attractions", "arguments": {"city": "Osaka"}}],
        }
    ] * 50  # way more than max_steps

    agent = PlannerAgent(db, max_steps=3)
    result = agent.plan(sess.id, goal="loop forever")

    assert result["truncated"] is True
    assert len(result["tool_calls"]) <= 3


# ---------------------------------------------------------------------------
# HTTP endpoint test
# ---------------------------------------------------------------------------


async def test_plan_endpoint_dispatches_and_persists(
    client: httpx.AsyncClient, script_llm
) -> None:
    """POST /sessions/{id}/plan runs the agent and returns the structured result."""
    # Create a session via the API
    r = await client.post("/sessions", json={"user_id": "eve", "title": "japan"})
    sid = r.json()["id"]

    script_llm.script = [
        {
            "content": "",
            "tool_calls": [
                {"name": "search_attractions", "arguments": {"city": "Kyoto", "limit": 1}}
            ],
        },
        {"content": "Here is your plan.", "tool_calls": []},
    ]

    r = await client.post(f"/sessions/{sid}/plan", json={"goal": "Kyoto trip"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["final"] == "Here is your plan."
    assert len(body["tool_calls"]) == 1
    assert body["tool_calls"][0]["name"] == "search_attractions"

    # User goal + final assistant message visible on the session
    r = await client.get(f"/sessions/{sid}?user_id=eve")
    msgs = r.json()["messages"]
    contents = [m["content"] for m in msgs]
    assert "Kyoto trip" in contents
    assert any("Here is your plan." in c for c in contents)
