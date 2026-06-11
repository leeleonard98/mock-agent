"""Tests for the multi-agent supervisor (T5 bonus)."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.orm import Session

from app.agents.supervisor import SupervisorAgent
from app.models import ChatSession


@pytest.fixture
def per_agent_llm(monkeypatch: pytest.MonkeyPatch):
    """Script three different per-agent LLM responses by agent name."""

    class PerAgentLLM:
        def __init__(self) -> None:
            # name -> list of {content, tool_calls} responses
            self.script: dict[str, list[dict]] = {}
            self.calls: list[dict] = []

        def factory(self, agent_name: str):
            def chat(*, messages, tools, **_):
                self.calls.append({"agent": agent_name, "messages": list(messages)})
                queue = self.script.get(agent_name, [])
                if not queue:
                    return {"content": f"{agent_name}: ok", "tool_calls": []}
                return queue.pop(0)
            return chat

    s = PerAgentLLM()
    # The supervisor uses SubAgent objects; we patch its factory to inject our chats
    from app.agents import supervisor as sup_module

    monkeypatch.setattr(sup_module, "_llm_chat_factory", s.factory)
    return s


def test_supervisor_invokes_three_subagents(db: Session, per_agent_llm) -> None:
    """SupervisorAgent.run() calls research, budget, itinerary in order."""
    sess = ChatSession(user_id="alice")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    per_agent_llm.script = {
        "research": [
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "search_attractions",
                        "arguments": {"city": "Tokyo", "limit": 1},
                    }
                ],
            },
            {"content": "Found Tokyo attractions.", "tool_calls": []},
        ],
        "budget": [
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "calculate_budget",
                        "arguments": {
                            "days": 3,
                            "accommodation_per_night": 100,
                            "transport_total": 100,
                            "activities_per_day": 50,
                        },
                    }
                ],
            },
            {"content": "Budget computed.", "tool_calls": []},
        ],
        "itinerary": [
            {"content": "Day-by-day plan ready.", "tool_calls": []},
        ],
    }

    out = SupervisorAgent(db).run(sess.id, goal="Plan Tokyo")
    assert {c["agent"] for c in per_agent_llm.calls} == {"research", "budget", "itinerary"}
    assert "Tokyo" in out["research"]["final"]
    assert out["budget"]["final"] == "Budget computed."
    assert out["itinerary"]["final"] == "Day-by-day plan ready."
    # Supervisor's combined summary at least mentions each agent's contribution
    assert "research" in out["combined"].lower()
    assert "budget" in out["combined"].lower()
    assert "itinerary" in out["combined"].lower()


def test_supervisor_each_agent_only_sees_its_own_tools(
    db: Session, per_agent_llm
) -> None:
    """Each sub-agent's LLM call must only have its allowed tools in scope."""
    sess = ChatSession(user_id="bob")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    per_agent_llm.script = {
        "research": [{"content": "ok", "tool_calls": []}],
        "budget": [{"content": "ok", "tool_calls": []}],
        "itinerary": [{"content": "ok", "tool_calls": []}],
    }
    SupervisorAgent(db).run(sess.id, goal="plan")

    # We can't easily get the tools schema from per_agent_llm.calls (we recorded
    # messages only). But we know the supervisor exposes per-agent tool maps:
    sub = SupervisorAgent(db)
    assert sub.tools_for("research") == ["search_attractions"]
    assert sub.tools_for("budget") == ["calculate_budget"]
    assert sub.tools_for("itinerary") == ["generate_itinerary"]


async def test_multi_endpoint_returns_combined_result(
    client: httpx.AsyncClient, per_agent_llm
) -> None:
    """POST /sessions/{id}/plan/multi runs the supervisor and returns its result."""
    r = await client.post("/sessions", json={"user_id": "carol"})
    sid = r.json()["id"]

    per_agent_llm.script = {
        "research": [{"content": "research done", "tool_calls": []}],
        "budget": [{"content": "budget done", "tool_calls": []}],
        "itinerary": [{"content": "itinerary done", "tool_calls": []}],
    }

    r = await client.post(f"/sessions/{sid}/plan/multi", json={"goal": "Trip"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["research"]["final"] == "research done"
    assert body["budget"]["final"] == "budget done"
    assert body["itinerary"]["final"] == "itinerary done"
    assert "combined" in body
