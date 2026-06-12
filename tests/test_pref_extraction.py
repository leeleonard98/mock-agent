"""Tests for auto-extracted preference memory (T4+).

The planner inspects the user's goal at the end of a run and asks the LLM
to extract structured preferences (activities, budget, diet, ...) which
are then upserted into UserPreference rows. The next session for the same
user benefits without the user having to PUT preferences manually.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.orm import Session

from app.agents.planner import PlannerAgent
from app.memory import load_preferences
from app.models import ChatSession, UserPreference


@pytest.fixture
def extract_seam(monkeypatch: pytest.MonkeyPatch):
    """Replace the LLM-backed extract_preferences function with a deterministic stub."""
    from app.agents import planner as planner_module

    captured: dict[str, list] = {"goals": []}

    def fake_extract(goal: str) -> dict:
        captured["goals"].append(goal)
        # Echo back a structured shape based on substrings — deterministic.
        out: dict = {}
        if "hiking" in goal.lower():
            out["activities"] = ["hiking", "nature"]
        if "vegetarian" in goal.lower():
            out["diet"] = "vegetarian"
        if "$" in goal:
            # crude: take the first $-prefixed integer
            import re
            m = re.search(r"\$(\d+)", goal)
            if m:
                out["budget"] = int(m.group(1))
        return out

    monkeypatch.setattr(planner_module, "extract_preferences", fake_extract)
    return captured


def test_planning_run_extracts_and_upserts_preferences(
    db: Session, script_llm, extract_seam
) -> None:
    """After plan() finishes, preferences mentioned in the goal are persisted."""
    sess = ChatSession(user_id="alice")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    script_llm.script = [{"content": "ok", "tool_calls": []}]
    PlannerAgent(db).plan(
        sess.id,
        goal="I'm vegetarian and love hiking. Plan me Paris under $1500.",
    )

    # Extract was called with the goal
    assert extract_seam["goals"][-1].startswith("I'm vegetarian")

    # Preferences are now in the DB
    prefs = load_preferences(db, "alice")
    assert prefs["activities"] == ["hiking", "nature"]
    assert prefs["diet"] == "vegetarian"
    assert prefs["budget"] == 1500


def test_extracted_prefs_visible_to_next_session(
    db: Session, script_llm, extract_seam
) -> None:
    """A second planning run for the same user sees the previously extracted prefs."""
    # Run 1: extract from chat
    s1 = ChatSession(user_id="bob")
    db.add(s1)
    db.commit()
    db.refresh(s1)
    script_llm.script = [{"content": "ok", "tool_calls": []}]
    PlannerAgent(db).plan(s1.id, goal="I love hiking. Plan Tokyo.")

    # Run 2: NEW session for bob; new script entry
    s2 = ChatSession(user_id="bob")
    db.add(s2)
    db.commit()
    db.refresh(s2)
    script_llm.script = [{"content": "ok", "tool_calls": []}]
    PlannerAgent(db).plan(s2.id, goal="Plan Kyoto.")

    # The system prompt for run 2 must include the prefs from run 1
    sys_msg_run2 = script_llm.calls[1]["messages"][0]
    assert "hiking" in sys_msg_run2["content"]


def test_extraction_upsert_does_not_clobber_other_keys(
    db: Session, script_llm, extract_seam
) -> None:
    """Pre-existing prefs that the new goal doesn't mention must survive."""
    db.add(UserPreference(user_id="carol", key="diet", value="kosher"))
    db.commit()

    sess = ChatSession(user_id="carol")
    db.add(sess)
    db.commit()
    db.refresh(sess)
    script_llm.script = [{"content": "ok", "tool_calls": []}]
    PlannerAgent(db).plan(sess.id, goal="I love hiking. Plan something.")

    prefs = load_preferences(db, "carol")
    assert prefs["diet"] == "kosher"  # not overwritten — goal didn't mention diet
    assert prefs["activities"] == ["hiking", "nature"]


async def test_chat_index_renders_preferences_panel(client: httpx.AsyncClient) -> None:
    """The chat UI exposes a preferences panel so the user can see what the agent remembers."""
    r = await client.get("/")
    assert r.status_code == 200
    body = r.text
    assert 'id="prefs-panel"' in body
    # Loads from /users/{id}/preferences on init / user-id change
    assert "/preferences" in body
