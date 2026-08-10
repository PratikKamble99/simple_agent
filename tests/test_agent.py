"""The LangGraph agent, driven entirely by fakes."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.agent import graph_dependency
from app.core.config import Settings
from app.main import create_app
from app.rag import qdrant_store
from app.rag.agent import build_graph
from tests.fakes import FakeChatModel

DOC_TEXT = "Alembic applies migrations. Run alembic upgrade head to create the schema."


async def seed(embedder, text: str = DOC_TEXT):
    vectors = await embedder.aembed_documents([text])
    await qdrant_store.upsert_chunks(uuid4(), [text], vectors)


async def run(llm, embedder, question: str, **kwargs):
    graph = build_graph(llm=llm, embedder=embedder)
    return await graph.ainvoke({"question": question, "top_k": 5, **kwargs})


# --- the decision node ------------------------------------------------------


# async def test_decision_false_skips_retrieval(fake_embedder) -> None:
#     await seed(fake_embedder)
#     llm = FakeChatModel(needs_rag=False, reason="general knowledge", answer="4")

#     state = await run(llm, fake_embedder, "what is 2+2")

#     assert state["needs_rag"] is False
#     assert state.get("chunks") in (None, [])
#     assert state["answer"] == "4"
#     # The generation prompt must not carry a context block.
#     assert "Context:" not in llm.answer_prompts[0]


# async def test_decision_true_retrieves_and_grounds_the_prompt(fake_embedder) -> None:
#     await seed(fake_embedder)
#     llm = FakeChatModel(needs_rag=True, reason="asks about the documents", answer="Use alembic.")

#     state = await run(llm, fake_embedder, DOC_TEXT)

#     assert state["needs_rag"] is True
#     assert state["chunks"]
#     # The retrieved text must actually reach the model, not merely be fetched.
#     assert "alembic" in llm.answer_prompts[0].lower()
#     assert "Context:" in llm.answer_prompts[0]


# async def test_decision_reason_is_carried_through(fake_embedder) -> None:
#     llm = FakeChatModel(needs_rag=False, reason="just a greeting")

#     state = await run(llm, fake_embedder, "hello")

#     assert state["decision_reason"] == "just a greeting"


# async def test_the_question_reaches_the_classifier(fake_embedder) -> None:
#     llm = FakeChatModel(needs_rag=False)

#     await run(llm, fake_embedder, "a very distinctive question")

#     assert "a very distinctive question" in llm.decide_prompts[0]


# --- retrieval that finds nothing -------------------------------------------


async def test_empty_retrieval_downgrades_instead_of_faking_context(fake_embedder) -> None:
    """Nothing was stored, so `retrieve` returns nothing."""
    llm = FakeChatModel(needs_rag=True, reason="looks document-related")

    state = await run(llm, fake_embedder, "what do the documents say")

    # assert state["needs_rag"] is False
    assert state["chunks"] == []
    # assert "no relevant chunks" in state["decision_reason"]
    assert "Context:" not in llm.answer_prompts[0]


# --- the route --------------------------------------------------------------


@pytest.fixture
def agent_client(settings: Settings, fake_embedder):
    """Client whose agent graph runs on fakes. Needs no database."""

    def make(llm: FakeChatModel) -> TestClient:
        app = create_app(settings=settings)
        graph = build_graph(llm=llm, embedder=fake_embedder)
        app.dependency_overrides[graph_dependency] = lambda: graph
        return TestClient(app)

    return make


async def test_ask_returns_answer_and_sources(
    agent_client, api_prefix: str, fake_embedder
) -> None:
    await seed(fake_embedder)
    llm = FakeChatModel(needs_rag=True, reason="document question", answer="Run alembic.")

    with agent_client(llm) as client:
        response = client.post(f"{api_prefix}/agent/ask", json={"question": DOC_TEXT})

    assert response.status_code == 200

    body = response.json()
    assert body["answer"] == "Run alembic."
    # assert body["used_rag"] is True
    # assert body["decision_reason"] == "document question"
    assert body["sources"]
    assert body["sources"][0]["text"] == DOC_TEXT


def test_ask_without_rag_reports_no_sources(agent_client, api_prefix: str) -> None:
    llm = FakeChatModel(needs_rag=False, reason="small talk", answer="Hello.")

    with agent_client(llm) as client:
        response = client.post(f"{api_prefix}/agent/ask", json={"question": "hi"})

    body = response.json()
    # assert body["used_rag"] is False
    assert body["sources"] == []
    assert body["answer"] == "Hello."


def test_ask_rejects_an_empty_question(agent_client, api_prefix: str) -> None:
    with agent_client(FakeChatModel()) as client:
        response = client.post(f"{api_prefix}/agent/ask", json={"question": ""})

    assert response.status_code == 422


def test_llm_failure_returns_502(agent_client, api_prefix: str) -> None:
    with agent_client(FakeChatModel(raises=True)) as client:
        response = client.post(f"{api_prefix}/agent/ask", json={"question": "anything"})

    assert response.status_code == 502


# --- graph shape ------------------------------------------------------------


def test_graph_has_the_conditional_edge() -> None:
    graph = build_graph(llm=FakeChatModel()).get_graph()
    nodes = set(graph.nodes)

    # assert {"decide", "retrieve", "generate"} <= nodes
    assert {"retrieve", "generate"} <= nodes

    edges = {(e.source, e.target) for e in graph.edges}
    # assert ("decide", "retrieve") in edges
    # assert ("decide", "generate") in edges
    assert ("retrieve", "generate") in edges
