"""Tests for the CodeSwarm framework itself (not the generated projects).

These run fully offline using the mock provider, so `pytest` works with no API
keys. They exercise the parsing utilities and a full end-to-end pipeline run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codeswarm.config import load_config
from codeswarm.pipeline import Swarm
from codeswarm.utils import extract_json, parse_file_blocks


# --- unit tests: parsing ----------------------------------------------------

def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced_with_prose():
    text = "Sure, here you go:\n```json\n{\"x\": [1, 2]}\n```\nHope that helps!"
    assert extract_json(text) == {"x": [1, 2]}


def test_extract_json_embedded():
    text = 'noise {"nested": {"k": "v"}} trailing'
    assert extract_json(text) == {"nested": {"k": "v"}}


def test_parse_file_blocks_roundtrip():
    text = (
        "### FILE: app/foo.py ###\n"
        "def foo():\n    return 1\n"
        "### END ###\n"
        "### FILE: tests/test_foo.py ###\n"
        "from app.foo import foo\n\ndef test_foo():\n    assert foo() == 1\n"
        "### END ###\n"
    )
    files = parse_file_blocks(text)
    assert len(files) == 2
    assert files[0].path == "app/foo.py"
    assert "def foo" in files[0].content
    assert files[1].path == "tests/test_foo.py"


# --- integration test: full pipeline on the mock provider -------------------

def test_end_to_end_parallel_mock(tmp_path: Path):
    # Default config builds features in parallel with isolated workspaces.
    config = load_config(overrides={"provider": "mock", "swarm": {"output_dir": str(tmp_path)}})
    swarm = Swarm(config)
    result = swarm.build("A tiny calculator library", project_name="calc")

    assert result.features_done >= 2  # planner yields add + multiply
    assert result.features_failed == 0
    assert result.integration_ok  # merged suite passes
    assert result.success

    out = Path(result.output_dir)
    assert (out / "conftest.py").exists()
    # The agentic developer wrote real modules that its tests import.
    assert (out / "app" / "add.py").exists()
    assert (out / "app" / "multiply.py").exists()
    # Scratch dirs are cleaned up.
    assert not (tmp_path / ".calc__scratch").exists()

    report = json.loads((out / ".codeswarm" / "report.json").read_text())
    assert report["summary"]["failed"] == 0
    assert report["summary"]["done"] == report["summary"]["total"]


def test_end_to_end_sequential_mock(tmp_path: Path):
    config = load_config(
        overrides={"provider": "mock", "swarm": {"output_dir": str(tmp_path), "parallel_features": False}}
    )
    result = Swarm(config).build("A tiny calculator library", project_name="calc_seq")
    assert result.success
    # Independently re-run the generated project's own tests to prove they pass.
    import subprocess, sys

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=result.output_dir, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_developer_tool_loop_writes_and_verifies(tmp_path: Path):
    # The developer agent should drive tools: write_file -> run_tests -> finish.
    from codeswarm.agents import DeveloperAgent
    from codeswarm.llm.providers import MockProvider
    from codeswarm.models import Feature
    from codeswarm.tools import build_dev_toolbox
    from codeswarm.workspace import Workspace

    ws = Workspace(tmp_path / "proj")
    ws.ensure_conftest()
    toolbox = build_dev_toolbox(ws)
    dev = DeveloperAgent(MockProvider())
    feature = Feature(id="f1", name="Add", description="add(a,b)", acceptance_criteria=["add(2,3)==5"])

    dev.implement("design", feature, toolbox, max_steps=6)

    # The loop actually created a source file on disk.
    assert (ws.root / "app" / "add.py").exists()


def test_missing_api_key_is_friendly(monkeypatch, tmp_path):
    # Selecting a real provider without a key should raise a clear error.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = load_config(overrides={"provider": "openai", "swarm": {"output_dir": str(tmp_path)}})
    with pytest.raises(ValueError, match="Missing API key"):
        Swarm(config)
