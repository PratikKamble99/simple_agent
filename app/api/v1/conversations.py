"""Conversation and message CRUD."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.db.session import DbSession
from app.models.conversation import Conversation, Message
from app.schemas.conversation_schema import (
    ConversationCreate,
    ConversationDetail,
    ConversationRead,
    MessageCreate,
    MessageRead,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def _get_or_404(db: DbSession, conversation_id: UUID) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )
    return conversation


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(payload: ConversationCreate, db: DbSession) -> Conversation:
    conversation = Conversation(title=payload.title)
    db.add(conversation)
    await db.commit()
    # Server-side defaults (id, timestamps) are only known after the INSERT.
    await db.refresh(conversation)
    return conversation


@router.get("", response_model=list[ConversationRead])
async def list_conversations(db: DbSession, limit: int = 50, offset: int = 0) -> list[Conversation]:
    result = await db.execute(
        select(Conversation).order_by(Conversation.created_at.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: UUID, db: DbSession) -> Conversation:
    return await _get_or_404(db, conversation_id)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: UUID, db: DbSession) -> None:
    conversation = await _get_or_404(db, conversation_id)
    await db.delete(conversation)
    await db.commit()


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_message(
    conversation_id: UUID, payload: MessageCreate, db: DbSession
) -> Message:
    await _get_or_404(db, conversation_id)

    message = Message(
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


@router.get("/{conversation_id}/messages", response_model=list[MessageRead])
async def list_messages(conversation_id: UUID, db: DbSession) -> list[Message]:
    await _get_or_404(db, conversation_id)

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())
