import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import agent, conversations, documents, health
from app.core.config import Settings, get_settings, settings
from app.core.logging_config import setup_logging
from app.db.session import dispose_engine
from app.middleware import RequestLoggingMiddleware
from app.rag import qdrant_store

logger = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application."""
    settings = settings or get_settings()

    setup_logging(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        # Re-applied here because uvicorn configures logging *after* importing
        # this module, which would otherwise restore its own access log. The
        # startup line lives here too: the FastAPI CLI imports this module once
        # to discover `app` before uvicorn imports it to serve, so anything
        # logged at import time is emitted twice per launch.
        setup_logging(settings)
        logger.info(
            "%s v%s started (environment=%s)",
            settings.APP_NAME,
            settings.APP_VERSION,
            settings.ENVIRONMENT,
        )
        yield
        # Close the connection pool, so a reload doesn't strand connections.
        await dispose_engine()
        await qdrant_store.close_client()
        logger.info("%s shutting down", settings.APP_NAME)

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.debug,
        lifespan=lifespan,
    )

    # Registered first so it wraps CORS and times the whole request.
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.include_router(conversations.router, prefix=settings.api_v1_prefix)
    app.include_router(documents.router, prefix=settings.api_v1_prefix)
    app.include_router(agent.router, prefix=settings.api_v1_prefix)

    return app


app = create_app(settings=settings)
