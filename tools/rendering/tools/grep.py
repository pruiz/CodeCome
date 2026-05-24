# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
GrepRenderer — match-highlighted panel for grep tool output.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from rendering.tools.base import ToolRenderer
from rendering.utils import is_likely_error, relativize_path

_GREP_LINE_RE = re.compile(r"^(?P<path>.+?):(?P<line>\d+):(?P<text>.*)$")

_GREP_HIGHLIGHT_STYLE = "bold yellow on grey23"
_GREP_BODY_STYLE = "default"
_GREP_LINENO_STYLE = "dim cyan"


def _grep_compile_pattern(pattern: str) -> re.Pattern[str] | None:
    if not pattern:
        return None
    try:
        return re.compile(pattern)
    except re.error:
        try:
            return re.compile(re.escape(pattern))
        except re.error:
            return None


def _grep_format_line_rich(line_no: int, text: str, pat: re.Pattern[str] | None, highlight: bool) -> Any:
    from rich.text import Text
    t = Text()
    t.append(f"    {line_no:>5}", style=_GREP_LINENO_STYLE)
    t.append(": ", style="dim")

    if pat is None or not highlight:
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
    return t


def _grep_format_line_plain(line_no: int, text: str, pat: re.Pattern[str] | None,
                            highlight: bool, color: bool) -> str:
    prefix = f"    {line_no:>5}: "
    if pat is None or not highlight:
        return prefix + text

    if color:
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
    raw_lines = [l for l in output.strip().split("\n") if l.strip()]
    if not raw_lines:
        return "files", []

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
                entries.append({"path": l.strip(), "line": 0, "text": ""})
        return "lines", entries
    else:
        return "files", [{"path": l.strip()} for l in raw_lines]


