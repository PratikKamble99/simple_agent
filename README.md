# simple-ai-agent-fastapi

A FastAPI service managed with [uv](https://docs.astral.sh/uv/). Python 3.12.

## Layout

```
app/
  main.py                     # create_app() factory, middleware + router wiring
  core/
    config.py                 # Settings (pydantic-settings) + cached get_settings()
    logging_config.py         # console logging setup
  db/
    base.py                   # DeclarativeBase, naming convention, TimestampMixin
    session.py                # async engine, session factory, DbSession dependency
  models/
    conversation.py           # Conversation, Message
    document.py               # Document + DocumentStatus
  rag/
    embeddings.py             # OpenAI embeddings (LangChain) + dim lookup
    qdrant_store.py           # the only module that talks to Qdrant
    ingestion.py              # extract -> chunk -> embed -> upsert
    retrieval.py              # the one similarity-search path
    agent.py                  # LangGraph: decide -> retrieve -> generate
  api/v1/
    health.py                 # GET /api/v1/health
    conversations.py          # conversation + message CRUD
    documents.py              # upload, list, get, delete, search
    agent.py                  # POST /api/v1/agent/ask
  schemas/
    base.py                   # shared BaseSchema
    health_schema.py
    conversation_schema.py
    document_schema.py
    agent_schema.py
  middleware/
    request_logging.py        # per-request access log + X-Request-ID
alembic/
  env.py                      # reads DATABASE_URL from Settings
  versions/                   # migrations
tests/
  conftest.py                 # TestClient, database, in-memory Qdrant, fake embedder
  test_main.py
  test_logging.py
  test_conversations.py       # skipped unless TEST_DATABASE_URL is set
  test_documents.py           # ditto
```

## Setup

```bash
uv sync
cp .env.example .env          # set DATABASE_URL here
uv run alembic upgrade head   # create the schema
```

## Database

PostgreSQL via SQLAlchemy 2.0 (async, `asyncpg`) with Alembic migrations. The connection
string comes from `DATABASE_URL` and must use the `postgresql+asyncpg://` scheme — a plain
`postgresql://` URL loads psycopg and fails at startup.

`alembic.ini` leaves `sqlalchemy.url` blank on purpose; `alembic/env.py` fills it in from
`Settings`, so the URL lives only in `.env` and no credentials are committed.

```bash
uv run alembic upgrade head                              # apply migrations
uv run alembic revision --autogenerate -m "add x"        # create one from model changes
uv run alembic downgrade -1                              # step back
uv run alembic check                                     # models vs. database drift
uv run alembic upgrade head --sql                        # render DDL without connecting
```

Add every new model to `app/models/__init__.py` — autogenerate diffs against
`Base.metadata`, which is only complete once each model module has been imported.

## Document ingestion (RAG)

`POST /api/v1/documents` takes a multipart upload (PDF, `.txt`, `.md`), extracts the text,
splits it with LangChain's `RecursiveCharacterTextSplitter`, embeds each chunk with OpenAI,
and writes the vectors to Qdrant. Processing is **inline** — the 201 comes back only once
every chunk is stored, with `status: "ready"` and a `chunk_count`.

Postgres owns the document record. Qdrant stores one point per chunk, and its payload is
deliberately minimal — just enough to filter by document and read the text back:

```json
{ "id": "<uuid>", "vector": [ ... ], "payload": { "document_id": "<uuid>", "text": "..." } }
```

No filenames, no titles, no status, no user data are duplicated into the payload. Everything
else is joined from Postgres on `document_id`, which carries a Qdrant payload index so
filtered search doesn't degrade to a full scan.

Routes: `POST /documents`, `GET /documents`, `GET /documents/{id}`, `DELETE /documents/{id}`
(removes the vectors first, then the row), and `POST /documents/search`
(`{query, limit, document_id?}`).

Failures are recorded rather than lost: an unsupported type, an empty file or an embedding
outage leaves a row with `status: "failed"` and the reason in `error`.

### Configuration

Only credentials and deployment-specific names are settings — `OPENAI_API_KEY`,
`OPENAI_EMBEDDING_MODEL`, `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`. Everything
else is a constant in the module that uses it:

| Constant | Value | Where |
|---|---|---|
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 1000 / 200 | `app/services/ingestion.py` |
| `MAX_UPLOAD_BYTES` | 10 MB | `app/api/v1/documents.py` |
| `EMBEDDING_DIMS` | model → width | `app/services/embeddings.py` |

Vector width is looked up from the model name rather than hardcoded, because Qdrant only
rejects a mismatched width at insert time — long after the collection was created. Changing
`OPENAI_EMBEDDING_MODEL` to one with different dimensions means creating a new collection.

## Retrieval

`app/rag/retrieval.py` is the single similarity-search path — both `POST /documents/search`
and the agent go through it, so they share the same ranking and score floor.

`retrieve(query, limit, document_id, min_score)` embeds the query, searches Qdrant, and drops
anything below `MIN_SCORE` (0.3). That floor matters: cosine search *always* returns its
nearest `k`, however irrelevant, so without it an unrelated corpus still yields "context" and
the model answers from noise.

## Agent

`POST /api/v1/agent/ask` runs a LangGraph graph:

```
START ──▶ decide ──needs_rag──▶ retrieve ──▶ generate ──▶ END
             │                                  ▲
             └──────── no ──────────────────────┘
```

- **`decide`** — an LLM classifier (`with_structured_output(RagDecision)`) judges whether the
  question needs the uploaded corpus at all. Retrieval costs an embedding call and a vector
  round-trip, and irrelevant context makes answers worse, so it is asked first.
- **`retrieve`** — similarity search. If nothing clears the score floor it flips `needs_rag`
  back to false, so `generate` never receives an empty context block it would treat as
  sources.
- **`generate`** — with context, answers only from it and cites blocks as `[1]`, `[2]`;
  without, answers directly.

```jsonc
// request
{ "question": "what do my docs say about migrations", "document_id": null, "top_k": 5 }
// response
{ "answer": "...",
  "used_rag": true,
  "decision_reason": "asks about the user's documents",
  "sources": [ { "document_id": "...", "chunk_id": "...", "score": 0.82, "text": "..." } ] }
```

`used_rag` and `decision_reason` are returned so the decision node is observable — otherwise
there is no way to tell from outside whether retrieval ran.

The chat model is `OPENAI_CHAT_MODEL` (default `gpt-4o-mini`). `build_graph(llm=, embedder=)`
takes injected dependencies, which is how the tests drive it without calling OpenAI.

## Run

```bash
uv run fastapi dev app/main.py       # reload server on http://127.0.0.1:8000
uv run fastapi run app/main.py       # production mode
```

- Health check: <http://127.0.0.1:8000/api/v1/health>
- OpenAPI docs: <http://127.0.0.1:8000/docs>

## Logging

Console only — nothing is written to disk. `RequestLoggingMiddleware` emits exactly one
line per request to stdout:

```
2026-08-07 17:12:44 | INFO     | app.request | a3f9c2e1 127.0.0.1 GET /api/v1/health -> 200 in 1.24ms
```

4xx responses log at `WARNING`, 5xx and unhandled exceptions at `ERROR` (with a traceback).
Each line carries a request id, also returned in the `X-Request-ID` response header; send
that header yourself and it is reused, so callers can correlate their logs with the server's.

uvicorn's own access log is silenced by default, since it would print a second, less
detailed line for every request. Set `LOG_UVICORN_ACCESS=true` to bring it back.
Log level is set with `LOG_LEVEL` (see `.env.example`).

## Test and lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```
