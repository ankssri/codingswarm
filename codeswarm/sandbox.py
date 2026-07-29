"""Run the generated test-suite as the quality gate.

Today this shells out to pytest in a subprocess with a timeout, using the same
interpreter that runs CodeSwarm. That is deliberately simple; the docstring in
README explains how to harden it (containers, fresh venv) for untrusted code.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from .models import TestOutcome


def run_pytest(workdir: str | Path, *, timeout: int = 120) -> TestOutcome:
    """Run `pytest -q` in `workdir`. Returns a normalized TestOutcome.

    pytest exit codes: 0 = all passed, 5 = no tests collected. We treat 5 as a
    failure of the quality gate because a feature with no tests is not verified.
    """
    workdir = Path(workdir)
    start = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration = time.time() - start
        output = (proc.stdout or "") + (proc.stderr or "")
        passed = proc.returncode == 0
        return TestOutcome(passed=passed, returncode=proc.returncode, output=output, duration_s=duration)
    except subprocess.TimeoutExpired as exc:
        duration = time.time() - start
        output = (exc.stdout or "") + (exc.stderr or "") if isinstance(exc.stdout, str) else ""
        return TestOutcome(
            passed=False,
            returncode=-1,
            output=output + f"\n[TIMEOUT] pytest exceeded {timeout}s.",
            duration_s=duration,
        )
    except FileNotFoundError:
        return TestOutcome(
            passed=False,
            returncode=-1,
            output="pytest is not installed in the current environment. Install with: pip install pytest",
            duration_s=time.time() - start,
        )


def run_coverage(workdir: str | Path, *, source: str = "app", timeout: int = 120) -> str:
    """Run the test-suite under coverage.py and return a report with missing lines.

    Gracefully degrades to a short note if coverage.py isn't installed, so the
    agentic Tester can call it opportunistically without hard-failing.
    """
    workdir = Path(workdir)
    try:
        run = subprocess.run(
            [sys.executable, "-m", "coverage", "run", f"--source={source}", "-m", "pytest", "-q"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if "No module named coverage" in (run.stderr or ""):
            return "coverage.py is not installed; skipping coverage inspection."
        report = subprocess.run(
            [sys.executable, "-m", "coverage", "report", "-m"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (run.stdout or "") + (run.stderr or "")
        rep = (report.stdout or "") + (report.stderr or "")
        return f"Test run under coverage:\n{out}\nCoverage report (Missing = uncovered lines):\n{rep}"
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT] coverage run exceeded {timeout}s."
    except FileNotFoundError:
        return "coverage.py is not installed; skipping coverage inspection."
