# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
ShellListingInterceptor — re-routes ls / find / tree bash commands
through the GlobRenderer so the user sees a Glob panel instead of
a generic Bash panel.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rendering.tools.base import ToolRenderer
from rendering.tools.command.interceptors.base import CommandExecutionInterceptor

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

_LS_LONG_FORMAT_RE = re.compile(
    # Permissions (10-12 chars incl. trailing @/+ or "."), link count,
    # user, group, size, then 2 or 3 date fields (Mon DD [YYYY|HH:MM]),
    # then the filename.
    r"^[\-dlbcps][rwxstST\-@\+\.]{9,11}"
    r"\s+\d+\s+\S+\s+\S+\s+\d+"
    r"\s+\S+\s+\S+(?:\s+\S+)?"
    r"\s+(?P<name>.+)$"
)


# ---------------------------------------------------------------------------
# ls long-format normaliser
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Parsers (called by _is_bash_shim_call in rtk_read)
# ---------------------------------------------------------------------------

def _parse_ls(rest: list[str], raw: str) -> Optional[Any]:
    """Parse `ls [args]`. Detect -l / -la for long format."""
    from .rtk_read import _BashShim  # noqa: E402

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


def _parse_find_tree(verb: str, rest: list[str], raw: str) -> Optional[Any]:
    """Parse `find PATH [args]` or `tree [PATH]`. Output is a list of paths.

    Extracts ``-name`` / ``-iname`` filters into *pattern* so the Glob
    panel header shows the actual search expression rather than the bare
    verb.
    """
    from .rtk_read import _BashShim  # noqa: E402

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


# ---------------------------------------------------------------------------
# ls / find shim renderer
# ---------------------------------------------------------------------------

def _render_shim_ls(renderer: ToolRenderer, state: dict[str, Any], shim: Any) -> bool:
    """Strip long-format if needed and delegate to GlobRenderer."""
    from .rtk_read import _BashShim  # noqa: E402
    from rendering.tools.glob import GlobRenderer

    shim_cast: _BashShim = shim
    settings = renderer.context.settings

    raw_output = str(state.get("output") or "")
    if shim_cast.long_format and settings.bash_shim_ls_strip_long_format:
        body = _strip_ls_long_format_to_filenames(raw_output)
    else:
        body = raw_output
    pattern_label = "ls" if shim_cast.family == "ls" else shim_cast.pattern
    syn_state = {
        "input": {"pattern": pattern_label, "path": shim_cast.path},
        "output": body,
        "status": str(state.get("status", "")),
    }

    glob_renderer = GlobRenderer(renderer.context)
    return glob_renderer.render("glob", syn_state)


# ---------------------------------------------------------------------------
# Interceptor class
# ---------------------------------------------------------------------------

class ShellListingInterceptor:
    """Interceptor that re-routes ls / find / tree bash commands
    through the GlobRenderer."""

    name = "shell_listing"

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

        if shim.family not in ("ls", "find"):
            return False

        return _render_shim_ls(renderer, state, shim)
