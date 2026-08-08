"""The question-answering agent."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.rag import agent as rag_agent
from app.schemas.agent_schema import AskRequest, AskResponse, Source

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


def graph_dependency() -> Any:
    """Indirection so tests can inject a graph built with fakes."""
    return rag_agent._default_graph()


GraphDep = Annotated[Any, Depends(graph_dependency)]


@router.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest, graph: GraphDep) -> AskResponse:
    """Answer a question, retrieving from the document corpus only if needed."""
    try:
        state = await rag_agent.answer_question(
            payload.question,
            document_id=payload.document_id,
            top_k=payload.top_k,
            graph=graph,
        )
    except Exception as exc:
        logger.exception("agent failed to answer")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The agent could not answer this question",
        ) from exc

    chunks = state.get("chunks") or []
    return AskResponse(
        answer=state.get("answer", ""),
        used_rag=bool(chunks),
        decision_reason=state.get("decision_reason", ""),
        sources=[
            Source(
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                score=chunk.score,
                text=chunk.text,
            )
            for chunk in chunks
        ],
    )
