"""Small shared helpers: robust JSON + file-block parsing, logging."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict:
    """Best-effort parse of a JSON object embedded in an LLM reply.

    Handles ```json fenced blocks and leading/trailing prose by scanning for
    the first balanced {...} object. Raises ValueError if nothing parses.
    """
    text = (text or "").strip()

    # 1) Try the whole thing.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) Try a fenced ```json block.
    for match in _JSON_FENCE_RE.finditer(text):
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # 3) Scan for the first balanced object.
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
        start = text.find("{", start + 1)

    raise ValueError(f"Could not extract JSON from response:\n{text[:500]}")


# ---------------------------------------------------------------------------
# File-block parsing
#
# Agents emit code using a delimiter format (not JSON) so that source code
# never has to be JSON-escaped — far more reliable for real code:
#
#   ### FILE: path/to/file.py ###
#   <file content>
#   ### END ###
# ---------------------------------------------------------------------------

_FILE_START_RE = re.compile(r"^###\s*FILE:\s*(.+?)\s*###\s*$")
_FILE_END_RE = re.compile(r"^###\s*END\s*###\s*$")


@dataclass
class ParsedFile:
    path: str
    content: str


def parse_file_blocks(text: str) -> list[ParsedFile]:
    """Extract ``### FILE: … ###`` / ``### END ###`` blocks from LLM output."""
    files: list[ParsedFile] = []
    lines = (text or "").splitlines()
    i = 0
    n = len(lines)
    while i < n:
        start = _FILE_START_RE.match(lines[i])
        if not start:
            i += 1
            continue
        path = start.group(1).strip().strip("`").strip()
        i += 1
        body: list[str] = []
        while i < n and not _FILE_END_RE.match(lines[i]):
            body.append(lines[i])
            i += 1
        # skip the END line if present
        if i < n:
            i += 1
        content = "\n".join(body)
        if content and not content.endswith("\n"):
            content += "\n"
        files.append(ParsedFile(path=path, content=content))
    return files


def file_blocks(files: dict[str, str]) -> str:
    """Render a dict of path->content as the file-block format (for prompts)."""
    parts = []
    for path, content in files.items():
        parts.append(f"### FILE: {path} ###")
        parts.append(content.rstrip("\n"))
        parts.append("### END ###")
    return "\n".join(parts)
