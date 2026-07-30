"""Command-line interface for CodeSwarm.

Usage examples:
    codeswarm build --idea "A CLI tool that converts between temperature units"
    codeswarm build --spec examples/todo_api.yaml --provider openai
    codeswarm build --idea "..." --dry-run          # offline, no API key needed
    python -m codeswarm build --idea "..."
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import load_config

# NOTE: `.env` is loaded explicitly in each command (see _load_env) rather than
# at import time, so `codeswarm doctor` can first capture the pre-load shell
# state to detect a stale shell key shadowing .env.


def _load_env() -> None:
    """Load .env, making it authoritative over stale shell exports.

    override=True matters: without it, python-dotenv leaves any value already
    exported in the shell in place, so a stale `export ARK_API_KEY=...` would
    silently shadow the key in .env and cause confusing 401s.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(override=True)
    except Exception:  # pragma: no cover - dotenv is optional at runtime
        pass


def _console():
    try:
        from rich.console import Console

        return Console()
    except Exception:  # pragma: no cover
        return None


def _make_event_printer(console):
    role_style = {
        "orchestrator": "bold cyan",
        "requirements": "green",
        "architect": "magenta",
        "planner": "yellow",
        "developer": "blue",
        "tester": "bright_black",
        "reviewer": "red",
        "security": "bright_red",
        "integrator": "cyan",
    }

    def printer(role: str, msg: str) -> None:
        label = f"[{role}]"
        if console:
            style = role_style.get(role, "white")
            console.print(f"[{style}]{label:<16}[/{style}] {msg}")
        else:
            print(f"{label:<16} {msg}")

    return printer


