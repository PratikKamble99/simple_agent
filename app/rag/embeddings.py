"""OpenAI embeddings via LangChain."""

from __future__ import annotations

from typing import Protocol

from langchain_openai import OpenAIEmbeddings

from app.core.config import get_settings

# Vector width per model. Looked up rather than hardcoded to a single number:
# the model is configurable, and Qdrant only rejects a mismatched width at
# insert time - long after the collection was created with the wrong size.
EMBEDDING_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class Embedder(Protocol):
    """The slice of the embeddings client this app actually uses.

    Declared as a Protocol so tests can substitute a deterministic stub and
    never call the real API.
    """

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def aembed_query(self, text: str) -> list[float]: ...


def embedding_dim(model: str | None = None) -> int:
    """Vector width for the configured model."""
    model = model or get_settings().OPENAI_EMBEDDING_MODEL
    try:
        return EMBEDDING_DIMS[model]
    except KeyError:
        raise ValueError(
            f"Unknown embedding model {model!r}. Add it to EMBEDDING_DIMS with its "
            f"vector width. Known: {', '.join(sorted(EMBEDDING_DIMS))}"
        ) from None


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """The process-wide embeddings client, created on first use."""
    global _embedder
    if _embedder is None:
        settings = get_settings()
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set; cannot embed documents")
        # Validates the model name before any network call.
        embedding_dim(settings.OPENAI_EMBEDDING_MODEL)
        _embedder = OpenAIEmbeddings(
            model=settings.OPENAI_EMBEDDING_MODEL,
            api_key=settings.OPENAI_API_KEY,
        )
    return _embedder


def reset_embedder() -> None:
    """Drop the cached client. Used by tests."""
    global _embedder
    _embedder = None
