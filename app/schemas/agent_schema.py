from __future__ import annotations

from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class AskRequest(BaseSchema):
    question: str = Field(min_length=1, max_length=4000)
    # Restricts retrieval to a single document.
    document_id: UUID | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class Source(BaseSchema):
    document_id: str | None
    chunk_id: str
    score: float
    text: str


class AskResponse(BaseSchema):
    answer: str
    # Exposed so the decision node is observable from outside: without these
    # there is no way to tell whether retrieval actually ran.
    # used_rag: bool
    # decision_reason: str
    sources: list[Source] = []