def _load_spec(spec_path: str) -> dict:
    import yaml

    with open(spec_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def cmd_build(args: argparse.Namespace) -> int:
    _load_env()
    console = _console()
    printer = _make_event_printer(console)

    # Resolve the idea, either inline or from a spec file.
    idea = args.idea
    project_name = args.name
    if args.spec:
        spec = _load_spec(args.spec)
        idea = spec.get("idea") or idea
        project_name = project_name or spec.get("name")
    if not idea:
        print("error: provide --idea \"...\" or --spec path.yaml", file=sys.stderr)
        return 2

    # Build CLI overrides for config.
    overrides: dict = {"swarm": {}}
    if args.dry_run:
        overrides["provider"] = "mock"
    elif args.provider:
        overrides["provider"] = args.provider
    if args.model:
        overrides.setdefault("providers", {})
    if args.max_iterations is not None:
        overrides["swarm"]["max_feature_iterations"] = args.max_iterations
    if args.output:
        overrides["swarm"]["output_dir"] = args.output
    if args.no_tests:
        overrides["swarm"]["run_tests"] = False
    if args.verbose:
        overrides["swarm"]["verbose"] = True
    if args.sequential:
        overrides["swarm"]["parallel_features"] = False
    if args.max_parallel is not None:
        overrides["swarm"]["max_parallel_features"] = args.max_parallel

    config = load_config(args.config, overrides)

    # A --model override applies to whichever provider is selected.
    if args.model:
        prov = config.get("provider")
        if prov in config.get("providers", {}):
            config["providers"][prov]["model"] = args.model

    # Import here so --help works without dependencies installed.
    from .pipeline import Swarm

    banner = f"CodeSwarm v{__version__}  |  provider={config.get('provider')}"
    if console:
        from rich.panel import Panel

        console.print(Panel.fit(banner, style="bold"))
        console.print(f"[bold]Idea:[/bold] {idea}\n")
    else:
        print(banner)
        print(f"Idea: {idea}\n")

    swarm = Swarm(config, on_event=printer)
    try:
        result = swarm.build(idea, project_name=project_name)
    except Exception as exc:  # noqa: BLE001
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1

    _print_summary(console, result)
    return 0 if result.success else 1


def _print_summary(console, result) -> None:
    state = result.state
    if console:
        from rich.table import Table

        table = Table(title="Feature Results", show_lines=False)
        table.add_column("ID")
        table.add_column("Feature")
        table.add_column("Tests")
        table.add_column("Review")
        table.add_column("Security")
        table.add_column("Status")
        for f in state.features:
            status_color = {"done": "green", "failed": "red"}.get(f.status.value, "yellow")
            table.add_row(
                f.id,
                f.name,
                "pass" if f.tests_passed else "fail",
                "ok" if f.review_approved else "-",
                "ok" if f.security_approved else "-",
                f"[{status_color}]{f.status.value}[/{status_color}]",
            )
        console.print()
        console.print(table)
        console.print(
            f"\n[bold]{result.features_done} done[/bold], "
            f"[bold]{result.features_failed} failed[/bold]  |  "
            f"combined suite: {'[green]passing[/green]' if result.integration_ok else '[red]failing[/red]'}"
        )
        console.print(f"Output: [underline]{result.output_dir}[/underline]")
        console.print(f"Report: {Path(result.output_dir) / '.codeswarm' / 'report.json'}")
    else:
        print("\n=== Feature Results ===")
        for f in state.features:
            print(f"  {f.id:<4} {f.name:<32} tests={'pass' if f.tests_passed else 'fail':<4} "
                  f"review={'ok' if f.review_approved else '-':<3} "
                  f"security={'ok' if f.security_approved else '-':<3} -> {f.status.value}")
        print(f"\n{result.features_done} done, {result.features_failed} failed")
        print(f"Output: {result.output_dir}")


def cmd_doctor(args: argparse.Namespace) -> int:
    """Diagnose setup: config, API key, connectivity, and tool-calling.

    Runs a few cheap checks and prints a table, so setup problems (like a stale
    shell key shadowing .env, a wrong model id, or no tool-calling support) are a
    single command to find instead of a failed build.
    """
    import time

    from .config import resolve_role
    from .llm import Message, build_provider
    from .llm.factory import key_fingerprint

    console = _console()
    checks: list[tuple[str, str, str]] = []  # (name, status, detail)

    # --- config ---
    try:
        config = load_config(args.config, {"provider": args.provider} if args.provider else None)
        checks.append(("Config", "OK", f"loaded ({args.config or 'built-in defaults'})"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("Config", "FAIL", str(exc)))
        _print_doctor(console, checks)
        return 1

    provider_name = config.get("provider", "mock")

    # --- resolve role/provider/model ---
    try:
        pname, pcfg, rcfg = resolve_role(config, "developer")
        model = args.model or rcfg.get("model") or pcfg.get("model")
        checks.append(("Provider", "OK", f"{provider_name} — base_url={pcfg.get('base_url') or '(default)'}"))
        checks.append(("Model", "OK" if model else "FAIL", model or "no model configured"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("Provider", "FAIL", str(exc)))
        _print_doctor(console, checks)
        return 1

    if provider_name == "mock":
        checks.append(("API key", "SKIP", "mock provider needs no key"))
        checks.append(("Connectivity", "SKIP", "mock provider is offline"))
        checks.append(("Tool-calling", "SKIP", "mock simulates tools"))
        _print_doctor(console, checks)
        return 0

    # --- API key: capture shell state BEFORE loading .env to detect shadowing ---
    var = pcfg.get("api_key_env", "")
    import os

    shell_val = os.environ.get(var)
    file_val = None
    try:
        from dotenv import dotenv_values, find_dotenv

        path = find_dotenv(usecwd=True)
        if path:
            file_val = (dotenv_values(path) or {}).get(var)
    except Exception:  # noqa: BLE001
        pass

    _load_env()  # override=True: .env wins
    effective = os.environ.get(var, "")

    if not effective:
        checks.append(("API key", "FAIL", f"{var} not set — add it to .env or export it"))
        _print_doctor(console, checks)
        return 1

    key_detail = f"{var} = {key_fingerprint(effective)}"
    checks.append(("API key", "OK", key_detail))
    if shell_val and file_val and shell_val.strip() != file_val.strip():
        checks.append(
            ("Key source", "WARN",
             f"a shell-exported {var} differs from .env — .env wins now (override=True), "
             f"but run `unset {var}` to avoid confusion")
        )
    elif shell_val and not file_val:
        checks.append(("Key source", "WARN", f"{var} comes from your shell, not .env"))
    else:
        checks.append(("Key source", "OK", ".env"))

    # --- connectivity: one tiny completion ---
    try:
        provider = build_provider(pname, pcfg, model_override=model)
        t0 = time.time()
        resp = provider.complete([Message("user", "reply with the single word: ok")], max_tokens=5)
        dt = time.time() - t0
        text = (resp.text or "").strip()[:40]
        checks.append(("Connectivity", "OK", f"{model} replied in {dt:.1f}s: {text!r}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("Connectivity", "FAIL", str(exc)[:300]))
        _print_doctor(console, checks)
        return 1

    # --- tool-calling: developer/tester depend on it ---
    try:
        tools = [{
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "write a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"],
                },
            },
        }]
        resp = provider.complete(
            [Message("user", "Create app/x.py with a hello() function using the write_file tool.")],
            tools=tools, max_tokens=200,
        )
        if resp.tool_calls:
            checks.append(("Tool-calling", "OK", f"model requested: {resp.tool_calls[0].name}(...)"))
        else:
            checks.append(("Tool-calling", "WARN",
                           "model returned no tool call — the agentic Developer/Tester may not "
                           "work well; pick a tool-calling-capable model"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("Tool-calling", "WARN", str(exc)[:200]))

    ok = _print_doctor(console, checks)
    return 0 if ok else 1


def _print_doctor(console, checks: list[tuple[str, str, str]]) -> bool:
    """Render the doctor results; return True if no FAIL rows."""
    colors = {"OK": "green", "WARN": "yellow", "FAIL": "red", "SKIP": "bright_black"}
    marks = {"OK": "✓", "WARN": "!", "FAIL": "✗", "SKIP": "–"}
    has_fail = any(s == "FAIL" for _, s, _ in checks)
    if console:
        from rich.table import Table

        table = Table(title="CodeSwarm Doctor", show_lines=False)
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Detail", overflow="fold")
        for name, status, detail in checks:
            c = colors.get(status, "white")
            table.add_row(name, f"[{c}]{marks.get(status,'?')} {status}[/{c}]", detail)
        console.print(table)
        summary = "[red]problems found[/red]" if has_fail else "[green]ready to build[/green]"
        console.print(f"\n{summary}")
    else:
        print("\n=== CodeSwarm Doctor ===")
        for name, status, detail in checks:
            print(f"  [{marks.get(status,'?')}] {name:<14} {status:<5} {detail}")
        print("\n" + ("problems found" if has_fail else "ready to build"))
    return not has_fail


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codeswarm",
        description="A swarm of LLM agents that builds, tests, and reviews software feature-by-feature.",
    )
    parser.add_argument("--version", action="version", version=f"codeswarm {__version__}")
    sub = parser.add_subparsers(dest="command")

    b = sub.add_parser("build", help="Build a project from an idea or spec file.")
    b.add_argument("--idea", help="One-line description of what to build.")
    b.add_argument("--spec", help="Path to a YAML spec file (with an 'idea' field).")
    b.add_argument("--name", help="Project name (defaults to a slug of the idea).")
    b.add_argument("--config", help="Path to a config YAML (overrides defaults).")
    b.add_argument("--provider", choices=["byteplus", "openai", "gemini", "mock"],
                   help="Override the default provider.")
    b.add_argument("--model", help="Override the model id for the selected provider.")
    b.add_argument("--output", help="Output directory (default ./output).")
    b.add_argument("--max-iterations", type=int, help="Max build/test/review attempts per feature.")
    b.add_argument("--sequential", action="store_true",
                   help="Build features one at a time (default: parallel).")
    b.add_argument("--max-parallel", type=int, help="Max features built concurrently (default 4).")
    b.add_argument("--no-tests", action="store_true", help="Generate code without running tests.")
    b.add_argument("--verbose", "-v", action="store_true",
                   help="Print requirements, full design, and acceptance criteria live as produced.")
    b.add_argument("--dry-run", action="store_true",
                   help="Use the offline mock provider (no API key needed).")
    b.set_defaults(func=cmd_build)

    d = sub.add_parser("doctor", help="Check config, API key, connectivity, and tool-calling.")
    d.add_argument("--provider", choices=["byteplus", "openai", "gemini", "mock"],
                   help="Provider to check (default: the one in config).")
    d.add_argument("--model", help="Model id to test (default: the configured one).")
    d.add_argument("--config", help="Path to a config YAML (overrides defaults).")
    d.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
