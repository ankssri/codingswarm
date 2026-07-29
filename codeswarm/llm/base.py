"""Core LLM types and the provider interface all backends implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    """A tool/function invocation requested by the model.

    `arguments` is always a parsed dict at this layer — providers normalize the
    raw JSON-string form the API returns before handing it back.
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    """A single chat message.

    Supports the full tool-calling round-trip:
      - an assistant message may carry `tool_calls`;
      - a `role="tool"` message carries the result of one call, tagged with the
        `tool_call_id` it answers.
    """

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: Optional[str] = None  # set on role="tool"
    name: Optional[str] = None  # tool name on role="tool"


@dataclass
class LLMResponse:
    """Normalized response returned by every provider."""

    text: str
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


class LLMProvider(ABC):
    """Interface every backend implements.

    Agents need only `complete()`. `tools` optionally passes OpenAI-style tool
    specs to enable function calling (used by the agentic Developer loop). `tag`
    is a hint describing the expected output kind; real providers ignore it, but
    the offline MockProvider uses it to return sensible canned output.
    """

    def __init__(self, name: str, model: str) -> None:
        self.name = name
        self.model = model

    @abstractmethod
    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tag: Optional[str] = None,
    ) -> LLMResponse:
        """Return a completion for the given messages."""

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r}, model={self.model!r})"
