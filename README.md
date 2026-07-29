# CodeSwarm 🐝

**A provider-agnostic swarm of LLM agents that builds, tests, and reviews software one feature at a time.**

CodeSwarm automates the software lifecycle you currently step through by hand —
requirements → design → planning → build → test → review → integration — and
enforces a **quality gate** so a feature is only ever marked *done* when its
tests pass **and** an independent reviewer agent approves it.

It runs as a **standalone Python program**. There is **no dependency on Claude,
Claude Code, or any single vendor** — it talks to LLMs over plain HTTP APIs.
Anyone with Python and an API key can run it. Supported providers out of the
box: **BytePlus ModelArk**, **OpenAI**, and **Google Gemini** (and an offline
**mock** provider for demos/CI).

---

## Why this exists

Today you ask an assistant to do each phase and you babysit every step. CodeSwarm
turns that into a repeatable pipeline where **specialist agents** each own a
phase, and an **orchestrator** drives them through an automatic build/test/review
loop per feature. You give it an idea; you get back a generated project plus a
report of exactly which features passed their gates.

---

## The swarm

| Agent | Role |
|---|---|
| **Requirements** | Turns your idea into concrete, testable functional/non-functional requirements. |
| **Architect** | Produces a minimal technical design and file layout. |
| **Planner** | Splits the design into 2–6 independently buildable, independently testable **features** with acceptance criteria. |
| **Developer** | **Agentic** — uses tools (`list_files`, `read_file`, `write_file`, `run_tests`) in a loop to inspect the real project, edit files, run the tests, read the output, and fix its own mistakes before handing off. |
| **Tester** | **Agentic** — reads the source, writes pytest tests, runs them, and uses `check_coverage` to find uncovered lines and close the gaps. |
| **Reviewer** | Correctness gate — approves only if the code is correct *and* adequately tested. |
| **Security Reviewer** | Dedicated security gate — scans for injection, unsafe `eval`/`exec`, path traversal, hardcoded secrets, unsafe deserialization, etc. |
| **Integrator** | Adds README / requirements scaffolding to the generated project. |

### How quality is guaranteed (the core of your ask)

For **every feature**, the orchestrator runs this loop (up to `max_feature_iterations`, default 3):

```
        ┌──────────────────────────────────────────────────────────┐
        │  Developer AGENT implements/fixes (reads, writes, runs)    │
        │                    ↓                                      │
        │  Tester AGENT writes tests + checks coverage              │
        │                    ↓                                      │
        │  ► GATE 1 (objective):  run pytest      ──── fail ──┐     │
        │                    ↓ pass                            │     │
        │  ► GATE 2 (correctness): reviewer agent ─ reject ────┤     │
        │                    ↓ approve                         │     │
        │  ► GATE 3 (security):    security agent ─ block ─────┤     │
        │                    ↓ clear                           │     │
        │            Feature = DONE ✓                          │     │
        │                                                      ↓     │
        │         compile failing tests + review + security notes    │
        │              → feed back into the next attempt             │
        └──────────────────────────────────────────────────────────┘
```

A feature is marked **DONE only if its tests actually execute and pass, the
correctness reviewer approves, *and* the security reviewer clears it.** If it
never satisfies all three within the retry budget it is marked **FAILED** and
reported as such — the swarm never silently ships an unverified feature. So for
your "5 features" example, you get a per-feature tests/review/security table
backed by a real test run, not just generated code.

The tests are **really executed** (`pytest` in a subprocess), so "tests pass"
means the machine ran them — not that a model claimed they would.

### Parallel feature building (with a merge gate)

By default, independent features build **concurrently**, each in its own
**isolated workspace**, then the swarm **merges them and runs the full combined
suite**. If merging two features breaks something (a cross-feature regression),
an **integration-repair loop** puts the agentic developer on the merged project
until the whole suite is green again. So the final project passes its *combined*
tests, not just each feature in isolation.

```
   plan ─┬─► [feature A] build/test/review  (isolated dir) ─┐
         ├─► [feature B] build/test/review  (isolated dir) ─┤
         └─► [feature C] build/test/review  (isolated dir) ─┘
                                                            ▼
                                 merge all → run FULL pytest suite
                                                            ▼
                               pass ✓   or   integration-repair loop → pass ✓
```

