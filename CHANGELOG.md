# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added
- `codeswarm doctor` — one-shot setup diagnosis: config, API key (masked
  fingerprint + whether it comes from .env or a shadowing shell export), live
  connectivity, and whether the model supports tool-calling.
- Per-phase artifact persistence: `.codeswarm/requirements.md`/`.json`,
  `design.md`, `plan.md`/`.json`, and a `report.json` refreshed after each phase
  — written *during* the run so you can inspect or `tail -f` them live.
- `build --verbose/-v` streams requirements, full design, and acceptance criteria
  to the console as they are produced.

### Fixed
- `.env` is now authoritative over stale shell exports (`load_dotenv(override=True)`);
  keys are sanitized (whitespace/quotes/`Bearer`); 401s show a masked key
  fingerprint and remediation hint.

## [0.1.0] — 2026-07-29

Initial release.

### Framework
- Standalone, vendor-neutral multi-agent SDLC framework in Python. No dependency
  on Claude Code or any single LLM vendor.
- Provider abstraction over an OpenAI-compatible client supporting **BytePlus
  ModelArk**, **OpenAI**, and **Google Gemini**, plus an offline **mock**
  provider for demos/CI. Per-role provider/model overrides.

### The swarm
- Agents: Requirements, Architect, Planner, Developer, Tester, Reviewer,
  Security Reviewer, Integrator, driven by an Orchestrator.
- **Agentic Developer** — a real tool-using loop (`list_files`, `read_file`,
  `write_file`, `run_tests`, `finish`) that inspects the project, edits files,
  runs the tests, and self-corrects.
- **Agentic Tester** — writes tests and uses `check_coverage` to find and close
  uncovered lines.

### Quality gates
- Per feature, up to `max_feature_iterations` attempts, gated by **three**
  checks that must all pass before a feature is `DONE`:
  1. objective — the pytest suite actually runs and passes;
  2. correctness — an independent reviewer approves;
  3. security — a dedicated security reviewer clears it.
- Failing features are marked `FAILED` and reported, never silently shipped.

### Execution
- **Parallel feature building** (default): independent features build in
  isolated workspaces concurrently, then merge and re-run the full combined
  suite, with an **integration-repair loop** for cross-feature breakage.
- `--sequential` and `--max-parallel N` to control it.

### Tooling & docs
- CLI (`codeswarm build`) with rich progress output and a per-feature results
  table. Runs from a one-line `--idea` or a YAML `--spec`.
- Example specs (`todo_api`, `password_strength`, `csv_stats`) and a reproducible
  evaluation harness (`scripts/run_eval.sh`) that builds each spec and then
  independently re-runs its generated tests.
- README (incl. a Quick-evaluation demo), ARCHITECTURE, CONTRIBUTING, and an
  offline test suite.
