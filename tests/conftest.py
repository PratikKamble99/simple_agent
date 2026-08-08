from collections.abc import AsyncGenerator, Iterator

import pytest
from fastapi.testclient import TestClient
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401 - registers every model on Base.metadata
from app.api.v1.documents import embedder_dependency
from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.rag import qdrant_store
from app.rag.embeddings import embedding_dim


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture(autouse=True)
def qdrant_memory() -> Iterator[AsyncQdrantClient]:
    """Point every test at an in-memory Qdrant.

    Autouse on purpose: QDRANT_URL defaults to a live Qdrant Cloud host, so
    without this a plain /health call in any test would reach the network.
    """
    client = AsyncQdrantClient(":memory:")
    qdrant_store.set_client(client)
    try:
        yield client
    finally:
        qdrant_store.set_client(None)


class FakeEmbedder:
    """Deterministic stand-in for OpenAI embeddings.

    Vectors are derived from the text so that identical text embeds
    identically and a query matches its own chunk, without any API call.
    """

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim or embedding_dim()
        self.calls: list[list[str]] = []

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for index, char in enumerate(text[:512]):
            vector[(ord(char) + index) % self.dim] += 1.0
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / norm for value in vector]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [self._vector(text) for text in texts]

    async def aembed_query(self, text: str) -> list[float]:
        return self._vector(text)


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


class UnavailableSession:
    """Stands in for a session when no database is configured.

    Without this the plain `client` fixture opens a real socket on every
    `/health` call and waits out the connect timeout.
    """

    async def execute(self, *args: object, **kwargs: object) -> object:
        raise ConnectionError("no database is configured for this fixture")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """App with no database. `/health` reports it as unreachable."""
    app = create_app(settings=settings)

    async def override_get_db() -> AsyncGenerator[UnavailableSession]:
        yield UnavailableSession()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def api_prefix(settings: Settings) -> str:
    return settings.api_v1_prefix


# --- database fixtures -------------------------------------------------
# These need a real Postgres. Everything below skips unless
# TEST_DATABASE_URL is set, so the rest of the suite runs without one.


@pytest.fixture
def test_database_url(settings: Settings) -> str:
    if not settings.TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    return settings.TEST_DATABASE_URL


@pytest.fixture
async def db_engine(test_database_url: str) -> AsyncGenerator[object]:
    """A schema built from the models, torn down afterwards.

    Built with `create_all` rather than by running migrations, so a broken
    migration fails the `alembic upgrade` check rather than every test at once.
    NullPool keeps no connections open between tests.
    """
    engine = create_async_engine(test_database_url, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def db_client(
    settings: Settings, db_session: AsyncSession, fake_embedder: FakeEmbedder
) -> Iterator[TestClient]:
    """Client sharing the test's session, an in-memory Qdrant and a fake embedder."""
    app = create_app(settings=settings)

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[embedder_dependency] = lambda: fake_embedder
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
