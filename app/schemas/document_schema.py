from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.document import DocumentStatus
from app.schemas.base import BaseSchema


class DocumentRead(BaseSchema):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    error: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class SearchRequest(BaseSchema):
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=50)
    # Restricts the search to a single document.
    document_id: UUID | None = None


class SearchHit(BaseSchema):
    id: str
    score: float
    document_id: str | None
    text: str
