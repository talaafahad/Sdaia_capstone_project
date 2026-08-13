"""Shared test configuration.

The suite runs OFFLINE by default: live Tavily search and OpenRouter embeddings
are disabled so results are deterministic and fast whether or not real API keys
are present in .env. Tests that specifically exercise the live path opt back in
by monkeypatching these away, and skip themselves when no key is configured.
"""

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _offline_by_default():
    os.environ.setdefault("DISABLE_LIVE_SEARCH", "1")
    os.environ.setdefault("DISABLE_DENSE_SEARCH", "1")
    yield


@pytest.fixture
def live_search_enabled(monkeypatch):
    """Opt in to real network calls for a single test."""
    from app.config.settings import settings

    if not (settings.tavily_api_key or "").strip() or "xxxx" in (
        settings.tavily_api_key or ""
    ).lower():
        pytest.skip("no real TAVILY_API_KEY configured")
    monkeypatch.delenv("DISABLE_LIVE_SEARCH", raising=False)
    yield
