"""Document ingestion: extract text, chunk it, embed it, store the vectors.

Orchestration only - the OpenAI and Qdrant clients live in their own modules.
"""

from __future__ import annotations

import io
import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.rag import qdrant_store
from app.rag.embeddings import Embedder, get_embedder

logger = logging.getLogger(__name__)

# Tuning constants, deliberately not settings.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

PDF_TYPES = {"application/pdf"}
TEXT_TYPES = {"text/plain", "text/markdown", "text/x-markdown", "application/octet-stream"}
TEXT_SUFFIXES = (".txt", ".md", ".markdown", ".text")


class UnsupportedDocument(Exception):
    """The uploaded file is not a type we can extract text from."""


class EmptyDocument(Exception):
    """The file parsed cleanly but contained no usable text."""


def extract_text(filename: str, content_type: str, data: bytes) -> str:
    """Plain text from an uploaded file.

    `content_type` is client-supplied and often wrong or generic, so the
    filename suffix is used as a fallback rather than trusted blindly.
    """
    lowered = filename.lower()

    if content_type in PDF_TYPES or lowered.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)

    if content_type in TEXT_TYPES or lowered.endswith(TEXT_SUFFIXES):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedDocument(f"{filename} is not valid UTF-8 text") from exc

    raise UnsupportedDocument(
        f"Cannot extract text from {filename!r} ({content_type}). Supported: PDF, .txt, .md"
    )


def split_text(text: str) -> list[str]:
    """Split into overlapping chunks with LangChain's recursive splitter."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )
    return [chunk for chunk in splitter.split_text(text) if chunk.strip()]


async def ingest(
    document_id,
    filename: str,
    content_type: str,
    data: bytes,
    embedder: Embedder | None = None,
) -> int:
    """Extract, chunk, embed and store. Returns the chunk count."""
    text = extract_text(filename, content_type, data)

    chunks = split_text(text)
    if not chunks:
        raise EmptyDocument(f"{filename} contained no extractable text")

    embedder = embedder or get_embedder()
    vectors = await embedder.aembed_documents(chunks)

    stored = await qdrant_store.upsert_chunks(document_id, chunks, vectors)
    logger.info("ingested %s: %d chunks", filename, stored)
    return stored
