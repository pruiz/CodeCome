# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
RtkGrepInterceptor — re-routes rtk grep / rg / grep bash commands
through the GrepRenderer so the user sees a Grep panel instead of
a generic Bash panel.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rendering.tools.base import ToolRenderer
from rendering.tools.interceptors.base import CommandExecutionInterceptor

# ---------------------------------------------------------------------------
# Regexes for rtk grep output normalisation
# ---------------------------------------------------------------------------

_RTK_GREP_FILE_HEADER_RE = re.compile(r"^\[file\]\s+(?P<path>.+?)\s+\((?P<count>\d+)\)\s*:\s*$")
_RTK_GREP_LINE_RE = re.compile(r"^\s+(?P<lineno>\d+):\s*(?P<text>.*)$")


# ---------------------------------------------------------------------------
# rtk grep output normaliser
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Grep parsers (called by _is_bash_shim_call in rtk_read)
# ---------------------------------------------------------------------------

def _parse_grep_or_rg(rest: list[str], raw: str) -> Optional[Any]:
    """Parse `rg PATTERN [PATH]` or `grep PATTERN PATH...` (best-effort)."""
    from .rtk_read import _BashShim  # noqa: E402

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


def _parse_rtk_grep(rest: list[str], raw: str) -> Optional[Any]:
    """Parse `rtk grep PATTERN [PATH] [extra args]`."""
    from .rtk_read import _BashShim  # noqa: E402

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


# ---------------------------------------------------------------------------
# Grep shim renderer
# ---------------------------------------------------------------------------

def _render_shim_grep(renderer: ToolRenderer, state: dict[str, Any], shim: Any) -> bool:
    """Normalize rtk grep output and delegate to GrepRenderer."""
    from .rtk_read import _BashShim  # noqa: E402
    from rendering.tools.grep import GrepRenderer

    shim_cast: _BashShim = shim

    raw_output = str(state.get("output") or "")
    normalized = _normalize_rtk_grep_output(raw_output)

    # If the normalizer found rtk-style markers but produced no rows,
    # something is unexpected; fall back to bash renderer.
    if "[file]" in raw_output and not normalized.strip():
        return False

    syn_state = {
        "input": {"pattern": shim_cast.pattern, "path": shim_cast.path},
        "output": normalized,
        "status": str(state.get("status", "")),
    }

    grep_renderer = GrepRenderer(renderer.context)
    return grep_renderer.render("grep", syn_state)


# ---------------------------------------------------------------------------
# Interceptor class
# ---------------------------------------------------------------------------

class RtkGrepInterceptor:
    """Interceptor that re-routes rtk grep / rg / grep bash commands
    through the GrepRenderer."""

    name = "rtk_grep"

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

        from .rtk_read import _is_bash_shim_call  # noqa: E402
        shim = _is_bash_shim_call(command)
        if shim is None:
            return False

        output = state.get("output")
        if not isinstance(output, str):
            return False

        if shim.family != "grep":
            return False

        return _render_shim_grep(renderer, state, shim)
