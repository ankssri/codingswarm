"""Base agent: wraps a provider and runs either a single turn or a tool loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

from ..llm import LLMProvider, Message

if TYPE_CHECKING:  # avoid import cycle at runtime
    from ..tools import Toolbox


@dataclass
class ToolStep:
    """One tool invocation during an agentic loop (for transcripts/reporting)."""

    name: str
    arguments: dict
    result: str


class Agent:
    """A single specialist role backed by an LLM provider.

    Subclasses set `role` and implement task-specific methods. They call either
    `chat()` for a one-shot turn, or `run_tool_loop()` for an agentic loop where
    the model reads/writes/tests via tools until it calls `finish`.
    """

    role: str = "agent"

    def __init__(
        self,
        provider: LLMProvider,
        *,
        temperature: float = 0.2,
        on_event: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.provider = provider
        self.temperature = temperature
        self._on_event = on_event

    def chat(self, system: str, user: str, *, tag: Optional[str] = None) -> str:
        messages = [Message("system", system), Message("user", user)]
        resp = self.provider.complete(messages, temperature=self.temperature, tag=tag)
        return resp.text

    def run_tool_loop(
        self,
        system: str,
        user: str,
        toolbox: "Toolbox",
        *,
        tag: Optional[str] = None,
        max_steps: int = 8,
    ) -> list[ToolStep]:
        """Drive an agentic loop: model -> tool calls -> results -> model ...

        Stops when the model calls `finish`, stops requesting tools, or the step
        budget is exhausted. Returns the transcript of tool steps taken.
        """
        messages: list[Message] = [Message("system", system), Message("user", user)]
        transcript: list[ToolStep] = []

        for _ in range(max_steps):
            resp = self.provider.complete(
                messages, temperature=self.temperature, tools=toolbox.specs(), tag=tag
            )
            if not resp.tool_calls:
                # Model answered with prose instead of a tool call -> it's done.
                break

            messages.append(
                Message(role="assistant", content=resp.text or "", tool_calls=resp.tool_calls)
            )
            finished = False
            for tc in resp.tool_calls:
                if tc.name == "finish":
                    result = "Done."
                    finished = True
                else:
                    result = toolbox.invoke(tc.name, tc.arguments)
                transcript.append(ToolStep(name=tc.name, arguments=tc.arguments, result=result))
                self.emit(f"tool:{tc.name}")
                messages.append(
                    Message(role="tool", content=result, tool_call_id=tc.id, name=tc.name)
                )
            if finished:
                break

        return transcript

    def emit(self, message: str) -> None:
        if self._on_event:
            self._on_event(self.role, message)
