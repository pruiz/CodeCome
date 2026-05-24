# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
RtkReadInterceptor — re-routes rtk read / cat / head / tail bash
commands through the ReadRenderer so the user sees a Read panel
instead of a generic Bash panel.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from rendering.tools.base import ToolRenderer
from rendering.tools.interceptors.base import CommandExecutionInterceptor
from rendering.utils import relativize_path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASH_SHIM_READ_VERBS = {"cat", "head", "tail"}
_BASH_SHIM_LEADING_NOISE = {"sudo", "time", "nice", "ionice", "command", "env"}
_BASH_SHIM_DISQUALIFIERS = ("|", ";", "&&", "||", ">", "<", "`", "$(")


# ---------------------------------------------------------------------------
# Shared data structures
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Command-line helper functions
# ---------------------------------------------------------------------------

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
        from .rtk_grep import _parse_rtk_grep  # noqa: E402
        return _parse_rtk_grep(rest, command_str)
    if head in {"rg", "grep"}:
        from .rtk_grep import _parse_grep_or_rg  # noqa: E402
        return _parse_grep_or_rg(rest, command_str)
    if head in {"ls"}:
        from .shell_listing import _parse_ls  # noqa: E402
        return _parse_ls(rest, command_str)
    if head in {"find", "tree"}:
        from .shell_listing import _parse_find_tree  # noqa: E402
        return _parse_find_tree(head, rest, command_str)
    return None


# ---------------------------------------------------------------------------
# Read shim renderer
# ---------------------------------------------------------------------------

def _render_shim_read(renderer: ToolRenderer, state: dict[str, Any], shim: _BashShim) -> bool:
    """Synthesize a read-tool state and delegate to ReadRenderer."""
    from rendering.tools.read import ReadRenderer

    raw_output = str(state.get("output") or "")
    status = str(state.get("status", ""))
    root = renderer.context.root

    # Choose the file_path for the panel: when only one file, the actual
    # path. When multiple files, fall back to a synthetic descriptor.
    if len(shim.files) == 1:
        file_path = shim.files[0]
    else:
        file_path = " + ".join(shim.files)

    # Synthesize OpenCode read framing around the raw content so the
    # existing renderer can parse and render without modification.
    rel_for_frame = relativize_path(shim.files[0], root) if shim.files else file_path

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

    read_renderer = ReadRenderer(renderer.context)
    ok = read_renderer.render("read", syn_state)

    if not ok:
        return False

    # Cache update: when filtering flags are present, or there are
    # multiple files (no reliable per-file content boundaries), re-read
    # each file directly from disk so the cache stays accurate.
    if shim.rtk_filtered or len(shim.files) > 1:
        for f in shim.files:
            full = f if os.path.isabs(f) else os.path.join(root, f)
            renderer.context.cache.reread(full)
    return True


# ---------------------------------------------------------------------------
# Interceptor class
# ---------------------------------------------------------------------------

class RtkReadInterceptor:
    """Interceptor that re-routes rtk read / cat / head / tail bash
    commands through the ReadRenderer."""

    name = "rtk_read"

    def try_render(
        self,
        command: str,
        state: dict[str, Any],
        renderer: ToolRenderer,
    ) -> bool:
        if not renderer.context.settings.bash_shim_render:
            return False

        inp = state.get("input")
        if not isinstance(inp, dict):
            return False

        command_str = str(inp.get("command", ""))
        shim = _is_bash_shim_call(command_str)
        if shim is None:
            return False

        output = state.get("output")
        if not isinstance(output, str):
            return False

        if shim.family != "read":
            return False

        return _render_shim_read(renderer, state, shim)
