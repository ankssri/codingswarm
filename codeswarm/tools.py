"""Local, in-process tools for the agentic Developer.

These are plain Python functions bound to a Workspace — deliberately NOT MCP.
The inner build loop (read / write / run tests) is local to the machine, so
wrapping it in an external tool-server protocol would only add latency and
failure surface. MCP is the right choice for *external* systems (live API docs,
real DB schemas, ticketing); such tools can be added to a Toolbox as extra
entries via an adapter without changing anything here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .sandbox import run_coverage, run_pytest
from .workspace import Workspace


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema for the arguments object
    handler: Callable[..., str]

    def spec(self) -> dict:
        """OpenAI-style tool spec."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class Toolbox:
    """A named collection of tools the agent loop can call."""

    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {t.name: t for t in tools}

    def specs(self) -> list[dict]:
        return [t.spec() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def invoke(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"ERROR: unknown tool '{name}'. Available: {', '.join(self._tools)}"
        try:
            return tool.handler(**(arguments or {}))
        except TypeError as exc:
            return f"ERROR: bad arguments for '{name}': {exc}"
        except Exception as exc:  # noqa: BLE001 - surface tool errors to the model
            return f"ERROR while running '{name}': {exc}"


# ---------------------------------------------------------------------------
# Developer toolbox factory
# ---------------------------------------------------------------------------

_MAX_TOOL_OUTPUT = 8000


def _clip(text: str, limit: int = _MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[clipped {len(text) - limit} chars]"


def build_dev_toolbox(workspace: Workspace, *, test_timeout: int = 120) -> Toolbox:
    """Tools that let a developer agent inspect, edit, and verify the project."""

    def list_files() -> str:
        paths = []
        for p in sorted(workspace.root.rglob("*")):
            if p.is_dir():
                continue
            rel = p.relative_to(workspace.root)
            if rel.parts and rel.parts[0] in {".codeswarm", "__pycache__", ".pytest_cache"}:
                continue
            paths.append(str(rel))
        return "\n".join(paths) if paths else "(empty project)"

    def read_file(path: str) -> str:
        try:
            return _clip(workspace.read_file(path))
        except FileNotFoundError:
            return f"ERROR: file not found: {path}"

    def write_file(path: str, content: str) -> str:
        workspace.write_file(path, content)
        return f"Wrote {path} ({len(content)} bytes)."

    def run_tests() -> str:
        outcome = run_pytest(workspace.root, timeout=test_timeout)
        status = "PASSED" if outcome.passed else "FAILED"
        return _clip(f"pytest {status} (exit {outcome.returncode})\n{outcome.output}")

    def finish(summary: str = "") -> str:
        return "Done."

    return Toolbox(
        [
            Tool(
                name="list_files",
                description="List all files currently in the project.",
                parameters={"type": "object", "properties": {}},
                handler=list_files,
            ),
            Tool(
                name="read_file",
                description="Read the full contents of a file by its project-relative path.",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                handler=read_file,
            ),
            Tool(
                name="write_file",
                description="Create or overwrite a file with the given full contents.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "project-relative path"},
                        "content": {"type": "string", "description": "the complete file contents"},
                    },
                    "required": ["path", "content"],
                },
                handler=write_file,
            ),
            Tool(
                name="run_tests",
                description="Run the project's pytest suite and return the output. Use this to check your work.",
                parameters={"type": "object", "properties": {}},
                handler=run_tests,
            ),
            Tool(
                name="finish",
                description="Call when the feature is implemented and its tests pass. Provide a short summary.",
                parameters={
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                },
                handler=finish,
            ),
        ]
    )


def build_tester_toolbox(workspace: Workspace, *, test_timeout: int = 120) -> Toolbox:
    """Tools for the agentic Tester: inspect source, write tests, run, check coverage."""
    dev = build_dev_toolbox(workspace, test_timeout=test_timeout)

    def check_coverage() -> str:
        return _clip(run_coverage(workspace.root, timeout=test_timeout))

    # Reuse read/list/write/run/finish; add coverage inspection.
    tools = [dev._tools[n] for n in ("list_files", "read_file", "write_file", "run_tests")]
    tools.append(
        Tool(
            name="check_coverage",
            description=(
                "Run the tests under coverage and report which source lines in `app/` are "
                "NOT yet covered. Use this to find gaps and add tests for them."
            ),
            parameters={"type": "object", "properties": {}},
            handler=check_coverage,
        )
    )
    tools.append(dev._tools["finish"])
    return Toolbox(tools)
