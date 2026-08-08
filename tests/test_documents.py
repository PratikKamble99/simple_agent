import pytest
from fastapi.testclient import TestClient
from qdrant_client import AsyncQdrantClient

from app.api.v1.documents import MAX_UPLOAD_BYTES, embedder_dependency
from app.core.config import get_settings
from app.rag import ingestion, qdrant_store

SAMPLE = b"Alembic manages the schema. Run alembic upgrade head to apply migrations.\n" * 40


def upload(client: TestClient, prefix: str, name="notes.txt", data=SAMPLE, ctype="text/plain"):
    return client.post(f"{prefix}/documents", files={"file": (name, data, ctype)})


async def stored_points(qdrant_memory: AsyncQdrantClient) -> list:
    collection = get_settings().QDRANT_COLLECTION
    if not await qdrant_memory.collection_exists(collection):
        return []
    points, _ = await qdrant_memory.scroll(collection, limit=1000, with_payload=True)
    return points


def test_upload_returns_ready_with_chunks(db_client: TestClient, api_prefix: str) -> None:
    response = upload(db_client, api_prefix)

    assert response.status_code == 201

    body = response.json()
    assert body["status"] == "ready"
    assert body["chunk_count"] > 0
    assert body["filename"] == "notes.txt"
    assert body["error"] is None


async def test_chunk_payload_is_exactly_document_id_and_text(
    db_client: TestClient, api_prefix: str, qdrant_memory: AsyncQdrantClient
) -> None:
    document = upload(db_client, api_prefix).json()

    points = await stored_points(qdrant_memory)

    assert len(points) == document["chunk_count"]
    for point in points:
        # The payload must carry nothing beyond the id needed for filtering
        # and the chunk text itself.
        assert set(point.payload) == {"document_id", "text"}
        assert point.payload["document_id"] == document["id"]
        assert point.payload["text"]


def test_search_finds_the_uploaded_chunk(db_client: TestClient, api_prefix: str) -> None:
    upload(db_client, api_prefix)

    response = db_client.post(
        f"{api_prefix}/documents/search",
        json={"query": "alembic upgrade head", "limit": 3},
    )

    assert response.status_code == 200

    hits = response.json()
    assert hits
    assert "alembic" in hits[0]["text"].lower()
    assert hits[0]["score"] > 0


def test_search_can_be_scoped_to_one_document(db_client: TestClient, api_prefix: str) -> None:
    first = upload(db_client, api_prefix, name="a.txt").json()
    upload(db_client, api_prefix, name="b.txt")

    response = db_client.post(
        f"{api_prefix}/documents/search",
        json={"query": "alembic", "limit": 10, "document_id": first["id"]},
    )

    assert response.status_code == 200
    assert {hit["document_id"] for hit in response.json()} == {first["id"]}


async def test_delete_removes_row_and_vectors(
    db_client: TestClient, api_prefix: str, qdrant_memory: AsyncQdrantClient
) -> None:
    document = upload(db_client, api_prefix).json()
    assert await stored_points(qdrant_memory)

    assert db_client.delete(f"{api_prefix}/documents/{document['id']}").status_code == 204

    assert db_client.get(f"{api_prefix}/documents/{document['id']}").status_code == 404
    assert await stored_points(qdrant_memory) == []


def test_oversized_upload_is_rejected(db_client: TestClient, api_prefix: str) -> None:
    response = upload(db_client, api_prefix, data=b"x" * (MAX_UPLOAD_BYTES + 1))

    assert response.status_code == 413


def test_empty_upload_is_rejected(db_client: TestClient, api_prefix: str) -> None:
    response = upload(db_client, api_prefix, data=b"")

    assert response.status_code == 422


def test_unsupported_type_is_recorded_as_failed(db_client: TestClient, api_prefix: str) -> None:
    response = upload(db_client, api_prefix, name="clip.mp3", data=b"ID3\x04", ctype="audio/mpeg")

    assert response.status_code == 415

    # The row survives, carrying the reason.
    listed = db_client.get(f"{api_prefix}/documents").json()
    assert listed[0]["status"] == "failed"
    assert "clip.mp3" in listed[0]["error"]


def test_embedding_failure_marks_document_failed(
    db_client: TestClient, api_prefix: str
) -> None:
    class BrokenEmbedder:
        async def aembed_documents(self, texts):
            raise RuntimeError("openai is down")

        async def aembed_query(self, text):
            raise RuntimeError("openai is down")

    db_client.app.dependency_overrides[embedder_dependency] = BrokenEmbedder

    response = upload(db_client, api_prefix)

    assert response.status_code == 502

    listed = db_client.get(f"{api_prefix}/documents").json()
    assert listed[0]["status"] == "failed"
    assert "openai is down" in listed[0]["error"]


def test_health_reports_vector_store(db_client: TestClient, api_prefix: str) -> None:
    body = db_client.get(f"{api_prefix}/health").json()

    assert body["database"] == "ok"
    assert body["vector_store"] == "ok"


# --- unit-level checks that need neither a database nor a client ------------


def test_split_text_produces_overlapping_chunks() -> None:
    chunks = ingestion.split_text("word " * 2000)

    assert len(chunks) > 1
    assert all(len(chunk) <= ingestion.CHUNK_SIZE for chunk in chunks)


def test_extract_text_rejects_unknown_types() -> None:
    with pytest.raises(ingestion.UnsupportedDocument):
        ingestion.extract_text("clip.mp3", "audio/mpeg", b"ID3")


def test_extract_text_reads_plain_text() -> None:
    assert ingestion.extract_text("a.txt", "text/plain", b"hello") == "hello"


async def test_upsert_rejects_mismatched_lengths(qdrant_memory: AsyncQdrantClient) -> None:
    from uuid import uuid4

    with pytest.raises(ValueError):
        await qdrant_store.upsert_chunks(uuid4(), ["a", "b"], [[0.1]])