Turn it off with `--sequential` (build strictly one feature at a time); tune the
width with `--max-parallel N`.

---

## Tools, and where MCP fits

The Developer is a real tool-using agent, but its tools are **local, in-process
Python functions** (`codeswarm/tools.py`) bound to the workspace — deliberately
**not MCP**. The inner build loop (read / write / run tests) lives on the same
machine, so wrapping it in an external tool-server protocol would only add
latency and failure surface.

**MCP is the right choice for _external_ systems** the code needs to be grounded
in — live API docs (e.g. BytePlus ModelArk), a real database or VikingDB schema,
Jira/Linear tickets as requirements, GitHub, or a staging environment. Those can
be added as *extra* tools in a `Toolbox` via an adapter without touching the core
loop. For typical app logic (including code that calls BytePlus SDKs at runtime),
the swarm needs **no external connection** to design, write, and test the code.

---

## Architecture

```
                        ┌──────────────────┐
   idea / spec ───────► │   Orchestrator   │  (codeswarm/pipeline.py)
                        │     (Swarm)      │
                        └───┬───┬───┬──────┘
             requirements   │   │   │   planner ... developer/tester/reviewer
                            ▼   ▼   ▼
                        ┌──────────────────┐
                        │   Agents (LLM)   │  (codeswarm/agents/)
                        └────────┬─────────┘
                                 │  every agent calls ▼
                        ┌──────────────────┐
                        │  LLM Provider    │  (codeswarm/llm/)
                        │  BytePlus/OpenAI │  one OpenAI-compatible client,
                        │  /Gemini/mock    │  swap base_url + key per provider
                        └──────────────────┘
        writes files ▼                         runs tests ▼
        Workspace (codeswarm/workspace.py)   Sandbox (codeswarm/sandbox.py)
                    │                                   │
                    └──────────► ./output/<project>/ ◄──┘
```

**Why Python?** You already know it, and it's the native language of LLM tooling
— plus it lets the swarm *run the tests it writes* in-process, which is what
makes the quality gate real rather than cosmetic. (The generated *projects* are
also Python by default; the architecture cleanly supports adding other target
languages later — see *Extending*.)

**Provider-agnostic by design:** BytePlus ModelArk, OpenAI, and Gemini all expose
an OpenAI-compatible chat API, so a single client with a swapped `base_url` + key
handles all three (`codeswarm/llm/providers.py`). Adding another provider is one
small class.

---

## Install

Requires Python 3.10+.

```bash
cd CodingSwarm
python3 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -e .
```

Then add your API key(s):

```bash
cp .env.example .env
# edit .env and set ARK_API_KEY (BytePlus) and/or OPENAI_API_KEY / GEMINI_API_KEY
```

---

## Quickstart

**Try it offline first** — no API key needed (uses the deterministic mock provider):

```bash
codeswarm build --idea "A tiny calculator library" --dry-run
```

**Real run against BytePlus** (the default provider):

```bash
codeswarm build --idea "A CLI tool that converts between temperature units"
```

**From a spec file**, choosing a provider:

```bash
codeswarm build --spec examples/todo_api.yaml --provider openai
```

Output lands in `./output/<project-name>/`, including:
- the generated source (`app/`) and tests (`tests/`),
- a `README.md` and `requirements.txt`,
- `.codeswarm/report.json` — the per-feature pass/fail record,
- `.codeswarm/design.md` — the architecture the swarm designed.

> **Note on `--dry-run`:** the mock provider ignores your idea and always emits a
> small calculator so the pipeline can run fully offline. Use a real provider to
> build your actual idea.

---

## CLI reference

```
codeswarm build [options]

  --idea "..."           One-line description of what to build.
  --spec path.yaml       YAML spec with an 'idea:' (and optional 'name:') field.
  --name NAME            Project name (default: a slug of the idea).
  --provider NAME        byteplus | openai | gemini | mock  (overrides config).
  --model ID             Model id for the selected provider.
  --config path.yaml     Custom config file (see config/default.yaml).
  --output DIR           Output directory (default ./output).
  --max-iterations N     Build/test/review attempts per feature (default 3).
  --sequential           Build features one at a time (default: parallel).
  --max-parallel N       Max features built concurrently (default 4).
  --no-tests             Generate code without running the test gate.
  --dry-run              Use the offline mock provider (no API key).
```

