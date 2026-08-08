"""Retrieval-augmented generation: embeddings, chunk storage, retrieval, agent.

Public surface, so callers import from `app.rag` rather than reaching into
submodules.
"""

from app.rag.agent import answer_question, build_graph
from app.rag.ingestion import EmptyDocument, UnsupportedDocument, ingest
from app.rag.qdrant_store import status
from app.rag.retrieval import RetrievedChunk, retrieve

__all__ = [
    "EmptyDocument",
    "RetrievedChunk",
    "UnsupportedDocument",
    "answer_question",
    "build_graph",
    "ingest",
    "retrieve",
    "status",
]
