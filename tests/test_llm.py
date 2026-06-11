"""Tests for the LLM mock seam and the real wrapper's no-key path."""

from __future__ import annotations

import importlib

import pytest

import app.llm as llm_module
from tests.conftest import MockLLM


def test_mock_llm_returns_configured_value(mock_llm: MockLLM) -> None:
    mock_llm.return_value = "hello"
    result = llm_module.complete("anything")
    assert result == "hello"


def test_mock_llm_records_calls_with_args(mock_llm: MockLLM) -> None:
    llm_module.complete("p1", system="sys")
    llm_module.complete("p2")
    assert mock_llm.calls == [
        {"prompt": "p1", "model": None, "system": "sys"},
        {"prompt": "p2", "model": None, "system": None},
    ]


def test_complete_without_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Deliberately do NOT use the mock_llm fixture: we want the real wrapper.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # The Settings instance and the OpenAI client are both lru_cached; clear
    # both so the no-key check actually fires.
    from app.config import get_settings

    get_settings.cache_clear()

    # Reload app.llm so its module-level imports pick up the fresh settings,
    # then clear its _client cache too.
    fresh_llm = importlib.reload(llm_module)
    fresh_llm._client.cache_clear()

    try:
        with pytest.raises(fresh_llm.LLMNotConfiguredError):
            fresh_llm.complete("hi")
    finally:
        # Reset caches so later tests in the session aren't affected.
        fresh_llm._client.cache_clear()
        get_settings.cache_clear()
