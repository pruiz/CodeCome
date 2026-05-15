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
import time
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
        model_field = payload.get("model")
        mid = payload.get("modelID") or (model_field if isinstance(model_field, str) else None)
        if isinstance(model_field, dict):
            inner_pid = model_field.get("providerID")
            inner_id = model_field.get("id") or model_field.get("modelID")
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
        return Console(force_terminal=True, highlight=False)
    if color_mode == "never":
        return Console(force_terminal=False, no_color=True, highlight=False)
    return Console(highlight=False)


_PHASE_NAMES = {
    "1": "reconnaissance",
    "2": "hypothesis_generation",
    "3": "counter_analysis",
    "4": "validation",
    "5": "exploit_development",
    "6": "reporting",
}


def load_prompt(prompt_file: Path, finding: str | None, phase: str | None = None) -> str:
    prompt = prompt_file.read_text(encoding="utf-8")
    if finding is not None:
        placeholder = "FINDING_PATH_OR_ID"
        if placeholder not in prompt:
            raise ValueError(f"Prompt placeholder {placeholder!r} not found in {prompt_file}")
        prompt = prompt.replace(placeholder, finding)

    # --- Extra prompt sources (additive, appended in order) ---------------
    extra_sections: list[tuple[str, str]] = []

    # Source 1: codecome.yml  audit.extra_prompts.<phase_name>
    if phase is not None:
        phase_name = _PHASE_NAMES.get(str(phase))
        if phase_name:
            try:
                import yaml  # type: ignore

                config_path = ROOT / "codecome.yml"
                if config_path.exists():
                    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                    ep = cfg.get("audit", {}).get("extra_prompts", {})
                    yml_extra = ep.get(phase_name, "").strip() if isinstance(ep, dict) else ""
                    if yml_extra:
                        extra_sections.append(("From codecome.yml", yml_extra))
            except Exception:
                pass  # Non-fatal; skip if yaml missing or config is broken.

    # Source 2: PROMPT_EXTRA_FILE env var
    extra_file = os.environ.get("PROMPT_EXTRA_FILE", "").strip()
    if extra_file:
        extra_path = Path(extra_file)
        if not extra_path.is_absolute():
            extra_path = ROOT / extra_path
        if extra_path.is_file():
            file_text = extra_path.read_text(encoding="utf-8").strip()
            if file_text:
                extra_sections.append((f"From {extra_file}", file_text))

    # Source 3: PROMPT_EXTRA env var
    extra_inline = os.environ.get("PROMPT_EXTRA", "").strip()
    if extra_inline:
        extra_sections.append(("Additional instructions", extra_inline))

    if extra_sections:
        prompt += "\n\n## Additional instructions\n"
        for heading, body in extra_sections:
            prompt += f"\n### {heading}\n\n{body}\n"

    return prompt


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


# --- Permission-error renderer ------------------------------------------------

def render_permission_error_rich(console: Console, message: str) -> None:
    """Draw a bold red panel when a tool permission is auto-rejected."""
    console.print(
        Panel(
            Text(message, style="bold red"),
            title="Permission Denied",
            border_style="red",
            expand=True,
        )
    )


def render_permission_error_plain(message: str) -> None:
    print(C.fail("Permission Denied"))
    print(C.fail(f"  {message}"))


# --- Shared helper utilities --------------------------------------------------

_SNAPSHOT_CACHE: OrderedDict[str, tuple[str, float]] = OrderedDict()
_SNAPSHOT_CACHE_CAP = int(os.environ.get("CODECOME_WRITE_CACHE_CAP", "200"))
_WRITE_CACHE_ENABLED = os.environ.get("CODECOME_WRITE_CACHE", "1") not in ("0", "false", "False", "no")

_READ_DISPLAY_LINES = int(os.environ.get("CODECOME_READ_DISPLAY_LINES", "10"))
_WRITE_CONTENT_LINES = int(os.environ.get("CODECOME_WRITE_CONTENT_LINES", "25"))
_WRITE_DIFF_LIMIT = int(os.environ.get("CODECOME_WRITE_DIFF_LIMIT", "50"))
_EDIT_DIFF_LINES = int(os.environ.get("CODECOME_EDIT_DIFF_LINES", "25"))
_READ_HIGHLIGHT_LIMIT = int(os.environ.get("CODECOME_READ_HIGHLIGHT_LIMIT", str(200 * 1024)))
_GLOB_MATCH_CAP = int(os.environ.get("CODECOME_GLOB_MATCH_CAP", "10"))

# Lines that look like OpenCode summary/status rather than actual file paths.
# Examples: "0 for '*.md'", "3 match(es)", "No matches found".
_GLOB_SUMMARY_LINE_RE = re.compile(
    r"^\d+\s+(?:for\s|match)"   # "0 for '*.md'" or "3 match(es)"
    r"|^No\s+matches?\s"        # "No matches found"
    r"|^\d+\s+file"             # "0 files" / "3 files found"
)
_APPLY_PATCH_DIFF_LINES = int(os.environ.get("CODECOME_APPLY_PATCH_DIFF_LINES", str(_EDIT_DIFF_LINES)))
_APPLY_PATCH_MAX_FILES = int(os.environ.get("CODECOME_APPLY_PATCH_MAX_FILES", "10"))
_GREP_FILE_CAP = int(os.environ.get("CODECOME_GREP_FILE_CAP", "50"))
_GREP_LINE_CAP_PER_FILE = int(os.environ.get("CODECOME_GREP_LINE_CAP_PER_FILE", "5"))
_GREP_TOTAL_LINE_CAP = int(os.environ.get("CODECOME_GREP_TOTAL_LINE_CAP", "200"))
_GREP_HIGHLIGHT = os.environ.get("CODECOME_GREP_HIGHLIGHT", "1") not in ("0", "false", "False", "no")
_REASONING_MAX_CHARS = int(os.environ.get("CODECOME_REASONING_MAX_CHARS", "4000"))
_RENDER_REASONING = os.environ.get("CODECOME_RENDER_REASONING", "1") not in ("0", "false", "False", "no")
_SANDBOX_RENDER = os.environ.get("CODECOME_SANDBOX_RENDER", "1") not in ("0", "false", "False", "no")
_SANDBOX_VALIDATE_STDERR_LINES = int(os.environ.get("CODECOME_SANDBOX_VALIDATE_STDERR_LINES", "20"))
_SANDBOX_FILES_CAP = int(os.environ.get("CODECOME_SANDBOX_FILES_CAP", "15"))
_BASH_SHIM_RENDER = os.environ.get("CODECOME_BASH_SHIM_RENDER", "1") not in ("0", "false", "False", "no")
_BASH_SHIM_LS_STRIP_LONG_FORMAT = os.environ.get("CODECOME_BASH_SHIM_LS_STRIP_LONG_FORMAT", "1") not in ("0", "false", "False", "no")
_INTERNAL_READ_SUPPRESS = os.environ.get("CODECOME_INTERNAL_READ_SUPPRESS", "1") not in ("0", "false", "False", "no")

# --- Subagent visibility tunables --------------------------------------------
_SUBAGENT_HEARTBEAT_INTERVAL_S = int(os.environ.get("CODECOME_SUBAGENT_HEARTBEAT_INTERVAL_S", "30"))
_SUBAGENT_UPDATE_THROTTLE_S = int(os.environ.get("CODECOME_SUBAGENT_UPDATE_THROTTLE_S", "5"))
_TASK_PROMPT_PREVIEW_LINES = int(os.environ.get("CODECOME_TASK_PROMPT_PREVIEW_LINES", "5"))
_RENDER_SUBAGENT_UPDATES = os.environ.get("CODECOME_RENDER_SUBAGENT_UPDATES", "1") not in ("0", "false", "False", "no")

# Per-session deduplication state for subagent update events.
_SUBAGENT_LAST_STATE: dict[str, tuple[dict[str, Any], float]] = {}


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
        raw_body = _strip_line_numbers(body)
        # Cache the full body before considering display suppression so
        # subsequent write/edit diffs always have a baseline.
        _cache_set(file_path, raw_body)

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
        raw_body = _strip_line_numbers(body)
        _cache_set(file_path, raw_body)

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
    r"^\*\*\*[ \t]*(Begin Patch|End Patch|Update File|Add File|Delete File|Rename File|Move File):?[ \t]*(.*)",
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
        diff_text = _first_string(p, ("diff", "patch", "patchText", "patch_text", "content", "body"))
        lines = diff_text.split("\n")
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        rel = _relativize_path(path)
        header = f"--- a/{rel}\n+++ b/{rel}\n"
        hunks = header + diff_text.strip() + "\n"
        results.append(_ParsedFilePatch(op="update", path=path, old_path="", hunks=hunks, added=added, removed=removed))
    return results


# Keys under which the apply_patch tool may stash its patch body, in
# precedence order. github-copilot/gpt-5.x emits 'patchText'; older
# OpenAI tool-use mode emits 'input'; some MCP bridges use 'diff' or
# 'body'. The first non-empty string wins.
_PATCH_TEXT_KEYS = ("patchText", "patch_text", "patch", "input", "content", "diff", "body")


def _first_string(d: dict[str, Any], keys: tuple[str, ...]) -> str:
    """Return the first non-empty string value in d under any of keys, else ''."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def _extract_apply_patch_payload(state: dict[str, Any]) -> tuple[str, list[_ParsedFilePatch], str]:
    """Extract and parse apply_patch input. Returns (raw_text, parsed_patches, output_str)."""
    inp = state.get("input")
    output = state.get("output")
    output_str = str(output) if output is not None else ""

    raw_text = ""
    if isinstance(inp, dict):
        raw_text = _first_string(inp, _PATCH_TEXT_KEYS)
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

def _parse_glob_output(output: str) -> tuple[list[str], list[str]]:
    """Split glob output into (file_paths, summary_lines).

    Summary lines (e.g. ``0 for '*.md'``) are separated from actual file
    paths so the match count reflects real results.
    """
    files: list[str] = []
    summaries: list[str] = []
    for line in output.strip().split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if _GLOB_SUMMARY_LINE_RE.match(stripped):
            summaries.append(stripped)
        else:
            files.append(stripped)
    return files, summaries


def render_glob_rich(console: Console, state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    if not isinstance(inp, dict) or not isinstance(output, str):
        return False

    pattern = str(inp.get("pattern", ""))
    search_path = str(inp.get("path", ""))

    matches, summaries = _parse_glob_output(output)
    n_matches = len(matches)

    border = "green" if n_matches > 0 else "dim"

    sections: list[Any] = [
        Text(f"pattern={pattern}  path={_relativize_path(search_path) if search_path else '.'}", style="dim"),
        Text(),
    ]

    if n_matches == 0:
        # Show summary lines from the tool if available, otherwise generic.
        if summaries:
            for s in summaries:
                sections.append(Text(f"  {s}", style="dim"))
        else:
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

    matches, summaries = _parse_glob_output(output)
    n_matches = len(matches)

    print(C.header(f"glob {pattern} in {_relativize_path(search_path) if search_path else '.'}"))

    if n_matches == 0:
        if summaries:
            for s in summaries:
                print(f"  {s}")
        else:
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


# --- Grep renderer ------------------------------------------------------------

_GREP_LINE_RE = re.compile(r"^(?P<path>.+?):(?P<line>\d+):(?P<text>.*)$")

_GREP_HIGHLIGHT_STYLE = "bold yellow on grey23"
_GREP_BODY_STYLE = "default"
_GREP_LINENO_STYLE = "dim cyan"


def _grep_compile_pattern(pattern: str) -> re.Pattern[str] | None:
    """Compile the user's grep pattern for match highlighting. Returns None on failure."""
    if not pattern or not _GREP_HIGHLIGHT:
        return None
    try:
        return re.compile(pattern)
    except re.error:
        # Fall back to literal substring match
        try:
            return re.compile(re.escape(pattern))
        except re.error:
            return None


def _grep_format_line_rich(line_no: int, text: str, pat: re.Pattern[str] | None) -> "Text":
    """Format a single grep match line as a rich Text with highlighted matches."""
    t = Text()
    t.append(f"    {line_no:>5}", style=_GREP_LINENO_STYLE)
    t.append(": ", style="dim")

    if pat is None or not _GREP_HIGHLIGHT:
        t.append(text, style=_GREP_BODY_STYLE)
        return t

    last = 0
    for m in pat.finditer(text):
        start, end = m.start(), m.end()
        if start > last:
            t.append(text[last:start], style=_GREP_BODY_STYLE)
        if start < end:
            t.append(text[start:end], style=_GREP_HIGHLIGHT_STYLE)
        last = end
    if last < len(text):
        t.append(text[last:], style=_GREP_BODY_STYLE)

    # If finditer yielded nothing, the whole body is already appended above
    # via the trailing slice. If body was empty, Text is fine as-is.
    return t


def _grep_format_line_plain(line_no: int, text: str, pat: re.Pattern[str] | None, color: bool) -> str:
    """Format a single grep match line for plain output with optional highlighting."""
    prefix = f"    {line_no:>5}: "

    if pat is None or not _GREP_HIGHLIGHT:
        return prefix + text

    if color:
        # Bold yellow ANSI
        hl_on = "\x1b[1;33m"
        hl_off = "\x1b[0m"
    else:
        hl_on = ">>>"
        hl_off = "<<<"

    parts = [prefix]
    last = 0
    for m in pat.finditer(text):
        start, end = m.start(), m.end()
        if start > last:
            parts.append(text[last:start])
        if start < end:
            parts.append(hl_on + text[start:end] + hl_off)
        last = end
    if last < len(text):
        parts.append(text[last:])

    return "".join(parts)


