"""The only module that talks to Qdrant.

Each chunk is one point: a vector plus a deliberately minimal payload.

    {"id": "<uuid>", "vector": [...], "payload": {"document_id": "...", "text": "..."}}

No document metadata is duplicated here beyond the id needed for filtering.
Titles, filenames and status live in Postgres and are joined on `document_id`.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import get_settings
from app.rag.embeddings import embedding_dim

logger = logging.getLogger(__name__)

DOCUMENT_ID_FIELD = "document_id"
TEXT_FIELD = "text"

# Health never blocks a request for long on an unreachable cluster.
REQUEST_TIMEOUT_SECONDS = 5

_client: AsyncQdrantClient | None = None


def api_key_problem() -> str | None:
    """Describe an obviously wrong API key, or None if it looks plausible.

    Pasting the cluster URL into QDRANT_API_KEY produces a bare 403 that looks
    identical to a revoked key, so it is worth naming explicitly.
    """
    settings = get_settings()
    key = settings.QDRANT_API_KEY

    if not key:
        return "QDRANT_API_KEY is not set"
    if key.startswith(("http://", "https://")):
        return "QDRANT_API_KEY looks like a URL, not a key"
    if key == settings.QDRANT_URL:
        return "QDRANT_API_KEY is the same value as QDRANT_URL"
    return None


def get_client() -> AsyncQdrantClient:
    """The process-wide Qdrant client, created on first use."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.QDRANT_URL:
            raise RuntimeError("QDRANT_URL is not set; cannot store chunks")

        problem = api_key_problem()
        if problem:
            logger.warning("qdrant auth will fail: %s", problem)

        _client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    return _client


def set_client(client: AsyncQdrantClient | None) -> None:
    """Swap the client. Used by tests to inject an in-memory instance."""
    global _client
    _client = client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def ensure_collection() -> None:
    """Create the collection and its payload index if they don't exist."""
    client = get_client()
    collection = get_settings().QDRANT_COLLECTION

    if await client.collection_exists(collection):
        return

    await client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(
            size=embedding_dim(),
            distance=models.Distance.COSINE,
        ),
    )
    # Without this index, filtering by document_id degrades to a full scan
    # once the collection grows.
    await client.create_payload_index(
        collection_name=collection,
        field_name=DOCUMENT_ID_FIELD,
        field_schema=models.PayloadSchemaType.KEYWORD,
    )
    logger.info("created qdrant collection %s", collection)


def _document_filter(document_id: UUID) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key=DOCUMENT_ID_FIELD,
                match=models.MatchValue(value=str(document_id)),
            )
        ]
    )


async def upsert_chunks(
    document_id: UUID,
    texts: list[str],
    vectors: list[list[float]],
) -> int:
    """Store one point per chunk. Returns how many were written."""
    if len(texts) != len(vectors):
        raise ValueError(f"got {len(texts)} chunks but {len(vectors)} vectors")
    if not texts:
        return 0

    await ensure_collection()

    points = [
        models.PointStruct(
            id=str(uuid4()),
            vector=vector,
            payload={DOCUMENT_ID_FIELD: str(document_id), TEXT_FIELD: chunk},
        )
        for chunk, vector in zip(texts, vectors, strict=True)
    ]

    await get_client().upsert(
        collection_name=get_settings().QDRANT_COLLECTION,
        points=points,
        wait=True,
    )
    return len(points)


async def delete_by_document(document_id: UUID) -> None:
    """Remove every chunk belonging to a document."""
    client = get_client()
    collection = get_settings().QDRANT_COLLECTION

    if not await client.collection_exists(collection):
        return

    await client.delete(
        collection_name=collection,
        points_selector=_document_filter(document_id),
        wait=True,
    )


async def search(
    vector: list[float],
    limit: int = 5,
    document_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Nearest chunks, optionally restricted to one document."""
    client = get_client()
    collection = get_settings().QDRANT_COLLECTION

    if not await client.collection_exists(collection):
        return []

    response = await client.query_points(
        collection_name=collection,
        query=vector,
        limit=limit,
        query_filter=_document_filter(document_id) if document_id else None,
        with_payload=True,
    )

    return [
        {
            "id": str(point.id),
            "score": point.score,
            "document_id": (point.payload or {}).get(DOCUMENT_ID_FIELD),
            "text": (point.payload or {}).get(TEXT_FIELD, ""),
        }
        for point in response.points
    ]


async def status() -> str:
    """Vector-store state for the health probe, naming the cause of failure.

    Logged at WARNING without a traceback: a misconfigured cluster is a known
    condition, and a stack trace on every liveness check buries real errors.
    """
    if not get_settings().QDRANT_URL:
        return "not configured"

    problem = api_key_problem()
    if problem:
        return f"misconfigured: {problem}"

    try:
        await get_client().get_collections()
    except UnexpectedResponse as exc:
        if exc.status_code in (401, 403):
            logger.warning("qdrant rejected our credentials (%s)", exc.status_code)
            return "forbidden: check QDRANT_API_KEY"
        logger.warning("qdrant returned %s", exc.status_code)
        return f"error: HTTP {exc.status_code}"
    except Exception as exc:
        logger.warning("qdrant unreachable: %s", exc)
        return "unreachable"

    return "ok"
