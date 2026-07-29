"""The orchestrator: wires agents together and runs the SDLC with a quality gate.

Flow:
    requirements -> architecture -> plan (features)
    build features:                       <-- the swarm quality loop, per feature
        (sequentially, OR in parallel with isolated workspaces + a merge gate)
        repeat up to N times:
            developer AGENT edits code via tools + runs tests (self-correcting)
            tester writes tests
            run pytest                      <-- objective gate #1
            reviewer reviews                <-- subjective gate #2
            if tests pass AND review approves -> feature DONE
            else -> feed failures back and retry
    (parallel only) merge features -> run full suite -> integration-repair loop
    integrator writes README/requirements
    -> final report

A feature is only ever marked DONE when its tests pass *and* the reviewer signs
off. In parallel mode, features build in isolated scratch directories and are
then merged and re-verified as a whole, with a repair loop for any cross-feature
breakage — so the final project passes its *combined* suite, not just per-feature.
"""

from __future__ import annotations

import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .agents import (
    ArchitectAgent,
    DeveloperAgent,
    IntegratorAgent,
    PlannerAgent,
    RequirementsAgent,
    ReviewerAgent,
    SecurityReviewerAgent,
    TesterAgent,
)
from .config import resolve_role
from .llm import build_provider
from .models import Feature, FeatureStatus, ProjectState, TestOutcome
from .sandbox import run_pytest
from .tools import build_dev_toolbox, build_tester_toolbox
from .workspace import Workspace


@dataclass
class FeatureBuild:
    """Files a single feature produced during its (possibly isolated) build."""

    source_files: dict[str, str] = field(default_factory=dict)
    test_files: dict[str, str] = field(default_factory=dict)


@dataclass
class RunResult:
    state: ProjectState
    output_dir: str
    features_done: int
    features_failed: int
    integration_ok: bool = True
    report: dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.features_failed == 0 and self.features_done > 0 and self.integration_ok


EventHook = Callable[[str, str], None]


