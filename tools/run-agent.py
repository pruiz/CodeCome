#!/usr/bin/env python3
"""
Structured wrapper around `opencode run --format json` for CodeCome phase targets.

Minimum supported OpenCode version: 1.14.39
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

try:
    from rich.console import Console, Group
    from rich.json import JSON
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.text import Text

    HAVE_RICH = True
except ImportError:  # pragma: no cover
    Console = Any  # type: ignore[assignment]
    Group = tuple  # type: ignore[assignment]
    JSON = None  # type: ignore[assignment]
    Markdown = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Rule = None  # type: ignore[assignment]
    Text = None  # type: ignore[assignment]
    HAVE_RICH = False

ROOT = Path(__file__).resolve().parents[1]
MINIMUM_OPENCODE_VERSION = "1.14.39"


def truthy_env(name: str) -> bool:
    value = os.environ.get(name)
    return value is not None and value not in {"", "0", "false", "False", "no", "No"}


def resolve_color_mode(flag: str) -> str:
    if flag != "auto":
        return flag
    if truthy_env("CLICOLOR_FORCE"):
        return "always"
    if os.environ.get("NO_COLOR") is not None or os.environ.get("TERM") == "dumb":
        return "never"
    return "auto"


def build_console(color_mode: str) -> Console:
    if not HAVE_RICH:
        return None  # type: ignore[return-value]
    if color_mode == "always":
        return Console(force_terminal=True, soft_wrap=True, highlight=False)
    if color_mode == "never":
        return Console(force_terminal=False, no_color=True, soft_wrap=True, highlight=False)
    return Console(soft_wrap=True, highlight=False)


def load_prompt(prompt_file: Path, finding: str | None) -> str:
    prompt = prompt_file.read_text(encoding="utf-8")
    if finding is None:
        return prompt

    placeholder = "FINDING_PATH_OR_ID"
    if placeholder not in prompt:
        raise ValueError(f"Prompt placeholder {placeholder!r} not found in {prompt_file}")

    return prompt.replace(placeholder, finding)


def format_tokens(tokens: dict[str, Any]) -> str:
    if not isinstance(tokens, dict):
        return ""

    parts = []
    for key in ("input", "output", "reasoning", "total"):
        value = tokens.get(key)
        if value is not None:
            parts.append(f"{key}={value}")
    return ", ".join(parts)


# --- Todo rendering helpers ---------------------------------------------------

_TODO_STATUS_ICONS = {
    "completed": "\u2714",     # ✔
    "in_progress": "\u25cf",   # ●
    "pending": "\u25cb",       # ○
    "cancelled": "\u2716",     # ✖
}

_TODO_STATUS_ASCII = {
    "completed": "[x]",
    "in_progress": "[~]",
    "pending": "[ ]",
    "cancelled": "[-]",
}

_TODO_PRIORITY_LETTERS = {
    "high": "H",
    "medium": "M",
    "low": "L",
}


def extract_todos(state: dict[str, Any]) -> list[dict[str, str]] | None:
    """Extract a todo list from a todowrite tool state, or None if unrecognized."""
    output = state.get("output")
    if isinstance(output, list):
        items = output
    else:
        input_data = state.get("input")
        if isinstance(input_data, dict) and isinstance(input_data.get("todos"), list):
            items = input_data["todos"]
        else:
            return None

    result: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            return None
        result.append({
            "content": str(item.get("content", "")),
            "status": str(item.get("status", "?")),
            "priority": str(item.get("priority", "?")),
        })
    return result


def _todo_summary(todos: list[dict[str, str]]) -> str:
    from collections import Counter
    counts = Counter(t["status"] for t in todos)
    parts = [f"{len(todos)} tasks"]
    for status in ("completed", "in_progress", "pending", "cancelled"):
        count = counts.get(status, 0)
        if count > 0:
            label = status.replace("_", " ")
            parts.append(f"{count} {label}")
    return " \u00b7 ".join(parts)


def _todo_border_style(todos: list[dict[str, str]]) -> str:
    statuses = {t["status"] for t in todos}
    if statuses == {"completed"}:
        return "green"
    if "in_progress" in statuses:
        return "yellow"
    return "dim"


def render_todowrite_rich(console: Console, state: dict[str, Any]) -> bool:
    """Render a todowrite tool call as a rich panel. Returns True if rendered."""
    todos = extract_todos(state)
    if todos is None:
        return False

    if not todos:
        console.print(Panel(Text("No todos.", style="dim"), title="Todos", border_style="dim", expand=True))
        return True

    from rich.table import Table

    summary = Text(_todo_summary(todos))

    table = Table(show_header=False, show_edge=False, padding=(0, 1), expand=True)
    table.add_column(width=2, no_wrap=True)   # status icon
    table.add_column(width=1, no_wrap=True)   # priority
    table.add_column(ratio=1)                 # content

    status_styles = {
        "completed": "bold green",
        "in_progress": "yellow",
        "pending": "dim",
        "cancelled": "dim strike",
    }
    priority_styles = {
        "high": "red",
        "medium": "yellow",
        "low": "dim",
    }

    for todo in todos:
        status = todo["status"]
        priority = todo["priority"]

        icon = _TODO_STATUS_ICONS.get(status, "?")
        icon_style = status_styles.get(status, "dim")

        pri_letter = _TODO_PRIORITY_LETTERS.get(priority, "?")
        pri_style = priority_styles.get(priority, "dim")

        table.add_row(
            Text(icon, style=icon_style),
            Text(pri_letter, style=pri_style),
            Text(todo["content"], style=status_styles.get(status, "")),
        )

    body = Group(summary, Text(), table)
    border = _todo_border_style(todos)
    console.print(Panel(body, title="Todos", border_style=border, expand=True))
    return True


def render_todowrite_plain(state: dict[str, Any]) -> bool:
    """Render a todowrite tool call in plain ASCII. Returns True if rendered."""
    todos = extract_todos(state)
    if todos is None:
        return False

    print(C.header("todos"))
    if not todos:
        print("  No todos.")
        return True

    print(f"  {_todo_summary(todos)}")
    for todo in todos:
        status = todo["status"]
        priority = todo["priority"]
        checkbox = _TODO_STATUS_ASCII.get(status, "[?]")
        pri_letter = _TODO_PRIORITY_LETTERS.get(priority, "?")
        content = todo["content"].replace("\n", " ")
        print(f"  {checkbox} {pri_letter} {content}")
    return True


# --- Shared helper utilities --------------------------------------------------

_SNAPSHOT_CACHE: OrderedDict[str, tuple[str, float]] = OrderedDict()
_SNAPSHOT_CACHE_CAP = int(os.environ.get("CODECOME_WRITE_CACHE_CAP", "200"))
_WRITE_CACHE_ENABLED = os.environ.get("CODECOME_WRITE_CACHE", "1") not in ("0", "false", "False", "no")

_READ_DISPLAY_LINES = int(os.environ.get("CODECOME_READ_DISPLAY_LINES", "10"))
_WRITE_CONTENT_LINES = int(os.environ.get("CODECOME_WRITE_CONTENT_LINES", "25"))
_WRITE_DIFF_LIMIT = int(os.environ.get("CODECOME_WRITE_DIFF_LIMIT", "50"))
_EDIT_DIFF_LINES = int(os.environ.get("CODECOME_EDIT_DIFF_LINES", "25"))
_READ_HIGHLIGHT_LIMIT = int(os.environ.get("CODECOME_READ_HIGHLIGHT_LIMIT", str(200 * 1024)))
_GLOB_MATCH_CAP = int(os.environ.get("CODECOME_GLOB_MATCH_CAP", "100"))

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
    ".py": "python", ".rb": "ruby", ".rs": "rust", ".go": "go",
    ".js": "javascript", ".ts": "typescript", ".tsx": "tsx", ".jsx": "jsx",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".yml": "yaml", ".yaml": "yaml", ".json": "json", ".toml": "toml",
    ".xml": "xml", ".html": "html", ".css": "css", ".sql": "sql",
    ".md": "markdown", ".mk": "make", ".cmake": "cmake",
    ".dockerfile": "docker", ".tf": "hcl", ".hcl": "hcl",
}


def _relativize_path(path: str) -> str:
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return path


def _strip_read_framing(output: str) -> tuple[str, Any, str | None]:
    """Parse OpenCode read tool output.

    Returns a 3-tuple:
      - kind: "file" | "directory" | "unknown"
      - payload: str (file body) | list[str] (directory entries) | None
      - footer: the trailing summary/entries-count line, or None
    """
    # Try file framing
    m = _READ_FILE_FRAMING_RE.search(output)
    if m:
        body = m.group("content")
        # Separate trailing summary line from body
        summary_m = _READ_SUMMARY_RE.search(body)
        if summary_m:
            footer = summary_m.group(0).strip()
            body = body[:summary_m.start()].rstrip()
        else:
            footer = None
        return "file", body, footer

    # Try directory framing
    d = _READ_DIR_FRAMING_RE.search(output)
    if d:
        raw_entries = d.group("entries")
        entries = []
        footer = None
        for line in raw_entries.split("\n"):
            line = line.strip()
            if not line:
                continue
            # The "(N entries)" summary is the footer
            if line.startswith("(") and "entries" in line and line.endswith(")"):
                footer = line
            else:
                entries.append(line)
        return "directory", entries, footer

    return "unknown", None, None


def _count_lines_and_bytes(text: str) -> tuple[int, int]:
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0), len(text.encode("utf-8", errors="replace"))


def _detect_lexer(path: str) -> str:
    ext = Path(path).suffix.lower()
    if Path(path).name.lower() == "makefile":
        return "make"
    if Path(path).name.lower() == "dockerfile":
        return "docker"
    return _LEXER_MAP.get(ext, "text")


def _format_excerpt(text: str, max_lines: int) -> tuple[str, int]:
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text, 0
    return "\n".join(lines[:max_lines]), len(lines) - max_lines


def _strip_line_numbers(text: str) -> str:
    """Remove OpenCode line-number prefixes like '  1: '."""
    raw_lines = []
    for line in text.split("\n"):
        colon_idx = line.find(": ")
        if colon_idx >= 0 and colon_idx <= 6 and line[:colon_idx].strip().isdigit():
            raw_lines.append(line[colon_idx + 2:])
        else:
            raw_lines.append(line)
    return "\n".join(raw_lines)


def _render_truncated_body_rich(
    console: Console,
    sections: list[Any],
    body: str,
    cap: int,
    lexer: str,
    footer: str | None,
) -> None:
    """Append Syntax block (capped), '... K more lines', and footer to sections."""
    from rich.syntax import Syntax

    body_lines = body.split("\n")
    total = len(body_lines)
    visible_lines = body_lines[:cap]
    leftover = max(0, total - cap)

    visible = "\n".join(visible_lines)
    if len(visible.encode("utf-8", errors="replace")) > _READ_HIGHLIGHT_LIMIT:
        sections.append(Text(visible))
    else:
        sections.append(Syntax(visible, lexer, theme="monokai", line_numbers=True, word_wrap=True))

    if leftover > 0:
        sections.append(Text(f"... {leftover} more lines", style="dim"))
    if footer:
        sections.append(Text(footer, style="dim"))


def _render_truncated_body_plain(
    body: str,
    cap: int,
    footer: str | None,
) -> None:
    """Print body lines (capped), '... K more lines', and footer."""
    body_lines = body.split("\n")
    total = len(body_lines)
    for line in body_lines[:cap]:
        print(line)
    leftover = max(0, total - cap)
    if leftover > 0:
        print(f"  ... {leftover} more lines")
    if footer:
        print(f"  {footer}")


def _is_likely_error(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in (
        "error", "traceback", "command not found", "failed", "permission denied",
        "no such file", "exception",
    ))


def _compute_diff(old: str, new: str, context: int = 3) -> list[str]:
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    return list(difflib.unified_diff(old_lines, new_lines, fromfile="old", tofile="new", n=context))


def _truncate_diff(diff_lines: list[str], max_lines: int) -> tuple[list[str], int]:
    if len(diff_lines) <= max_lines:
        return diff_lines, 0
    return diff_lines[:max_lines], len(diff_lines) - max_lines


def _current_mtime(path: str) -> float | None:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def _cache_set(path: str, content: str) -> None:
    if not _WRITE_CACHE_ENABLED:
        return
    mtime = _current_mtime(path)
    if mtime is None:
        return
    _SNAPSHOT_CACHE[path] = (content, mtime)
    _SNAPSHOT_CACHE.move_to_end(path)
    while len(_SNAPSHOT_CACHE) > _SNAPSHOT_CACHE_CAP:
        _SNAPSHOT_CACHE.popitem(last=False)


def _cache_get(path: str) -> str | None:
    if not _WRITE_CACHE_ENABLED:
        return None
    entry = _SNAPSHOT_CACHE.get(path)
    if entry is None:
        return None
    content, recorded_mtime = entry
    return content


def _cache_invalidate_stale() -> None:
    if not _WRITE_CACHE_ENABLED:
        return
    stale = []
    for path, (_, recorded_mtime) in _SNAPSHOT_CACHE.items():
        actual = _current_mtime(path)
        if actual is None or actual != recorded_mtime:
            stale.append(path)
    for path in stale:
        del _SNAPSHOT_CACHE[path]


# --- Read renderer ------------------------------------------------------------

def render_read_rich(console: Console, state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    if not isinstance(inp, dict) or not isinstance(output, str):
        return False

    file_path = str(inp.get("filePath", ""))
    if not file_path:
        return False

    rel_path = _relativize_path(file_path)
    offset = inp.get("offset")
    limit = inp.get("limit")

    border = "green" if state.get("status") == "completed" else "yellow"
    sections: list[Any] = [Text(rel_path, style="bold cyan")]
    if offset is not None and limit is not None:
        sections.append(Text(f"lines {offset}..{offset + limit - 1}", style="dim"))

    kind, payload, footer = _strip_read_framing(output)

    if kind == "unknown":
        if _is_likely_error(output):
            sections.append(Text())
            sections.append(Text(output.strip(), style="red"))
            console.print(Panel(Group(*sections), title="Read", border_style="red", expand=True))
        else:
            return False
        return True

    sections.append(Text())

    if kind == "file":
        body = str(payload).strip()
        if not body:
            sections.append(Text("(empty file)", style="dim"))
        else:
            raw_body = _strip_line_numbers(body)
            lexer = _detect_lexer(file_path)
            _render_truncated_body_rich(console, sections, raw_body, _READ_DISPLAY_LINES, lexer, footer)
        # Cache the full body (not display-truncated)
        _cache_set(file_path, body)

    elif kind == "directory":
        entries = payload if isinstance(payload, list) else []
        for entry in entries:
            if entry.endswith("/"):
                sections.append(Text(f"  {entry}", style="bold blue"))
            else:
                sections.append(Text(f"  {entry}"))
        if footer:
            sections.append(Text(footer, style="dim"))

    console.print(Panel(Group(*sections), title="Read", border_style=border, expand=True))
    return True


def render_read_plain(state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    if not isinstance(inp, dict) or not isinstance(output, str):
        return False

    file_path = str(inp.get("filePath", ""))
    if not file_path:
        return False

    rel_path = _relativize_path(file_path)
    offset = inp.get("offset")
    limit = inp.get("limit")

    print(C.header(f"read {rel_path}"))
    if offset is not None and limit is not None:
        print(f"  lines {offset}..{offset + limit - 1}")

    kind, payload, footer = _strip_read_framing(output)

    if kind == "file":
        body = str(payload).strip()
        raw_body = _strip_line_numbers(body)
        _render_truncated_body_plain(raw_body, _READ_DISPLAY_LINES, footer)
        _cache_set(file_path, body)
    elif kind == "directory":
        entries = payload if isinstance(payload, list) else []
        for entry in entries:
            print(f"  {entry}")
        if footer:
            print(f"  {footer}")
    else:
        print(output.strip())

    return True


# --- Write renderer -----------------------------------------------------------

def render_write_rich(console: Console, state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    if not isinstance(inp, dict):
        return False

    file_path = str(inp.get("filePath", ""))
    new_content = str(inp.get("content", ""))
    output_str = str(output) if output is not None else ""

    if not file_path:
        return False

    from rich.syntax import Syntax

    rel_path = _relativize_path(file_path)
    n_lines, n_bytes = _count_lines_and_bytes(new_content)

    is_error = output is not None and not output_str.startswith("Wrote file")
    border = "red" if is_error else "green"

    sections: list[Any] = [
        Text(rel_path, style="bold cyan"),
        Text(f"{n_lines} lines, {n_bytes} bytes", style="dim"),
    ]

    if is_error:
        sections.append(Text())
        sections.append(Text(output_str.strip(), style="red"))
        console.print(Panel(Group(*sections), title="Write", border_style=border, expand=True))
        _cache_set(file_path, new_content)
        return True

    prev = _cache_get(file_path)
    lexer = _detect_lexer(file_path)
    status_text = output_str.strip()

    if prev is not None:
        diff_lines = _compute_diff(prev, new_content)
        if not diff_lines:
            sections.append(Text("(no changes)", style="dim"))
        else:
            added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
            sections.append(Text(f"diff: -{removed} +{added}", style="dim"))
            sections.append(Text())
            truncated, leftover = _truncate_diff(diff_lines, _WRITE_DIFF_LIMIT)
            diff_text = "".join(truncated)
            sections.append(Syntax(diff_text, "diff", theme="monokai", word_wrap=True))
            if leftover > 0:
                sections.append(Text(f"... {leftover} more lines", style="dim"))
    else:
        sections.append(Text("(new file)", style="dim"))
        sections.append(Text())
        _render_truncated_body_rich(console, sections, new_content, _WRITE_CONTENT_LINES, lexer, None)

    sections.append(Text())
    sections.append(Text(status_text, style="green" if not is_error else "red"))

    console.print(Panel(Group(*sections), title="Write", border_style=border, expand=True))
    _cache_set(file_path, new_content)
    return True


def render_write_plain(state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    if not isinstance(inp, dict):
        return False

    file_path = str(inp.get("filePath", ""))
    new_content = str(inp.get("content", ""))
    output_str = str(output) if output is not None else ""

    if not file_path:
        return False

    rel_path = _relativize_path(file_path)
    n_lines, n_bytes = _count_lines_and_bytes(new_content)

    print(C.header(f"write {rel_path}"))
    print(f"  {n_lines} lines, {n_bytes} bytes")

    is_error = output is not None and not output_str.startswith("Wrote file")

    if is_error:
        print(C.fail(output_str.strip()))
        _cache_set(file_path, new_content)
        return True

    prev = _cache_get(file_path)

    if prev is not None:
        diff_lines = _compute_diff(prev, new_content)
        if not diff_lines:
            print("  (no changes)")
        else:
            added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
            print(f"  diff: -{removed} +{added}")
            truncated, leftover = _truncate_diff(diff_lines, _WRITE_DIFF_LIMIT)
            for line in truncated:
                print(f"  {line}", end="")
            if leftover > 0:
                print(f"  ... {leftover} more lines")
    else:
        print("  (new file)")
        _render_truncated_body_plain(new_content, _WRITE_CONTENT_LINES, None)

    print(f"  {output_str.strip()}")
    _cache_set(file_path, new_content)
    return True


# --- Edit renderer ------------------------------------------------------------

def _cache_reread(file_path: str) -> None:
    """Invalidate cache for path and re-read from disk."""
    if not _WRITE_CACHE_ENABLED:
        return
    if file_path in _SNAPSHOT_CACHE:
        del _SNAPSHOT_CACHE[file_path]
    try:
        content = Path(file_path).read_text(encoding="utf-8", errors="replace")
        _cache_set(file_path, content)
    except OSError:
        pass  # File gone; cache entry already removed


def render_edit_rich(console: Console, state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    if not isinstance(inp, dict):
        return False

    file_path = str(inp.get("filePath", ""))
    old_string = inp.get("oldString")
    new_string = inp.get("newString")
    replace_all = bool(inp.get("replaceAll", False))

    if not file_path or old_string is None or new_string is None:
        return False

    from rich.syntax import Syntax

    rel_path = _relativize_path(file_path)
    output_str = str(output) if output is not None else ""
    is_error = _is_likely_error(output_str) or (output is not None and "successfully" not in output_str.lower() and "applied" not in output_str.lower())
    border = "red" if is_error else "green"
    scope = "replace all" if replace_all else "replace 1 occurrence"

    sections: list[Any] = [
        Text(rel_path, style="bold cyan"),
        Text(scope, style="dim"),
        Text(),
    ]

    diff_lines = _compute_diff(str(old_string), str(new_string))
    if not diff_lines:
        sections.append(Text("(no changes in edit)", style="dim"))
    else:
        added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
        sections.append(Text(f"diff: -{removed} +{added}", style="dim"))
        sections.append(Text())
        truncated, leftover = _truncate_diff(diff_lines, _EDIT_DIFF_LINES)
        diff_text = "".join(truncated)
        sections.append(Syntax(diff_text, "diff", theme="monokai", word_wrap=True))
        if leftover > 0:
            sections.append(Text(f"... {leftover} more lines", style="dim"))

    sections.append(Text())
    sections.append(Text(output_str.strip(), style="red" if is_error else "green"))

    console.print(Panel(Group(*sections), title="Edit", border_style=border, expand=True))

    # Re-read cache after edit
    if _cache_get(file_path) is not None or file_path in _SNAPSHOT_CACHE:
        _cache_reread(file_path)

    return True


def render_edit_plain(state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    if not isinstance(inp, dict):
        return False

    file_path = str(inp.get("filePath", ""))
    old_string = inp.get("oldString")
    new_string = inp.get("newString")
    replace_all = bool(inp.get("replaceAll", False))

    if not file_path or old_string is None or new_string is None:
        return False

    rel_path = _relativize_path(file_path)
    output_str = str(output) if output is not None else ""
    scope = "replace all" if replace_all else "replace 1 occurrence"

    print(C.header(f"edit {rel_path}"))
    print(f"  {scope}")

    diff_lines = _compute_diff(str(old_string), str(new_string))
    if not diff_lines:
        print("  (no changes in edit)")
    else:
        added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
        print(f"  diff: -{removed} +{added}")
        truncated, leftover = _truncate_diff(diff_lines, _EDIT_DIFF_LINES)
        for line in truncated:
            print(f"  {line}", end="")
        if leftover > 0:
            print(f"  ... {leftover} more lines")

    print(f"  {output_str.strip()}")

    if _cache_get(file_path) is not None or file_path in _SNAPSHOT_CACHE:
        _cache_reread(file_path)

    return True


# --- Glob renderer ------------------------------------------------------------

def render_glob_rich(console: Console, state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    if not isinstance(inp, dict) or not isinstance(output, str):
        return False

    pattern = str(inp.get("pattern", ""))
    search_path = str(inp.get("path", ""))

    matches = [m.strip() for m in output.strip().split("\n") if m.strip()]
    n_matches = len(matches)

    border = "green" if n_matches > 0 else "dim"

    sections: list[Any] = [
        Text(f"pattern={pattern}  path={_relativize_path(search_path) if search_path else '.'}", style="dim"),
        Text(),
    ]

    if n_matches == 0:
        sections.append(Text("(no matches)", style="dim"))
    else:
        shown = matches[:_GLOB_MATCH_CAP]
        for m in shown:
            try:
                rel = str(Path(m).relative_to(search_path)) if search_path else m
            except ValueError:
                rel = _relativize_path(m)
            sections.append(Text(f"  {rel}"))
        if n_matches > _GLOB_MATCH_CAP:
            sections.append(Text(f"  ... and {n_matches - _GLOB_MATCH_CAP} more", style="dim"))

    sections.append(Text())
    sections.append(Text(f"{n_matches} match(es)", style="dim"))

    console.print(Panel(Group(*sections), title="Glob", border_style=border, expand=True))
    return True


def render_glob_plain(state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    if not isinstance(inp, dict) or not isinstance(output, str):
        return False

    pattern = str(inp.get("pattern", ""))
    search_path = str(inp.get("path", ""))

    matches = [m.strip() for m in output.strip().split("\n") if m.strip()]
    n_matches = len(matches)

    print(C.header(f"glob {pattern} in {_relativize_path(search_path) if search_path else '.'}"))

    if n_matches == 0:
        print("  (no matches)")
    else:
        shown = matches[:_GLOB_MATCH_CAP]
        for m in shown:
            try:
                rel = str(Path(m).relative_to(search_path)) if search_path else m
            except ValueError:
                rel = _relativize_path(m)
            print(f"  {rel}")
        if n_matches > _GLOB_MATCH_CAP:
            print(f"  ... and {n_matches - _GLOB_MATCH_CAP} more")

    print(f"  {n_matches} match(es)")
    return True


# --- Bash renderer ------------------------------------------------------------

def render_bash_rich(console: Console, state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    if not isinstance(inp, dict):
        return False

    command = str(inp.get("command", ""))
    description = inp.get("description", "")
    output_str = str(output) if output is not None else ""

    if not command:
        return False

    is_error = _is_likely_error(output_str)
    border = "red" if is_error else ("green" if state.get("status") == "completed" else "yellow")

    sections: list[Any] = [
        Text(f"$ {command}", style="bold cyan"),
    ]
    if description:
        sections.append(Text(str(description), style="dim italic"))

    sections.append(Text())

    if output_str.strip():
        sections.append(Text("Output", style="bold green"))
        sections.append(Text(output_str.strip()))
    else:
        sections.append(Text("(no output)", style="dim"))

    console.print(Panel(Group(*sections), title="Bash", border_style=border, expand=True))
    return True


def render_bash_plain(state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    if not isinstance(inp, dict):
        return False

    command = str(inp.get("command", ""))
    description = inp.get("description", "")
    output_str = str(output) if output is not None else ""

    if not command:
        return False

    print(C.header(f"bash $ {command}"))
    if description:
        print(f"  # {description}")

    if output_str.strip():
        print(output_str.strip())
    else:
        print("  (no output)")

    return True


# --- Skill renderer -----------------------------------------------------------

def render_skill_rich(console: Console, state: dict[str, Any]) -> bool:
    inp = state.get("input")
    if not isinstance(inp, dict):
        return False

    name = str(inp.get("name", ""))
    if not name:
        label = "(unknown skill)"
        style = "dim"
    else:
        label = f"loaded skill: {name}"
        style = ""

    console.print(Panel(Text(label, style=style), title="Skill", border_style="dim", expand=True))
    return True


def render_skill_plain(state: dict[str, Any]) -> bool:
    inp = state.get("input")
    if not isinstance(inp, dict):
        return False

    name = str(inp.get("name", ""))
    if not name:
        print(C.header("skill (unknown)"))
    else:
        print(C.header(f"skill {name}"))
    return True


# --- Tool dispatch ------------------------------------------------------------

def _dispatch_tool_renderer(console: Console, tool: str, state: dict[str, Any]) -> bool:
    """Try tool-specific rendering. Returns True if handled."""
    tool_lower = tool.strip().lower()
    if tool_lower == "todowrite":
        if HAVE_RICH:
            return render_todowrite_rich(console, state)
        else:
            return render_todowrite_plain(state)
    elif tool_lower == "read":
        # Invalidate stale cache entries before non-write events
        _cache_invalidate_stale()
        if HAVE_RICH:
            return render_read_rich(console, state)
        else:
            return render_read_plain(state)
    elif tool_lower == "write":
        if HAVE_RICH:
            return render_write_rich(console, state)
        else:
            return render_write_plain(state)
    elif tool_lower == "edit":
        if HAVE_RICH:
            return render_edit_rich(console, state)
        else:
            return render_edit_plain(state)
    elif tool_lower == "glob":
        _cache_invalidate_stale()
        if HAVE_RICH:
            return render_glob_rich(console, state)
        else:
            return render_glob_plain(state)
    elif tool_lower == "bash":
        _cache_invalidate_stale()
        if HAVE_RICH:
            return render_bash_rich(console, state)
        else:
            return render_bash_plain(state)
    elif tool_lower == "skill":
        _cache_invalidate_stale()
        if HAVE_RICH:
            return render_skill_rich(console, state)
        else:
            return render_skill_plain(state)
    else:
        _cache_invalidate_stale()
    return False


def render_step_start(console: Console, phase: str, label: str, event: dict[str, Any]) -> None:
    step_type = event.get("part", {}).get("type", "step-start")
    if HAVE_RICH:
        console.print(Text(f"[{phase}] {label}: {step_type}", style="cyan"))
    else:
        print(C.info(f"[{phase}] {label}: {step_type}"))


def render_text(console: Console, event: dict[str, Any]) -> None:
    part = event.get("part", {})
    text = str(part.get("text", "")).strip()
    if not text:
        return
    if HAVE_RICH:
        console.print(Panel(Markdown(text), title="Assistant", border_style="blue", expand=True))
    else:
        print(C.header("Assistant"))
        print(text)


def render_tool_use(console: Console, event: dict[str, Any]) -> None:
    part = event.get("part", {})
    tool = str(part.get("tool", "unknown"))
    state = part.get("state", {}) if isinstance(part.get("state"), dict) else {}
    status = str(state.get("status", "unknown"))
    input_data = state.get("input")
    output_data = state.get("output")

    if _dispatch_tool_renderer(console, tool, state):
        return

    if HAVE_RICH:
        sections: list[Any] = []
        if input_data is not None:
            sections.append(Text("Input", style="bold cyan"))
            try:
                sections.append(JSON.from_data(input_data))
            except Exception:
                sections.append(Text(str(input_data)))

        if output_data is not None:
            if sections:
                sections.append(Text())
            sections.append(Text("Output", style="bold green"))
            if isinstance(output_data, (dict, list)):
                try:
                    sections.append(JSON.from_data(output_data))
                except Exception:
                    sections.append(Text(str(output_data)))
            else:
                sections.append(Text(str(output_data)))

        body = Group(*sections) if sections else Text("No tool payload", style="dim")
        title = f"Tool: {tool} [{status}]"
        border = "green" if status == "completed" else "yellow"
        console.print(Panel(body, title=title, border_style=border, expand=True))
    else:
        print(C.header(f"Tool: {tool} [{status}]"))
        if input_data is not None:
            print(C.info("Input"))
            print(json.dumps(input_data, indent=2) if isinstance(input_data, (dict, list)) else str(input_data))
        if output_data is not None:
            print(C.info("Output"))
            print(json.dumps(output_data, indent=2) if isinstance(output_data, (dict, list)) else str(output_data))


def render_step_finish(console: Console, event: dict[str, Any]) -> None:
    part = event.get("part", {})
    reason = str(part.get("reason", "unknown"))
    tokens = format_tokens(part.get("tokens", {}))
    suffix = f" ({tokens})" if tokens else ""
    if HAVE_RICH:
        console.print(Text(f"step finished: {reason}{suffix}", style="dim"))
    else:
        print(f"step finished: {reason}{suffix}")


def render_unknown(console: Console, event: dict[str, Any]) -> None:
    message = f"unknown event type: {event.get('type', '<missing>')}"
    if HAVE_RICH:
        console.print(Text(message, style="dim"))
    else:
        print(message)


def render_event(console: Console, phase: str, label: str, event: dict[str, Any]) -> None:
    event_type = event.get("type")
    if event_type == "step_start":
        render_step_start(console, phase, label, event)
    elif event_type == "text":
        render_text(console, event)
    elif event_type == "tool_use":
        render_tool_use(console, event)
    elif event_type == "step_finish":
        render_step_finish(console, event)
    else:
        render_unknown(console, event)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a CodeCome phase with structured output.")
    parser.add_argument("--phase", required=True, help="Phase number.")
    parser.add_argument("--label", required=True, help="Human-readable phase label.")
    parser.add_argument("--agent", required=True, help="OpenCode agent name.")
    parser.add_argument("--prompt-file", required=True, help="Prompt file path relative to repo root.")
    parser.add_argument("--finding", help="Finding id for prompt substitution.")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("--debug", action="store_true", help="Mirror raw JSON events to stderr.")
    parser.add_argument("--read-display-lines", type=int, help="Max lines shown in read output (default: 10, env: CODECOME_READ_DISPLAY_LINES).")
    parser.add_argument("--write-content-lines", type=int, help="Max lines shown for new-file write content (default: 25, env: CODECOME_WRITE_CONTENT_LINES).")
    parser.add_argument("--write-diff-limit", type=int, help="Max diff lines shown for write (default: 50, env: CODECOME_WRITE_DIFF_LIMIT).")
    parser.add_argument("--edit-diff-lines", type=int, help="Max diff lines shown for edit (default: 25, env: CODECOME_EDIT_DIFF_LINES).")
    return parser


def build_child_command(args: argparse.Namespace) -> list[str]:
    cmd = ["opencode", "run", "--format", "json", "--agent", args.agent]
    if truthy_env("CODECOME_THINKING"):
        cmd.append("--thinking")

    extra_args = shlex.split(os.environ.get("OPENCODE_ARGS", ""))
    cmd.extend(extra_args)
    return cmd


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # CLI flags override env var defaults for tunables.
    global _READ_DISPLAY_LINES, _WRITE_CONTENT_LINES, _WRITE_DIFF_LIMIT, _EDIT_DIFF_LINES
    if args.read_display_lines is not None:
        _READ_DISPLAY_LINES = args.read_display_lines
    if args.write_content_lines is not None:
        _WRITE_CONTENT_LINES = args.write_content_lines
    if args.write_diff_limit is not None:
        _WRITE_DIFF_LIMIT = args.write_diff_limit
    if args.edit_diff_lines is not None:
        _EDIT_DIFF_LINES = args.edit_diff_lines

    color_mode = resolve_color_mode(args.color)
    console = build_console(color_mode)
    prompt_file = ROOT / args.prompt_file
    prompt = load_prompt(prompt_file, args.finding)
    command = build_child_command(args)

    if HAVE_RICH:
        console.print(Rule(title=f"Phase {args.phase}: {args.label}", style="bold cyan"))
        console.print(Text(f"agent={args.agent}  prompt={args.prompt_file}", style="dim"))
        if args.finding:
            console.print(Text(f"finding={args.finding}", style="dim"))
    else:
        print(C.header(f"Phase {args.phase}: {args.label}"))
        print(C.info(f"agent={args.agent}  prompt={args.prompt_file}"))
        if args.finding:
            print(C.info(f"finding={args.finding}"))
        print(C.warn("rich is not installed; using plain structured output fallback"))

    process: subprocess.Popen[str] | None = None
    interrupted = False

    def forward_signal(signum: int, _frame: Any) -> None:
        nonlocal interrupted
        interrupted = True
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass

    previous_sigint = signal.signal(signal.SIGINT, forward_signal)
    previous_sigterm = signal.signal(signal.SIGTERM, forward_signal)

    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid,
        )

        assert process.stdin is not None
        process.stdin.write(prompt)
        process.stdin.close()

        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            if args.debug:
                sys.stderr.write(line + "\n")
                sys.stderr.flush()
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                if args.debug:
                    sys.stderr.write(f"json-parse-error: {line}\n")
                    sys.stderr.flush()
                continue
            render_event(console, args.phase, args.label, event)

        process.wait()
        returncode = process.returncode
    except Exception as exc:
        if HAVE_RICH:
            console.print(Panel(Text(str(exc), style="red"), title="Wrapper Error", border_style="red"))
        else:
            print(C.fail(str(exc)), file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)

    if returncode is None:
        returncode = 1

    if returncode < 0:
        returncode = 128 + abs(returncode)

    if interrupted and returncode == 0:
        returncode = 130

    if returncode == 0:
        if HAVE_RICH:
            console.print(Rule(style="green"))
            console.print(Text(f"{C.SYM_OK} Phase {args.phase} completed successfully", style="green"))
        else:
            print(C.ok(f"Phase {args.phase} completed successfully"))
    elif returncode == 130:
        if HAVE_RICH:
            console.print(Rule(style="yellow"))
            console.print(Text(f"{C.SYM_WARN} Phase {args.phase} interrupted", style="yellow"))
        else:
            print(C.warn(f"Phase {args.phase} interrupted"))
    else:
        if HAVE_RICH:
            console.print(Rule(style="red"))
            console.print(Text(f"{C.SYM_FAIL} Phase {args.phase} failed with exit code {returncode}", style="red"))
        else:
            print(C.fail(f"Phase {args.phase} failed with exit code {returncode}"))

    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
