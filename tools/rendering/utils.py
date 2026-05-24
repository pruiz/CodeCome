# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Shared utilities for read/write/edit/apply_patch/glob/grep renderers.

Path relativization, lexer detection, diff computation, read-framing
parsing, internal read suppression, and truncated body rendering.
"""

from __future__ import annotations

import difflib
import os
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Regexes and lookup tables
# ---------------------------------------------------------------------------

_READ_FILE_FRAMING_RE = re.compile(
    r"<path>(?P<path>.*?)</path>\s*"
    r"<type>(?P<type>.*?)</type>\s*"
    r"<content>\s*\n(?P<content>.*?)\n\s*</content>",
    re.DOTALL,
)
_READ_DIR_FRAMING_RE = re.compile(
    r"<path>(?P<path>.*?)</path>\s*"
    r"<type>directory</type>\s*"
    r"<entries>\s*\n(?P<entries>.*?)\n\s*</entries>",
    re.DOTALL,
)
_READ_SUMMARY_RE = re.compile(
    r"\((?:End of file|Showing lines|Buffer has more lines)[^\)]*\)\s*$",
    re.MULTILINE,
)

_LEXER_MAP = {
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".hpp": "cpp", ".hh": "cpp", ".cs": "csharp", ".java": "java",
    ".erl": "erlang", ".hrl": "erlang", ".app.src": "erlang", ".config": "erlang",
    ".ex": "elixir", ".exs": "elixir", ".py": "python", ".rb": "ruby",
    ".rs": "rust", ".go": "go",
    ".js": "javascript", ".ts": "typescript", ".tsx": "tsx", ".jsx": "jsx",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".yml": "yaml", ".yaml": "yaml", ".json": "json", ".toml": "toml",
    ".xml": "xml", ".html": "html", ".css": "css", ".sql": "sql",
    ".md": "markdown", ".mk": "make", ".cmake": "cmake",
    ".dockerfile": "docker", ".tf": "hcl", ".hcl": "hcl",
}

_FINDING_FILENAME_RE = re.compile(r"^(CC-\d{4,})-(.+)\.md$")
_ROUT_WORKSPACE_DOCS = {"AGENTS.md", "README.md"}
_ROUT_WORKSPACE_CONFIGS = {"codecome.yml"}


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def relativize_path(path: str, root: Path) -> str:
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return path


def detect_lexer(path: str) -> str:
    ext = Path(path).suffix.lower()
    if Path(path).name.lower() == "makefile":
        return "make"
    if Path(path).name.lower() == "dockerfile":
        return "docker"
    return _LEXER_MAP.get(ext, "text")


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

def compute_diff(old: str, new: str, context: int = 3) -> list[str]:
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    return list(difflib.unified_diff(old_lines, new_lines, fromfile="old", tofile="new", n=context))


def truncate_diff(diff_lines: list[str], max_lines: int) -> tuple[list[str], int]:
    if len(diff_lines) <= max_lines:
        return diff_lines, 0
    return diff_lines[:max_lines], len(diff_lines) - max_lines


# ---------------------------------------------------------------------------
# Body rendering
# ---------------------------------------------------------------------------

def count_lines_and_bytes(text: str) -> tuple[int, int]:
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0), len(text.encode("utf-8", errors="replace"))


def strip_line_numbers(text: str) -> str:
    raw_lines = []
    for line in text.split("\n"):
        colon_idx = line.find(": ")
        if colon_idx >= 0 and colon_idx <= 6 and line[:colon_idx].strip().isdigit():
            raw_lines.append(line[colon_idx + 2:])
        else:
            raw_lines.append(line)
    return "\n".join(raw_lines)


def format_excerpt(text: str, max_lines: int) -> tuple[str, int]:
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text, 0
    return "\n".join(lines[:max_lines]), len(lines) - max_lines


def is_likely_error(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in (
        "error", "traceback", "command not found", "failed", "permission denied",
        "no such file", "exception",
    ))


# ---------------------------------------------------------------------------
# Read-framing parsing
# ---------------------------------------------------------------------------

def strip_read_framing(output: str) -> tuple[str, Any, str | None]:
    """Parse OpenCode read tool output.

    Returns (kind, payload, footer) where kind is 'file', 'directory',
    or 'unknown'.
    """
    m = _READ_FILE_FRAMING_RE.search(output)
    if m:
        body = m.group("content")
        summary_m = _READ_SUMMARY_RE.search(body)
        if summary_m:
            footer = summary_m.group(0).strip()
            body = body[:summary_m.start()].rstrip()
        else:
            footer = None
        return "file", body, footer

    d = _READ_DIR_FRAMING_RE.search(output)
    if d:
        raw_entries = d.group("entries")
        entries = []
        footer = None
        for line in raw_entries.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("(") and "entries" in line and line.endswith(")"):
                footer = line
            else:
                entries.append(line)
        return "directory", entries, footer

    return "unknown", None, None


# ---------------------------------------------------------------------------
# Internal read suppression
# ---------------------------------------------------------------------------

def classify_internal_read(rel_path: str) -> str | None:
    if not rel_path or os.path.isabs(rel_path):
        return None

    parts = Path(rel_path).parts
    if not parts:
        return None

    if len(parts) == 1:
        name = parts[0]
        if name in _ROUT_WORKSPACE_DOCS:
            return f"reading workspace doc: {name}"
        if name in _ROUT_WORKSPACE_CONFIGS:
            return f"reading workspace config: {name}"
        return None

    if parts[0] == ".opencode":
        if len(parts) >= 3 and parts[1] == "agents":
            agent_name = Path(parts[2]).stem
            return f"loading agent: {agent_name}"
        if len(parts) >= 3 and parts[1] == "skills":
            skill_name = parts[2]
            if len(parts) == 4 and parts[3] == "SKILL.md":
                return f"loading skill: {skill_name}"
            if len(parts) >= 4:
                rest = "/".join(parts[3:])
                return f"loading skill resource: {skill_name}/{rest}"
            return f"loading skill: {skill_name}"
        return f"loading opencode config: {rel_path}"

    if parts[0] == "itemdb":
        if len(parts) >= 4 and parts[1] == "findings":
            status = parts[2]
            filename = parts[3]
            m = _FINDING_FILENAME_RE.match(filename)
            if m:
                return f"reading finding: {m.group(1)} [{status}] - {m.group(2)}"
            return f"reading itemdb file: {rel_path}"
        if len(parts) >= 3 and parts[1] == "notes":
            return f"reading note: {parts[2]}"
        if len(parts) >= 3 and parts[1] == "evidence":
            rest = "/".join(parts[2:])
            return f"reading evidence: {rest}"
        if len(parts) >= 3 and parts[1] == "reports":
            return f"reading report: {parts[2]}"
        if len(parts) == 2 and parts[1] == "index.md":
            return "reading items index"
        return f"reading itemdb file: {rel_path}"

    if parts[0] == "runs" and len(parts) >= 2:
        return f"reading run summary: {parts[1]}"

    if parts[0] == "templates" and len(parts) >= 2:
        return f"reading template: {parts[1]}"

    return None