def _parse_grep_output(output: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse grep tool output. Returns (mode, entries).

    mode is "lines" or "files".
    entries: for "files" -> [{"path": str}], for "lines" -> [{"path": str, "line": int, "text": str}].
    """
    raw_lines = [l for l in output.strip().split("\n") if l.strip()]
    if not raw_lines:
        return "files", []

    # Detect mode: if >=70% of lines match path:linenum:content, use "lines"
    line_matches = 0
    for l in raw_lines:
        if _GREP_LINE_RE.match(l):
            line_matches += 1

    if line_matches >= len(raw_lines) * 0.7:
        entries: list[dict[str, Any]] = []
        for l in raw_lines:
            m = _GREP_LINE_RE.match(l)
            if m:
                entries.append({"path": m.group("path"), "line": int(m.group("line")), "text": m.group("text")})
            else:
                # Non-matching line in lines mode; treat as file-only
                entries.append({"path": l.strip(), "line": 0, "text": ""})
        return "lines", entries
    else:
        return "files", [{"path": l.strip()} for l in raw_lines]


def render_grep_rich(console: Console, state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    status = str(state.get("status", ""))

    if not isinstance(inp, dict):
        return False

    # Handle output that might be a dict with a results/matches field
    if isinstance(output, dict):
        output_str = str(output.get("matches", output.get("results", "")))
    elif isinstance(output, str):
        output_str = output
    else:
        return False

    pattern = str(inp.get("pattern", ""))
    search_path = str(inp.get("path", ""))
    include = str(inp.get("include", ""))

    is_error = _is_likely_error(output_str)

    if status == "completed":
        border = "red" if is_error else "green"
    else:
        border = "yellow"

    sections: list[Any] = []

    # Header
    header_parts = [f"pattern={pattern!r}"]
    if search_path:
        header_parts.append(f"path={_relativize_path(search_path)}")
    if include:
        header_parts.append(f"include={include}")
    sections.append(Text("  ".join(header_parts), style="dim"))
    sections.append(Text())

    if is_error:
        sections.append(Text(output_str.strip(), style="red"))
    elif not output_str.strip():
        sections.append(Text("(no matches)", style="dim"))
        border = "dim"
    else:
        mode, entries = _parse_grep_output(output_str)

        if mode == "files":
            n_files = len(entries)
            shown = entries[:_GREP_FILE_CAP]
            for e in shown:
                sections.append(Text(f"  {_relativize_path(e['path'])}"))
            if n_files > _GREP_FILE_CAP:
                sections.append(Text(f"  ... and {n_files - _GREP_FILE_CAP} more", style="dim"))
            sections.append(Text())
            sections.append(Text(f"{n_files} file(s) matched", style="dim"))
        else:
            # Group by file, preserving order
            from collections import OrderedDict as _OD
            grep_pat = _grep_compile_pattern(pattern)
            grouped: OrderedDict[str, list[dict[str, Any]]] = _OD()
            for e in entries:
                grouped.setdefault(e["path"], []).append(e)

            n_files = len(grouped)
            n_total = len(entries)
            total_lines_emitted = 0
            files_shown = 0
            truncated_globally = False

            for fpath, file_entries in grouped.items():
                if total_lines_emitted >= _GREP_TOTAL_LINE_CAP:
                    truncated_globally = True
                    break
                if files_shown >= _GREP_FILE_CAP:
                    truncated_globally = True
                    break
                files_shown += 1
                rel = _relativize_path(fpath)
                sections.append(Text(f"  {rel}  ({len(file_entries)} match(es))", style="bold cyan"))
                shown_lines = file_entries[:_GREP_LINE_CAP_PER_FILE]
                for e in shown_lines:
                    text = e["text"]
                    if len(text) > 200:
                        text = text[:200] + "…"
                    sections.append(_grep_format_line_rich(e["line"], text, grep_pat))
                    total_lines_emitted += 1
                    if total_lines_emitted >= _GREP_TOTAL_LINE_CAP:
                        truncated_globally = True
                        break
                if len(file_entries) > _GREP_LINE_CAP_PER_FILE:
                    remaining = len(file_entries) - _GREP_LINE_CAP_PER_FILE
                    sections.append(Text(f"    ... and {remaining} more in {rel}", style="dim"))

            if truncated_globally:
                remaining_files = n_files - files_shown
                if remaining_files > 0:
                    sections.append(Text(f"  ... and {remaining_files} more file(s)", style="dim"))
                else:
                    sections.append(Text("  ... (further matches truncated)", style="dim"))

            sections.append(Text())
            sections.append(Text(f"{n_total} match(es) across {n_files} file(s)", style="dim"))

    console.print(Panel(Group(*sections), title="Grep", border_style=border, expand=True))
    return True


def render_grep_plain(state: dict[str, Any]) -> bool:
    inp = state.get("input")
    output = state.get("output")
    status = str(state.get("status", ""))

    if not isinstance(inp, dict):
        return False

    if isinstance(output, dict):
        output_str = str(output.get("matches", output.get("results", "")))
    elif isinstance(output, str):
        output_str = output
    else:
        return False

    pattern = str(inp.get("pattern", ""))
    search_path = str(inp.get("path", ""))
    include = str(inp.get("include", ""))

    is_error = _is_likely_error(output_str)

    header_parts = [f"grep {pattern!r}"]
    if search_path:
        header_parts.append(f"in {_relativize_path(search_path)}")
    if include:
        header_parts.append(f"include={include}")
    print(C.header(" ".join(header_parts)))

    if is_error:
        print(f"  {C.fail(output_str.strip())}")
    elif not output_str.strip():
        print("  (no matches)")
    else:
        mode, entries = _parse_grep_output(output_str)

        if mode == "files":
            n_files = len(entries)
            shown = entries[:_GREP_FILE_CAP]
            for e in shown:
                print(f"  {_relativize_path(e['path'])}")
            if n_files > _GREP_FILE_CAP:
                print(f"  ... and {n_files - _GREP_FILE_CAP} more")
            print(f"  {n_files} file(s) matched")
        else:
            from collections import OrderedDict as _OD
            grep_pat = _grep_compile_pattern(pattern)
            _plain_color = C.color_enabled()
            grouped: OrderedDict[str, list[dict[str, Any]]] = _OD()
            for e in entries:
                grouped.setdefault(e["path"], []).append(e)

            n_files = len(grouped)
            n_total = len(entries)
            total_lines_emitted = 0
            files_shown = 0
            truncated_globally = False

            for fpath, file_entries in grouped.items():
                if total_lines_emitted >= _GREP_TOTAL_LINE_CAP:
                    truncated_globally = True
                    break
                if files_shown >= _GREP_FILE_CAP:
                    truncated_globally = True
                    break
                files_shown += 1
                rel = _relativize_path(fpath)
                print(f"  {rel}  ({len(file_entries)} match(es))")
                shown_lines = file_entries[:_GREP_LINE_CAP_PER_FILE]
                for e in shown_lines:
                    text = e["text"]
                    if len(text) > 200:
                        text = text[:200] + "…"
                    print(_grep_format_line_plain(e["line"], text, grep_pat, _plain_color))
                    total_lines_emitted += 1
                    if total_lines_emitted >= _GREP_TOTAL_LINE_CAP:
                        truncated_globally = True
                        break
                if len(file_entries) > _GREP_LINE_CAP_PER_FILE:
                    remaining = len(file_entries) - _GREP_LINE_CAP_PER_FILE
                    print(f"    ... and {remaining} more in {rel}")

            if truncated_globally:
                remaining_files = n_files - files_shown
                if remaining_files > 0:
                    print(f"  ... and {remaining_files} more file(s)")
                else:
                    print("  ... (further matches truncated)")

            print(f"  {n_total} match(es) across {n_files} file(s)")

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


# --- Sandbox-bootstrap renderer ---------------------------------------------
#
# Detects bash invocations of `tools/sandbox-bootstrap.py --format json` and
# renders the JSON output as a structured, color-coded `Sandbox` panel
# instead of the generic Bash panel. The script is CodeCome-owned, so its
# JSON schema is stable and we can rely on per-subcommand shapes.

_SANDBOX_BOOTSTRAP_SCRIPT = "tools/sandbox-bootstrap.py"
_SANDBOX_KNOWN_SUBCOMMANDS = {
    "list", "inspect", "detect", "status", "apply", "regenerate", "validate",
}
# make targets that wrap the script and where we can confidently infer the
# subcommand from the target name.
_SANDBOX_MAKE_TARGETS = {
    "sandbox-list": "list",
    "sandbox-inspect": "inspect",
    "sandbox-detect": "detect",
    "sandbox-status": "status",
    "sandbox-bootstrap": "apply",       # `make sandbox-bootstrap ID=...` -> apply
    "sandbox-regenerate": "regenerate",
    "sandbox-validate": "validate",
}
_SANDBOX_REQUIRED_CAPABILITIES = ("setup", "start", "check", "build", "test", "stop")
_SANDBOX_HELPER_CAPABILITIES = ("shell", "logs", "clean", "reset")


def _console_supports_emoji(console: Optional[Any]) -> bool:
    """Return True when the console encoding can carry common emojis."""
    if console is None:
        # Plain mode: trust the stdout encoding, which is typically utf-8.
        enc = (sys.stdout.encoding or "").lower()
    else:
        enc = (getattr(console, "encoding", "") or "").lower()
    return "utf" in enc


def _sandbox_glyphs(console: Optional[Any]) -> dict[str, str]:
    """Return a name->glyph table, with emoji on utf-8 terminals and
    ASCII fallbacks elsewhere."""
    if _console_supports_emoji(console):
        return {
            "ok": "✅",
            "fail": "❌",
            "warn": "⚠️ ",
            "skip": "⏭️ ",
            "info": "ℹ️ ",
            "box": "📦",
            "check": "🧪",
            "alarm": "🚦",
            "clock": "⏱",
            "bullet": "•",
        }
    return {
        "ok": "[OK]",
        "fail": "[FAIL]",
        "warn": "[!]",
        "skip": "[--]",
        "info": "[i]",
        "box": "[box]",
        "check": "[chk]",
        "alarm": "[gate]",
        "clock": "t=",
        "bullet": "-",
    }


def _is_sandbox_bootstrap_json_call(command_str: str) -> Optional[str]:
    """Return the subcommand name if this bash invocation is a
    sandbox-bootstrap call configured for --format json, else None.

    Recognises both:
      - direct script invocations:
          .venv/bin/python3 tools/sandbox-bootstrap.py --format json status
          python tools/sandbox-bootstrap.py status --format=json
      - make-target wrappers when BOOTSTRAP_ARGS forces json:
          make sandbox-status BOOTSTRAP_ARGS='--format json'
          make sandbox-validate BOOTSTRAP_ARGS=--format=json
    """
    if not command_str:
        return None
    try:
        tokens = shlex.split(command_str)
    except ValueError:
        return None
    if not tokens:
        return None

    # Look for --format json or --format=json anywhere in the tokens.
    # Also recognise it when nested inside a make-style assignment such as
    # BOOTSTRAP_ARGS='--format json' (which shlex collapses into a single
    # token "BOOTSTRAP_ARGS=--format json").
    has_json_format = False
    for i, tok in enumerate(tokens):
        if tok == "--format=json":
            has_json_format = True
            break
        if tok == "--format" and i + 1 < len(tokens) and tokens[i + 1] == "json":
            has_json_format = True
            break
        # Make-style env assignments (e.g. BOOTSTRAP_ARGS=--format json,
        # BOOTSTRAP_ARGS=--format=json, OPENCODE_ARGS=...).
        if "=" in tok and ("--format json" in tok or "--format=json" in tok):
            has_json_format = True
            break

    # Direct script invocation path.
    script_idx = -1
    for i, tok in enumerate(tokens):
        if tok.endswith(_SANDBOX_BOOTSTRAP_SCRIPT) or tok.endswith("/" + _SANDBOX_BOOTSTRAP_SCRIPT):
            script_idx = i
            break
    if script_idx >= 0 and has_json_format:
        # Subcommand: first non-flag positional after the script path.
        for j in range(script_idx + 1, len(tokens)):
            t = tokens[j]
            if t.startswith("-"):
                # Skip --format json (two-token form).
                if t == "--format" and j + 1 < len(tokens):
                    continue
                continue
            # A bare token after --format json may be the value of --format.
            # Skip if previous token was --format (without =).
            if j > 0 and tokens[j - 1] == "--format":
                continue
            if t in _SANDBOX_KNOWN_SUBCOMMANDS:
                return t
        return None

    # Make-target wrapper path.
    # Accept env-prefixed forms too, e.g.:
    #   BOOTSTRAP_ARGS='--format json --keep-going' make sandbox-validate
    make_idx = -1
    for i, tok in enumerate(tokens):
        if tok == "make":
            make_idx = i
            break
    if make_idx >= 0:
        # Find the first sandbox-* target token after `make`.
        for tok in tokens[make_idx + 1:]:
            if tok in _SANDBOX_MAKE_TARGETS and has_json_format:
                return _SANDBOX_MAKE_TARGETS[tok]
    return None


def _maybe_render_sandbox_bootstrap(console: Optional[Any], state: dict[str, Any]) -> bool:
    """Try to render a bash invocation of sandbox-bootstrap.py --format json
    as a styled Sandbox panel. Return True if handled, False to fall back to
    the generic bash renderer."""
    if not _SANDBOX_RENDER:
        return False
    inp = state.get("input")
    output = state.get("output")
    if not isinstance(inp, dict):
        return False

    command = str(inp.get("command", ""))
    subcommand = _is_sandbox_bootstrap_json_call(command)
    if subcommand is None:
        return False

    output_str = str(output) if output is not None else ""
    stripped = output_str.strip()
    if not stripped:
        # In-flight or silent success; let the bash renderer handle it.
        return False

    # Only proceed when output parses as a single JSON document.
    # make commands often echo the invocation line, so try to find
    # the first JSON-like delimiter if a strict parse fails.
    try:
        payload = json.loads(stripped)
    except (ValueError, TypeError):
        first_brace = stripped.find("{")
        first_bracket = stripped.find("[")
        idxs = [i for i in (first_brace, first_bracket) if i >= 0]
        if not idxs:
            return False
        start_idx = min(idxs)
        try:
            payload = json.loads(stripped[start_idx:])
        except (ValueError, TypeError):
            return False

    # Per-subcommand schema sniff: if the payload doesn't carry the
    # expected top-level structure, fall through to the bash renderer.
    if not _sandbox_payload_matches(subcommand, payload):
        return False

    description = str(inp.get("description", "")).strip()
    status = str(state.get("status", ""))

    if HAVE_RICH and console is not None:
        return _render_sandbox_rich(
            console, subcommand, payload, command, description, status
        )
    return _render_sandbox_plain(
        subcommand, payload, command, description, status
    )


def _sandbox_payload_matches(subcommand: str, payload: Any) -> bool:
    """Cheap structural sniff so we don't render unrelated JSON as a
    Sandbox panel. Returns False on obvious schema mismatch so the bash
    renderer can take over."""
    if subcommand == "list":
        return isinstance(payload, list) and (not payload or isinstance(payload[0], dict))
    if not isinstance(payload, dict):
        return False
    if subcommand == "inspect":
        return any(k in payload for k in ("id", "display_name", "files"))
    if subcommand == "detect":
        return "candidates" in payload or "signals" in payload
    if subcommand == "status":
        return "sandbox_state" in payload or "phase2_gate_pass" in payload or "capabilities" in payload
    if subcommand in ("apply", "regenerate"):
        return any(k in payload for k in ("example", "files_to_write", "written_files", "status"))
    if subcommand == "validate":
        return "overall_outcome" in payload or "tiers" in payload
    return False


def _sandbox_outcome_style(outcome: str) -> tuple[str, str]:
    """Return (rich_style, glyph_key) for a tier outcome string."""
    if outcome == "passed":
        return "green", "ok"
    if outcome == "failed":
        return "red", "fail"
    if outcome == "skipped":
        return "dim", "skip"
    return "yellow", "warn"


def _sandbox_state_style(state_value: str) -> str:
    if state_value == "generated":
        return "green"
    if state_value == "user-managed":
        return "yellow"
    if state_value == "missing":
        return "red"
    return "dim"


def _sandbox_last_validation_style(value: Optional[str]) -> str:
    if value == "passed":
        return "green"
    if value == "mixed":
        return "yellow"
    if value == "failed":
        return "red"
    if value == "skipped":
        return "yellow"
    return "dim"


def _render_sandbox_rich(
    console: Any,
    subcommand: str,
    payload: Any,
    command: str,
    description: str,
    status: str,
) -> bool:
    glyphs = _sandbox_glyphs(console)

    # Default border = yellow (in flight) / green (completed); per-subcommand
    # renderers may override based on payload contents (e.g. validate failed).
    border = "yellow" if status != "completed" else "green"

    title = f"{glyphs['box']} Sandbox · {subcommand}"
    sections: list[Any] = []
    sections.append(Text(f"$ {command}", style="bold cyan"))
    if description:
        sections.append(Text(description, style="dim italic"))
    sections.append(Text())

    try:
        if subcommand == "list":
            border = _render_sandbox_list_rich(sections, payload, border)
        elif subcommand == "inspect":
            border = _render_sandbox_inspect_rich(sections, payload, border, glyphs)
        elif subcommand == "detect":
            border = _render_sandbox_detect_rich(sections, payload, border, glyphs)
        elif subcommand == "status":
            border = _render_sandbox_status_rich(sections, payload, border, glyphs)
        elif subcommand in ("apply", "regenerate"):
            border = _render_sandbox_apply_rich(sections, payload, subcommand, border, glyphs)
        elif subcommand == "validate":
            border = _render_sandbox_validate_rich(sections, payload, border, glyphs)
        else:
            return False
    except (KeyError, TypeError, AttributeError):
        # Defensive: schema mismatch -> fall through to bash renderer.
        return False

    console.print(Panel(Group(*sections), title=title, border_style=border, expand=True))
    return True


def _render_sandbox_list_rich(sections: list[Any], payload: Any, border: str) -> str:
    from rich.table import Table
    if not isinstance(payload, list):
        raise TypeError("list subcommand expects a JSON array")
    table = Table(show_header=True, header_style="bold cyan", expand=True, pad_edge=False)
    table.add_column("id", style="bold cyan", no_wrap=True)
    table.add_column("name")
    table.add_column("languages", style="dim")
    table.add_column("manifests", style="dim")
    for ex in payload:
        applies = ex.get("applies_when") or {}
        langs = ", ".join(applies.get("languages") or []) or "-"
        mans = ", ".join((applies.get("manifests") or [])[:4]) or "-"
        if applies.get("manifests") and len(applies["manifests"]) > 4:
            mans += " …"
        table.add_row(str(ex.get("id", "")), str(ex.get("display_name", "")), langs, mans)
    sections.append(table)
    sections.append(Text())
    sections.append(Text(f"{len(payload)} example(s) available", style="dim"))
    return border


def _render_sandbox_inspect_rich(
    sections: list[Any], payload: dict, border: str, glyphs: dict
) -> str:
    sections.append(Text(f"{payload.get('display_name', '')}", style="bold cyan"))
    sections.append(Text(f"  id:    {payload.get('id', '')}", style="dim"))
    sections.append(Text(f"  path:  {payload.get('path', '')}", style="dim"))
    applies = payload.get("applies_when") or {}
    if applies:
        for k, v in applies.items():
            joined = ", ".join(v) if isinstance(v, list) else str(v)
            sections.append(Text(f"  applies_when.{k}: {joined}", style="dim"))
    if payload.get("required_tools"):
        sections.append(Text(f"  required_tools: {', '.join(payload['required_tools'])}", style="dim"))
    if payload.get("template_vars"):
        sections.append(Text(f"  template_vars:  {', '.join(payload['template_vars'])}", style="dim"))
    if payload.get("default_ports"):
        sections.append(Text(f"  default_ports:  {', '.join(str(p) for p in payload['default_ports'])}", style="dim"))
    if payload.get("build_command"):
        sections.append(Text(f"  build_command:  {payload['build_command']}", style="dim"))
    if payload.get("test_command"):
        sections.append(Text(f"  test_command:   {payload['test_command']}", style="dim"))
    if payload.get("caveats"):
        sections.append(Text())
        sections.append(Text("Caveats:", style="bold yellow"))
        for c in payload["caveats"]:
            sections.append(Text(f"  {glyphs['warn']} {c}", style="yellow"))
    files = payload.get("files") or []
    if files:
        sections.append(Text())
        cap = _SANDBOX_FILES_CAP
        sections.append(Text(f"Files ({len(files)}):", style="bold cyan"))
        for f in files[:cap]:
            sections.append(Text(f"  {glyphs['bullet']} {f}"))
        if len(files) > cap:
            sections.append(Text(f"  ... and {len(files) - cap} more", style="dim"))
    return border


def _render_sandbox_detect_rich(
    sections: list[Any], payload: dict, border: str, glyphs: dict
) -> str:
    from rich.table import Table
    signals = payload.get("signals") or {}
    sections.append(Text("Detection signals", style="bold cyan"))
    sections.append(Text(f"  source:    {signals.get('source', '-')}", style="dim"))
    sections.append(Text(f"  languages: {', '.join(signals.get('languages') or []) or '-'}", style="dim"))
    sections.append(Text(f"  manifests: {', '.join(signals.get('manifests') or []) or '-'}", style="dim"))
    sections.append(Text())

    candidates = payload.get("candidates") or []
    sections.append(Text(f"Ranked candidates ({len(candidates)}):", style="bold cyan"))
    table = Table(show_header=True, header_style="bold cyan", expand=True, pad_edge=False)
    table.add_column("score", justify="right", no_wrap=True)
    table.add_column("id", style="bold cyan", no_wrap=True)
    table.add_column("name")
    table.add_column("path", style="dim")
    cap = _SANDBOX_FILES_CAP
    for c in candidates[:cap]:
        score = c.get("score", 0)
        score_style = "green" if score >= 5 else ("yellow" if score >= 1 else "dim")
        table.add_row(
            Text(str(score), style=score_style),
            str(c.get("id", "")),
            str(c.get("display_name", "")),
            str(c.get("path", "")),
        )
    sections.append(table)
    if len(candidates) > cap:
        sections.append(Text(f"... and {len(candidates) - cap} more", style="dim"))
    return border


def _render_sandbox_status_rich(
    sections: list[Any], payload: dict, border: str, glyphs: dict
) -> str:
    from rich.table import Table
    state_value = str(payload.get("sandbox_state", "unknown"))
    last_validation = payload.get("last_validation")
    gate_pass = bool(payload.get("phase2_gate_pass"))
    gate_reason = str(payload.get("phase2_gate_reason", ""))

    state_glyph = {"generated": glyphs["ok"], "user-managed": glyphs["warn"], "missing": glyphs["fail"]}.get(state_value, glyphs["info"])
    sections.append(Text.assemble(
        ("state: ", "bold"),
        (f"{state_glyph} {state_value}", _sandbox_state_style(state_value)),
    ))
    sections.append(Text(f"  path:           {payload.get('sandbox_path', '-')}", style="dim"))
    sections.append(Text(f"  provenance:     {'yes' if payload.get('provenance_present') else 'no'}", style="dim"))
    lv_text = last_validation if last_validation is not None else "-"
    sections.append(Text.assemble(
        ("  last validation: ", "dim"),
        (str(lv_text), _sandbox_last_validation_style(last_validation)),
    ))
    sections.append(Text(f"  allow override: {'yes' if payload.get('allow_no_sandbox') else 'no'}", style="dim"))
    sections.append(Text())

    # Gate badge.
    if gate_pass:
        sections.append(Text.assemble(
            (f"{glyphs['alarm']} ", ""),
            (f"Phase 2 gate would PASS", "bold green"),
            (f" — {gate_reason}", "dim"),
        ))
    else:
        sections.append(Text.assemble(
            (f"{glyphs['alarm']} ", ""),
            (f"Phase 2 gate would BLOCK", "bold red"),
            (f" — {gate_reason}", "dim"),
        ))
        # Status doesn't fail the script; signal informational alarm via yellow.
        border = "yellow"

    sections.append(Text())
    capabilities = payload.get("capabilities") or {}
    if capabilities:
        table = Table(show_header=True, header_style="bold cyan", expand=True, pad_edge=False)
        table.add_column("capability", no_wrap=True)
        table.add_column("status", no_wrap=True)
        table.add_column("path", style="dim")
        # Required first, helpers after.
        for name in (*_SANDBOX_REQUIRED_CAPABILITIES, *_SANDBOX_HELPER_CAPABILITIES):
            cap = capabilities.get(name)
            if cap is None:
                continue
            satisfied = bool(cap.get("satisfied"))
            present = bool(cap.get("present"))
            is_helper = name in _SANDBOX_HELPER_CAPABILITIES
            if satisfied:
                badge = Text(f"{glyphs['ok']} ok", style="green")
            elif is_helper and not present:
                badge = Text(f"{glyphs['skip']} optional", style="dim")
            else:
                badge = Text(f"{glyphs['fail']} missing", style="red")
            table.add_row(name, badge, str(cap.get("path", "")))
        sections.append(table)
    return border


def _render_sandbox_apply_rich(
    sections: list[Any], payload: dict, subcommand: str, border: str, glyphs: dict
) -> str:
    apply_status = str(payload.get("status", ""))
    is_dry = bool(payload.get("dry_run")) or apply_status == "dry-run"
    chip_text = "DRY RUN" if is_dry else apply_status.upper() or "(unknown)"
    chip_style = "yellow" if is_dry else ("green" if apply_status == "applied" else "dim")
    sections.append(Text.assemble(
        (f"{glyphs['box']} ", ""),
        (f"{subcommand} ", "bold cyan"),
        (f"{payload.get('example', '-')}  ", "bold cyan"),
        (f"[{chip_text}]", chip_style),
    ))
    sections.append(Text(f"  example_path: {payload.get('example_path', '-')}", style="dim"))
    sections.append(Text(f"  sandbox_path: {payload.get('sandbox_path', '-')}", style="dim"))
    sections.append(Text(f"  force:        {payload.get('force', False)}", style="dim"))
    if payload.get("backup_dir"):
        sections.append(Text(f"  backup_dir:   {payload['backup_dir']}", style="dim"))

    files_to_write = payload.get("files_to_write") or []
    written = payload.get("written_files") or []
    sections.append(Text())
    sections.append(Text(
        f"files: planned={len(files_to_write)}  written={len(written)}",
        style="bold cyan",
    ))
    markers = payload.get("markers_provided") or {}
    if markers:
        sections.append(Text(f"markers_provided ({len(markers)}):", style="bold cyan"))
        for k, v in markers.items():
            sections.append(Text(f"  {k} = {v}", style="dim"))
    unfilled = payload.get("markers_used_unfilled") or []
    if unfilled:
        sections.append(Text())
        sections.append(Text.assemble(
            (f"{glyphs['warn']} ", ""),
            (f"Declared markers used but not provided: {', '.join(unfilled)}", "yellow"),
        ))
        border = "yellow"
    undeclared = payload.get("markers_used_undeclared") or []
    if undeclared:
        sections.append(Text.assemble(
            (f"{glyphs['warn']} ", ""),
            (f"Markers used but not declared: {', '.join(undeclared)}", "yellow"),
        ))
        border = "yellow"

    show_files = files_to_write or written
    if show_files:
        sections.append(Text())
        cap = _SANDBOX_FILES_CAP
        for f in show_files[:cap]:
            sections.append(Text(f"  {glyphs['bullet']} {f}"))
        if len(show_files) > cap:
            sections.append(Text(f"  ... and {len(show_files) - cap} more", style="dim"))

    if apply_status == "applied" and not is_dry:
        sections.append(Text())
        sections.append(Text.assemble(
            (f"{glyphs['ok']} ", ""),
            (f"Applied '{payload.get('example', '-')}'", "bold green"),
            (f" → {payload.get('sandbox_path', '-')}", "dim"),
        ))
        if payload.get("provenance_path"):
            sections.append(Text(f"  provenance: {payload['provenance_path']}", style="dim"))
    return border


def _render_sandbox_validate_rich(
    sections: list[Any], payload: dict, border: str, glyphs: dict
) -> str:
    from rich.table import Table
    overall = str(payload.get("overall_outcome", "unknown"))
    overall_style, overall_glyph_key = _sandbox_outcome_style(overall)

    sections.append(Text.assemble(
        (f"{glyphs['check']} ", ""),
        ("overall: ", "bold"),
        (f"{glyphs[overall_glyph_key]} {overall}", overall_style),
    ))

    if overall == "failed":
        border = "red"
    elif overall == "passed":
        border = "green"
    else:
        border = "yellow"

    tiers = payload.get("tiers") or []
    if tiers:
        sections.append(Text())
        table = Table(show_header=True, header_style="bold cyan", expand=True, pad_edge=False)
        table.add_column("tier", no_wrap=True)
        table.add_column("purpose")
        table.add_column("outcome", no_wrap=True)
        table.add_column("dur", justify="right", no_wrap=True)
        table.add_column("exit", justify="right", no_wrap=True)
        for t in tiers:
            t_outcome = str(t.get("outcome", "unknown"))
            o_style, o_key = _sandbox_outcome_style(t_outcome)
            badge = Text(f"{glyphs[o_key]} {t_outcome}", style=o_style)
            dur = t.get("duration_seconds")
            dur_str = f"{dur:.2f}s" if isinstance(dur, (int, float)) else "-"
            exit_code = t.get("exit_code")
            exit_str = "-" if exit_code is None else str(exit_code)
            table.add_row(
                str(t.get("tier", "")),
                str(t.get("purpose", "")),
                badge,
                dur_str,
                exit_str,
            )
        sections.append(table)

        # For each failed tier, show a capped stderr_tail under it.
        for t in tiers:
            if t.get("outcome") != "failed":
                continue
            stderr_tail = str(t.get("stderr_tail") or "").strip()
            if not stderr_tail:
                continue
            sections.append(Text())
            sections.append(Text(
                f"{glyphs['fail']} {t.get('tier', '')} {t.get('purpose', '')} stderr (tail):",
                style="bold red",
            ))
            tail_lines = stderr_tail.splitlines()
            cap = _SANDBOX_VALIDATE_STDERR_LINES
            shown = tail_lines[-cap:]
            for line in shown:
                sections.append(Text(f"  {line}", style="red"))
            if len(tail_lines) > cap:
                sections.append(Text(
                    f"  ... ({len(tail_lines) - cap} earlier lines truncated; "
                    f"see tmp/last-phase-*.jsonl for full output)",
                    style="dim",
                ))

    missing = payload.get("missing_helpers") or []
    if missing:
        sections.append(Text())
        sections.append(Text.assemble(
            (f"{glyphs['warn']} ", ""),
            (f"Helper capabilities still missing: {', '.join(missing)}", "yellow"),
        ))

    if payload.get("history_updated"):
        sections.append(Text(f"{glyphs['info']} history updated in sandbox/CODECOME-GENERATED.md", style="dim"))
    return border


def _render_sandbox_plain(
    subcommand: str,
    payload: Any,
    command: str,
    description: str,
    status: str,
) -> bool:
    glyphs = _sandbox_glyphs(None)
    print(C.header(f"{glyphs['box']} Sandbox · {subcommand}"))
    print(f"  $ {command}")
    if description:
        print(f"  # {description}")

    try:
        if subcommand == "list":
            _render_sandbox_list_plain(payload, glyphs)
        elif subcommand == "inspect":
            _render_sandbox_inspect_plain(payload, glyphs)
        elif subcommand == "detect":
            _render_sandbox_detect_plain(payload, glyphs)
        elif subcommand == "status":
            _render_sandbox_status_plain(payload, glyphs)
        elif subcommand in ("apply", "regenerate"):
            _render_sandbox_apply_plain(payload, subcommand, glyphs)
        elif subcommand == "validate":
            _render_sandbox_validate_plain(payload, glyphs)
        else:
            return False
    except (KeyError, TypeError, AttributeError):
        return False
    return True


def _render_sandbox_list_plain(payload: Any, glyphs: dict) -> None:
    if not isinstance(payload, list):
        raise TypeError
    for ex in payload:
        applies = ex.get("applies_when") or {}
        langs = ", ".join(applies.get("languages") or []) or "-"
        print(f"  {glyphs['bullet']} {ex.get('id', ''):<20} {ex.get('display_name', '')}  ({langs})")
    print(f"  {len(payload)} example(s) available")


def _render_sandbox_inspect_plain(payload: dict, glyphs: dict) -> None:
    print(f"  id:    {payload.get('id', '')}")
    print(f"  name:  {payload.get('display_name', '')}")
    print(f"  path:  {payload.get('path', '')}")
    applies = payload.get("applies_when") or {}
    for k, v in applies.items():
        joined = ", ".join(v) if isinstance(v, list) else str(v)
        print(f"  applies_when.{k}: {joined}")
    if payload.get("required_tools"):
        print(f"  required_tools: {', '.join(payload['required_tools'])}")
    if payload.get("template_vars"):
        print(f"  template_vars:  {', '.join(payload['template_vars'])}")
    if payload.get("default_ports"):
        print(f"  default_ports:  {', '.join(str(p) for p in payload['default_ports'])}")
    if payload.get("build_command"):
        print(f"  build_command:  {payload['build_command']}")
    if payload.get("test_command"):
        print(f"  test_command:   {payload['test_command']}")
    if payload.get("caveats"):
        print("  Caveats:")
        for c in payload["caveats"]:
            print(f"    {glyphs['warn']} {c}")
    files = payload.get("files") or []
    if files:
        cap = _SANDBOX_FILES_CAP
        print(f"  Files ({len(files)}):")
        for f in files[:cap]:
            print(f"    {glyphs['bullet']} {f}")
        if len(files) > cap:
            print(f"    ... and {len(files) - cap} more")


def _render_sandbox_detect_plain(payload: dict, glyphs: dict) -> None:
    signals = payload.get("signals") or {}
    print("  signals:")
    print(f"    source:    {signals.get('source', '-')}")
    print(f"    languages: {', '.join(signals.get('languages') or []) or '-'}")
    print(f"    manifests: {', '.join(signals.get('manifests') or []) or '-'}")
    candidates = payload.get("candidates") or []
    print(f"  candidates ({len(candidates)}):")
    cap = _SANDBOX_FILES_CAP
    for c in candidates[:cap]:
        print(f"    score={c.get('score', 0):>2}  {c.get('id', ''):<20} {c.get('display_name', '')}")
    if len(candidates) > cap:
        print(f"    ... and {len(candidates) - cap} more")


def _render_sandbox_status_plain(payload: dict, glyphs: dict) -> None:
    state_value = str(payload.get("sandbox_state", "unknown"))
    last_validation = payload.get("last_validation")
    gate_pass = bool(payload.get("phase2_gate_pass"))
    gate_reason = str(payload.get("phase2_gate_reason", ""))

    print(f"  state:           {state_value}")
    print(f"  path:            {payload.get('sandbox_path', '-')}")
    print(f"  provenance:      {'yes' if payload.get('provenance_present') else 'no'}")
    print(f"  last validation: {last_validation if last_validation is not None else '-'}")
    print(f"  allow override:  {'yes' if payload.get('allow_no_sandbox') else 'no'}")
    if gate_pass:
        print(C.ok(f"  {glyphs['alarm']} Phase 2 gate would PASS — {gate_reason}"))
    else:
        print(C.warn(f"  {glyphs['alarm']} Phase 2 gate would BLOCK — {gate_reason}"))

    capabilities = payload.get("capabilities") or {}
    if capabilities:
        print("  capabilities:")
        for name in (*_SANDBOX_REQUIRED_CAPABILITIES, *_SANDBOX_HELPER_CAPABILITIES):
            cap = capabilities.get(name)
            if cap is None:
                continue
            satisfied = bool(cap.get("satisfied"))
            present = bool(cap.get("present"))
            is_helper = name in _SANDBOX_HELPER_CAPABILITIES
            if satisfied:
                marker = f"{glyphs['ok']} ok"
            elif is_helper and not present:
                marker = f"{glyphs['skip']} optional"
            else:
                marker = f"{glyphs['fail']} missing"
            print(f"    {name:<14} {marker:<14} {cap.get('path', '')}")


def _render_sandbox_apply_plain(payload: dict, subcommand: str, glyphs: dict) -> None:
    apply_status = str(payload.get("status", ""))
    is_dry = bool(payload.get("dry_run")) or apply_status == "dry-run"
    chip_text = "DRY RUN" if is_dry else apply_status.upper() or "(unknown)"
    print(f"  {glyphs['box']} {subcommand} {payload.get('example', '-')}  [{chip_text}]")
    print(f"    example_path: {payload.get('example_path', '-')}")
    print(f"    sandbox_path: {payload.get('sandbox_path', '-')}")
    print(f"    force:        {payload.get('force', False)}")
    if payload.get("backup_dir"):
        print(f"    backup_dir:   {payload['backup_dir']}")
    files_to_write = payload.get("files_to_write") or []
    written = payload.get("written_files") or []
    print(f"    files: planned={len(files_to_write)} written={len(written)}")
    markers = payload.get("markers_provided") or {}
    if markers:
        print(f"    markers_provided ({len(markers)}):")
        for k, v in markers.items():
            print(f"      {k} = {v}")
    unfilled = payload.get("markers_used_unfilled") or []
    if unfilled:
        print(C.warn(f"    {glyphs['warn']} Declared markers used but not provided: {', '.join(unfilled)}"))
    undeclared = payload.get("markers_used_undeclared") or []
    if undeclared:
        print(C.warn(f"    {glyphs['warn']} Markers used but not declared: {', '.join(undeclared)}"))
    show_files = files_to_write or written
    if show_files:
        cap = _SANDBOX_FILES_CAP
        for f in show_files[:cap]:
            print(f"    {glyphs['bullet']} {f}")
        if len(show_files) > cap:
            print(f"    ... and {len(show_files) - cap} more")
    if apply_status == "applied" and not is_dry:
        print(C.ok(f"    {glyphs['ok']} Applied '{payload.get('example', '-')}'"))
        if payload.get("provenance_path"):
            print(f"      provenance: {payload['provenance_path']}")


def _render_sandbox_validate_plain(payload: dict, glyphs: dict) -> None:
    overall = str(payload.get("overall_outcome", "unknown"))
    overall_glyph = glyphs["ok"] if overall == "passed" else glyphs["fail"] if overall == "failed" else glyphs["warn"]
    print(f"  {glyphs['check']} overall: {overall_glyph} {overall}")
    tiers = payload.get("tiers") or []
    for t in tiers:
        t_outcome = str(t.get("outcome", "unknown"))
        o_glyph = glyphs["ok"] if t_outcome == "passed" else glyphs["fail"] if t_outcome == "failed" else glyphs["skip"]
        dur = t.get("duration_seconds")
        dur_str = f"{dur:.2f}s" if isinstance(dur, (int, float)) else "-"
        exit_code = t.get("exit_code")
        exit_str = "-" if exit_code is None else str(exit_code)
        print(f"    {t.get('tier', ''):<3} {str(t.get('purpose', '')):<20} "
              f"{o_glyph} {t_outcome:<8} dur={dur_str:<7} exit={exit_str}")
        if t_outcome == "failed":
            stderr_tail = str(t.get("stderr_tail") or "").strip()
            if stderr_tail:
                tail_lines = stderr_tail.splitlines()
                cap = _SANDBOX_VALIDATE_STDERR_LINES
                shown = tail_lines[-cap:]
                for line in shown:
                    print(f"      | {line}")
                if len(tail_lines) > cap:
                    print(f"      | ... ({len(tail_lines) - cap} earlier lines truncated)")
    missing = payload.get("missing_helpers") or []
    if missing:
        print(C.warn(f"  {glyphs['warn']} Helper capabilities still missing: {', '.join(missing)}"))
    if payload.get("history_updated"):
        print(f"  {glyphs['info']} history updated in sandbox/CODECOME-GENERATED.md")


# --- Bash-shim detection ----------------------------------------------------
#
# Some models (e.g. google/gemini-3.1-pro-preview) prefer to invoke a CLI
# helper such as `rtk read FILE`, `rtk grep PAT PATH`, `rtk ls`, plain
# `ls`, `cat`, `head`, `tail`, `find`, `tree`, or `rg` via the bash tool
# instead of using OpenCode's native Read / Grep / Glob tools. The
# wrapper detects these by inspecting the bash command and routes the
# output through the existing styled renderers, so the user sees the
# same Read / Grep / Glob panels regardless of how the agent invoked
# the operation.

# Recognised verbs at the head of a bash command, after env assignments
# and shell wrappers like sudo / time / nice / ionice are stripped.
_BASH_SHIM_READ_VERBS = {"cat", "head", "tail"}
_BASH_SHIM_GREP_VERBS = {"rg", "grep"}
_BASH_SHIM_LS_VERBS = {"ls"}
_BASH_SHIM_FIND_VERBS = {"find", "tree"}
# Wrappers we ignore at the start of a command line.
_BASH_SHIM_LEADING_NOISE = {"sudo", "time", "nice", "ionice", "command", "env"}
# Shell metacharacters that disqualify the command from shim handling.
_BASH_SHIM_DISQUALIFIERS = ("|", ";", "&&", "||", ">", "<", "`", "$(")


def _strip_leading_env_and_wrappers(tokens: list[str]) -> list[str]:
    """Drop leading KEY=VAL env assignments and known shell wrappers
    (sudo, time, nice, ionice, command, env) so the next significant
    token is the actual command verb."""
    out = list(tokens)
    while out:
        head = out[0]
        # KEY=VAL env assignments are tokens with `=` and an UPPER_CASE
        # identifier on the left.
        if "=" in head and head.split("=", 1)[0].replace("_", "").isalnum():
            left = head.split("=", 1)[0]
            if left and (left[0].isalpha() or left[0] == "_") and left.isupper():
                out.pop(0)
                continue
        if head in _BASH_SHIM_LEADING_NOISE:
            # Skip wrapper plus its options (best-effort: drop only the
            # wrapper itself and any -flags directly after it).
            out.pop(0)
            while out and out[0].startswith("-"):
                out.pop(0)
            continue
        break
    return out


def _bash_command_has_pipeline(command_str: str) -> bool:
    """Heuristic: avoid shim handling for any pipeline / redirection /
    command-substitution / background invocation."""
    for marker in _BASH_SHIM_DISQUALIFIERS:
        if marker in command_str:
            return True
    return False


@dataclass
class _BashShim:
    family: str  # "read" | "grep" | "ls" | "find"
    files: list[str]              # for read family
    pattern: str                  # for grep family
    path: str                     # for grep / ls / find
    long_format: bool             # for ls family
    head_limit: int | None        # for `head -n N`
    tail_limit: int | None        # for `tail -n N`
    rtk_filtered: bool            # rtk read --level/--max-lines/--tail-lines present
    raw_command: str


def _is_bash_shim_call(command_str: str) -> Optional[_BashShim]:
    """Recognise bash invocations the wrapper can re-route to the
    Read/Grep/Glob renderers. Returns a _BashShim, or None when the
    command should be left to the generic Bash renderer."""
    if not command_str or _bash_command_has_pipeline(command_str):
        return None
    try:
        tokens = shlex.split(command_str)
    except ValueError:
        return None
    if not tokens:
        return None

    tokens = _strip_leading_env_and_wrappers(tokens)
    if not tokens:
        return None

    head = tokens[0]
    rest = tokens[1:]

    # rtk dispatcher: peel `rtk` and re-evaluate against the subcommand.
    via_rtk = False
    if head == "rtk":
        if not rest:
            return None
        head = rest[0]
        rest = rest[1:]
        via_rtk = True

    if head == "read" and via_rtk:
        return _parse_rtk_read(rest, command_str)
    if head in _BASH_SHIM_READ_VERBS:
        return _parse_cat_head_tail(head, rest, command_str)
    if head == "grep" and via_rtk:
        return _parse_rtk_grep(rest, command_str)
    if head in _BASH_SHIM_GREP_VERBS:
        return _parse_grep_or_rg(rest, command_str)
    if head in _BASH_SHIM_LS_VERBS:
        return _parse_ls(rest, command_str)
    if head in _BASH_SHIM_FIND_VERBS:
        return _parse_find_tree(head, rest, command_str)
    return None


def _parse_rtk_read(rest: list[str], raw: str) -> Optional[_BashShim]:
    """Parse `rtk read [flags] FILE [FILE...]`."""
    files: list[str] = []
    filtered = False
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok in ("-l", "--level"):
            filtered = True
            if i + 1 < len(rest):
                i += 2
            else:
                i += 1
            continue
        if tok.startswith("--level="):
            filtered = True
            i += 1
            continue
        if tok in ("-m", "--max-lines", "--tail-lines"):
            filtered = True
            if i + 1 < len(rest):
                i += 2
            else:
                i += 1
            continue
        if tok.startswith(("--max-lines=", "--tail-lines=")):
            filtered = True
            i += 1
            continue
        if tok in ("-n", "--line-numbers", "--ultra-compact", "--skip-env"):
            i += 1
            continue
        if tok.startswith("-v") and all(c == "v" for c in tok[1:]):
            i += 1
            continue
        if tok == "--":
            i += 1
            continue
        if tok.startswith("-"):
            # Unknown flag; skip just the flag itself.
            i += 1
            continue
        files.append(tok)
        i += 1
    if not files:
        return None
    return _BashShim(
        family="read",
        files=files,
        pattern="",
        path="",
        long_format=False,
        head_limit=None,
        tail_limit=None,
        rtk_filtered=filtered,
        raw_command=raw,
    )


def _parse_cat_head_tail(verb: str, rest: list[str], raw: str) -> Optional[_BashShim]:
    """Parse `cat FILE...`, `head [-n N] FILE`, `tail [-n N] FILE`."""
    files: list[str] = []
    head_limit: Optional[int] = None
    tail_limit: Optional[int] = None
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok == "-n" and i + 1 < len(rest):
            try:
                count = int(rest[i + 1].lstrip("+-"))
                if verb == "head":
                    head_limit = count
                elif verb == "tail":
                    tail_limit = count
            except ValueError:
                pass
            i += 2
            continue
        if tok.startswith("-n") and len(tok) > 2:
            try:
                count = int(tok[2:].lstrip("+-"))
                if verb == "head":
                    head_limit = count
                elif verb == "tail":
                    tail_limit = count
            except ValueError:
                pass
            i += 1
            continue
        if tok.startswith("-") and tok != "-":
            i += 1
            continue
        files.append(tok)
        i += 1
    if not files:
        return None
    return _BashShim(
        family="read",
        files=files,
        pattern="",
        path="",
        long_format=False,
        head_limit=head_limit,
        tail_limit=tail_limit,
        rtk_filtered=False,
        raw_command=raw,
    )


def _parse_grep_or_rg(rest: list[str], raw: str) -> Optional[_BashShim]:
    """Parse `rg PATTERN [PATH]` or `grep PATTERN PATH...` (best-effort)."""
    # Drop common option flags so we can pull the pattern out. We don't
    # need to be exhaustive: anything we miss simply falls through.
    pattern = ""
    path = ""
    i = 0
    saw_pattern = False
    while i < len(rest):
        tok = rest[i]
        if tok == "--":
            i += 1
            continue
        if tok.startswith("-") and tok != "-":
            # rg/grep flags that take a value.
            if tok in ("-e", "-f", "-A", "-B", "-C", "-g", "--glob", "--max-count",
                       "--max-depth", "-t", "--type", "--ignore-file"):
                i += 2
                continue
            i += 1
            continue
        if not saw_pattern:
            pattern = tok
            saw_pattern = True
        elif not path:
            path = tok
        i += 1
    if not saw_pattern:
        return None
    return _BashShim(
        family="grep",
        files=[],
        pattern=pattern,
        path=path,
        long_format=False,
        head_limit=None,
        tail_limit=None,
        rtk_filtered=False,
        raw_command=raw,
    )


def _parse_rtk_grep(rest: list[str], raw: str) -> Optional[_BashShim]:
    """Parse `rtk grep PATTERN [PATH] [extra args]`."""
    pattern = ""
    path = ""
    i = 0
    saw_pattern = False
    while i < len(rest):
        tok = rest[i]
        if tok in ("-l", "--max-len", "-m", "--max", "-t", "--file-type"):
            i += 2
            continue
        if tok in ("-c", "--context-only", "-n", "--line-numbers",
                   "--ultra-compact", "--skip-env"):
            i += 1
            continue
        if tok.startswith("-v") and all(c == "v" for c in tok[1:]):
            i += 1
            continue
        if tok == "--":
            i += 1
            continue
        if tok.startswith("-"):
            i += 1
            continue
        if not saw_pattern:
            pattern = tok
            saw_pattern = True
        elif not path:
            path = tok
        i += 1
    if not saw_pattern:
        return None
    return _BashShim(
        family="grep",
        files=[],
        pattern=pattern,
        path=path,
        long_format=False,
        head_limit=None,
        tail_limit=None,
        rtk_filtered=False,
        raw_command=raw,
    )


def _parse_ls(rest: list[str], raw: str) -> Optional[_BashShim]:
    """Parse `ls [args]`. Detect -l / -la for long format."""
    long_format = False
    paths: list[str] = []
    for tok in rest:
        if tok.startswith("-") and tok != "-":
            if "l" in tok[1:]:
                long_format = True
            continue
        paths.append(tok)
    path = paths[0] if paths else "."
    return _BashShim(
        family="ls",
        files=[],
        pattern="",
        path=path,
        long_format=long_format,
        head_limit=None,
        tail_limit=None,
        rtk_filtered=False,
        raw_command=raw,
    )


def _parse_find_tree(verb: str, rest: list[str], raw: str) -> Optional[_BashShim]:
    """Parse `find PATH [args]` or `tree [PATH]`. Output is a list of paths.

    Extracts ``-name`` / ``-iname`` filters into *pattern* so the Glob
    panel header shows the actual search expression rather than the bare
    verb.
    """
    path: str = ""
    name_filter: str = ""
    # Flags whose next token is a value (not a path).
    _FIND_VALUE_FLAGS = {
        "-name", "-iname", "-path", "-ipath", "-regex", "-iregex",
        "-type", "-maxdepth", "-mindepth", "-perm", "-user", "-group",
        "-newer", "-size", "-amin", "-atime", "-cmin", "-ctime",
        "-mmin", "-mtime", "-printf", "-fprintf", "-fls",
    }
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok in _FIND_VALUE_FLAGS:
            # Consume the value token.
            if i + 1 < len(rest):
                val = rest[i + 1]
                if tok in ("-name", "-iname"):
                    name_filter = val
                i += 2
                continue
            i += 1
            continue
        if tok.startswith("-") and tok != "-":
            # Other flags without values (e.g. -print, -delete).
            i += 1
            continue
        # First non-flag, non-value token is the path.
        if not path:
            path = tok
        i += 1
    if not path:
        path = "."
    pattern = name_filter if name_filter else verb
    return _BashShim(
        family="find",
        files=[],
        pattern=pattern,
        path=path,
        long_format=False,
        head_limit=None,
        tail_limit=None,
        rtk_filtered=False,
        raw_command=raw,
    )


# --- Bash-shim normalizers and renderers ------------------------------------

_RTK_GREP_FILE_HEADER_RE = re.compile(r"^\[file\]\s+(?P<path>.+?)\s+\((?P<count>\d+)\)\s*:\s*$")
_RTK_GREP_LINE_RE = re.compile(r"^\s+(?P<lineno>\d+):\s*(?P<text>.*)$")


def _normalize_rtk_grep_output(text: str) -> str:
    """Convert rtk grep grouped output to standard `path:line:text` lines.

    Input shape (from `rtk grep`):
        4 matches in 3F:
        [file] tools/run-agent.py (2):
          2811: return render_grep_rich(console, state)

    Output shape (compatible with _parse_grep_output):
        tools/run-agent.py:2811:return render_grep_rich(console, state)

    If no `[file] <path> (N):` markers are found, returns the text
    unchanged (no-op safe).
    """
    if "[file]" not in text:
        return text
    lines_in = text.split("\n")
    out: list[str] = []
    current_path: Optional[str] = None
    found_marker = False
    for line in lines_in:
        m = _RTK_GREP_FILE_HEADER_RE.match(line)
        if m:
            current_path = m.group("path").strip()
            found_marker = True
            continue
        n = _RTK_GREP_LINE_RE.match(line)
        if n and current_path:
            out.append(f"{current_path}:{n.group('lineno')}:{n.group('text')}")
            continue
        # Skip blanks and the "N matches in NF:" header; pass through anything else.
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^\d+\s+matches?\s+in\s+\d+F:\s*$", stripped):
            continue
        # Unknown line; drop it to keep the output clean.
    if not found_marker:
        return text
    return "\n".join(out) + ("\n" if out else "")


_LS_LONG_FORMAT_RE = re.compile(
    # Permissions (10-12 chars incl. trailing @/+ or "."), link count,
    # user, group, size, then 2 or 3 date fields (Mon DD [YYYY|HH:MM]),
    # then the filename.
    r"^[\-dlbcps][rwxstST\-@\+\.]{9,11}"
    r"\s+\d+\s+\S+\s+\S+\s+\d+"
    r"\s+\S+\s+\S+(?:\s+\S+)?"
    r"\s+(?P<name>.+)$"
)


def _strip_ls_long_format_to_filenames(text: str) -> str:
    """Strip `ls -l` long-format columns down to just the filename.
    Lines that don't look like long-format are kept as-is. The `total N`
    header line is removed."""
    out: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        if line.startswith("total ") and line[6:].strip().isdigit():
            continue
        m = _LS_LONG_FORMAT_RE.match(line)
        if m:
            out.append(m.group("name").strip())
        else:
            # Keep non-matching lines (might be paths separating directories
            # in a multi-arg ls call).
            out.append(line.rstrip())
    return "\n".join(out)


def _maybe_render_bash_shim(console: Optional[Any], state: dict[str, Any]) -> bool:
    """Detect bash invocations of read/grep/ls-equivalent CLI helpers
    (rtk *, rg, plain ls/cat/head/tail/find/tree) and route the output
    through the matching styled renderer. Returns True if handled."""
    if not _BASH_SHIM_RENDER:
        return False
    inp = state.get("input")
    if not isinstance(inp, dict):
        return False
    command = str(inp.get("command", ""))
    shim = _is_bash_shim_call(command)
    if shim is None:
        return False

    output = state.get("output")
    if not isinstance(output, str):
        return False

    if shim.family == "read":
        return _render_shim_read(console, state, shim)
    if shim.family == "grep":
        return _render_shim_grep(console, state, shim)
    if shim.family == "ls":
        return _render_shim_ls(console, state, shim)
    if shim.family == "find":
        return _render_shim_ls(console, state, shim)
    return False


def _render_shim_read(console: Optional[Any], state: dict[str, Any], shim: _BashShim) -> bool:
    """Synthesize a read-tool state and call render_read_*.

    For multi-file input (rtk read F1 F2, cat F1 F2), the output is
    concatenated with no delimiter. We render a single combined Read
    panel using the first file's path as the panel header, but we
    update the read cache by re-reading each file directly from disk
    so subsequent edit/write diffs see fresh content per the user
    directive.
    """
    raw_output = str(state.get("output") or "")
    status = str(state.get("status", ""))

    # Choose the file_path for the panel: when only one file, the actual
    # path. When multiple files, fall back to a synthetic descriptor.
    if len(shim.files) == 1:
        file_path = shim.files[0]
    else:
        file_path = " + ".join(shim.files)

    # Synthesize OpenCode read framing around the raw content so the
    # existing renderer can parse and render without modification.
    rel_for_frame = _relativize_path(shim.files[0]) if shim.files else file_path

    # Optional offset/limit from `head -n N` / `tail -n N`.
    offset: Optional[int] = None
    limit: Optional[int] = None
    if shim.head_limit is not None:
        offset = 1
        limit = shim.head_limit
    elif shim.tail_limit is not None:
        # We don't know the file length, so leave offset unset and let
        # the renderer omit the lines header.
        limit = shim.tail_limit

    framed = (
        f"<path>{rel_for_frame}</path>\n"
        f"<type>file</type>\n"
        f"<content>\n{raw_output}\n</content>"
    )

    syn_state = {
        "input": {"filePath": file_path, "offset": offset, "limit": limit},
        "output": framed,
        "status": status,
    }

    if HAVE_RICH and console is not None:
        ok = render_read_rich(console, syn_state)
    else:
        ok = render_read_plain(syn_state)

    if not ok:
        return False

    # Cache update: when filtering flags are present, or there are
    # multiple files (no reliable per-file content boundaries), re-read
    # each file directly from disk so the cache stays accurate.
    if shim.rtk_filtered or len(shim.files) > 1:
        for f in shim.files:
            full = f if os.path.isabs(f) else os.path.join(ROOT, f)
            _cache_reread(full)
    return True


def _render_shim_grep(console: Optional[Any], state: dict[str, Any], shim: _BashShim) -> bool:
    raw_output = str(state.get("output") or "")
    normalized = _normalize_rtk_grep_output(raw_output)

    # If the normalizer found rtk-style markers but produced no rows,
    # something is unexpected; fall back to bash renderer.
    if "[file]" in raw_output and not normalized.strip():
        return False

    syn_state = {
        "input": {"pattern": shim.pattern, "path": shim.path},
        "output": normalized,
        "status": str(state.get("status", "")),
    }
    if HAVE_RICH and console is not None:
        return render_grep_rich(console, syn_state)
    return render_grep_plain(syn_state)


def _render_shim_ls(console: Optional[Any], state: dict[str, Any], shim: _BashShim) -> bool:
    raw_output = str(state.get("output") or "")
    if shim.long_format and _BASH_SHIM_LS_STRIP_LONG_FORMAT:
        body = _strip_ls_long_format_to_filenames(raw_output)
    else:
        body = raw_output
    pattern_label = "ls" if shim.family == "ls" else shim.pattern
    syn_state = {
        "input": {"pattern": pattern_label, "path": shim.path},
        "output": body,
        "status": str(state.get("status", "")),
    }
    if HAVE_RICH and console is not None:
        return render_glob_rich(console, syn_state)
    return render_glob_plain(syn_state)


# --- Subagent summary helper --------------------------------------------------

def _format_subagent_summary(summary: Any) -> str:
    """Format a Session.summary dict into a compact '+N -M  K files' string."""
    if not isinstance(summary, dict):
        return ""
    additions = summary.get("additions")
    deletions = summary.get("deletions")
    files = summary.get("files")
    parts: list[str] = []
    if additions is not None or deletions is not None:
        parts.append(f"+{additions or 0} -{deletions or 0}")
    if files is not None:
        parts.append(f"{files} file(s)")
    return "  ".join(parts)


# --- Task renderer ------------------------------------------------------------

def render_task_rich(console: Console, state: dict[str, Any]) -> bool:
    inp = state.get("input")
    if not isinstance(inp, dict):
        return False

    description = str(inp.get("description", ""))
    subagent_type = str(inp.get("subagent_type", inp.get("subagentType", "")))
    prompt = str(inp.get("prompt", ""))
    status = str(state.get("status", "unknown"))
    border = "green" if status == "completed" else "yellow"

    sections: list[Any] = []
    if description:
        type_tag = f"  [{subagent_type}]" if subagent_type else ""
        sections.append(Text(f"{description}{type_tag}", style="bold cyan"))

    if prompt:
        sections.append(Text())
        prompt_lines = prompt.split("\n")
        preview_lines = prompt_lines[:_TASK_PROMPT_PREVIEW_LINES]
        leftover = max(0, len(prompt_lines) - _TASK_PROMPT_PREVIEW_LINES)
        sections.append(Text("\n".join(preview_lines), style="dim"))
        if leftover > 0:
            sections.append(Text(f"... {leftover} more lines", style="dim"))

    output_data = state.get("output")
    if output_data is not None:
        sections.append(Text())
        sections.append(Text("Output", style="bold green"))
        output_str = str(output_data)
        if len(output_str) > 200:
            output_str = output_str[:200] + "..."
        sections.append(Text(output_str, style="dim"))

    console.print(
        Panel(Group(*sections), title=Text(f"Task [{status}]"), border_style=border, expand=True)
    )
    return True


def render_task_plain(state: dict[str, Any]) -> bool:
    inp = state.get("input")
    if not isinstance(inp, dict):
        return False

    description = str(inp.get("description", ""))
    subagent_type = str(inp.get("subagent_type", inp.get("subagentType", "")))
    prompt = str(inp.get("prompt", ""))
    status = str(state.get("status", "unknown"))

    type_tag = f" [{subagent_type}]" if subagent_type else ""
    print(C.header(f"task {description}{type_tag} [{status}]"))

    if prompt:
        prompt_lines = prompt.split("\n")
        for line in prompt_lines[:_TASK_PROMPT_PREVIEW_LINES]:
            print(f"  {line}")
        leftover = max(0, len(prompt_lines) - _TASK_PROMPT_PREVIEW_LINES)
        if leftover > 0:
            print(f"  ... {leftover} more lines")

    output_data = state.get("output")
    if output_data is not None:
        print(C.info("Output"))
        output_str = str(output_data)
        if len(output_str) > 200:
            output_str = output_str[:200] + "..."
        print(f"  {output_str}")

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
    elif tool_lower == "grep":
        _cache_invalidate_stale()
        if HAVE_RICH:
            return render_grep_rich(console, state)
        else:
            return render_grep_plain(state)
    elif tool_lower == "bash":
        _cache_invalidate_stale()
        # Try the sandbox-bootstrap sub-renderer first; it handles bash
        # invocations of `tools/sandbox-bootstrap.py --format json …` and
        # `make sandbox-* BOOTSTRAP_ARGS='--format json'` with structured
        # styling. Falls through to the generic bash renderer otherwise.
        if _maybe_render_sandbox_bootstrap(console if HAVE_RICH else None, state):
            return True
        # Then try the bash-shim sub-renderer: detects `rtk read`,
        # `rtk grep`, `rg`, `rtk ls` / `ls`, `cat`, `head`, `tail`,
        # `find`, `tree` and routes them through the Read / Grep /
        # Glob renderers as if the agent had used the native tool.
        if _maybe_render_bash_shim(console if HAVE_RICH else None, state):
            return True
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
    elif tool_lower == "task":
        _cache_invalidate_stale()
        if HAVE_RICH:
            return render_task_rich(console, state)
        else:
            return render_task_plain(state)
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


def render_reasoning(console: Console, event: dict[str, Any]) -> None:
    """Render a model's reasoning/thinking block.

    OpenCode emits these only when --thinking is on AND the part is
    finalized (part.time?.end set). The wrapper draws them as a
    visually-subordinate variant of the Assistant panel.
    """
    if not _RENDER_REASONING:
        return
    part = event.get("part", {})
    text = str(part.get("text", "")).strip()
    if not text:
        return

    truncated_note = ""
    if len(text) > _REASONING_MAX_CHARS:
        cut = len(text) - _REASONING_MAX_CHARS
        text = text[:_REASONING_MAX_CHARS]
        truncated_note = f"\n\n... ({cut} chars truncated)"

    if HAVE_RICH:
        body_md = Markdown(text)
        if truncated_note:
            sections: list[Any] = [body_md, Text(truncated_note.strip(), style="dim")]
            body: Any = Group(*sections)
        else:
            body = body_md
        console.print(
            Panel(
                body,
                title="Thinking",
                border_style="blue",
                expand=True,
                style="dim",
            )
        )
    else:
        print(C.header("Thinking"))
        print(text)
        if truncated_note:
            print(truncated_note.strip())


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


def _extract_tool_permission_error(event: dict[str, Any]) -> Optional[str]:
    """Return a human-readable permission rejection summary for a tool_use error.

    The OpenCode stream reports rejected approvals as tool_use events with
    state.status == "error" and an error string mentioning permission rejection.
    When this occurs near the end of a turn, we should report that explicit
    cause instead of a generic "mid-turn" truncation message.
    """
    if event.get("type") != "tool_use":
        return None
    part = event.get("part")
    if not isinstance(part, dict):
        return None
    state = part.get("state")
    if not isinstance(state, dict):
        return None
    if str(state.get("status", "")) != "error":
        return None

    err = str(state.get("error", "")).strip()
    low = err.lower()
    if "rejected permission" not in low and "permission" not in low:
        return None

    tool_name = str(part.get("tool", "tool")).strip() or "tool"
    input_data = state.get("input")
    if isinstance(input_data, dict):
        # Prefer path-like identifiers for file-oriented tools.
        for key in ("filePath", "path", "selector"):
            value = input_data.get(key)
            if isinstance(value, str) and value.strip():
                return f"tool permission rejected: {tool_name} {value.strip()}"
        # Bash tool:
        cmd = input_data.get("command")
        if isinstance(cmd, str) and cmd.strip():
            return f"tool permission rejected: {tool_name} `{cmd.strip()}`"

    return f"tool permission rejected: {tool_name}"


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


def render_error(console: Console, event: dict[str, Any]) -> None:
    """Render a session.error event from the OpenCode JSON stream.

    Border is yellow (alarm) and the message body is rendered red.
    Distinct from tool failures (which are red borders on tool panels)
    and from completed-but-truncated runs (which are red banners).
    """
    err = event.get("error")
    msg_parts: list[str] = []
    if isinstance(err, dict):
        # Common shapes: {"name": "...", "message": "..."} or
        # {"name": "...", "data": {"message": "..."}}
        name = err.get("name")
        if isinstance(name, str) and name:
            msg_parts.append(name)
        data = err.get("data")
        if isinstance(data, dict):
            data_msg = data.get("message")
            if isinstance(data_msg, str) and data_msg:
                msg_parts.append(data_msg)
        elif isinstance(err.get("message"), str):
            msg_parts.append(err["message"])
    elif isinstance(err, str):
        msg_parts.append(err)

    text = ": ".join(msg_parts) if msg_parts else "(no error message)"

    if HAVE_RICH:
        console.print(
            Panel(
                Text(text, style="red"),
                title="Error",
                border_style="yellow",
                expand=True,
            )
        )
    else:
        print(C.warn("Error"))
        print(C.fail(text))


def render_event(console: Console, phase: str, label: str, event: dict[str, Any]) -> None:
    event_type = event.get("type")
    if event_type == "step_start":
        render_step_start(console, phase, label, event)
    elif event_type == "text":
        render_text(console, event)
    elif event_type == "reasoning":
        render_reasoning(console, event)
    elif event_type == "tool_use":
        render_tool_use(console, event)
    elif event_type == "step_finish":
        render_step_finish(console, event)
    elif event_type == "error":
        render_error(console, event)
    elif event_type == "session.status":
        render_session_status(console, event)
    elif event_type == "subagent.status":
        render_subagent_status(console, event)
    else:
        render_unknown(console, event)


def render_session_status(console: Console, event: dict[str, Any]) -> None:
    properties = event.get("properties", {})
    status = properties.get("status", {})
    status_type = status.get("type")
    
    if status_type == "retry":
        attempt = status.get("attempt", 1)
        message = status.get("message", "Unknown error")
        text = f"⏳ Waiting for LLM provider response (retry attempt {attempt}): {message}"
        if HAVE_RICH:
            console.print(Text(text, style="bold yellow"))
        else:
            print(C.warn(text))


def render_subagent_status(console: Console, event: dict[str, Any]) -> None:
    """Render a subagent.status event injected by the StatusForwarder plugin.

    The plugin emits these events for subagent lifecycle (created/updated/
    deleted) and heartbeats so that run-agent.py can show real-time progress
    while child sessions work in parallel.
    """
    if not _RENDER_SUBAGENT_UPDATES:
        return

    properties = event.get("properties", {})
    status_type = str(properties.get("statusType", ""))
    session_id = str(properties.get("sessionID", ""))
    title = str(properties.get("title", "(untitled)"))
    summary = properties.get("summary")
    elapsed_ms = properties.get("elapsedMs")

    # Deduplicate unchanged update snapshots to avoid flooding the UI.
    if status_type == "updated":
        snapshot: dict[str, Any] = {"title": title}
        if isinstance(summary, dict):
            snapshot["additions"] = summary.get("additions")
            snapshot["deletions"] = summary.get("deletions")
            snapshot["files"] = summary.get("files")

        last_snapshot, last_time = _SUBAGENT_LAST_STATE.get(session_id, ({}, 0.0))
        now = time.time()
        # Identical snapshot inside the throttle window -> suppress.
        if (
            last_snapshot == snapshot
            and (now - last_time) < _SUBAGENT_UPDATE_THROTTLE_S
        ):
            return

        _SUBAGENT_LAST_STATE[session_id] = (snapshot, now)

    if status_type == "created":
        if HAVE_RICH:
            console.print(
                Panel(
                    Text(title, style="bold cyan"),
                    title="Subagent started",
                    border_style="cyan",
                    expand=True,
                )
            )
        else:
            print(C.header(f"[subagent] started: {title}"))
    elif status_type == "finished":
        if HAVE_RICH:
            console.print(
                Panel(
                    Text(title, style="bold cyan"),
                    title="Subagent finished",
                    border_style="green",
                    expand=True,
                )
            )
        else:
            print(C.ok(f"[subagent] finished: {title}"))
    elif status_type == "heartbeat" and elapsed_ms is not None:
        elapsed_s = elapsed_ms // 1000
        text = f"⏳ Subagent · {title} still running ({elapsed_s}s)"
        if HAVE_RICH:
            console.print(Text(text, style="bold yellow"))
        else:
            print(C.warn(text))
    elif status_type == "updated":
        summary_text = _format_subagent_summary(summary)
        line = f"Subagent · {title}"
        if summary_text:
            line += f"  {summary_text}"
        if HAVE_RICH:
            console.print(Text(line, style="dim"))
        else:
            print(f"  {line}")


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


def _thinking_default_for_provider(provider_id: Optional[str]) -> bool:
    """Return True if --thinking should default to ON for this provider.

    Anthropic interleaves thinking with text blocks via the
    interleaved-thinking beta header (set by OpenCode by default), so
    the wrapper already shows multiple Assistant panels per turn. Adding
    --thinking on top would double the panels for no extra information.

    All other known reasoning-capable providers hide their reasoning
    unless --thinking is on. Default ON for those, and ON for unknown
    future providers (cheaper to over-surface than under-surface in a
    research workflow).
    """
    if not provider_id:
        return True
    pid = provider_id.lower()
    if pid.startswith("anthropic"):
        return False
    return True


def _resolve_thinking_decision(
    model: Optional[str],
    extra_args: list[str],
) -> tuple[bool, str]:
    """Decide whether to enable --thinking for the child opencode run.

    Precedence:
      1. --thinking explicitly present in OPENCODE_ARGS -> on (user-args).
      2. CODECOME_THINKING env var -> on/off (env).
      3. Per-provider default based on the model's provider prefix.

    Returns (enabled, source).
    """
    if "--thinking" in extra_args:
        return True, "user-args"

    raw = os.environ.get("CODECOME_THINKING")
    if raw is not None:
        if raw.strip() in ("0", "false", "False", "no", ""):
            return False, "env"
        return True, "env"

    provider_id = None
    if model and "/" in model:
        provider_id = model.split("/", 1)[0]
    enabled = _thinking_default_for_provider(provider_id)
    return enabled, "provider-default"


def build_child_command(args: argparse.Namespace) -> tuple[list[str], Optional[str], Optional[str], str, str, bool, str]:
    """Return the child command and the resolved model/variant + sources.

    Appends --model/--variant from env or codecome.yml only when
    OPENCODE_ARGS does not already pass them. Also resolves the
    --thinking decision per provider and returns it for the banner.
    """
    cmd = ["opencode", "run", "--format", "json", "--agent", args.agent]

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

    # Decide --thinking based on env override, OPENCODE_ARGS, or
    # per-provider default. Skip appending if it was already in
    # extra_args (already added via cmd.extend(extra_args) above).
    thinking_on, thinking_source = _resolve_thinking_decision(model, extra_args)
    if thinking_on and "--thinking" not in extra_args:
        cmd.append("--thinking")

    return cmd, model, variant, model_source, variant_source, thinking_on, thinking_source


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


_PHASE1_REQUIRED_ARTIFACT_NAMES = [
    "target-profile.md",
    "attack-surface.md",
    "build-model.md",
    "execution-model.md",
    "trust-boundaries.md",
    "data-flow.md",
    "validation-model.md",
    "interesting-files.md",
    "file-risk-index.yml",
    "security-assumptions.md",
    "sandbox-plan.md",
]


def _phase1_required_artifacts() -> list[Path]:
    notes_dir = ROOT / "itemdb" / "notes"
    return [notes_dir / name for name in _PHASE1_REQUIRED_ARTIFACT_NAMES]


def _path_is_fresh(path: Path, run_start_time: float) -> bool:
    return path.exists() and path.stat().st_mtime >= run_start_time


def _iter_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def _phase_checklist_lines(phase: str, finding: str | None) -> list[str]:
    if str(phase) == "1":
        return [
            "Ensure all required Phase 1 notes exist under itemdb/notes/.",
            "Ensure itemdb/notes/file-risk-index.yml is present and consistent with interesting-files.md.",
            "Ensure itemdb/notes/sandbox-plan.md documents the Phase 1b outcome.",
            "If sandbox bootstrap succeeded, ensure sandbox/CODECOME-GENERATED.md exists; otherwise document the halt clearly in sandbox-plan.md.",
        ]
    if str(phase) in ("2", "sweep"):
        return [
            "Create or update precise findings under itemdb/findings/PENDING/.",
            "Each finding must identify affected code, trust-boundary/source-to-sink reasoning, attackability, impact, validation plan, and counter-analysis placeholder.",
            "Do not stop until the new or updated findings are durable on disk.",
        ]
    if str(phase) == "3":
        return [
            "Review all candidate findings under itemdb/findings/PENDING/.",
            "Move clearly invalid findings to REJECTED and duplicates to DUPLICATE.",
            "Leave surviving findings reviewable, deduplicated, and updated with counter-analysis.",
        ]
    if str(phase) == "4":
        finding_ref = finding or "<finding-id>"
        return [
            f"Ensure validation evidence exists under itemdb/evidence/{finding_ref}/, including README.md.",
            "Update the finding with validation results and move it to the correct status directory if needed.",
            "Do not stop until the evidence and finding status are consistent.",
        ]
    if str(phase) == "5":
        finding_ref = finding or "<finding-id>"
        return [
            f"If exploitation succeeds, ensure itemdb/evidence/{finding_ref}/exploits/ contains the exploit artifacts and exploits/README.md.",
            "If exploitation is not feasible, keep the finding in CONFIRMED and update its exploitation.status to NOT_FEASIBLE with a clear explanation.",
            "Do not stop until the exploit artifacts or the NOT_FEASIBLE documentation are durable and consistent.",
        ]
    if str(phase) == "6":
        return [
            "Ensure the report output under itemdb/reports/ is written and reviewable.",
            "Include the required summary sections and evidence references for exploited and confirmed findings.",
            "Do not stop until the report artifacts are durable on disk.",
        ]
    return ["Finish the remaining required work for the current phase before ending."]


def _build_phase_resume_prompt(
    phase: str,
    finding: str | None,
    reason: str,
    step_finish_count: int,
) -> str:
    checklist = "\n".join(f"- {line}" for line in _phase_checklist_lines(phase, finding))
    return (
        "Your previous response was cut off by the model/provider before you produced a final completion signal.\n\n"
        f"Observed finish reason: {reason}.\n"
        f"Completed loops before cutoff: {step_finish_count}.\n\n"
        "Treat your prior work as partial. First, briefly reassess what remains unfinished for this phase. "
        "Then complete only the remaining required work. Do not restart from scratch unless necessary.\n\n"
        f"Phase {phase} completion checklist:\n"
        f"{checklist}\n\n"
        "Before ending, verify that the required durable artifacts for this phase exist, are updated, and are internally consistent."
    )


def _build_frontmatter_resume_prompt(phase: str, finding: str | None, validation_output: str) -> str:
    checklist = "\n".join(f"- {line}" for line in _phase_checklist_lines(phase, finding))
    return (
        "Your previous run produced files that failed local validation.\n\n"
        "Validation errors:\n"
        f"{validation_output}\n\n"
        "Repair only the reported YAML/frontmatter issues with minimal changes. Do not redo unrelated analysis.\n\n"
        f"Phase {phase} completion checklist:\n"
        f"{checklist}\n\n"
        "After fixing the validation errors, ensure the affected files remain in the correct status/location and are internally consistent."
    )


def _build_resume_command(initial_command: list[str], session_id: str, prompt: str) -> list[str]:
    """Preserve connection/runtime flags needed to reach the original session."""
    resume = ["opencode", "run"]
    pending_passthrough_value = False
    passthrough_value_flags = {"--attach", "--port", "-p"}
    passthrough_standalone_flags = {"--thinking"}
    drop_value_flags = {"--agent", "--model", "-m", "--variant", "--session", "-s", "--format"}
    drop_standalone_flags = {"--continue", "-c", "--fork"}

    for token in initial_command[2:]:
        if pending_passthrough_value:
            resume.append(token)
            pending_passthrough_value = False
            continue

        name, has_equals, _ = token.partition("=")
        if name in drop_standalone_flags:
            continue
        if name in drop_value_flags:
            if not has_equals:
                pending_passthrough_value = False
            continue
        if name in passthrough_standalone_flags:
            resume.append(token)
            continue
        if name in passthrough_value_flags:
            resume.append(token)
            if not has_equals:
                pending_passthrough_value = True
            continue

    resume.extend(["--session", session_id, "--format", "json", prompt])
    return resume



_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _load_finding_frontmatter(path: Path) -> dict[str, Any] | None:
    """Return the YAML frontmatter dict from a finding file, or None."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(m.group(1))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _exploitation_status_looks_real(frontmatter: dict[str, Any] | None) -> bool:
    """Return True when the exploitation block has a non-placeholder status."""
    if not isinstance(frontmatter, dict):
        return False
    exploitation = frontmatter.get("exploitation")
    if not isinstance(exploitation, dict):
        return False
    status = str(exploitation.get("status", "")).strip().lower()
    return bool(status and status not in ("", "pending.", "todo.", "tbd."))


def check_phase_graceful_completion(phase: str, finding: str | None, run_start_time: float) -> bool:
    """Check if the phase produced its primary artifacts, allowing us to forgive mid-turn cutoffs."""
    try:
        if str(phase) == "1":
            required_artifacts = _phase1_required_artifacts()
            if all(path.exists() for path in required_artifacts):
                fresh_required = any(_path_is_fresh(path, run_start_time) for path in required_artifacts)
                sandbox_generated = ROOT / "sandbox" / "CODECOME-GENERATED.md"
                sandbox_state_recorded = _path_is_fresh(sandbox_generated, run_start_time) or _path_is_fresh(
                    ROOT / "itemdb" / "notes" / "sandbox-plan.md", run_start_time
                )
                return fresh_required and sandbox_state_recorded
            return False
        elif str(phase) in ("2", "sweep"):
            pending_dir = ROOT / "itemdb" / "findings" / "PENDING"
            if pending_dir.exists():
                return any(f.name.endswith(".md") and f.name != ".gitkeep" and f.stat().st_mtime >= run_start_time for f in pending_dir.iterdir())
            return False
        elif str(phase) == "3":
            findings_dir = ROOT / "itemdb" / "findings"
            return any(
                path.suffix == ".md" and path.name != ".gitkeep" and path.stat().st_mtime >= run_start_time
                for path in _iter_files(findings_dir)
            )
        elif str(phase) == "4" and finding:
            evidence_dir = ROOT / "itemdb" / "evidence" / finding
            return any(path.stat().st_mtime >= run_start_time for path in _iter_files(evidence_dir))
        elif str(phase) == "5" and finding:
            # Path A: finding promoted to EXPLOITED with real frontmatter + exploit artifacts.
            exploited_file = ROOT / "itemdb" / "findings" / "EXPLOITED" / f"{finding}.md"
            if (
                exploited_file.exists()
                and exploited_file.stat().st_mtime >= run_start_time
            ):
                fm = _load_finding_frontmatter(exploited_file)
                if (
                    isinstance(fm, dict)
                    and fm.get("status") == "EXPLOITED"
                    and _exploitation_status_looks_real(fm)
                ):
                    exploits_dir = ROOT / "itemdb" / "evidence" / finding / "exploits"
                    if any(
                        path.stat().st_mtime >= run_start_time
                        for path in _iter_files(exploits_dir)
                    ):
                        return True

            # Path B: CONFIRMED finding documented as NOT_FEASIBLE.
            confirmed_file = ROOT / "itemdb" / "findings" / "CONFIRMED" / f"{finding}.md"
            if (
                confirmed_file.exists()
                and confirmed_file.stat().st_mtime >= run_start_time
            ):
                fm = _load_finding_frontmatter(confirmed_file)
                if (
                    isinstance(fm, dict)
                    and fm.get("status") == "CONFIRMED"
                    and isinstance(fm.get("exploitation"), dict)
                    and str(fm["exploitation"].get("status", "")).upper()
                    == "NOT_FEASIBLE"
                ):
                    return True

            return False
        elif str(phase) == "6":
            reports_dir = ROOT / "itemdb" / "reports"
            if reports_dir.exists():
                return any(f.name.endswith(".md") and f.name != ".gitkeep" and f.stat().st_mtime >= run_start_time for f in reports_dir.iterdir())
            return False
    except Exception:
        pass
    return False

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
    thinking_on, thinking_source = _resolve_thinking_decision(model, extra_args)
    print(f"  {C.BOLD}effective{C.RESET}                     "
          f"model={effective_model}  variant={effective_variant}  "
          f"thinking={'on' if thinking_on else 'off'}")
    print(f"  {C.DIM}sources{C.RESET}                       "
          f"model: {model_source}  variant: {variant_source}  "
          f"thinking: {thinking_source}")
    return 0


def main() -> int:
    RUN_START_TIME = time.time()
    iteration_retry_count = 0
    frontmatter_retry_count = 0
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
    prompt = load_prompt(prompt_file, args.finding, phase=args.phase)
    command, model, variant, model_source, variant_source, thinking_on, thinking_source = build_child_command(args)
    base_command = list(command)
    model, variant, model_source, variant_source = resolve_runtime_model_for_banner(
        args, command, model, variant, model_source, variant_source
    )

    # If the runtime probe revealed a different provider and the user
    # didn't explicitly pin --thinking via env or OPENCODE_ARGS, redo
    # the per-provider decision now. This keeps the banner truthful.
    if thinking_source == "provider-default":
        new_thinking_on, _ = _resolve_thinking_decision(model, shlex.split(os.environ.get("OPENCODE_ARGS", "")))
        if new_thinking_on != thinking_on:
            # Adjust the command for the late discovery: add or remove --thinking.
            if new_thinking_on and "--thinking" not in command:
                command.append("--thinking")
            elif not new_thinking_on and "--thinking" in command:
                command.remove("--thinking")
            thinking_on = new_thinking_on

    model_label = model or "(unknown)"
    variant_label = variant or "(unknown)"

    # Build the single-line banner. Order: agent  model  variant?  prompt
    # followed by a trailing parenthetical with the resolution source(s).
    parts = [f"agent={args.agent}", f"model={model_label}"]
    if variant is not None:
        parts.append(f"variant={variant_label}")
    parts.append(f"thinking={'on' if thinking_on else 'off'}")
    parts.append(f"prompt={args.prompt_file}")

    if variant is not None:
        sources_tail = (
            f"(model source: {model_source}, variant source: {variant_source}, "
            f"thinking source: {thinking_source})"
        )
    else:
        sources_tail = (
            f"(model source: {model_source}, thinking source: {thinking_source})"
        )

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

    attempt_number = 0
    while True:
        attempt_number += 1
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
            finding_tag = (args.finding or "no-finding").replace("/", "_")
            transcript_dir = ROOT / "tmp"
            transcript_dir.mkdir(parents=True, exist_ok=True)
            transcript_path = transcript_dir / f"last-phase-{args.phase}-{finding_tag}-attempt-{attempt_number}.jsonl"
            last_finish_reason: Optional[str] = None
            last_finish_tokens: dict[str, Any] = {}
            last_permission_error: Optional[str] = None
            any_step_finish_seen = False
            step_finish_count = 0
            stream_session_id: Optional[str] = None
            
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
                        if stream_session_id is None and "sessionID" in event:
                            stream_session_id = event["sessionID"]
                    except json.JSONDecodeError:
                        if args.debug:
                            sys.stderr.write(f"json-parse-error: {line}\n")
                            sys.stderr.flush()
                        continue

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

                    if event.get("type") == "step_finish":
                        any_step_finish_seen = True
                        step_finish_count += 1
                        part = event.get("part") or {}
                        reason = part.get("reason")
                        if isinstance(reason, str):
                            last_finish_reason = reason
                        tokens = part.get("tokens")
                        if isinstance(tokens, dict):
                            last_finish_tokens = tokens

                    permission_error = _extract_tool_permission_error(event)
                    if permission_error is not None:
                        last_permission_error = permission_error
                        if HAVE_RICH and console is not None:
                            render_permission_error_rich(console, permission_error)
                        else:
                            render_permission_error_plain(permission_error)

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

        finish_warning: Optional[str] = None
        if returncode == 0:
            if not any_step_finish_seen:
                finish_warning = (
                    "CodeCome observed no step_finish events in the JSON stream, so the model/provider did not emit a "
                    "completion signal. Treating the run as incomplete."
                )
            elif last_finish_reason is None:
                finish_warning = (
                    "CodeCome observed a step_finish event without a finish reason, so the model/provider completion "
                    "state is ambiguous. Treating the run as incomplete."
                )
            elif last_finish_reason in _FINISH_FAILURE:
                finish_warning = (
                    f"CodeCome observed finish reason '{last_finish_reason}', which means the model/provider stopped "
                    "before completing the phase. Treating the run as incomplete rather than as a CodeCome logic error."
                )
            elif last_finish_reason in _FINISH_MID_TURN:
                if last_permission_error:
                    finish_warning = (
                        f"{last_permission_error}; CodeCome observed the model/provider stop mid-turn with finish "
                        f"reason '{last_finish_reason}', so the phase did not reach a final completion signal."
                    )
                else:
                    finish_warning = (
                        f"CodeCome observed the model/provider stop mid-turn with finish reason '{last_finish_reason}' "
                        f"after {step_finish_count} completed loops, without a terminal completion signal. Treating the "
                        "phase as incomplete because the model/provider cut off the response."
                    )
            elif last_finish_reason not in _FINISH_TERMINAL_OK:
                finish_warning = (
                    f"CodeCome observed an unrecognised model/provider finish reason '{last_finish_reason}'. Treating "
                    "the run as incomplete rather than assuming success."
                )

        if finish_warning is not None and returncode == 0:
            if (
                last_finish_reason in _FINISH_MID_TURN
                and last_permission_error is None
                and check_phase_graceful_completion(args.phase, args.finding, RUN_START_TIME)
            ):
                msg = (
                    f"CodeCome observed a mid-turn model/provider cutoff for Phase {args.phase} after {step_finish_count} "
                    "completed loops, but the required durable artifacts were already written. Treating the phase as complete."
                )
                if HAVE_RICH:
                    console.print(Text(msg, style="bold green"))
                else:
                    print(C.ok(msg))
                finish_warning = None
                last_finish_reason = "graceful_forgiveness"
            else:
                returncode = 2

        # -----------------------------------------------------
        # Auto-Resume Logic
        # -----------------------------------------------------
        
        last_session_id = stream_session_id
        if not last_session_id:
            try:
                db_query = subprocess.run(
                    ["opencode", "db", "SELECT id FROM session ORDER BY time_updated DESC LIMIT 1", "--format", "tsv"],
                    capture_output=True, text=True, timeout=1.0
                )
                if db_query.returncode == 0 and db_query.stdout.strip():
                    last_session_id = db_query.stdout.strip().splitlines()[-1].strip()
            except Exception:
                pass

        # Frontmatter Resume
        if returncode == 0:
            validation_result = subprocess.run(
                [sys.executable, "tools/check-frontmatter.py"],
                cwd=ROOT,
                capture_output=True,
                text=True
            )
            if validation_result.returncode != 0:
                max_frontmatter_retries = 2
                validation_output = (validation_result.stderr or validation_result.stdout).strip() or "(no validator output)"
                if frontmatter_retry_count < max_frontmatter_retries:
                    frontmatter_retry_count += 1
                    msg = (
                        "\n[Auto-Correction] The model completed a turn, but its output failed local frontmatter "
                        f"validation. CodeCome will resume the same session and ask for a minimal repair "
                        f"(retry {frontmatter_retry_count}/{max_frontmatter_retries})."
                    )
                    if HAVE_RICH:
                        console.print(Text(msg, style="bold yellow"))
                    else:
                        print(C.warn(msg))
                        
                    if last_session_id and last_session_id != "id":
                        prompt = _build_frontmatter_resume_prompt(
                            args.phase,
                            args.finding,
                            validation_output,
                        )
                        command = _build_resume_command(base_command, last_session_id, prompt)
                        if HAVE_RICH:
                            console.print(Text(f"Resuming session {last_session_id}...", style="dim"))
                        continue # loop back and retry
                    else:
                        returncode = 2
                        finish_warning = (
                            "The model output failed local frontmatter validation, and CodeCome could not determine a "
                            "session ID to resume for repair. Treating the phase as incomplete so the validator output "
                            "can be reported back with the saved transcript."
                        )
                        if HAVE_RICH:
                            console.print(Text("Could not determine session ID to resume.", style="red"))
                        else:
                            print(C.fail("Could not determine session ID to resume."))
                else:
                    returncode = 2
                    finish_warning = (
                        f"The model output still fails local frontmatter validation after {max_frontmatter_retries} "
                        "auto-repair attempts. Treating the phase as incomplete so the validation errors can be reported back."
                    )
                    msg = f"\n[Warning] Frontmatter errors persist after {max_frontmatter_retries} auto-retries."
                    if HAVE_RICH:
                        console.print(Text(msg, style="bold red"))
                    else:
                        print(C.fail(msg))
                    print(validation_output)
            
            # If no frontmatter errors or we ran out of retries, we are done
            break

        # Iteration Limit Resume
        if returncode == 2 and last_finish_reason in _FINISH_MID_TURN:
            max_iteration_retries = int(os.environ.get("CODECOME_MAX_ITERATION_RETRIES", "1"))
            if iteration_retry_count < max_iteration_retries:
                iteration_retry_count += 1
                msg = (
                    "\n[Auto-Resume] CodeCome observed a mid-turn model/provider cutoff and will resume the same "
                    f"session once to let the model finish the interrupted work (retry {iteration_retry_count}/{max_iteration_retries})."
                )
                if HAVE_RICH:
                    console.print(Text(msg, style="bold yellow"))
                else:
                    print(C.warn(msg))
                
                if last_session_id and last_session_id != "id":
                    prompt = _build_phase_resume_prompt(
                        args.phase,
                        args.finding,
                        last_finish_reason,
                        step_finish_count,
                    )
                    command = _build_resume_command(base_command, last_session_id, prompt)
                    if HAVE_RICH:
                        console.print(Text(f"Resuming session {last_session_id}...", style="dim"))
                    continue # loop back and retry
                else:
                    finish_warning = (
                        "CodeCome correctly detected that the model/provider stopped mid-turn, but it could not determine "
                        "a session ID for automatic continuation. Treating the phase as incomplete."
                    )
                    if HAVE_RICH:
                        console.print(Text("Could not determine session ID to resume.", style="red"))
                    else:
                        print(C.fail("Could not determine session ID to resume."))
                        
            # If we run out of iteration retries, we break out
            break
            
        # Any other return code (e.g. failure, interrupt), we break
        break

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