You can also run it as a module: `python -m codeswarm build --idea "..."`.

---

## Configuration

Everything is driven by `config/default.yaml`. Copy it, edit it, pass it with
`--config`. Key sections:

- **`provider`** — the default provider for all agents.
- **`providers`** — `base_url`, `api_key_env`, and `model` for each backend.
  Set `model` to a model/endpoint you actually have access to (e.g. your
  ModelArk endpoint id for BytePlus).
- **`agents`** — optional per-role overrides. Example: use a stronger model for
  `architect` and `reviewer`, a cheaper/faster one for the `developer` loop:

  ```yaml
  agents:
    reviewer:
      provider: openai
      model: gpt-4.1
    developer:
      provider: byteplus
      model: seed-1-6-250615
  ```

- **`swarm`** — `max_feature_iterations`, `developer_max_steps` (agentic tool
  budget per attempt), `parallel_features` + `max_parallel_features`,
  `run_tests`, `test_timeout_seconds`, `temperature`, `output_dir`,
  `target_language`.

This mix-and-match is a feature: you can, for instance, let a **BytePlus** model
write code while a **different** model reviews it, which tends to catch more
issues than one model grading its own work.

---

## How the swarm runs the framework's own tests

```bash
pytest            # runs tests/ — all offline via the mock provider
```

The suite covers the parsing utilities and a full end-to-end pipeline run, so it
passes with no API keys.

---

## Security note on the sandbox

`codeswarm/sandbox.py` runs the generated tests with `pytest` in a subprocess in
the current environment. That is fine for code your own swarm generates from your
prompts. If you ever point this at untrusted specs, run it inside a container or
disposable VM and/or a fresh virtualenv — generated code executes on your
machine when tests run. This is called out in the code so it's easy to harden.

---

## Extending

- **New provider:** add a class in `codeswarm/llm/providers.py` (or reuse
  `OpenAICompatibleProvider` with a new `base_url`) and a block in config.
- **New / changed agent behaviour:** edit the prompts in
  `codeswarm/agents/prompts.py` or the role classes in `codeswarm/agents/roles.py`.
- **New pipeline stage or gate:** the loop lives in `codeswarm/pipeline.py`
  (`Swarm._build_feature`) — e.g. add a security-review agent as a third gate.
- **New developer tool (incl. MCP):** add a `Tool` in `codeswarm/tools.py`. For
  an external system, wrap an MCP client call as the tool's `handler` — the
  agent loop treats it identically to the local tools.
- **Other target languages:** the Developer/Tester agents already emit files
  generically; wire a language-specific runner alongside `run_pytest` in
  `sandbox.py` and branch on `swarm.target_language` in the pipeline.

---

## Project layout

```
CodingSwarm/
├── codeswarm/
│   ├── cli.py            # command-line interface
│   ├── config.py         # layered config loading
│   ├── pipeline.py       # orchestrator + per-feature quality loop  ← core
│   ├── models.py         # Feature/ProjectState/… dataclasses
│   ├── workspace.py      # safe file writes to the output dir
│   ├── sandbox.py        # runs pytest + coverage as the objective gate
│   ├── tools.py          # local dev/tester tools (read/write/run/coverage) — the agentic loop
│   ├── utils.py          # JSON + file-block parsing
│   ├── llm/              # provider abstraction + tool-calling (BytePlus/OpenAI/Gemini/mock)
│   └── agents/           # the specialist roles + their prompts
├── config/default.yaml   # all tunable settings
├── examples/todo_api.yaml
├── docs/ARCHITECTURE.md  # deep-dive design doc
├── tests/                # the framework's own offline test suite
├── CONTRIBUTING.md · CHANGELOG.md · LICENSE
└── requirements.txt / pyproject.toml
```

---

## Documentation

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — how the layers fit together,
  the quality loop, parallel/merge internals, and extension points.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — dev setup and conventions.
- **[CHANGELOG.md](CHANGELOG.md)** — what's in each release.

---

## License

MIT — see [LICENSE](LICENSE).
