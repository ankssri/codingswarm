# Contributing to CodeSwarm

Thanks for your interest in improving CodeSwarm. This is a small, hackable
codebase — the goal is to keep it that way.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env   # add keys only if you want to run against real providers
```

## Running the tests

The whole suite runs **offline** via the mock provider — no API keys needed:

```bash
pytest -q
```

Please keep it that way: new features should be exercisable through the mock
provider so CI stays key-free. If you add an agent or tool, extend
`codeswarm/llm/providers.py::MockProvider` so the offline pipeline still runs
end-to-end.

## Project conventions

- **Python 3.10+**, standard library first. Keep runtime dependencies minimal.
- Match the surrounding style: small focused modules, docstrings that explain
  *why*, type hints on public functions.
- Agents are thin: prompt in `agents/prompts.py`, logic in `agents/roles.py`.
- Anything that executes generated code goes through `sandbox.py`.

## Good first contributions

- A new LLM provider (or a native, non-OpenAI-compatible one).
- A new quality gate (performance, lint/style, license scanning).
- A new target language runner (Node/pytest-equivalent) in `sandbox.py`.
- Durable checkpoints so a run can resume after interruption.
- An MCP-backed tool adapter for external grounding (docs, DB schema, tickets).

## Pull requests

1. Branch from `main`.
2. Add/adjust tests; make sure `pytest -q` passes.
3. Keep PRs focused and describe the change and its motivation.
