"""Concrete providers.

`OpenAICompatibleProvider` covers OpenAI, BytePlus ModelArk, and Gemini — all
three expose an OpenAI-style `/chat/completions` surface (including tool calls),
so one client with a different `base_url` + key handles all of them.
`MockProvider` lets the whole swarm run offline with deterministic output,
including a simulated tool-calling loop for the agentic Developer.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Optional

from .base import LLMProvider, LLMResponse, Message, ToolCall


def _messages_to_payload(messages: list[Message]) -> list[dict]:
    """Convert our Message objects into OpenAI chat payload dicts."""
    payload: list[dict] = []
    for m in messages:
        if m.role == "tool":
            payload.append(
                {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
            )
        elif m.role == "assistant" and m.tool_calls:
            payload.append(
                {
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in m.tool_calls
                    ],
                }
            )
        else:
            payload.append({"role": m.role, "content": m.content})
    return payload


class OpenAICompatibleProvider(LLMProvider):
    """Talks to any OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self,
        name: str,
        model: str,
        api_key: str,
        base_url: str,
        *,
        max_retries: int = 4,
        request_timeout: float = 180.0,
    ) -> None:
        super().__init__(name=name, model=model)
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "The 'openai' package is required. Install with: pip install openai"
            ) from exc

        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url or None,
            timeout=request_timeout,
            max_retries=0,  # we implement our own backoff below
        )
        self._max_retries = max_retries

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tag: Optional[str] = None,
    ) -> LLMResponse:
        payload = _messages_to_payload(messages)
        last_err: Optional[Exception] = None

        for attempt in range(self._max_retries):
            try:
                kwargs: dict = {
                    "model": self.model,
                    "messages": payload,
                    "temperature": temperature,
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"

                resp = self._client.chat.completions.create(**kwargs)
                choice = resp.choices[0]
                msg = choice.message
                text = msg.content or ""

                tool_calls: list[ToolCall] = []
                for tc in getattr(msg, "tool_calls", None) or []:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {"_raw": tc.function.arguments}
                    tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

                usage = {}
                if getattr(resp, "usage", None) is not None:
                    usage = {
                        "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
                        "completion_tokens": getattr(resp.usage, "completion_tokens", None),
                        "total_tokens": getattr(resp.usage, "total_tokens", None),
                    }
                return LLMResponse(
                    text=text, model=self.model, tool_calls=tool_calls, usage=usage, raw=resp
                )
            except Exception as exc:  # noqa: BLE001 - normalize provider errors
                last_err = exc
                if attempt < self._max_retries - 1:
                    time.sleep(2 ** attempt)

        raise RuntimeError(
            f"LLM request to provider '{self.name}' (model '{self.model}') failed "
            f"after {self._max_retries} attempts: {last_err}"
        ) from last_err


# ---------------------------------------------------------------------------
# Offline provider
# ---------------------------------------------------------------------------

class MockProvider(LLMProvider):
    """Deterministic offline provider.

    Returns canned-but-coherent output keyed off the `tag` an agent passes, so
    the full pipeline runs (and its generated tests pass) with no network. For
    the agentic developer (tag="develop" with tools), it simulates a realistic
    tool-calling loop: write the file, run the tests, then finish.
    """

    def __init__(self, model: str = "mock") -> None:
        super().__init__(name="mock", model=model)

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        tools: Optional[list[dict]] = None,
        tag: Optional[str] = None,
    ) -> LLMResponse:
        if tag == "develop" and tools:
            return self._develop_step(messages)
        if tag == "test" and tools:
            return self._test_step(messages)
        text = self._respond(tag or "", messages)
        return LLMResponse(text=text, model=self.model, usage={"total_tokens": 0})

    # -- agentic developer simulation ------------------------------------

    def _develop_step(self, messages: list[Message]) -> LLMResponse:
        ctx = "\n".join(m.content for m in messages if m.content)
        fid = self._feature_id(ctx)
        fn = "add" if fid == "f1" else "multiply"
        op = "a + b" if fid == "f1" else "a * b"

        n_tool_results = sum(1 for m in messages if m.role == "tool")
        if n_tool_results == 0:
            content = f'"""Feature {fid}: {fn}."""\n\n\ndef {fn}(a, b):\n    return {op}\n'
            call = ToolCall(
                id="call_write",
                name="write_file",
                arguments={"path": f"app/{fn}.py", "content": content},
            )
        elif n_tool_results == 1:
            call = ToolCall(id="call_run", name="run_tests", arguments={})
        else:
            call = ToolCall(
                id="call_finish",
                name="finish",
                arguments={"summary": f"Implemented {fn} for {fid}."},
            )
        return LLMResponse(text="", model=self.model, tool_calls=[call], usage={"total_tokens": 0})

    def _test_step(self, messages: list[Message]) -> LLMResponse:
        ctx = "\n".join(m.content for m in messages if m.content)
        fid = self._feature_id(ctx)
        fn = "add" if fid == "f1" else "multiply"
        if fn == "add":
            body = (
                "def test_add_positive():\n    assert add(2, 3) == 5\n\n\n"
                "def test_add_zero():\n    assert add(-1, 1) == 0\n"
            )
        else:
            body = (
                "def test_multiply_positive():\n    assert multiply(2, 3) == 6\n\n\n"
                "def test_multiply_zero():\n    assert multiply(0, 5) == 0\n"
            )
        content = f"from app.{fn} import {fn}\n\n\n{body}"

        n_tool_results = sum(1 for m in messages if m.role == "tool")
        if n_tool_results == 0:
            call = ToolCall(
                id="t_write",
                name="write_file",
                arguments={"path": f"tests/test_{fn}.py", "content": content},
            )
        elif n_tool_results == 1:
            call = ToolCall(id="t_run", name="run_tests", arguments={})
        else:
            call = ToolCall(id="t_finish", name="finish", arguments={"summary": f"Tested {fn}."})
        return LLMResponse(text="", model=self.model, tool_calls=[call], usage={"total_tokens": 0})

    # -- canned responses -------------------------------------------------

    def _respond(self, tag: str, messages: list[Message]) -> str:
        ctx = "\n".join(m.content for m in messages if m.content)
        if tag == "requirements":
            return json.dumps(
                {
                    "summary": "A small demonstration service.",
                    "functional": [
                        "The system performs its core operation correctly.",
                        "The system validates input and reports errors.",
                    ],
                    "non_functional": ["Runs on the Python standard library."],
                    "assumptions": ["Offline mock run."],
                }
            )
        if tag == "architect":
            return (
                "# Architecture\n\n"
                "Single Python package with pure functions, tested with pytest. "
                "No external services.\n"
            )
        if tag == "planner":
            return json.dumps(
                {
                    "features": [
                        {
                            "id": "f1",
                            "name": "Add numbers",
                            "description": "Provide an add(a, b) function.",
                            "acceptance_criteria": ["add(2, 3) returns 5", "add(-1, 1) returns 0"],
                        },
                        {
                            "id": "f2",
                            "name": "Multiply numbers",
                            "description": "Provide a multiply(a, b) function.",
                            "acceptance_criteria": ["multiply(2, 3) returns 6", "multiply(0, 5) returns 0"],
                        },
                    ]
                }
            )
        if tag == "test":
            fid = self._feature_id(ctx)
            fn = "add" if fid == "f1" else "multiply"
            if fn == "add":
                body = (
                    "def test_add_positive():\n    assert add(2, 3) == 5\n\n\n"
                    "def test_add_zero():\n    assert add(-1, 1) == 0\n"
                )
            else:
                body = (
                    "def test_multiply_positive():\n    assert multiply(2, 3) == 6\n\n\n"
                    "def test_multiply_zero():\n    assert multiply(0, 5) == 0\n"
                )
            return (
                f"### FILE: tests/test_{fn}.py ###\n"
                f"from app.{fn} import {fn}\n\n\n{body}### END ###\n"
            )
        if tag == "review":
            return json.dumps({"approved": True, "score": 9, "issues": [], "summary": "Looks correct."})
        if tag == "security":
            return json.dumps({"approved": True, "score": 10, "issues": [], "summary": "No security issues."})
        if tag == "integrate":
            return (
                "### FILE: README.md ###\n"
                "# Generated Project\n\nBuilt by CodeSwarm (mock run).\n\nRun tests with: `pytest`\n"
                "### END ###\n"
                "### FILE: requirements.txt ###\npytest\n### END ###\n"
            )
        digest = hashlib.sha256(ctx.encode()).hexdigest()[:8]
        return f"[mock:{tag or 'generic'}:{digest}]"

    @staticmethod
    def _feature_id(ctx: str) -> str:
        m = re.search(r'"?id"?\s*[:=]\s*"?(f\d+)"?', ctx) or re.search(r"\b(f\d+)\b", ctx)
        return m.group(1) if m else "f1"
