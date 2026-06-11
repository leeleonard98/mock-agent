"""Tests for chat sessions and message history (T1)."""

from __future__ import annotations

import httpx


async def test_create_session_and_post_message(client: httpx.AsyncClient) -> None:
    """Happy path: create session, post a user message, fetch history."""
    # Create session
    r = await client.post("/sessions", json={"user_id": "alice", "title": "Japan trip"})
    assert r.status_code == 201, r.text
    session = r.json()
    session_id = session["id"]
    assert session["user_id"] == "alice"
    assert session["title"] == "Japan trip"

    # Post a user message
    r = await client.post(
        f"/sessions/{session_id}/messages",
        json={"role": "user", "content": "Plan me a 5-day Japan trip under $2000"},
    )
    assert r.status_code == 201, r.text
    msg = r.json()
    assert msg["role"] == "user"
    assert msg["content"] == "Plan me a 5-day Japan trip under $2000"
    assert msg["session_id"] == session_id

    # Fetch the session with messages
    r = await client.get(f"/sessions/{session_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == session_id
    assert len(body["messages"]) == 1
    assert body["messages"][0]["content"] == "Plan me a 5-day Japan trip under $2000"


async def test_messages_returned_in_creation_order(client: httpx.AsyncClient) -> None:
    """History must preserve order across multiple posts (regression-prone behaviour)."""
    r = await client.post("/sessions", json={"user_id": "bob"})
    session_id = r.json()["id"]

    contents = ["first", "second", "third", "fourth"]
    for c in contents:
        r = await client.post(
            f"/sessions/{session_id}/messages",
            json={"role": "user", "content": c},
        )
        assert r.status_code == 201

    r = await client.get(f"/sessions/{session_id}")
    assert r.status_code == 200
    returned = [m["content"] for m in r.json()["messages"]]
    assert returned == contents, f"order not preserved: {returned}"


async def test_get_missing_session_returns_404(client: httpx.AsyncClient) -> None:
    """A session id that doesn't exist must 404, not 500 or empty 200."""
    r = await client.get("/sessions/99999")
    assert r.status_code == 404
    body = r.json()
    assert "detail" in body

    # Posting to a missing session is also a 404
    r = await client.post(
        "/sessions/99999/messages",
        json={"role": "user", "content": "hi"},
    )
    assert r.status_code == 404


async def test_chat_index_page_renders(client: httpx.AsyncClient) -> None:
    """The minimal Jinja chat UI must render at /, including the session sidebar."""
    r = await client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "Smart Travel Planner" in body
    assert "<form id=\"composer\">" in body
    # Session sidebar elements (T1 polish)
    assert 'id="sessions-list"' in body
    assert 'id="new-chat"' in body


async def test_user_id_scoping_prevents_cross_user_reads(client: httpx.AsyncClient) -> None:
    """When user_id is supplied, you can only see your own session (404 otherwise)."""
    r = await client.post("/sessions", json={"user_id": "alice"})
    alice_session = r.json()["id"]

    # Bob asks for Alice's session; must 404
    r = await client.get(f"/sessions/{alice_session}?user_id=bob")
    assert r.status_code == 404

    # Alice can see her own
    r = await client.get(f"/sessions/{alice_session}?user_id=alice")
    assert r.status_code == 200
    assert r.json()["user_id"] == "alice"

    # Bob can't post to Alice's session either
    r = await client.post(
        f"/sessions/{alice_session}/messages?user_id=bob",
        json={"role": "user", "content": "hi"},
    )
    assert r.status_code == 404


async def test_list_sessions_requires_user_id_and_filters(client: httpx.AsyncClient) -> None:
    """GET /sessions must require user_id (no global dump) and only return that user's."""
    await client.post("/sessions", json={"user_id": "alice", "title": "a1"})
    await client.post("/sessions", json={"user_id": "alice", "title": "a2"})
    await client.post("/sessions", json={"user_id": "bob", "title": "b1"})

    # Missing user_id → 422 (FastAPI validation)
    r = await client.get("/sessions")
    assert r.status_code == 422

    # alice sees only her two
    r = await client.get("/sessions?user_id=alice")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert {row["title"] for row in rows} == {"a1", "a2"}
    assert all(row["user_id"] == "alice" for row in rows)


async def test_message_validation_rejects_empty_and_unknown_role(
    client: httpx.AsyncClient,
) -> None:
    """Empty content and unknown role must return 422 (pydantic validation)."""
    r = await client.post("/sessions", json={"user_id": "alice"})
    sid = r.json()["id"]

    r = await client.post(
        f"/sessions/{sid}/messages",
        json={"role": "user", "content": ""},
    )
    assert r.status_code == 422

    r = await client.post(
        f"/sessions/{sid}/messages",
        json={"role": "stranger", "content": "hi"},
    )
    assert r.status_code == 422
