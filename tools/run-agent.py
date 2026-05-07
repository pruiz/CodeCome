#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

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
from dataclasses import dataclass
from functools import lru_cache
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


def check_opencode_version() -> None:
    try:
        result = subprocess.run(["opencode", "--version"], capture_output=True, text=True)
    except FileNotFoundError:
        print(C.fail("OpenCode is not installed or not in PATH."), file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0:
        print(C.fail(f"Failed to check OpenCode version (exit code {result.returncode})."), file=sys.stderr)
        sys.exit(1)

    version_str = result.stdout.strip().split()[-1]

    def parse_ver(v: str) -> tuple[int, ...]:
        match = re.search(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", v)
        if match:
            return tuple(int(x) for x in match.groups() if x is not None)
        return (0,)

    actual = parse_ver(version_str)
    required = parse_ver(MINIMUM_OPENCODE_VERSION)

    if actual < required:
        print(C.fail(f"OpenCode version is too old: found {version_str}, require >= {MINIMUM_OPENCODE_VERSION}"), file=sys.stderr)
        sys.exit(1)


def truthy_env(name: str) -> bool:
    value = os.environ.get(name)
    return value is not None and value not in {"", "0", "false", "False", "no", "No"}


# --- Stream-based late model discovery ---------------------------------------

_MODEL_BEARING_KEYS = ("modelID", "providerID", "model")


def _scan_event_for_model(payload: Any) -> Optional[str]:
    """Recursively walk an event payload looking for a model identity.

    Returns a 'providerID/modelID' string if both are found in the
    same dict, else just the value of the first useful key found, or
    None.
    """
    if isinstance(payload, dict):
        # Same-dict providerID + modelID combo wins.
        pid = payload.get("providerID")
        mid = payload.get("modelID") or (
            payload.get("model") if isinstance(payload.get("model"), str) else None
        )
        if isinstance(mid, dict):
            inner_pid = mid.get("providerID")
            inner_id = mid.get("id") or mid.get("modelID")
            if inner_pid and inner_id:
                return f"{inner_pid}/{inner_id}"
            if inner_id:
                return str(inner_id)
        if pid and mid and isinstance(mid, str):
            return f"{pid}/{mid}"
        if isinstance(mid, str) and mid:
            return mid

        for v in payload.values():
            found = _scan_event_for_model(v)
            if found:
                return found
        return None
    if isinstance(payload, list):
        for item in payload:
            found = _scan_event_for_model(item)
            if found:
                return found
    return None


# --- Model resolution ---------------------------------------------------------

_MODEL_FLAG_NAMES = ("--model", "-m")
_VARIANT_FLAG_NAMES = ("--variant",)


def _extract_flag_value(tokens: list[str], flag_names: tuple[str, ...]) -> Optional[str]:
    """Return the value of the first matching flag in tokens, or None.

    Supports both `--flag value` and `--flag=value` forms.
    """
    for i, tok in enumerate(tokens):
        for flag in flag_names:
            if tok == flag and i + 1 < len(tokens):
                return tokens[i + 1]
            prefix = flag + "="
            if tok.startswith(prefix):
                return tok[len(prefix):]
    return None


_DISCOVERY_TIMEOUT_S = float(os.environ.get("CODECOME_MODEL_DISCOVERY_TIMEOUT", "1.0"))
_MODEL_PROBE_TIMEOUT_S = float(os.environ.get("CODECOME_MODEL_PROBE_TIMEOUT", "20.0"))


def _discover_opencode_default_model() -> Optional[str]:
    """Best-effort: return the model used in the most recent opencode
    session for this project's worktree, or None.

    Implementation: query the opencode SQLite DB via `opencode db`,
    asking for the latest session.model JSON for this worktree;
    fall back to the latest session globally.

    Honors a 1-second timeout. Errors are silently ignored.
    """
    worktree = str(ROOT)

    queries = [
        # Project-scoped first.
        (
            "SELECT s.model FROM session s "
            "JOIN project p ON s.project_id = p.id "
            f"WHERE p.worktree = '{worktree}' AND s.model IS NOT NULL "
            "ORDER BY s.time_updated DESC LIMIT 1"
        ),
        # Global fallback.
        (
            "SELECT s.model FROM session s "
            "WHERE s.model IS NOT NULL "
            "ORDER BY s.time_updated DESC LIMIT 1"
        ),
    ]

    for query in queries:
        try:
            result = subprocess.run(
                ["opencode", "db", query, "--format", "tsv"],
                capture_output=True,
                text=True,
                timeout=_DISCOVERY_TIMEOUT_S,
            )
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            return None
        if result.returncode != 0:
            continue

        # Output looks like:
        #   model
        #   {"id":"gpt-5.4","providerID":"github-copilot"}
        lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        raw = lines[-1]
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            # Some opencode versions may print bare strings.
            return raw if raw and raw != "model" else None

        if isinstance(obj, dict):
            mid = obj.get("id") or obj.get("modelID")
            pid = obj.get("providerID")
            if pid and mid:
                return f"{pid}/{mid}"
            if mid:
                return str(mid)

    return None


def _extract_model_from_export(export_text: str) -> Optional[str]:
    try:
        payload = json.loads(export_text)
    except json.JSONDecodeError:
        return None

    if isinstance(payload, dict):
        found = _scan_event_for_model(payload)
        if found:
            return found
    return None


def _strip_probe_unsafe_flags(command: list[str]) -> list[str]:
    """Remove flags that would make a probe reuse or mutate a real session."""
    stripped: list[str] = []
    skip_next = False
    value_flags = {"--session", "-s", "--title", "--attach", "--port", "-p"}
    standalone_flags = {"--continue", "-c", "--fork", "--share"}

    for token in command:
        if skip_next:
            skip_next = False
            continue

        name = token.split("=", 1)[0]
        if name in standalone_flags:
            continue
        if name in value_flags:
            if "=" not in token:
                skip_next = True
            continue

        stripped.append(token)

    return stripped


@lru_cache(maxsize=32)
def _probe_effective_model(probe_key: tuple[str, ...]) -> Optional[str]:
    """Run a tiny throwaway session and read the actual chosen model.

    This is only used when the wrapper would otherwise have to guess from
    session history or show unknown. The probe session is deleted after the
    export succeeds.
    """
    command = list(probe_key)
    session_id: str | None = None
    try:
        result = subprocess.run(
            command + ["Reply with exactly OK."],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=_MODEL_PROBE_TIMEOUT_S,
        )
        if result.returncode != 0:
            return None

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return None

        first = json.loads(lines[0])
        if not isinstance(first, dict):
            return None
        session_id = first.get("sessionID")
        if not isinstance(session_id, str) or not session_id:
            return None

        exported = subprocess.run(
            ["opencode", "export", session_id],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=_MODEL_PROBE_TIMEOUT_S,
        )
        if exported.returncode != 0:
            return None
        return _extract_model_from_export(exported.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    finally:
        if session_id:
            try:
                subprocess.run(
                    ["opencode", "session", "delete", session_id],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except (OSError, subprocess.SubprocessError):
                pass


def _read_codecome_yml_agent(agent_name: str) -> tuple[Optional[str], Optional[str]]:
    """Return (model, variant) from codecome.yml agents.<name>, or (None, None)."""
    config_path = ROOT / "codecome.yml"
    if not config_path.exists():
        return None, None
    try:
        import yaml  # type: ignore
    except ImportError:
        return None, None
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:  # noqa: BLE001
        return None, None
    if not isinstance(data, dict):
        return None, None
    agents = data.get("agents")
    if not isinstance(agents, dict):
        return None, None
    entry = agents.get(agent_name)
    if not isinstance(entry, dict):
        return None, None
    model = entry.get("model")
    variant = entry.get("variant")
    return (str(model) if model else None, str(variant) if variant else None)


def resolve_model_and_variant(
    agent_name: str,
    opencode_args_tokens: list[str],
    *,
    discover_default: bool = True,
) -> tuple[Optional[str], Optional[str], str, str]:
    """Resolve effective model and variant with source labels.

    Returns (model, variant, model_source, variant_source).
    Source values: 'OPENCODE_ARGS', 'env CODECOME_MODEL',
    'env CODECOME_MODEL_VARIANT', 'codecome.yml',
    'opencode session history', or '(unknown)'.

    `discover_default=True` enables the (slow-ish) opencode db probe
    when none of the configured sources resolved a model.
    """
    model_from_args = _extract_flag_value(opencode_args_tokens, _MODEL_FLAG_NAMES)
    variant_from_args = _extract_flag_value(opencode_args_tokens, _VARIANT_FLAG_NAMES)

    env_model = (os.environ.get("CODECOME_MODEL") or "").strip() or None
    env_variant = (os.environ.get("CODECOME_MODEL_VARIANT") or "").strip() or None

    yaml_model, yaml_variant = _read_codecome_yml_agent(agent_name)

    if model_from_args:
        model, model_source = model_from_args, "OPENCODE_ARGS"
    elif env_model:
        model, model_source = env_model, "env CODECOME_MODEL"
    elif yaml_model:
        model, model_source = yaml_model, "codecome.yml"
    else:
        discovered = _discover_opencode_default_model() if discover_default else None
        if discovered:
            model, model_source = discovered, "opencode session history"
        else:
            model, model_source = None, "(unknown)"

    if variant_from_args:
        variant, variant_source = variant_from_args, "OPENCODE_ARGS"
    elif env_variant:
        variant, variant_source = env_variant, "env CODECOME_MODEL_VARIANT"
    elif yaml_variant:
        variant, variant_source = yaml_variant, "codecome.yml"
    else:
        # Discovery doesn't carry variant (no DB column).
        variant, variant_source = None, "(unknown)"

    return model, variant, model_source, variant_source


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
_APPLY_PATCH_DIFF_LINES = int(os.environ.get("CODECOME_APPLY_PATCH_DIFF_LINES", str(_EDIT_DIFF_LINES)))
_APPLY_PATCH_MAX_FILES = int(os.environ.get("CODECOME_APPLY_PATCH_MAX_FILES", "10"))
_INTERNAL_READ_SUPPRESS = os.environ.get("CODECOME_INTERNAL_READ_SUPPRESS", "1") not in ("0", "false", "False", "no")

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


_FINDING_FILENAME_RE = re.compile(r"^(CC-\d{4,})-(.+)\.md$")
_ROOT_WORKSPACE_DOCS = {"AGENTS.md", "README.md"}
_ROOT_WORKSPACE_CONFIGS = {"codecome.yml"}


def _classify_internal_read(rel_path: str) -> str | None:
    """Return a description for a suppressible internal read, or None.

    rel_path is repo-relative. Absolute paths (outside the repo) return None.
    """
    if not rel_path or os.path.isabs(rel_path):
        return None

    parts = Path(rel_path).parts
    if not parts:
        return None

    # Root-level workspace docs and config
    if len(parts) == 1:
        name = parts[0]
        if name in _ROOT_WORKSPACE_DOCS:
            return f"reading workspace doc: {name}"
        if name in _ROOT_WORKSPACE_CONFIGS:
            return f"reading workspace config: {name}"
        return None

    # .opencode/...
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

    # itemdb/...
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

    # runs/<name>.md
    if parts[0] == "runs" and len(parts) >= 2:
        return f"reading run summary: {parts[1]}"

    # templates/<name>
    if parts[0] == "templates" and len(parts) >= 2:
        return f"reading template: {parts[1]}"

    return None


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
        # Cache the full body before considering display suppression so
        # subsequent write/edit diffs always have a baseline.
        _cache_set(file_path, body)

        # Display suppression for internal workspace files.
        if _INTERNAL_READ_SUPPRESS:
            description = _classify_internal_read(rel_path)
            if description is not None:
                is_partial = offset is not None or limit is not None
                if is_partial:
                    description = f"{description} (partial)"
                # Build a fresh sections list for the suppressed panel:
                # path header + dim italic description, no body.
                suppressed: list[Any] = [Text(rel_path, style="bold cyan")]
                suppressed.append(Text(description, style="dim italic"))
                console.print(Panel(Group(*suppressed), title="Read", border_style=border, expand=True))
                return True

        if not body:
            sections.append(Text("(empty file)", style="dim"))
        else:
            raw_body = _strip_line_numbers(body)
            lexer = _detect_lexer(file_path)
            _render_truncated_body_rich(console, sections, raw_body, _READ_DISPLAY_LINES, lexer, footer)

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

    kind, payload, footer = _strip_read_framing(output)

    if kind == "file":
        body = str(payload).strip()
        _cache_set(file_path, body)

        if _INTERNAL_READ_SUPPRESS:
            description = _classify_internal_read(rel_path)
            if description is not None:
                is_partial = offset is not None or limit is not None
                suffix = " (partial)" if is_partial else ""
                print(C.header(f"read [{description}]{suffix}"))
                return True

        print(C.header(f"read {rel_path}"))
        if offset is not None and limit is not None:
            print(f"  lines {offset}..{offset + limit - 1}")
        raw_body = _strip_line_numbers(body)
        _render_truncated_body_plain(raw_body, _READ_DISPLAY_LINES, footer)
        return True

    print(C.header(f"read {rel_path}"))
    if offset is not None and limit is not None:
        print(f"  lines {offset}..{offset + limit - 1}")

    if kind == "directory":
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


# --- Apply-patch renderer -----------------------------------------------------

@dataclass
class _ParsedFilePatch:
    op: str  # add, update, delete, rename, unknown
    path: str
    old_path: str
    hunks: str  # unified-diff-ready text
    added: int
    removed: int


_APPLY_PATCH_HEADER_RE = re.compile(
    r"^\*\*\*\s*(Begin Patch|End Patch|Update File|Add File|Delete File|Rename File|Move File):?\s*(.*)",
    re.MULTILINE,
)


def _parse_apply_patch_envelope(text: str) -> list[_ParsedFilePatch]:
    """Parse the *** Begin Patch / *** Update File / *** End Patch envelope."""
    results: list[_ParsedFilePatch] = []
    # Split on *** headers
    parts = _APPLY_PATCH_HEADER_RE.split(text)
    # parts is [preamble, directive1, path1, body1, directive2, path2, body2, ...]
    i = 1  # skip preamble
    while i + 2 <= len(parts):
        directive = parts[i].strip()
        file_path = parts[i + 1].strip()
        body = parts[i + 2] if i + 2 < len(parts) else ""
        i += 3

        if directive in ("Begin Patch", "End Patch"):
            continue

        op_map = {
            "Update File": "update",
            "Add File": "add",
            "Delete File": "delete",
            "Rename File": "rename",
            "Move File": "rename",
        }
        op = op_map.get(directive, "unknown")
        old_path = ""
        if op == "rename" and " -> " in file_path:
            old_path, file_path = file_path.split(" -> ", 1)
            old_path = old_path.strip()
            file_path = file_path.strip()

        # Count +/- lines
        body_lines = body.split("\n")
        added = sum(1 for l in body_lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in body_lines if l.startswith("-") and not l.startswith("---"))

        # Synthesize unified diff header
        rel = _relativize_path(file_path)
        old_rel = _relativize_path(old_path) if old_path else rel
        if op == "add":
            header = f"--- /dev/null\n+++ b/{rel}\n"
        elif op == "delete":
            header = f"--- a/{rel}\n+++ /dev/null\n"
        else:
            header = f"--- a/{old_rel}\n+++ b/{rel}\n"

        hunks = header + body.strip() + "\n"
        results.append(_ParsedFilePatch(op=op, path=file_path, old_path=old_path, hunks=hunks, added=added, removed=removed))

    return results


def _parse_apply_patch_json_list(patches: list[dict[str, Any]]) -> list[_ParsedFilePatch]:
    """Parse {patches: [{path, diff}, ...]} variant."""
    results: list[_ParsedFilePatch] = []
    for p in patches:
        path = str(p.get("path", p.get("file", "")))
        diff_text = str(p.get("diff", p.get("patch", "")))
        lines = diff_text.split("\n")
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        rel = _relativize_path(path)
        header = f"--- a/{rel}\n+++ b/{rel}\n"
        hunks = header + diff_text.strip() + "\n"
        results.append(_ParsedFilePatch(op="update", path=path, old_path="", hunks=hunks, added=added, removed=removed))
    return results


def _extract_apply_patch_payload(state: dict[str, Any]) -> tuple[str, list[_ParsedFilePatch], str]:
    """Extract and parse apply_patch input. Returns (raw_text, parsed_patches, output_str)."""
    inp = state.get("input")
    output = state.get("output")
    output_str = str(output) if output is not None else ""

    raw_text = ""
    if isinstance(inp, dict):
        raw_text = str(inp.get("patch", inp.get("input", inp.get("content", ""))))
        # Check for {patches: [...]} variant
        if not raw_text and isinstance(inp.get("patches"), list):
            patches = _parse_apply_patch_json_list(inp["patches"])
            return "", patches, output_str
    elif isinstance(inp, str):
        raw_text = inp

    if not raw_text:
        return "", [], output_str

    # Try envelope parse
    if "*** " in raw_text:
        patches = _parse_apply_patch_envelope(raw_text)
        if patches:
            return raw_text, patches, output_str

    # Fallback: raw unified diff — treat as single file
    if raw_text.lstrip().startswith(("--- ", "diff --git")):
        lines = raw_text.split("\n")
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        patches = [_ParsedFilePatch(op="unknown", path="(patch)", old_path="", hunks=raw_text, added=added, removed=removed)]
        return raw_text, patches, output_str

    # Could not parse; return raw text with empty patches for fallback rendering
    return raw_text, [], output_str


def render_apply_patch_rich(console: Console, state: dict[str, Any]) -> bool:
    raw_text, patches, output_str = _extract_apply_patch_payload(state)
    status = str(state.get("status", ""))

    if not patches and not raw_text:
        return False

    from rich.syntax import Syntax

    is_error = _is_likely_error(output_str)
    if status == "completed":
        border = "red" if is_error else "green"
    else:
        border = "yellow"

    sections: list[Any] = []

    if not patches:
        # Fallback: could not parse, show raw as diff syntax
        byte_size = len(raw_text.encode("utf-8", errors="replace"))
        line_count = raw_text.count("\n")
        sections.append(Text(f"Raw patch: {line_count} lines, {byte_size} bytes", style="dim"))
        sections.append(Text())
        truncated_lines = raw_text.split("\n")[:_WRITE_DIFF_LIMIT]
        leftover = max(0, raw_text.count("\n") - _WRITE_DIFF_LIMIT)
        sections.append(Syntax("\n".join(truncated_lines), "diff", theme="monokai", word_wrap=True))
        if leftover > 0:
            sections.append(Text(f"... {leftover} more lines", style="dim"))
    else:
        # Summary header
        total_added = sum(p.added for p in patches)
        total_removed = sum(p.removed for p in patches)
        sections.append(Text(f"{len(patches)} file(s) changed: +{total_added} -{total_removed}", style="dim"))
        sections.append(Text())

        # Per-file rendering
        shown = patches[:_APPLY_PATCH_MAX_FILES]
        for fp in shown:
            rel = _relativize_path(fp.path)
            label = f"{fp.op:<8} {rel}  +{fp.added} -{fp.removed}"
            sections.append(Text(label, style="bold cyan"))

            diff_lines_list = fp.hunks.split("\n")
            # Convert to list with newlines for _truncate_diff
            diff_with_nl = [l + "\n" for l in diff_lines_list if l or diff_lines_list[-1:] != [l]]
            truncated, leftover = _truncate_diff(diff_with_nl, _APPLY_PATCH_DIFF_LINES)
            diff_text = "".join(truncated)
            if diff_text.strip():
                sections.append(Syntax(diff_text, "diff", theme="monokai", word_wrap=True))
            if leftover > 0:
                sections.append(Text(f"... {leftover} more lines", style="dim"))
            sections.append(Text())

        if len(patches) > _APPLY_PATCH_MAX_FILES:
            remaining = len(patches) - _APPLY_PATCH_MAX_FILES
            sections.append(Text(f"... and {remaining} more file(s)", style="dim"))

    # Status line
    if output_str.strip():
        sections.append(Text(output_str.strip(), style="red" if is_error else "green"))

    console.print(Panel(Group(*sections), title="Apply patch", border_style=border, expand=True))

    # Cache invalidation on success
    if status == "completed" and not is_error:
        for fp in patches:
            full_path = fp.path
            if not os.path.isabs(full_path):
                full_path = os.path.join(ROOT, full_path)
            _cache_reread(full_path)

    return True


def render_apply_patch_plain(state: dict[str, Any]) -> bool:
    raw_text, patches, output_str = _extract_apply_patch_payload(state)
    status = str(state.get("status", ""))

    if not patches and not raw_text:
        return False

    is_error = _is_likely_error(output_str)

    if not patches:
        # Fallback
        line_count = raw_text.count("\n")
        byte_size = len(raw_text.encode("utf-8", errors="replace"))
        print(C.header(f"apply_patch (raw: {line_count} lines, {byte_size} bytes)"))
        truncated_lines = raw_text.split("\n")[:_WRITE_DIFF_LIMIT]
        for line in truncated_lines:
            print(f"  {line}")
        leftover = max(0, raw_text.count("\n") - _WRITE_DIFF_LIMIT)
        if leftover > 0:
            print(f"  ... {leftover} more lines")
    else:
        total_added = sum(p.added for p in patches)
        total_removed = sum(p.removed for p in patches)
        print(C.header(f"apply_patch ({len(patches)} file(s): +{total_added} -{total_removed})"))

        shown = patches[:_APPLY_PATCH_MAX_FILES]
        for fp in shown:
            rel = _relativize_path(fp.path)
            print(f"  {fp.op:<8} {rel}  +{fp.added} -{fp.removed}")
            diff_with_nl = [l + "\n" for l in fp.hunks.split("\n")]
            truncated, leftover = _truncate_diff(diff_with_nl, _APPLY_PATCH_DIFF_LINES)
            for line in truncated:
                print(f"    {line}", end="")
            if leftover > 0:
                print(f"    ... {leftover} more lines")

        if len(patches) > _APPLY_PATCH_MAX_FILES:
            remaining = len(patches) - _APPLY_PATCH_MAX_FILES
            print(f"  ... and {remaining} more file(s)")

    if output_str.strip():
        if is_error:
            print(f"  {C.fail(output_str.strip())}")
        else:
            print(f"  {C.ok(output_str.strip())}")

    # Cache invalidation on success
    if status == "completed" and not is_error:
        for fp in patches:
            full_path = fp.path
            if not os.path.isabs(full_path):
                full_path = os.path.join(ROOT, full_path)
            _cache_reread(full_path)

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
    elif tool_lower in ("apply_patch", "applypatch", "apply-patch"):
        if HAVE_RICH:
            return render_apply_patch_rich(console, state)
        else:
            return render_apply_patch_plain(state)
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


# LLM finish reasons we have observed, classified.
#
# Clean terminal: the model finished the turn on its own, after emitting
# the final assistant message.
#
# Mid-turn: the model emitted tool calls and is expected to be invoked
# again with the tool results. Not terminal on its own.
#
# Failure terminal: the response was cut short by something other than
# the model itself signalling end-of-turn. The wrapper currently treats
# these as success because opencode still exits 0; we explicitly flag
# them here so callers can fail loudly instead.
_FINISH_TERMINAL_OK = {"stop", "end_turn"}
_FINISH_MID_TURN = {"tool-calls", "tool_use"}
_FINISH_FAILURE = {
    "content-filter",   # provider safety filter aborted the response
    "content_filter",   # alternative spelling
    "length",           # output token cap reached
    "max_tokens",       # alternative spelling
    "error",
}


def render_step_finish(console: Console, event: dict[str, Any]) -> None:
    part = event.get("part", {})
    reason = str(part.get("reason", "unknown"))
    tokens = format_tokens(part.get("tokens", {}))
    suffix = f" ({tokens})" if tokens else ""
    style = "dim"
    if reason in _FINISH_FAILURE:
        style = "bold red"
    if HAVE_RICH:
        console.print(Text(f"step finished: {reason}{suffix}", style=style))
    else:
        if reason in _FINISH_FAILURE:
            print(C.fail(f"step finished: {reason}{suffix}"))
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
    parser.add_argument("--phase", help="Phase number (required unless --show-model).")
    parser.add_argument("--label", help="Human-readable phase label (required unless --show-model).")
    parser.add_argument("--agent", help="OpenCode agent name.")
    parser.add_argument("--prompt-file", help="Prompt file path relative to repo root (required unless --show-model).")
    parser.add_argument("--finding", help="Finding id for prompt substitution.")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("--debug", action="store_true", help="Mirror raw JSON events to stderr.")
    parser.add_argument("--read-display-lines", type=int, help="Max lines shown in read output (default: 10, env: CODECOME_READ_DISPLAY_LINES).")
    parser.add_argument("--write-content-lines", type=int, help="Max lines shown for new-file write content (default: 25, env: CODECOME_WRITE_CONTENT_LINES).")
    parser.add_argument("--write-diff-limit", type=int, help="Max diff lines shown for write (default: 50, env: CODECOME_WRITE_DIFF_LIMIT).")
    parser.add_argument("--edit-diff-lines", type=int, help="Max diff lines shown for edit (default: 25, env: CODECOME_EDIT_DIFF_LINES).")
    parser.add_argument(
        "--show-model",
        action="store_true",
        help="Print the model-resolution table for --agent and exit. No phase is launched.",
    )
    return parser


def build_child_command(args: argparse.Namespace) -> tuple[list[str], Optional[str], Optional[str], str, str]:
    """Return the child command and the resolved model/variant + sources.

    Appends --model/--variant from env or codecome.yml only when
    OPENCODE_ARGS does not already pass them.
    """
    cmd = ["opencode", "run", "--format", "json", "--agent", args.agent]
    if truthy_env("CODECOME_THINKING"):
        cmd.append("--thinking")

    extra_args = shlex.split(os.environ.get("OPENCODE_ARGS", ""))
    cmd.extend(extra_args)

    model, variant, model_source, variant_source = resolve_model_and_variant(
        args.agent, extra_args
    )

    # Append --model/--variant to enforce env/yaml-resolved values when
    # OPENCODE_ARGS did not already pass them. OPENCODE_ARGS (and any
    # earlier --model/-m/--variant in cmd) always wins because we never
    # touch values that came from there. Discovered defaults
    # ('opencode session history') are display-only and are NOT
    # enforced — opencode will pick its own default anyway, and
    # forcing it would surprise users when they switch models in the
    # TUI between phases.
    _ENFORCING_SOURCES = {"env CODECOME_MODEL", "codecome.yml"}
    _ENFORCING_VARIANT_SOURCES = {"env CODECOME_MODEL_VARIANT", "codecome.yml"}

    if model and model_source in _ENFORCING_SOURCES:
        cmd.extend(["--model", model])
    if variant and variant_source in _ENFORCING_VARIANT_SOURCES:
        cmd.extend(["--variant", variant])

    return cmd, model, variant, model_source, variant_source


def resolve_runtime_model_for_banner(
    args: argparse.Namespace,
    command: list[str],
    model: Optional[str],
    variant: Optional[str],
    model_source: str,
    variant_source: str,
) -> tuple[Optional[str], Optional[str], str, str]:
    """Prefer the actual runtime model over a historical guess.

    Env/YAML/CLI-pinned values remain authoritative. When the wrapper would
    otherwise show a best-effort historical value or unknown, run a tiny probe
    with the same launch configuration and use the exported session metadata.
    """
    if model_source in {"OPENCODE_ARGS", "env CODECOME_MODEL", "codecome.yml"}:
        return model, variant, model_source, variant_source

    probe_command = _strip_probe_unsafe_flags(command)
    probed = _probe_effective_model(tuple(probe_command))
    if probed:
        return probed, variant, "runtime probe", variant_source

    return model, variant, model_source, variant_source


def show_model_table(agent_name: str) -> int:
    """Print the model-resolution table for an agent and exit."""
    extra_args = shlex.split(os.environ.get("OPENCODE_ARGS", ""))

    args_model = _extract_flag_value(extra_args, _MODEL_FLAG_NAMES)
    args_variant = _extract_flag_value(extra_args, _VARIANT_FLAG_NAMES)
    env_model = (os.environ.get("CODECOME_MODEL") or "").strip() or None
    env_variant = (os.environ.get("CODECOME_MODEL_VARIANT") or "").strip() or None
    yaml_model, yaml_variant = _read_codecome_yml_agent(agent_name)
    discovered = _discover_opencode_default_model()

    model, variant, model_source, variant_source = resolve_model_and_variant(
        agent_name, extra_args
    )

    def fmt(v: Optional[str]) -> str:
        return v if v else "(not set)"

    print(C.header(f"Model resolution for agent {agent_name}:"))
    print()
    print(f"  {C.DIM}OPENCODE_ARGS{C.RESET}                 model={fmt(args_model)}  variant={fmt(args_variant)}")
    print(f"  {C.DIM}env CODECOME_MODEL{C.RESET}            model={fmt(env_model)}")
    print(f"  {C.DIM}env CODECOME_MODEL_VARIANT{C.RESET}    variant={fmt(env_variant)}")
    print(f"  {C.DIM}codecome.yml{C.RESET}                  model={fmt(yaml_model)}  variant={fmt(yaml_variant)}")
    print(f"  {C.DIM}opencode session history{C.RESET}      model={fmt(discovered)}")
    print(f"  {C.DIM}runtime probe{C.RESET}                 not run by show-model")
    print()
    effective_model = model or "(unknown)"
    effective_variant = variant or "(unknown)"
    print(f"  {C.BOLD}effective{C.RESET}                     "
          f"model={effective_model}  variant={effective_variant}")
    print(f"  {C.DIM}sources{C.RESET}                       "
          f"model: {model_source}  variant: {variant_source}")
    return 0


def main() -> int:
    check_opencode_version()

    parser = build_parser()
    args = parser.parse_args()

    # --show-model short-circuit: print the resolution table and exit.
    if args.show_model:
        agent_name = args.agent or "recon"
        return show_model_table(agent_name)

    # The phase-launching mode requires the usual arguments.
    missing = [n for n in ("phase", "label", "agent", "prompt_file") if getattr(args, n) is None]
    if missing:
        parser.error(
            "the following arguments are required when not using --show-model: "
            + ", ".join("--" + n.replace("_", "-") for n in missing)
        )

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
    command, model, variant, model_source, variant_source = build_child_command(args)
    model, variant, model_source, variant_source = resolve_runtime_model_for_banner(
        args, command, model, variant, model_source, variant_source
    )

    model_label = model or "(unknown)"
    variant_label = variant or "(unknown)"

    # Build the single-line banner. Order: agent  model  variant?  prompt
    # followed by a trailing parenthetical with the resolution source(s).
    parts = [f"agent={args.agent}", f"model={model_label}"]
    if variant is not None:
        parts.append(f"variant={variant_label}")
    parts.append(f"prompt={args.prompt_file}")

    if variant is not None:
        sources_tail = (
            f"(model source: {model_source}, variant source: {variant_source})"
        )
    else:
        sources_tail = f"(model source: {model_source})"

    main_line = "  ".join(parts) + "  " + sources_tail

    if HAVE_RICH:
        console.print(Rule(title=f"Phase {args.phase}: {args.label}", style="bold cyan"))
        console.print(Text(main_line, style="dim"))
        if args.finding:
            console.print(Text(f"finding={args.finding}", style="dim"))
        if str(args.phase) == "1":
            console.print(Text(
                "Phase 1 has two sub-stages: 1a recon notes, 1b sandbox bootstrap.",
                style="cyan",
            ))
    else:
        print(C.header(f"Phase {args.phase}: {args.label}"))
        print(C.info(main_line))
        if args.finding:
            print(C.info(f"finding={args.finding}"))
        if str(args.phase) == "1":
            print(C.info(
                "Phase 1 has two sub-stages: 1a recon notes, 1b sandbox bootstrap."
            ))
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
        late_model_announced = False
        # Tee the raw JSONL stream to disk for post-mortem analysis.
        # The path is under tmp/ which is intended to be ephemeral.
        finding_tag = (args.finding or "no-finding").replace("/", "_")
        transcript_dir = ROOT / "tmp"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = transcript_dir / f"last-phase-{args.phase}-{finding_tag}.jsonl"
        last_finish_reason: Optional[str] = None
        last_finish_tokens: dict[str, Any] = {}
        any_step_finish_seen = False
        try:
            transcript_fp: Optional[Any] = transcript_path.open("w", encoding="utf-8")
        except OSError as exc:
            transcript_fp = None
            if HAVE_RICH:
                console.print(Text(f"warning: could not open transcript {transcript_path}: {exc}", style="yellow"))
            else:
                print(C.warn(f"warning: could not open transcript {transcript_path}: {exc}"))

        try:
            for raw_line in process.stdout:
                if transcript_fp is not None:
                    try:
                        transcript_fp.write(raw_line)
                    except OSError:
                        pass
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

                # Late discovery: if the JSON stream ever carries the model
                # identity in a tool/event payload, surface it once.
                if not late_model_announced:
                    discovered_in_stream = _scan_event_for_model(event)
                    if discovered_in_stream and discovered_in_stream != model:
                        late_model_announced = True
                        msg = (
                            f"[model resolved from stream] {discovered_in_stream} "
                            f"(banner showed {model_label})"
                        )
                        if HAVE_RICH:
                            console.print(Text(msg, style="yellow"))
                        else:
                            print(C.warn(msg))

                # Track every step_finish so we can audit the turn after
                # the child exits. The LAST step_finish in the stream is
                # the one that decides whether the run completed cleanly.
                if event.get("type") == "step_finish":
                    any_step_finish_seen = True
                    part = event.get("part") or {}
                    reason = part.get("reason")
                    if isinstance(reason, str):
                        last_finish_reason = reason
                    tokens = part.get("tokens")
                    if isinstance(tokens, dict):
                        last_finish_tokens = tokens

                render_event(console, args.phase, args.label, event)
        finally:
            if transcript_fp is not None:
                try:
                    transcript_fp.flush()
                    transcript_fp.close()
                except OSError:
                    pass

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

    # Decide whether the LLM stream ended cleanly. Even when opencode
    # itself exits 0, a non-clean finish reason (e.g. content-filter,
    # length, error) means the model's response was cut short and the
    # phase did not complete its intended work. Treat that as a failure
    # so callers (Make, exploit-all, CI) can react instead of being
    # told "Phase N completed successfully" on a half-finished run.
    finish_warning: Optional[str] = None
    if returncode == 0:
        if not any_step_finish_seen:
            finish_warning = (
                "no step_finish events were observed in the JSON stream; "
                "the agent likely produced no work"
            )
        elif last_finish_reason is None:
            finish_warning = "step_finish observed but reason was missing"
        elif last_finish_reason in _FINISH_FAILURE:
            finish_warning = (
                f"LLM stream ended with finish reason '{last_finish_reason}' "
                "(provider truncated the response; the phase did not finish)"
            )
        elif last_finish_reason in _FINISH_MID_TURN:
            finish_warning = (
                f"LLM stream ended after a mid-turn step (reason "
                f"'{last_finish_reason}') without a terminal 'stop'; the "
                "agent likely ran out of iterations or was cut short by "
                "the provider before producing a final response"
            )
        elif last_finish_reason not in _FINISH_TERMINAL_OK:
            finish_warning = (
                f"LLM stream ended with unrecognised finish reason "
                f"'{last_finish_reason}'; treating as incomplete"
            )

    if finish_warning is not None and returncode == 0:
        # Promote to an error so the make target / exploit-all loop fails.
        returncode = 2

    if returncode == 0:
        if HAVE_RICH:
            console.print(Rule(style="green"))
            console.print(Text(f"{C.SYM_OK} Phase {args.phase} completed successfully", style="green"))
            console.print(
                Text(
                    f"  finish reason: {last_finish_reason!r}  "
                    f"transcript: {transcript_path.relative_to(ROOT)}",
                    style="dim",
                )
            )
        else:
            print(C.ok(f"Phase {args.phase} completed successfully"))
            print(
                f"  finish reason: {last_finish_reason!r}  "
                f"transcript: {transcript_path.relative_to(ROOT)}"
            )
    elif returncode == 130:
        if HAVE_RICH:
            console.print(Rule(style="yellow"))
            console.print(Text(f"{C.SYM_WARN} Phase {args.phase} interrupted", style="yellow"))
        else:
            print(C.warn(f"Phase {args.phase} interrupted"))
    else:
        if HAVE_RICH:
            console.print(Rule(style="red"))
            console.print(
                Text(
                    f"{C.SYM_FAIL} Phase {args.phase} did not complete cleanly "
                    f"(exit code {returncode})",
                    style="red",
                )
            )
            if finish_warning:
                console.print(Text(f"  reason: {finish_warning}", style="red"))
            console.print(
                Text(
                    f"  transcript: {transcript_path.relative_to(ROOT)}",
                    style="dim",
                )
            )
            console.print(
                Text(
                    "  hint: the run is likely partial; rerun the phase or "
                    "switch to a different model/provider before retrying",
                    style="yellow",
                )
            )
        else:
            print(
                C.fail(
                    f"Phase {args.phase} did not complete cleanly "
                    f"(exit code {returncode})"
                )
            )
            if finish_warning:
                print(C.fail(f"  reason: {finish_warning}"))
            print(f"  transcript: {transcript_path.relative_to(ROOT)}")
            print(
                C.warn(
                    "  hint: the run is likely partial; rerun the phase or "
                    "switch to a different model/provider before retrying"
                )
            )

    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
