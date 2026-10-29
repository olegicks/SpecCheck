"""Data types shared by the agent loop, LLM clients and the API."""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    THINKING = "thinking"
    SEARCH = "search"
    READ_PAGE = "read_page"
    EXTRACT = "extract"
    SUBMIT = "submit"
    VERIFY = "verify"
    DECIDE = "decide"
    WARNING = "warning"
    ERROR = "error"
    RUN_COMPLETED = "run_completed"


class AgentEvent(BaseModel):
    """One entry in the live agent timeline (streamed to the UI via SSE)."""

    seq: int = 0
    type: EventType
    title: str
    detail: str | None = None
    step: int | None = None
    duration_ms: int | None = None
    timestamp: float = Field(default_factory=time.time)
    data: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """A tool call requested by the model. ``arguments`` is raw JSON text (may be invalid)."""

    id: str
    name: str
    arguments: str


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, other: Usage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)


Message = dict[str, Any]


class LLMError(RuntimeError):
    """Raised by LLM clients for unrecoverable API errors (message is already redacted)."""


class LLMClient(Protocol):
    """Minimal interface the agent needs. Implemented by the OpenAI client and fakes."""

    model: str

    async def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        """Send the conversation and tool schemas; return the model's next message."""
        ...
