"""Shared pytest fixtures for the test suite.

Provides a transactional DB fixture, an httpx AsyncClient bound to the FastAPI app,
and a mock_llm fixture that replaces app.llm.complete so tests never hit the network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.llm as llm_module
from app.config import get_settings
from app.db import get_db
from app.main import app as fastapi_app
from app.models import Base


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """Session-scoped engine pointing at TEST_DATABASE_URL.

    Creates the schema on entry and drops it on teardown. Tests run against a
    clean schema; we deliberately do not run alembic in tests.
    """
    settings = get_settings()
    engine = create_engine(settings.TEST_DATABASE_URL, pool_pre_ping=True, future=True)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def db(test_engine: Engine) -> Iterator[Session]:
    """Function-scoped transactional session.

    Opens a connection, begins an outer transaction, binds a Session to the
    connection, yields it, then rolls back so each test sees a clean DB.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    TestingSessionLocal = sessionmaker(
        bind=connection, autocommit=False, autoflush=False, future=True
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest_asyncio.fixture
async def client(db: Session) -> AsyncIterator[httpx.AsyncClient]:
    """httpx.AsyncClient wired to the FastAPI app via ASGITransport.

    Overrides get_db so requests use the per-test transactional session, and
    clears the override on teardown.
    """

    def _override_get_db() -> Iterator[Session]:
        yield db

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=fastapi_app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        fastapi_app.dependency_overrides.clear()


class MockLLM:
    """Records calls to complete() and returns a configurable string.

    Attributes:
        calls: list of dicts with keys {"prompt", "model", "system"} in call order.
        return_value: the string returned by complete(). Defaults to a deterministic
            "MOCK: <prompt>" (truncated to 200 chars) when left as None.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.return_value: str | None = None

    def __call__(
        self, prompt: str, *, model: str | None = None, system: str | None = None
    ) -> str:
        self.calls.append({"prompt": prompt, "model": model, "system": system})
        if self.return_value is not None:
            return self.return_value
        return f"MOCK: {prompt}"[:200]


@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[MockLLM]:
    """Monkeypatch app.llm.complete with a recording stub.

    Yields a MockLLM instance; tests can inspect `.calls` or set `.return_value`.
    """
    mock = MockLLM()
    monkeypatch.setattr(llm_module, "complete", mock)
    yield mock


class ScriptedLLM:
    """Drives a fake multi-turn LLM for the planner tests.

    Each `script` entry is either ``{"content": str, "tool_calls": []}`` for a
    final-answer turn or ``{"content": "", "tool_calls": [{"name", "arguments"}]}``
    for a tool-calling turn. The planner pops one entry per turn.
    """

    def __init__(self) -> None:
        self.script: list[dict] = []
        self.calls: list[dict] = []

    def chat(self, *, messages, tools, **_):
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self.script:
            return {"content": "DONE", "tool_calls": []}
        return self.script.pop(0)


@pytest.fixture
def script_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[ScriptedLLM]:
    """Monkeypatch the planner's llm_chat seam with a scripted multi-turn fake."""
    from app.agents import planner as planner_module

    s = ScriptedLLM()
    monkeypatch.setattr(planner_module, "llm_chat", s.chat)
    yield s


@pytest.fixture(autouse=True)
def _silence_extract_preferences(monkeypatch: pytest.MonkeyPatch):
    """Default: replace extract_preferences with a no-op so tests never hit OpenAI.

    Tests that want to exercise the extraction wiring (test_pref_extraction.py)
    can replace it with a real stub via their own monkeypatch.
    """
    from app.agents import planner as planner_module

    monkeypatch.setattr(planner_module, "extract_preferences", lambda _goal: {})
