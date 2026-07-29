"""Filesystem workspace for a generated project.

All file writes go through here so we can (a) keep them inside the output
directory (path-traversal guard) and (b) keep an in-memory mirror for prompts.
"""

from __future__ import annotations

import os
from pathlib import Path


class Workspace:
    def __init__(self, root: str | os.PathLike) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, rel_path: str) -> Path:
        # Normalize and ensure the target stays within the workspace root.
        candidate = (self.root / rel_path).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            raise ValueError(f"Refusing to write outside workspace: {rel_path}")
        return candidate

    def write_file(self, rel_path: str, content: str) -> Path:
        path = self._safe_path(rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def write_files(self, files: dict[str, str]) -> list[Path]:
        return [self.write_file(p, c) for p, c in files.items()]

    def read_file(self, rel_path: str) -> str:
        path = self._safe_path(rel_path)
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    _IGNORE_TOP = {".codeswarm", "__pycache__", ".pytest_cache", ".git"}

    def snapshot(self, *, subdir: str | None = None, tests: bool | None = None) -> dict[str, str]:
        """Return {relative_path: content} for files currently on disk.

        Args:
            subdir: if given, only files under this top-level dir (e.g. "tests").
            tests: if True only files under tests/; if False exclude tests/ and
                   conftest.py; if None include everything (minus internal dirs).
        """
        out: dict[str, str] = {}
        for p in sorted(self.root.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(self.root)
            if rel.parts and rel.parts[0] in self._IGNORE_TOP:
                continue
            top = rel.parts[0] if rel.parts else ""
            if subdir is not None and top != subdir:
                continue
            if tests is True and top != "tests":
                continue
            if tests is False and (top == "tests" or str(rel) == "conftest.py"):
                continue
            try:
                out[str(rel)] = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
        return out

    def ensure_conftest(self) -> None:
        """Write an empty root ``conftest.py``.

        pytest treats the directory containing the nearest conftest.py as the
        rootdir and puts it on sys.path, which makes top-level generated modules
        importable from tests without any packaging ceremony.
        """
        conftest = self.root / "conftest.py"
        if not conftest.exists():
            conftest.write_text("# Ensures the project root is importable in tests.\n", encoding="utf-8")
