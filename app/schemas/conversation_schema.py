from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.conversation import MessageRole
from app.schemas.base import BaseSchema


class MessageCreate(BaseSchema):
    role: MessageRole
    content: str = Field(min_length=1)


class MessageRead(BaseSchema):
    id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str
    created_at: datetime


class ConversationCreate(BaseSchema):
    title: str | None = Field(default=None, max_length=200)


class ConversationRead(BaseSchema):
    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[MessageRead] = []
