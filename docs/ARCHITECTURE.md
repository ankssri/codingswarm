# CodeSwarm Architecture

This document explains how CodeSwarm is put together and why, in more depth than
the README. Read the README first for the quickstart and the big picture.

## Design goals

1. **Vendor-neutral.** No dependency on any single LLM vendor or on Claude Code.
   Runs anywhere Python runs, driven by plain HTTP APIs.
2. **Quality is verified, not asserted.** Generated code must pass *executed*
   tests and independent review before a feature counts as done.
3. **Simple core, extensible edges.** The orchestration is deterministic Python
   (easy to reason about); the intelligence lives in swappable agents and tools.

## Layers

```
 CLI (cli.py)
   │  parses args, loads config, prints progress
   ▼
 Orchestrator  (pipeline.py :: Swarm)
   │  runs the SDLC phases + the per-feature quality loop
   ├── Agents (agents/)          specialist roles, one responsibility each
   │      │ every agent calls ▼
   │   LLM providers (llm/)      OpenAI-compatible client (BytePlus/OpenAI/Gemini) + mock
   │
   ├── Tools (tools.py)          local read/write/run/coverage tools for agent loops
   ├── Workspace (workspace.py)  guarded file writes + snapshots of the project
   └── Sandbox (sandbox.py)      executes pytest / coverage as the objective gate
```

### `llm/` — provider abstraction

- `base.py` defines `Message`, `ToolCall`, `LLMResponse`, and the `LLMProvider`
  interface (one method: `complete`).
- `providers.py` has `OpenAICompatibleProvider` (used for OpenAI, BytePlus
  ModelArk, and Gemini — they all speak the OpenAI chat + tool-calling protocol)
  and `MockProvider` (deterministic offline output, including a simulated
  tool-calling loop, so the whole system runs with no keys).
- `factory.py` builds a provider from config and resolves the API key from env.

Adding a provider = add one class or reuse `OpenAICompatibleProvider` with a new
`base_url`, then add a block under `providers:` in config.

### `agents/` — the swarm

Each role is a small class over a provider:

| Role | Kind | Output |
|---|---|---|
| Requirements | one-shot | structured requirements (JSON) |
| Architect | one-shot | design (Markdown) |
| Planner | one-shot | features + acceptance criteria (JSON) |
| Developer | **agentic loop** | edits files on disk via tools |
| Tester | **agentic loop** | writes tests + inspects coverage via tools |
| Reviewer | one-shot | approve/score/issues (JSON) |
| Security Reviewer | one-shot | approve/score/issues (JSON) |
| Integrator | one-shot | README + requirements files |

`base.py` provides both `chat()` (single turn) and `run_tool_loop()` (the agentic
loop: model → tool calls → results → model … until `finish`).

### `tools.py` — local tools (not MCP)

`build_dev_toolbox` and `build_tester_toolbox` bind `list_files`, `read_file`,
`write_file`, `run_tests`, `check_coverage`, and `finish` to a specific
`Workspace`. These are deliberately **in-process, local** functions — the inner
build loop shouldn't pay a network hop. An external system (live docs, DB schema,
tickets, GitHub) is where **MCP** belongs: wrap an MCP client call as a `Tool`
handler and add it to a toolbox; the agent loop treats it identically.

### `pipeline.py` — orchestration & the quality loop

`Swarm.build()` runs five phases: requirements → architecture → planning →
feature build → integration.

The feature-build phase is the heart. For each feature, `_build_feature` runs up
to `max_feature_iterations` attempts of:

1. Developer agent edits code (tools).
2. Tester agent writes/inspects tests (tools).
3. **Gate 1** — run the suite (`sandbox.run_pytest`).
4. **Gate 2** — correctness review.
5. **Gate 3** — security review.
6. If all three pass → `DONE`; else compile the failures into feedback and retry.

**Parallel mode** (default): independent features build concurrently, each in an
isolated scratch `Workspace`, via a `ThreadPoolExecutor`. Agents are stateless
per call and the Tester/Reviewer/Security agents take files as arguments (not
shared mutable state), so parallel execution is race-free. After the barrier, all
features are merged into the main workspace and the **full combined suite** runs;
any cross-feature breakage triggers `_repair_integration`, which puts the agentic
developer on the merged project until the whole suite is green.

## Concurrency & isolation notes

- Parallel workers write to separate directories; the merge is a union of files.
  A genuine same-path conflict is last-writer-wins — the integration-repair loop
  is the safety net, not a 3-way merge. Features that touch disjoint files (the
  common case, one module per feature) merge cleanly.
- The test sandbox runs generated code in a subprocess with a timeout, using the
  interpreter that runs CodeSwarm. For untrusted specs, run inside a container or
  disposable VM (see the README security note).

## Extending

- **New gate** (e.g. performance, style): add an agent + prompt, call it in
  `_build_feature`, and include it in the DONE condition + feedback.
- **New tool** (incl. MCP-backed): add a `Tool` in `tools.py`.
- **New target language:** add a runner alongside `run_pytest` in `sandbox.py`
  and branch on `swarm.target_language` in the pipeline.
- **Durable/resumable runs:** the per-feature state is serializable
  (`ProjectState.to_dict`); persisting it between phases would enable resume.
