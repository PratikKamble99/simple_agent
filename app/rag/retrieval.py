"""Similarity search: the one place a question becomes ranked chunks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.rag import qdrant_store
from app.rag.embeddings import Embedder, get_embedder

logger = logging.getLogger(__name__)

# Tuning constants, deliberately not settings.
DEFAULT_TOP_K = 5
# Cosine search always returns its nearest k, however irrelevant. Without a
# floor an empty or unrelated corpus still yields "context", and the model
# will dutifully answer from noise.
MIN_SCORE = 0.3


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    text: str
    score: float
    document_id: str | None
    chunk_id: str

    @classmethod
    def from_hit(cls, hit: dict) -> RetrievedChunk:
        return cls(
            text=hit.get("text", ""),
            score=float(hit.get("score", 0.0)),
            document_id=hit.get("document_id"),
            chunk_id=str(hit.get("id", "")),
        )


async def retrieve(
    query: str,
    *,
    limit: int = DEFAULT_TOP_K,
    document_id: UUID | None = None,
    min_score: float = MIN_SCORE,
    embedder: Embedder | None = None,
) -> list[RetrievedChunk]:
    """Embed the query and return the chunks nearest to it, best first."""
    if not query.strip():
        return []

    embedder = embedder or get_embedder()
    vector = await embedder.aembed_query(query)

    hits = await qdrant_store.search(vector, limit=limit, document_id=document_id)
    chunks = [RetrievedChunk.from_hit(hit) for hit in hits]
    kept = [chunk for chunk in chunks if chunk.score >= min_score]

    logger.debug(
        "retrieved %d chunks, kept %d at or above score %.2f",
        len(chunks),
        len(kept),
        min_score,
    )
    return kept


def format_context(chunks: list[RetrievedChunk]) -> str:
    """Numbered blocks the generation prompt can cite by index."""
    return "\n\n".join(
        f"[{index}] {chunk.text}" for index, chunk in enumerate(chunks, start=1)
    )