class GrepRenderer(ToolRenderer):
    tool_names = ("grep",)

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
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

        if self.rich:
            return self._render_rich(inp, output_str, status)
        else:
            return self._render_plain(inp, output_str, status)

    def _render_rich(self, inp: dict[str, Any], output_str: str, status: str) -> bool:
        from rich.console import Group
        from rich.panel import Panel
        from rich.text import Text

        settings = self.context.settings
        pattern = str(inp.get("pattern", ""))
        search_path = str(inp.get("path", ""))
        include = str(inp.get("include", ""))

        is_err = is_likely_error(output_str)
        border = "red" if is_err else ("green" if status == "completed" else "yellow")

        sections: list[Any] = []
        header_parts = [f"pattern={pattern!r}"]
        if search_path:
            header_parts.append(f"path={relativize_path(search_path, self.context.root)}")
        if include:
            header_parts.append(f"include={include}")
        sections.append(Text("  ".join(header_parts), style="dim"))
        sections.append(Text())

        if is_err:
            sections.append(Text(output_str.strip(), style="red"))
        elif not output_str.strip():
            sections.append(Text("(no matches)", style="dim"))
            border = "dim"
        else:
            mode, entries = _parse_grep_output(output_str)

            if mode == "files":
                n_files = len(entries)
                shown = entries[:settings.grep_file_cap]
                for e in shown:
                    sections.append(Text(f"  {relativize_path(e['path'], self.context.root)}"))
                if n_files > settings.grep_file_cap:
                    sections.append(Text(f"  ... and {n_files - settings.grep_file_cap} more", style="dim"))
                sections.append(Text())
                sections.append(Text(f"{n_files} file(s) matched", style="dim"))
            else:
                grep_pat = _grep_compile_pattern(pattern)
                grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
                for e in entries:
                    grouped.setdefault(e["path"], []).append(e)

                n_files = len(grouped)
                n_total = len(entries)
                total_emitted = 0
                files_shown = 0
                truncated = False

                for fpath, file_entries in grouped.items():
                    if total_emitted >= settings.grep_total_line_cap or files_shown >= settings.grep_file_cap:
                        truncated = True
                        break
                    files_shown += 1
                    rel = relativize_path(fpath, self.context.root)
                    sections.append(Text(f"  {rel}  ({len(file_entries)} match(es))", style="bold cyan"))
                    shown_lines = file_entries[:settings.grep_line_cap_per_file]
                    for e in shown_lines:
                        text = e["text"]
                        if len(text) > 200:
                            text = text[:200] + "\u2026"
                        sections.append(_grep_format_line_rich(e["line"], text, grep_pat, settings.grep_highlight))
                        total_emitted += 1
                        if total_emitted >= settings.grep_total_line_cap:
                            truncated = True
                            break
                    if len(file_entries) > settings.grep_line_cap_per_file:
                        remaining = len(file_entries) - settings.grep_line_cap_per_file
                        sections.append(Text(f"    ... and {remaining} more in {rel}", style="dim"))

                if truncated:
                    remaining_files = n_files - files_shown
                    if remaining_files > 0:
                        sections.append(Text(f"  ... and {remaining_files} more file(s)", style="dim"))
                    else:
                        sections.append(Text("  ... (further matches truncated)", style="dim"))

                sections.append(Text())
                sections.append(Text(f"{n_total} match(es) across {n_files} file(s)", style="dim"))

        self.sink.write(Panel(Group(*sections), title="Grep", border_style=border, expand=True))
        return True

    def _render_plain(self, inp: dict[str, Any], output_str: str, status: str) -> bool:
        import _colors as C

        settings = self.context.settings
        pattern = str(inp.get("pattern", ""))
        search_path = str(inp.get("path", ""))
        include = str(inp.get("include", ""))

        is_err = is_likely_error(output_str)

        header_parts = [f"grep {pattern!r}"]
        if search_path:
            header_parts.append(f"in {relativize_path(search_path, self.context.root)}")
        if include:
            header_parts.append(f"include={include}")
        self.sink.write_text(C.header(" ".join(header_parts)))

        if is_err:
            self.sink.write_text(C.fail(output_str.strip()))
        elif not output_str.strip():
            self.sink.write_text("  (no matches)")
        else:
            mode, entries = _parse_grep_output(output_str)

            if mode == "files":
                n_files = len(entries)
                shown = entries[:settings.grep_file_cap]
                for e in shown:
                    self.sink.write_text(f"  {relativize_path(e['path'], self.context.root)}")
                if n_files > settings.grep_file_cap:
                    self.sink.write_text(f"  ... and {n_files - settings.grep_file_cap} more")
                self.sink.write_text(f"  {n_files} file(s) matched")
            else:
                grep_pat = _grep_compile_pattern(pattern)
                plain_color = C.color_enabled()
                grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
                for e in entries:
                    grouped.setdefault(e["path"], []).append(e)

                n_files = len(grouped)
                n_total = len(entries)
                total_emitted = 0
                files_shown = 0
                truncated = False

                for fpath, file_entries in grouped.items():
                    if total_emitted >= settings.grep_total_line_cap or files_shown >= settings.grep_file_cap:
                        truncated = True
                        break
                    files_shown += 1
                    rel = relativize_path(fpath, self.context.root)
                    self.sink.write_text(f"  {rel}  ({len(file_entries)} match(es))")
                    shown_lines = file_entries[:settings.grep_line_cap_per_file]
                    for e in shown_lines:
                        text = e["text"]
                        if len(text) > 200:
                            text = text[:200] + "\u2026"
                        self.sink.write_text(_grep_format_line_plain(e["line"], text, grep_pat, settings.grep_highlight, plain_color))
                        total_emitted += 1
                        if total_emitted >= settings.grep_total_line_cap:
                            truncated = True
                            break
                    if len(file_entries) > settings.grep_line_cap_per_file:
                        remaining = len(file_entries) - settings.grep_line_cap_per_file
                        self.sink.write_text(f"    ... and {remaining} more in {rel}")

                if truncated:
                    remaining_files = n_files - files_shown
                    if remaining_files > 0:
                        self.sink.write_text(f"  ... and {remaining_files} more file(s)")
                    else:
                        self.sink.write_text("  ... (further matches truncated)")

                self.sink.write_text(f"  {n_total} match(es) across {n_files} file(s)")
        return True
