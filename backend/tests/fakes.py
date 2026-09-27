"""Scripted chat model injected through `get_chat_model()` — no network."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolCall
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel, PrivateAttr


class FakeStructured:
    """Runnable returned by `with_structured_output`."""

    def __init__(self, parent: FakeChatModel, schema: type[BaseModel]):
        self.parent = parent
        self.schema = schema

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        return self.parent._pop_structured(self.schema)

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        return self.parent._pop_structured(self.schema)


class FakeChatModel(BaseChatModel):
    """Queue of scripted replies.

    Each item is either:
    - a Pydantic instance / dict (returned by with_structured_output)
    - an AIMessage (ReAct tool calls or text)
    - a dict ``{"tool": name, "args": {...}}`` turned into a tool-call AIMessage
    """

    _script: list[Any] = PrivateAttr(default_factory=list)
    _bound_tools: list[Any] = PrivateAttr(default_factory=list)

    def __init__(self, script: list[Any] | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        self._script = list(script or [])
        self._bound_tools = []

    @property
    def _llm_type(self) -> str:
        return "fake-scripted"

    def push(self, *items: Any) -> None:
        self._script.extend(items)

    def _pop(self) -> Any:
        if not self._script:
            return AIMessage(content="")
        return self._script.pop(0)

    def _pop_structured(self, schema: type[BaseModel]) -> Any:
        item = self._pop()
        if isinstance(item, schema):
            return item
        if isinstance(item, BaseModel):
            return schema.model_validate(item.model_dump())
        if isinstance(item, dict):
            return schema.model_validate(item)
        if isinstance(item, AIMessage) and item.content:
            return schema.model_validate_json(
                item.content if isinstance(item.content, str) else "{}"
            )
        return schema()

    def with_structured_output(self, schema: type[BaseModel], **kwargs: Any) -> FakeStructured:
        return FakeStructured(self, schema)

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> FakeChatModel:
        clone = FakeChatModel(script=[])
        clone._script = self._script
        clone._bound_tools = list(tools)
        return clone

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        item = self._pop()
        if isinstance(item, AIMessage):
            msg = item
        elif isinstance(item, dict) and "tool" in item:
            msg = AIMessage(
                content="",
                tool_calls=[
                    ToolCall(name=item["tool"], args=item.get("args") or {}, id=str(uuid4()))
                ],
            )
        elif isinstance(item, BaseModel):
            msg = AIMessage(content=item.model_dump_json())
        else:
            msg = AIMessage(content=str(item) if item is not None else "")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class ReuseSession:
    """Async context manager that yields the test `db_session` without closing it."""

    def __init__(self, session: Any):
        self.session = session

    async def __aenter__(self) -> Any:
        return self.session

    async def __aexit__(self, *exc: Any) -> bool:
        return False
