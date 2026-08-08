"""Liveness and readiness probes."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.db.session import DbSession
from app.rag import qdrant_store
from app.schemas.health_schema import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health(db: DbSession) -> HealthResponse:
    """Return 200 as long as the process is serving requests.

    A database outage is reported in the body rather than raised: a probe that
    500s when the database is down is useless for diagnosing that the database
    is down.
    """
    try:
        await db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001 - a probe must never propagate
        # Deliberately broad: asyncpg raises bare OSError for a refused
        # connection, which never reaches SQLAlchemyError.
        logger.exception("database health check failed")
        database = "unreachable"

    vector_store = await qdrant_store.status()

    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        database=database,
        vector_store=vector_store,
    )
