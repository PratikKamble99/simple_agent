from __future__ import annotations

from app.schemas.base import BaseSchema

__all__ = ["BaseSchema", "HealthResponse"]


class HealthResponse(BaseSchema):
    status: str
    app: str
    version: str
    environment: str
    database: str
    vector_store: str
