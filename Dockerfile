# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /bin/uv

# UV_LINK_MODE=copy: the uv cache lives on a BuildKit cache mount, a different
# filesystem than /app, so hardlinking into the venv would warn and fall back.
# PATH: puts the venv's bin first, so `uvicorn` resolves without `uv run`.
ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Only the dependency manifests, so editing app code doesn't invalidate the sync layer.
COPY pyproject.toml uv.lock ./

# use this target for compose
FROM base AS development

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


FROM base AS production

ENV UV_COMPILE_BYTECODE=1

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
