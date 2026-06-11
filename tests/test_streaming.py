"""Tests for streaming responses (T6)."""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy.orm import Session

from app.agents.planner import PlannerAgent
from app.models import ChatSession, Message


@pytest.fixture
def stream_llm(monkeypatch: pytest.MonkeyPatch):
    """Fake llm_chat_stream that yields a scripted list of chunks then a final tool/content turn."""
    from app.agents import planner as planner_module

    class StreamScripted:
        def __init__(self) -> None:
            # Each entry is a dict {"chunks": [str, ...], "tool_calls": [...]}
            self.script: list[dict] = []
            self.calls: list[dict] = []

        def chat_stream(self, *, messages, tools, **_):
            self.calls.append({"messages": list(messages), "tools": tools})
            if not self.script:
                # Yield a default single chunk
                yield {"delta": "DONE", "done": False}
                yield {"delta": "", "done": True, "tool_calls": []}
                return
            entry = self.script.pop(0)
            for chunk in entry.get("chunks", []):
                yield {"delta": chunk, "done": False}
            yield {
                "delta": "",
                "done": True,
                "tool_calls": entry.get("tool_calls", []),
            }

    s = StreamScripted()
    monkeypatch.setattr(planner_module, "llm_chat_stream", s.chat_stream)
    return s


# ---------------------------------------------------------------------------
# Direct PlannerAgent.plan_stream tests
# ---------------------------------------------------------------------------


def test_plan_stream_yields_token_chunks(db: Session, stream_llm) -> None:
    """plan_stream emits incremental token deltas and a final 'done' event."""
    sess = ChatSession(user_id="alice")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    stream_llm.script = [
        {
            "chunks": ["Here", " is", " your", " plan."],
            "tool_calls": [],
        }
    ]

    events = list(PlannerAgent(db).plan_stream(sess.id, goal="hi"))
    # token events
    token_events = [e for e in events if e["type"] == "token"]
    assert [e["delta"] for e in token_events] == ["Here", " is", " your", " plan."]
    # exactly one done event
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    assert done_events[0]["final"] == "Here is your plan."


def test_plan_stream_persists_full_assistant_message_after_completion(
    db: Session, stream_llm
) -> None:
    """The concatenated streamed text must be persisted as one assistant message."""
    sess = ChatSession(user_id="bob")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    stream_llm.script = [
        {"chunks": ["hello ", "world"], "tool_calls": []},
    ]
    list(PlannerAgent(db).plan_stream(sess.id, goal="hi"))

    msgs = (
        db.query(Message)
        .filter(Message.session_id == sess.id, Message.role == "assistant")
        .all()
    )
    assert len(msgs) == 1
    assert msgs[0].content == "hello world"


def test_plan_stream_emits_tool_events_when_llm_calls_tools(
    db: Session, stream_llm
) -> None:
    """Streaming planner still dispatches tools and emits tool_call/tool_result events."""
    sess = ChatSession(user_id="carol")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    stream_llm.script = [
        {
            "chunks": [],
            "tool_calls": [
                {"name": "search_attractions", "arguments": {"city": "Tokyo", "limit": 1}}
            ],
        },
        {"chunks": ["all ", "set"], "tool_calls": []},
    ]
    events = list(PlannerAgent(db).plan_stream(sess.id, goal="plan"))
    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    # final text from the second turn arrives as token deltas
    deltas = [e["delta"] for e in events if e["type"] == "token"]
    assert "".join(deltas) == "all set"


# ---------------------------------------------------------------------------
# HTTP SSE endpoint
# ---------------------------------------------------------------------------


async def test_plan_stream_endpoint_returns_sse_event_stream(
    client: httpx.AsyncClient, stream_llm
) -> None:
    """POST /sessions/{id}/plan/stream returns SSE chunks the browser can consume."""
    r = await client.post("/sessions", json={"user_id": "eve"})
    sid = r.json()["id"]

    stream_llm.script = [
        {"chunks": ["Plan: ", "go to ", "Kyoto"], "tool_calls": []},
    ]

    async with client.stream(
        "POST",
        f"/sessions/{sid}/plan/stream",
        json={"goal": "Kyoto trip"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = ""
        async for chunk in response.aiter_text():
            body += chunk

    # SSE format: lines like `data: {...}\n\n`
    payload_lines = [
        line.removeprefix("data: ")
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    assert payload_lines, f"no SSE data lines in body: {body!r}"
    events = [json.loads(p) for p in payload_lines]
    deltas = [e["delta"] for e in events if e["type"] == "token"]
    assert "".join(deltas) == "Plan: go to Kyoto"
    assert any(e["type"] == "done" for e in events)


def test_plan_stream_emits_plan_event_instead_of_raw_json(
    db: Session, stream_llm
) -> None:
    """When the first turn is a JSON plan, stream a 'plan' event with the parsed
    sub-tasks — NOT raw JSON token deltas. Otherwise the user sees ugly
    {"plan": [...]} text in the chat."""
    sess = ChatSession(user_id="eve")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    plan_json = '{"plan": ["Find attractions", "Estimate cost", "Build itinerary"]}'
    stream_llm.script = [
        {"chunks": [plan_json], "tool_calls": []},
        {"chunks": ["Final answer."], "tool_calls": []},
    ]

    events = list(PlannerAgent(db).plan_stream(sess.id, goal="hi"))
    types = [e["type"] for e in events]

    # No token event should leak the raw JSON to the user
    token_text = "".join(e["delta"] for e in events if e["type"] == "token")
    assert '{"plan"' not in token_text, f"raw JSON leaked into tokens: {token_text!r}"

    # A 'plan' event with the parsed list should be emitted instead
    plan_events = [e for e in events if e["type"] == "plan"]
    assert len(plan_events) == 1
    assert plan_events[0]["subtasks"] == [
        "Find attractions",
        "Estimate cost",
        "Build itinerary",
    ]
    # Final answer still streams as token deltas
    assert "Final answer." in token_text
    assert "done" in types
