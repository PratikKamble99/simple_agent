"""A small LangGraph agent that answers a question, retrieving only when needed.

    START -> decide -+-- needs_rag --> retrieve --> generate -> END
                     |
                     +-- no ------------------------> generate

`decide` is an LLM classifier: retrieval costs an embedding call and a vector
round-trip, and stuffing irrelevant context into the prompt makes answers
worse, so "does this even need the corpus?" is asked first.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated, Any, TypedDict
from uuid import UUID

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.rag import retrieval
from app.rag.embeddings import Embedder
from app.rag.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)


class RagDecision(BaseModel):
    """Structured verdict from the decision node."""

    needs_rag: bool = Field(
        description="True if answering requires the user's uploaded documents."
    )
    reason: str = Field(description="One short sentence explaining the choice.")


DECIDE_SYSTEM = """You route questions for a document question-answering system.

The corpus contains documents the user uploaded themselves. Decide whether \
answering needs that corpus.

needs_rag = true  - the question is about the user's documents, their content, \
or anything specific to them that you could not know.
needs_rag = false - greetings, small talk, general knowledge, arithmetic, \
definitions, or anything answerable without the user's private material.

Give one short sentence of reasoning."""

ANSWER_WITH_CONTEXT = """Answer the question using only the context below.

If the context does not contain the answer, say so plainly - do not guess and \
do not fall back on outside knowledge. Cite the blocks you used as [1], [2].

Context:
{context}"""

ANSWER_WITHOUT_CONTEXT = """Answer the user's question directly and concisely.

You have no document context for this one, so rely on general knowledge. If \
the question turns out to need their documents, say that instead of guessing."""


class AgentState(TypedDict, total=False):
    question: str
    document_id: UUID | None
    top_k: int
    # needs_rag: bool
    # decision_reason: str
    chunks: Annotated[list[RetrievedChunk], "retrieved context"]
    answer: str


def get_chat_model() -> BaseChatModel:
    """The configured OpenAI chat model."""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set; the agent cannot run")
    return ChatOpenAI(
        model=settings.OPENAI_CHAT_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
    )


def build_graph(
    llm: BaseChatModel | None = None,
    embedder: Embedder | None = None,
) -> Any:
    """Compile the graph. Dependencies are injected so tests can supply fakes."""

    def _llm() -> BaseChatModel:
        return llm or get_chat_model()

    async def decide(state: AgentState) -> dict:
        question = state["question"]
        classifier = _llm().with_structured_output(RagDecision)
        decision: RagDecision = await classifier.ainvoke(
            [SystemMessage(content=DECIDE_SYSTEM), HumanMessage(content=question)]
        )
        logger.info("rag decision: %s (%s)", decision.needs_rag, decision.reason)
        return {"needs_rag": decision.needs_rag, "decision_reason": decision.reason}

    async def retrieve(state: AgentState) -> dict:
        chunks = await retrieval.retrieve(
            state["question"],
            limit=state.get("top_k") or retrieval.DEFAULT_TOP_K,
            document_id=state.get("document_id"),
            embedder=embedder,
        )
        if not chunks:
            # Nothing cleared the score floor. Downgrade rather than handing
            # `generate` an empty context block it would treat as sources.
            return {
                "chunks": [],
                "needs_rag": False,
                "decision_reason": "no relevant chunks found; answered without context",
            }
        return {"chunks": chunks}

    async def generate(state: AgentState) -> dict:
        chunks = state.get("chunks") or []
        if chunks:
            system = ANSWER_WITH_CONTEXT.format(context=retrieval.format_context(chunks))
        else:
            system = ANSWER_WITHOUT_CONTEXT

        response = await _llm().ainvoke(
            [SystemMessage(content=system), HumanMessage(content=state["question"])]
        )
        return {"answer": str(response.content)}

    def route(state: AgentState) -> str:
        return "retrieve" if state.get("needs_rag") else "generate"

    graph = StateGraph(AgentState)
    # graph.add_node("decide", decide)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)

    # graph.add_edge(START, "decide")
    graph.add_edge(START, "retrieve")
    # graph.add_conditional_edges(
    #     "decide", route, {"retrieve": "retrieve", "generate": "generate"}
    # )
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


@lru_cache(maxsize=1)
def _default_graph() -> Any:
    """Compiled once per process - rebuilding per request is wasted work."""
    return build_graph()


async def answer_question(
    question: str,
    *,
    document_id: UUID | None = None,
    top_k: int | None = None,
    graph: Any | None = None,
) -> AgentState:
    """Run the graph and return its final state."""
    graph = graph or _default_graph()
    return await graph.ainvoke(
        {
            "question": question,
            "document_id": document_id,
            "top_k": top_k or retrieval.DEFAULT_TOP_K,
        }
    )
