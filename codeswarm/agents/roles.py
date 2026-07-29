"""Concrete agent roles."""

from __future__ import annotations

from ..models import Feature, ProjectState, Requirements, ReviewOutcome, TestOutcome
from ..tools import Toolbox
from ..utils import extract_json, file_blocks, parse_file_blocks
from . import prompts
from .base import Agent


def _truncate(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


class RequirementsAgent(Agent):
    role = "requirements"

    def analyze(self, idea: str) -> Requirements:
        self.emit("Analyzing the idea into testable requirements...")
        reply = self.chat(
            prompts.REQUIREMENTS_SYSTEM,
            f"Product idea:\n{idea}",
            tag="requirements",
        )
        data = extract_json(reply)
        return Requirements(
            summary=data.get("summary", ""),
            functional=list(data.get("functional", [])),
            non_functional=list(data.get("non_functional", [])),
            assumptions=list(data.get("assumptions", [])),
        )


class ArchitectAgent(Agent):
    role = "architect"

    def design(self, idea: str, requirements: Requirements) -> str:
        self.emit("Designing the architecture...")
        user = (
            f"Product idea:\n{idea}\n\n"
            f"Requirements:\n{requirements.to_dict()}"
        )
        return self.chat(prompts.ARCHITECT_SYSTEM, user, tag="architect").strip()


class PlannerAgent(Agent):
    role = "planner"

    def plan(self, idea: str, requirements: Requirements, design: str) -> list[Feature]:
        self.emit("Breaking the design into features...")
        user = (
            f"Product idea:\n{idea}\n\n"
            f"Requirements:\n{requirements.to_dict()}\n\n"
            f"Design:\n{design}"
        )
        data = extract_json(self.chat(prompts.PLANNER_SYSTEM, user, tag="planner"))
        features: list[Feature] = []
        for i, raw in enumerate(data.get("features", []), start=1):
            features.append(
                Feature(
                    id=str(raw.get("id") or f"f{i}"),
                    name=raw.get("name", f"Feature {i}"),
                    description=raw.get("description", ""),
                    acceptance_criteria=list(raw.get("acceptance_criteria", [])),
                )
            )
        return features


class DeveloperAgent(Agent):
    """Agentic developer: reads/writes/tests the project via tools in a loop.

    This mirrors how Anthropic's own coding agents work — the model inspects the
    real codebase, edits files, runs the tests, sees the output, and iterates —
    rather than emitting code blind in a single shot.
    """

    role = "developer"

    def implement(
        self,
        design: str,
        feature: Feature,
        toolbox: Toolbox,
        *,
        feedback: str = "",
        max_steps: int = 8,
    ) -> None:
        self.emit(f"Implementing feature '{feature.name}'...")
        user = (
            f"DESIGN:\n{design}\n\n"
            f"TARGET FEATURE ({feature.id}): {feature.name}\n"
            f"{feature.description}\n"
            f"Acceptance criteria:\n- " + "\n- ".join(feature.acceptance_criteria) + "\n\n"
            "Start by listing and reading the existing files, then implement this feature."
        )
        if feedback:
            user += (
                f"\n\nFEEDBACK TO ADDRESS (fix all of this):\n{_truncate(feedback, 4000)}"
            )
        # The loop writes files directly to the workspace via the toolbox; the
        # pipeline snapshots the result afterwards.
        self.run_tool_loop(
            prompts.DEVELOPER_SYSTEM, user, toolbox, tag="develop", max_steps=max_steps
        )

    def repair(self, design: str, failure_output: str, toolbox: Toolbox, *, max_steps: int = 10) -> None:
        """Fix a failing *combined* test suite after features are merged."""
        self.emit("Repairing cross-feature integration failures...")
        user = (
            f"DESIGN:\n{design}\n\n"
            "The combined project's test suite is FAILING after several features were "
            "merged together. Investigate with list_files/read_file, run_tests to see "
            "failures, fix the source so ALL tests pass, and call finish.\n\n"
            f"Latest test output:\n{_truncate(failure_output, 4000)}"
        )
        self.run_tool_loop(
            prompts.DEVELOPER_SYSTEM, user, toolbox, tag="develop", max_steps=max_steps
        )


class TesterAgent(Agent):
    """Agentic tester: reads source, writes tests, runs them, and inspects
    coverage via tools until the feature is well covered."""

    role = "tester"

    def write_tests(
        self,
        feature: Feature,
        toolbox: Toolbox,
        *,
        feedback: str = "",
        max_steps: int = 8,
    ) -> None:
        self.emit(f"Writing tests for '{feature.name}'...")
        user = (
            f"TARGET FEATURE ({feature.id}): {feature.name}\n"
            f"{feature.description}\n"
            f"Acceptance criteria:\n- " + "\n- ".join(feature.acceptance_criteria) + "\n\n"
            f"Put this feature's tests in tests/test_{feature.id}.py. Start by reading "
            "the source under app/."
        )
        if feedback:
            user += f"\n\nCONTEXT FROM PREVIOUS ATTEMPT:\n{_truncate(feedback, 3000)}"
        self.run_tool_loop(
            prompts.TESTER_SYSTEM, user, toolbox, tag="test", max_steps=max_steps
        )


class SecurityReviewerAgent(Agent):
    """Third gate: an application-security review independent of correctness."""

    role = "security"

    def review(self, feature: Feature, source_files: dict[str, str]) -> ReviewOutcome:
        self.emit(f"Security review of '{feature.name}'...")
        source = file_blocks(source_files) if source_files else "(none)"
        user = (
            f"FEATURE ({feature.id}): {feature.name}\n{feature.description}\n\n"
            f"IMPLEMENTATION:\n{_truncate(source)}\n"
        )
        data = extract_json(self.chat(prompts.SECURITY_SYSTEM, user, tag="security"))
        return ReviewOutcome(
            approved=bool(data.get("approved", False)),
            score=data.get("score"),
            issues=list(data.get("issues", [])),
            summary=data.get("summary", ""),
        )


class ReviewerAgent(Agent):
    role = "reviewer"

    def review(
        self,
        feature: Feature,
        source_files: dict[str, str],
        test_files: dict[str, str],
        test_outcome: TestOutcome,
    ) -> ReviewOutcome:
        self.emit(f"Reviewing '{feature.name}'...")
        source = file_blocks(source_files) if source_files else "(none)"
        tests = file_blocks(test_files) if test_files else "(none)"
        user = (
            f"TARGET FEATURE ({feature.id}): {feature.name}\n"
            f"{feature.description}\n"
            f"Acceptance criteria:\n- " + "\n- ".join(feature.acceptance_criteria) + "\n\n"
            f"IMPLEMENTATION:\n{_truncate(source)}\n\n"
            f"TESTS:\n{_truncate(tests)}\n\n"
            f"TEST RUN: {'PASSED' if test_outcome.passed else 'FAILED'} "
            f"(exit {test_outcome.returncode})\n{_truncate(test_outcome.output, 3000)}\n"
        )
        data = extract_json(self.chat(prompts.REVIEWER_SYSTEM, user, tag="review"))
        return ReviewOutcome(
            approved=bool(data.get("approved", False)),
            score=data.get("score"),
            issues=list(data.get("issues", [])),
            summary=data.get("summary", ""),
        )


class IntegratorAgent(Agent):
    role = "integrator"

    def finalize(self, state: ProjectState) -> dict[str, str]:
        self.emit("Integrating and writing project scaffolding...")
        listing = "\n".join(sorted(state.all_files()))
        user = (
            f"PROJECT: {state.name}\n"
            f"IDEA: {state.idea}\n\n"
            f"FILES IN PROJECT:\n{listing}\n\n"
            f"Produce README.md and requirements.txt as file blocks."
        )
        reply = self.chat(prompts.INTEGRATOR_SYSTEM, user, tag="integrate")
        return {pf.path: pf.content for pf in parse_file_blocks(reply)}
