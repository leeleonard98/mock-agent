"""Tests for the /health endpoint."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app as fastapi_app


async def test_health_returns_200_and_ok_status(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


async def test_health_reports_db_ok_when_db_up(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["db"] == "ok"


async def test_health_reports_db_down_when_db_unavailable(
    client: httpx.AsyncClient,
) -> None:
    class _BrokenSession:
        def execute(self, *_args: object, **_kwargs: object) -> None:
            raise SQLAlchemyError("simulated db outage")

        def close(self) -> None:
            return None

    def _override_broken_db() -> Iterator[_BrokenSession]:
        session = _BrokenSession()
        try:
            yield session
        finally:
            session.close()

    # Replace the override the `client` fixture installed with one that yields
    # a session whose execute() always raises.
    fastapi_app.dependency_overrides[get_db] = _override_broken_db
    try:
        response = await client.get("/health")
    finally:
        # The client fixture clears overrides on teardown, but we restore the
        # transactional override so any later assertions in this test would
        # still work. Not strictly needed here.
        pass

    assert response.status_code == 200
    body = response.json()
    assert body["db"] == "down"
    assert body["status"] == "ok"
    # Silence unused-import lint for Session (kept for type clarity above).
    _ = Session
