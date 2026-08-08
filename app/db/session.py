"""Async engine, session factory, and the FastAPI session dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine: AsyncEngine | None = None
sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """The process-wide engine, created on first use.
    Built lazily rather than at import time so that importing the app never opens a pool.
    """
    global engine
    if engine is None:
        engine = create_async_engine(
            settings.DATABASE_URL,
            connect_args={"timeout": settings.DB_CONNECT_TIMEOUT},
        )
    return engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global sessionmaker
    if sessionmaker is None:
        sessionmaker = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
        )
    return sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield a session for one request, rolling back if the handler raises."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close the pool. Called from the app's lifespan on shutdown."""
    global engine, sessionmaker
    if engine is not None:
        await engine.dispose()
        engine = None
        sessionmaker = None


DbSession = Annotated[AsyncSession, Depends(get_db)]
