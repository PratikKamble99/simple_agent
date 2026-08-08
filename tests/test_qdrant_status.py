"""Health reporting for the vector store.

These need neither a database nor credentials.
"""

import pytest
from qdrant_client import AsyncQdrantClient

from app.core.config import get_settings
from app.rag import qdrant_store

URL = "https://cluster.example.cloud.qdrant.io"


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """`get_settings` is lru_cached, so monkeypatched env must invalidate it."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_api_key_problem_flags_a_url_pasted_as_the_key(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_URL", URL)
    monkeypatch.setenv("QDRANT_API_KEY", URL)

    assert "looks like a URL" in (qdrant_store.api_key_problem() or "")


def test_api_key_problem_flags_a_missing_key(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_URL", URL)
    monkeypatch.setenv("QDRANT_API_KEY", "")

    assert "not set" in (qdrant_store.api_key_problem() or "")


def test_api_key_problem_accepts_a_plausible_key(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_URL", URL)
    monkeypatch.setenv("QDRANT_API_KEY", "abc123-not-a-url")

    assert qdrant_store.api_key_problem() is None


async def test_status_names_the_misconfiguration_without_a_request(monkeypatch) -> None:
    """A key that cannot work should be reported without a network round-trip."""
    monkeypatch.setenv("QDRANT_URL", URL)
    monkeypatch.setenv("QDRANT_API_KEY", URL)
    qdrant_store.set_client(None)

    result = await qdrant_store.status()

    assert result.startswith("misconfigured:")
    assert "looks like a URL" in result


async def test_status_reports_not_configured_without_a_url(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("QDRANT_API_KEY", "")

    assert await qdrant_store.status() == "not configured"


async def test_status_is_ok_against_a_reachable_cluster(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_URL", URL)
    monkeypatch.setenv("QDRANT_API_KEY", "abc123-not-a-url")
    qdrant_store.set_client(AsyncQdrantClient(":memory:"))

    assert await qdrant_store.status() == "ok"
