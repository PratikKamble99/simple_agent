"""Document upload and vector search."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.db.session import DbSession
from app.models.document import Document, DocumentStatus
from app.rag import ingestion, qdrant_store, retrieval
from app.rag.embeddings import Embedder, get_embedder
from app.schemas.document_schema import DocumentRead, SearchHit, SearchRequest

logger = logging.getLogger(__name__)

# Read fully into memory before parsing, so keep the ceiling modest.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

router = APIRouter(prefix="/documents", tags=["documents"])


def embedder_dependency() -> Embedder:
    """Indirection so tests can inject a stub instead of calling OpenAI."""
    return get_embedder()


EmbedderDep = Annotated[Embedder, Depends(embedder_dependency)]


async def _get_or_404(db: DbSession, document_id: UUID) -> Document:
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
    return document


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    db: DbSession,
    embedder: EmbedderDep,
    file: Annotated[UploadFile, File()],
) -> Document:
    """Upload a document, embed its chunks, and store them in Qdrant.

    Processing is inline: the response is sent only once every chunk has been
    embedded and written.
    """
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="File is empty",
        )

    document = Document(
        filename=file.filename or "untitled",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        status=DocumentStatus.PROCESSING,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # From here the row exists, so every failure is recorded on it rather than
    # vanishing with the response.
    try:
        chunk_count = await ingestion.ingest(
            document.id,
            document.filename,
            document.content_type,
            data,
            embedder=embedder,
        )
    except ingestion.UnsupportedDocument as exc:
        await _mark_failed(db, document, str(exc))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except ingestion.EmptyDocument as exc:
        await _mark_failed(db, document, str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except Exception as exc:
        logger.exception("ingestion failed for document %s", document.id)
        await _mark_failed(db, document, str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to embed or store the document",
        ) from exc

    document.status = DocumentStatus.READY
    document.chunk_count = chunk_count
    document.error = None
    await db.commit()
    await db.refresh(document)
    return document


async def _mark_failed(db: DbSession, document: Document, error: str) -> None:
    document.status = DocumentStatus.FAILED
    document.error = error
    await db.commit()


@router.get("", response_model=list[DocumentRead])
async def list_documents(db: DbSession, limit: int = 50, offset: int = 0) -> list[Document]:
    result = await db.execute(
        select(Document).order_by(Document.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


@router.post("/search", response_model=list[SearchHit])
async def search_documents(payload: SearchRequest, embedder: EmbedderDep) -> list[SearchHit]:
    """Return the chunks nearest to the query.

    Delegates to `app.rag.retrieval` so this and the agent share one search
    path, score floor included.
    """
    chunks = await retrieval.retrieve(
        payload.query,
        limit=payload.limit,
        document_id=payload.document_id,
        embedder=embedder,
    )
    return [
        SearchHit(
            id=chunk.chunk_id,
            score=chunk.score,
            document_id=chunk.document_id,
            text=chunk.text,
        )
        for chunk in chunks
    ]


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: UUID, db: DbSession) -> Document:
    return await _get_or_404(db, document_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: UUID, db: DbSession) -> None:
    document = await _get_or_404(db, document_id)

    # Vectors first: an orphaned row is visible and easy to clean up, whereas
    # orphaned vectors have nothing left pointing at them.
    await qdrant_store.delete_by_document(document.id)

    await db.delete(document)
    await db.commit()