class Swarm:
    """Builds one project from an idea."""

    def __init__(self, config: dict, *, on_event: Optional[EventHook] = None) -> None:
        self.config = config
        self.swarm_cfg = config.get("swarm", {})
        self._on_event = on_event or (lambda role, msg: None)

        temp = float(self.swarm_cfg.get("temperature", 0.2))

        def make(role_name: str, agent_cls):
            provider_name, provider_cfg, role_cfg = resolve_role(config, role_name)
            provider = build_provider(
                provider_name, provider_cfg, model_override=role_cfg.get("model")
            )
            role_temp = float(role_cfg.get("temperature", temp))
            return agent_cls(provider, temperature=role_temp, on_event=self._on_event)

        self.requirements_agent: RequirementsAgent = make("requirements", RequirementsAgent)
        self.architect_agent: ArchitectAgent = make("architect", ArchitectAgent)
        self.planner_agent: PlannerAgent = make("planner", PlannerAgent)
        self.developer_agent: DeveloperAgent = make("developer", DeveloperAgent)
        self.tester_agent: TesterAgent = make("tester", TesterAgent)
        self.reviewer_agent: ReviewerAgent = make("reviewer", ReviewerAgent)
        self.security_agent: SecurityReviewerAgent = make("security", SecurityReviewerAgent)
        self.integrator_agent: IntegratorAgent = make("integrator", IntegratorAgent)

        # Cached swarm knobs.
        self.max_iter = int(self.swarm_cfg.get("max_feature_iterations", 3))
        self.run_tests = bool(self.swarm_cfg.get("run_tests", True))
        self.test_timeout = int(self.swarm_cfg.get("test_timeout_seconds", 120))
        self.dev_max_steps = int(self.swarm_cfg.get("developer_max_steps", 8))
        self.parallel = bool(self.swarm_cfg.get("parallel_features", True))
        self.max_parallel = int(self.swarm_cfg.get("max_parallel_features", 4))
        self.target_language = self.swarm_cfg.get("target_language", "python")
        self.verbose = bool(self.swarm_cfg.get("verbose", False))

    # -- helpers ----------------------------------------------------------

    def _event(self, role: str, msg: str) -> None:
        self._on_event(role, msg)

    @staticmethod
    def _slugify(idea: str) -> str:
        words = re.findall(r"[a-zA-Z0-9]+", idea.lower())
        slug = "-".join(words[:5]) or "project"
        return slug[:48]

    def _neutral_or_pytest(self, ws: Workspace) -> TestOutcome:
        if self.run_tests and self.target_language == "python":
            return run_pytest(ws.root, timeout=self.test_timeout)
        return TestOutcome(passed=True, returncode=0, output="(test execution skipped)")

    # -- main entry -------------------------------------------------------

    def build(self, idea: str, *, project_name: Optional[str] = None, output_dir: Optional[str] = None) -> RunResult:
        name = project_name or self._slugify(idea)
        base_out = Path(output_dir or self.swarm_cfg.get("output_dir", "./output"))
        workdir = base_out / name
        ws = Workspace(workdir)
        ws.ensure_conftest()

        state = ProjectState(idea=idea, name=name, target_language=self.target_language)

        # Phase 1: requirements  (persisted immediately)
        self._event("orchestrator", "Phase 1/5 — Requirements")
        state.requirements = self.requirements_agent.analyze(idea)
        self._save_requirements(ws, state)
        self._event("requirements", f"saved → .codeswarm/requirements.md")
        self._event("requirements", f"summary: {state.requirements.summary}")

        # Phase 2: architecture  (persisted immediately)
        self._event("orchestrator", "Phase 2/5 — Architecture")
        state.design = self.architect_agent.design(idea, state.requirements)
        ws.write_file(".codeswarm/design.md", state.design or "")
        self._event("architect", "saved → .codeswarm/design.md")
        if self.verbose:
            self._event("architect", "\n" + (state.design or ""))

        # Phase 3: planning  (persisted immediately, plan printed live)
        self._event("orchestrator", "Phase 3/5 — Planning")
        state.features = self.planner_agent.plan(idea, state.requirements, state.design)
        self._save_plan(ws, state)
        self._event("planner", f"planned {len(state.features)} feature(s) → .codeswarm/plan.md")
        for f in state.features:
            self._event("planner", f"  • {f.id}: {f.name}")
            if self.verbose:
                for c in f.acceptance_criteria:
                    self._event("planner", f"      - {c}")
        # Write an initial report now so it exists during the (long) build phase.
        self._persist_report(ws, state, integration_ok=True)

        # Phase 4: build features (sequential or parallel)
        integration_ok = True
        if self.parallel and len(state.features) > 1:
            self._event("orchestrator", f"Phase 4/5 — Build/Test/Review (parallel x{self.max_parallel})")
            integration_ok = self._build_parallel(ws, state, base_out)
        else:
            self._event("orchestrator", "Phase 4/5 — Build/Test/Review (sequential)")
            self._build_sequential(ws, state)
        # Refresh the report now that all features are built (before integration).
        self._persist_report(ws, state, integration_ok)

        # Phase 5: integration
        self._event("orchestrator", "Phase 5/5 — Integration")
        scaffold = self.integrator_agent.finalize(state)
        for path, content in scaffold.items():
            if path in state.source_files or path in state.test_files:
                continue
            ws.write_file(path, content)

        report = self._persist_report(ws, state, integration_ok)
        done = sum(1 for f in state.features if f.status == FeatureStatus.DONE)
        failed = sum(1 for f in state.features if f.status == FeatureStatus.FAILED)
        return RunResult(
            state=state,
            output_dir=str(ws.root),
            features_done=done,
            features_failed=failed,
            integration_ok=integration_ok,
            report=report,
        )

    # -- sequential build -------------------------------------------------

    def _build_sequential(self, ws: Workspace, state: ProjectState) -> None:
        for feature in state.features:
            build = self._build_feature(ws, state.design, feature)
            state.source_files.update(build.source_files)
            state.test_files.update(build.test_files)

    # -- parallel build + merge + repair ---------------------------------

    def _build_parallel(self, ws: Workspace, state: ProjectState, base_out: Path) -> bool:
        scratch_root = base_out / f".{state.name}__scratch"
        builds: dict[str, FeatureBuild] = {}

        def work(feature: Feature) -> tuple[Feature, FeatureBuild]:
            fws = Workspace(scratch_root / feature.id)
            fws.ensure_conftest()
            try:
                build = self._build_feature(fws, state.design, feature)
            except Exception as exc:  # noqa: BLE001 - isolate a worker failure
                feature.status = FeatureStatus.FAILED
                feature.log.append(f"worker error: {exc}")
                build = FeatureBuild()
            return feature, build

        workers = min(self.max_parallel, len(state.features))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(work, f) for f in state.features]
            for fut in as_completed(futures):
                feature, build = fut.result()
                builds[feature.id] = build

        # Merge all feature outputs into the main workspace.
        for feature in state.features:
            build = builds.get(feature.id, FeatureBuild())
            state.source_files.update(build.source_files)
            state.test_files.update(build.test_files)
        ws.write_files(state.source_files)
        ws.write_files(state.test_files)

        # Cross-feature regression gate on the *combined* project.
        integration_ok = True
        if self.run_tests and self.target_language == "python":
            outcome = run_pytest(ws.root, timeout=self.test_timeout)
            if outcome.passed:
                self._event("orchestrator", "Merged suite PASSED ✓")
            else:
                self._event("orchestrator", "Merged suite FAILED — running integration repair")
                integration_ok = self._repair_integration(ws, state, outcome)

        # Clean up scratch dirs.
        shutil.rmtree(scratch_root, ignore_errors=True)
        return integration_ok

    def _repair_integration(self, ws: Workspace, state: ProjectState, outcome: TestOutcome) -> bool:
        toolbox = build_dev_toolbox(ws, test_timeout=self.test_timeout)
        for attempt in range(1, self.max_iter + 1):
            self._event("orchestrator", f"[integration] repair attempt {attempt}/{self.max_iter}")
            self.developer_agent.repair(
                state.design, outcome.output, toolbox, max_steps=self.dev_max_steps + 2
            )
            outcome = run_pytest(ws.root, timeout=self.test_timeout)
            if outcome.passed:
                # Re-capture fixed files.
                state.source_files = ws.snapshot(tests=False)
                state.test_files = ws.snapshot(tests=True)
                self._event("orchestrator", "[integration] repaired ✓")
                return True
        self._event("orchestrator", "[integration] could not fully repair ✗")
        state.source_files = ws.snapshot(tests=False)
        state.test_files = ws.snapshot(tests=True)
        return False

    # -- the per-feature quality loop ------------------------------------

    def _build_feature(self, ws: Workspace, design: str, feature: Feature) -> FeatureBuild:
        """Build/test/review one feature inside workspace `ws`. Thread-safe:
        it only reads the immutable `design` and mutates its own workspace +
        the feature's own status fields.
        """
        dev_toolbox = build_dev_toolbox(ws, test_timeout=self.test_timeout)
        test_toolbox = build_tester_toolbox(ws, test_timeout=self.test_timeout)
        feature.status = FeatureStatus.IN_PROGRESS
        feedback = ""

        for attempt in range(1, self.max_iter + 1):
            feature.attempts = attempt
            self._event("orchestrator", f"[{feature.id}] attempt {attempt}/{self.max_iter}")

            # 1) Developer agent implements/fixes the feature via tools.
            self.developer_agent.implement(
                design, feature, dev_toolbox, feedback=feedback, max_steps=self.dev_max_steps
            )
            source = ws.snapshot(tests=False)

            # 2) Tester agent writes/inspects tests via tools (coverage-aware).
            self.tester_agent.write_tests(
                feature, test_toolbox, feedback=feedback, max_steps=self.dev_max_steps
            )
            all_tests = ws.snapshot(tests=True)

            # 3) Objective gate: run the tests.
            outcome = self._neutral_or_pytest(ws)
            feature.tests_passed = outcome.passed
            self._event(
                "tester",
                f"[{feature.id}] tests {'PASSED' if outcome.passed else 'FAILED'} (exit {outcome.returncode})",
            )

            # 4) Subjective gate: correctness review.
            review = self.reviewer_agent.review(feature, source, all_tests, outcome)
            feature.review_approved = review.approved
            feature.review_score = review.score
            self._event(
                "reviewer",
                f"[{feature.id}] {'APPROVED' if review.approved else 'CHANGES REQUESTED'}"
                + (f" (score {review.score})" if review.score is not None else ""),
            )

            # 5) Third gate: security review.
            security = self.security_agent.review(feature, source)
            feature.security_approved = security.approved
            self._event(
                "security",
                f"[{feature.id}] {'CLEARED' if security.approved else 'BLOCKED'}"
                + (f" (score {security.score})" if security.score is not None else ""),
            )

            feature.log.append(
                f"attempt {attempt}: tests={'pass' if outcome.passed else 'fail'}, "
                f"review={'approved' if review.approved else 'rejected'}, "
                f"security={'cleared' if security.approved else 'blocked'}"
            )

            # 6) All THREE gates must pass.
            if outcome.passed and review.approved and security.approved:
                feature.status = FeatureStatus.DONE
                self._event("orchestrator", f"[{feature.id}] DONE ✓")
                return FeatureBuild(source_files=source, test_files=all_tests)

            feedback = self._compile_feedback(outcome, review, security)

        feature.status = FeatureStatus.FAILED
        self._event("orchestrator", f"[{feature.id}] FAILED after {self.max_iter} attempts ✗")
        return FeatureBuild(source_files=ws.snapshot(tests=False), test_files=ws.snapshot(tests=True))

    @staticmethod
    def _compile_feedback(outcome: TestOutcome, review, security=None) -> str:
        parts = []
        if not outcome.passed:
            parts.append("TESTS ARE FAILING. Full test output:\n" + outcome.output.strip())
        if not review.approved:
            parts.append("CODE REVIEW REQUESTED CHANGES:")
            if review.summary:
                parts.append(f"- summary: {review.summary}")
            for issue in review.issues:
                parts.append(f"- {issue}")
        if security is not None and not security.approved:
            parts.append("SECURITY REVIEW BLOCKED — fix these vulnerabilities:")
            if security.summary:
                parts.append(f"- summary: {security.summary}")
            for issue in security.issues:
                parts.append(f"- {issue}")
        return "\n".join(parts)

    # -- per-phase artifact persistence ----------------------------------

    def _save_requirements(self, ws: Workspace, state: ProjectState) -> None:
        """Write requirements as JSON + a human-readable Markdown file."""
        req = state.requirements
        if not req:
            return
        ws.write_file(".codeswarm/requirements.json", json.dumps(req.to_dict(), indent=2))
        lines = [f"# Requirements — {state.name}", "", f"**Idea:** {state.idea}", "",
                 f"## Summary", req.summary or "", "", "## Functional"]
        lines += [f"- {r}" for r in req.functional] or ["- (none)"]
        lines += ["", "## Non-functional"] + ([f"- {r}" for r in req.non_functional] or ["- (none)"])
        lines += ["", "## Assumptions"] + ([f"- {r}" for r in req.assumptions] or ["- (none)"])
        ws.write_file(".codeswarm/requirements.md", "\n".join(lines) + "\n")

    def _save_plan(self, ws: Workspace, state: ProjectState) -> None:
        """Write the feature plan as JSON + a human-readable Markdown file."""
        plan = [
            {
                "id": f.id,
                "name": f.name,
                "description": f.description,
                "acceptance_criteria": f.acceptance_criteria,
            }
            for f in state.features
        ]
        ws.write_file(".codeswarm/plan.json", json.dumps({"features": plan}, indent=2))
        lines = [f"# Feature Plan — {state.name}", "",
                 f"{len(state.features)} feature(s) planned.", ""]
        for f in state.features:
            lines += [f"## {f.id}: {f.name}", "", f.description or "", "", "**Acceptance criteria:**"]
            lines += [f"- {c}" for c in f.acceptance_criteria] or ["- (none)"]
            lines += [""]
        ws.write_file(".codeswarm/plan.md", "\n".join(lines) + "\n")

    # -- reporting --------------------------------------------------------

    def _persist_report(self, ws: Workspace, state: ProjectState, integration_ok: bool) -> dict:
        """Write/refresh report.json. Idempotent — called after each phase so the
        report exists and updates on disk *during* the run, not only at the end."""
        report = {
            "project": state.name,
            "idea": state.idea,
            "requirements": state.requirements.to_dict() if state.requirements else None,
            "features": [f.to_dict() for f in state.features],
            "integration_ok": integration_ok,
            "summary": {
                "total": len(state.features),
                "done": sum(1 for f in state.features if f.status == FeatureStatus.DONE),
                "failed": sum(1 for f in state.features if f.status == FeatureStatus.FAILED),
            },
        }
        ws.write_file(".codeswarm/report.json", json.dumps(report, indent=2))
        return report
