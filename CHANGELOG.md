# Changelog

All notable changes to this project are documented here.

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
- README, ARCHITECTURE, CONTRIBUTING, example spec, and an offline test suite.
