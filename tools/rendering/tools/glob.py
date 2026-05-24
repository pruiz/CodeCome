# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
GlobRenderer — file listing panel for glob tool output.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from rendering.tools.base import ToolRenderer
from rendering.utils import relativize_path

_GLOB_SUMMARY_LINE_RE = re.compile(
    r"^\d+\s+(?:for\s|match)"
    r"|^No\s+matches?\s"
    r"|^\d+\s+file"
)


def _parse_glob_output(output: str) -> tuple[list[str], list[str]]:
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


class GlobRenderer(ToolRenderer):
    tool_names = ("glob",)

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        inp = state.get("input")
        output = state.get("output")
        if not isinstance(inp, dict) or not isinstance(output, str):
            return False

        pattern = str(inp.get("pattern", ""))
        search_path = str(inp.get("path", ""))
        matches, summaries = _parse_glob_output(output)
        if self.rich:
            return self._render_rich(pattern, search_path, matches, summaries)
        else:
            return self._render_plain(pattern, search_path, matches, summaries)

    def _render_rich(self, pattern: str, search_path: str,
                     matches: list[str], summaries: list[str]) -> bool:
        from rich.console import Group
        from rich.panel import Panel
        from rich.text import Text

        settings = self.context.settings
        n_matches = len(matches)
        border = "green" if n_matches > 0 else "dim"

        sections: list[Any] = [
            Text(f"pattern={pattern}  path={relativize_path(search_path, self.context.root) if search_path else '.'}", style="dim"),
            Text(),
        ]

        if n_matches == 0:
            if summaries:
                for s in summaries:
                    sections.append(Text(f"  {s}", style="dim"))
            else:
                sections.append(Text("(no matches)", style="dim"))
        else:
            shown = matches[:settings.glob_match_cap]
            for m in shown:
                try:
                    rel = str(Path(m).relative_to(search_path)) if search_path else m
                except ValueError:
                    rel = relativize_path(m, self.context.root)
                sections.append(Text(f"  {rel}"))
            if n_matches > settings.glob_match_cap:
                sections.append(Text(f"  ... and {n_matches - settings.glob_match_cap} more", style="dim"))

        sections.append(Text())
        sections.append(Text(f"{n_matches} match(es)", style="dim"))

        self.sink.write(Panel(Group(*sections), title="Glob", border_style=border, expand=True))
        return True

    def _render_plain(self, pattern: str, search_path: str,
                      matches: list[str], summaries: list[str]) -> bool:
        import _colors as C

        settings = self.context.settings
        n_matches = len(matches)

        self.sink.write_text(C.header(f"glob {pattern} in {relativize_path(search_path, self.context.root) if search_path else '.'}"))

        if n_matches == 0:
            if summaries:
                for s in summaries:
                    self.sink.write_text(f"  {s}")
            else:
                self.sink.write_text("  (no matches)")
        else:
            shown = matches[:settings.glob_match_cap]
            for m in shown:
                try:
                    rel = str(Path(m).relative_to(search_path)) if search_path else m
                except ValueError:
                    rel = relativize_path(m, self.context.root)
                self.sink.write_text(f"  {rel}")
            if n_matches > settings.glob_match_cap:
                self.sink.write_text(f"  ... and {n_matches - settings.glob_match_cap} more")

        self.sink.write_text(f"  {n_matches} match(es)")
        return True
