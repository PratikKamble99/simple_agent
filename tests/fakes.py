"""Stand-ins for the OpenAI chat model, so no test makes a network call."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from app.rag.agent import RagDecision


class FakeStructuredModel:
    """What `with_structured_output(RagDecision)` returns."""

    def __init__(self, decision: RagDecision, parent: FakeChatModel) -> None:
        self._decision = decision
        self._parent = parent

    async def ainvoke(self, messages: Any, **_: Any) -> RagDecision:
        self._parent.decide_prompts.append(_as_text(messages))
        if self._parent.raises:
            raise RuntimeError("openai is down")
        return self._decision


class FakeChatModel:
    """Scripted chat model that records the prompts it was given.

    Deliberately not a `BaseChatModel` subclass: the graph only ever calls
    `ainvoke` and `with_structured_output`, and implementing those two keeps
    the fake honest about what the code actually depends on.
    """

    def __init__(
        self,
        *,
        needs_rag: bool = False,
        reason: str = "scripted",
        answer: str = "scripted answer",
        raises: bool = False,
    ) -> None:
        self.decision = RagDecision(needs_rag=needs_rag, reason=reason)
        self.answer = answer
        self.raises = raises
        self.decide_prompts: list[str] = []
        self.answer_prompts: list[str] = []

    def with_structured_output(self, schema: Any, **_: Any) -> FakeStructuredModel:
        return FakeStructuredModel(self.decision, self)

    async def ainvoke(self, messages: Any, **_: Any) -> AIMessage:
        self.answer_prompts.append(_as_text(messages))
        if self.raises:
            raise RuntimeError("openai is down")
        return AIMessage(content=self.answer)


def _as_text(messages: Any) -> str:
    if isinstance(messages, str):
        return messages
    return "\n".join(str(getattr(m, "content", m)) for m in messages)
