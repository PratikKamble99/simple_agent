"""Similarity search. Uses the in-memory Qdrant and the fake embedder."""

from uuid import uuid4

from qdrant_client import AsyncQdrantClient

from app.rag import qdrant_store, retrieval

DOC_TEXT = "Alembic applies migrations. Run alembic upgrade head."
NOISE = "Bananas ripen quickly in warm weather."


async def _store(embedder, texts: list[str], document_id=None):
    document_id = document_id or uuid4()
    vectors = await embedder.aembed_documents(texts)
    await qdrant_store.upsert_chunks(document_id, texts, vectors)
    return document_id


async def test_retrieve_returns_the_matching_chunk(fake_embedder) -> None:
    await _store(fake_embedder, [DOC_TEXT, NOISE])

    chunks = await retrieval.retrieve(DOC_TEXT, embedder=fake_embedder, min_score=0.0)

    assert chunks
    assert chunks[0].text == DOC_TEXT
    assert chunks[0].chunk_id


async def test_results_are_ordered_best_first(fake_embedder) -> None:
    await _store(fake_embedder, [DOC_TEXT, NOISE])

    chunks = await retrieval.retrieve(DOC_TEXT, embedder=fake_embedder, min_score=0.0)

    assert [c.score for c in chunks] == sorted((c.score for c in chunks), reverse=True)


async def test_min_score_filters_weak_hits(fake_embedder) -> None:
    await _store(fake_embedder, [DOC_TEXT, NOISE])

    # A floor above any achievable cosine score must drop everything, proving
    # the filter is applied rather than ignored.
    assert await retrieval.retrieve(DOC_TEXT, embedder=fake_embedder, min_score=1.1) == []


async def test_retrieve_can_be_scoped_to_a_document(fake_embedder) -> None:
    wanted = await _store(fake_embedder, [DOC_TEXT])
    await _store(fake_embedder, [DOC_TEXT])

    chunks = await retrieval.retrieve(
        DOC_TEXT, embedder=fake_embedder, document_id=wanted, min_score=0.0
    )

    assert chunks
    assert {c.document_id for c in chunks} == {str(wanted)}


async def test_empty_query_short_circuits(fake_embedder) -> None:
    assert await retrieval.retrieve("   ", embedder=fake_embedder) == []


async def test_retrieve_on_an_empty_corpus(
    fake_embedder, qdrant_memory: AsyncQdrantClient
) -> None:
    assert await retrieval.retrieve("anything", embedder=fake_embedder) == []


def test_format_context_numbers_the_blocks() -> None:
    chunks = [
        retrieval.RetrievedChunk(text="first", score=0.9, document_id="d", chunk_id="1"),
        retrieval.RetrievedChunk(text="second", score=0.8, document_id="d", chunk_id="2"),
    ]

    assert retrieval.format_context(chunks) == "[1] first\n\n[2] second"
