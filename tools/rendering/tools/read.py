# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
ReadRenderer — styled panel for read tool output.
"""

from __future__ import annotations

from typing import Any

from rendering.tools.base import ToolRenderer
from rendering.utils import (
    classify_internal_read, detect_lexer, is_likely_error,
    relativize_path, strip_line_numbers, strip_read_framing,
)


class ReadRenderer(ToolRenderer):
    tool_names = ("read",)

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        inp = state.get("input")
        output = state.get("output")
        if not isinstance(inp, dict) or not isinstance(output, str):
            return False

        file_path = str(inp.get("filePath", ""))
        if not file_path:
            return False

        rel_path = relativize_path(file_path, self.context.root)
        offset = inp.get("offset")
        limit = inp.get("limit")
        settings = self.context.settings
        cache = self.context.cache

        if self.rich:
            return self._render_rich(rel_path, file_path, output, offset, limit, state, settings, cache)
        else:
            return self._render_plain(rel_path, file_path, output, offset, limit, state, settings, cache)

    # ------------------------------------------------------------------
    # Rich
    # ------------------------------------------------------------------

    def _render_rich(self, rel_path: str, file_path: str, output: str,
                     offset, limit, state, settings, cache) -> bool:
        from rich.console import Group
        from rich.panel import Panel
        from rich.text import Text

        border = "green" if state.get("status") == "completed" else "yellow"
        sections: list[Any] = [Text(rel_path, style="bold cyan")]
        if offset is not None and limit is not None:
            sections.append(Text(f"lines {offset}..{offset + limit - 1}", style="dim"))

        kind, payload, footer = strip_read_framing(output)

        if kind == "unknown":
            if is_likely_error(output):
                sections.append(Text())
                sections.append(Text(output.strip(), style="red"))
                self.sink.write(Panel(Group(*sections), title="Read", border_style="red", expand=True))
            else:
                return False
            return True

        sections.append(Text())

        if kind == "file":
            body = str(payload).strip()
            raw_body = strip_line_numbers(body)
            cache.set(file_path, raw_body)

            if settings.internal_read_suppress:
                description = classify_internal_read(rel_path)
                if description is not None:
                    is_partial = offset is not None or limit is not None
                    if is_partial:
                        description = f"{description} (partial)"
                    suppressed: list[Any] = [Text(rel_path, style="bold cyan")]
                    suppressed.append(Text(description, style="dim italic"))
                    self.sink.write(Panel(Group(*suppressed), title="Read", border_style=border, expand=True))
                    return True

            if not body:
                sections.append(Text("(empty file)", style="dim"))
            else:
                lexer = detect_lexer(file_path)
                self._render_truncated_body(sections, raw_body, settings.read_display_lines, lexer, footer, settings.read_highlight_limit)

        elif kind == "directory":
            entries = payload if isinstance(payload, list) else []
            for entry in entries:
                if entry.endswith("/"):
                    sections.append(Text(f"  {entry}", style="bold blue"))
                else:
                    sections.append(Text(f"  {entry}"))
            if footer:
                sections.append(Text(footer, style="dim"))

        self.sink.write(Panel(Group(*sections), title="Read", border_style=border, expand=True))
        return True

    @staticmethod
    def _render_truncated_body(sections: list[Any], body: str, cap: int, lexer: str, footer: str | None,
                                highlight_limit: int = 200 * 1024) -> None:
        from rich.syntax import Syntax
        from rich.text import Text

        body_lines = body.split("\n")
        total = len(body_lines)
        visible_lines = body_lines[:cap]
        leftover = max(0, total - cap)

        visible = "\n".join(visible_lines)
        if len(visible.encode("utf-8", errors="replace")) > highlight_limit:
            sections.append(Text(visible))
        else:
            sections.append(Syntax(visible, lexer, theme="monokai", line_numbers=True, word_wrap=True))

        if leftover > 0:
            sections.append(Text(f"... {leftover} more lines", style="dim"))
        if footer:
            sections.append(Text(footer, style="dim"))

    # ------------------------------------------------------------------
    # Plain
    # ------------------------------------------------------------------

    def _render_plain(self, rel_path: str, file_path: str, output: str,
                      offset, limit, state, settings, cache) -> bool:
        import _colors as C

        kind, payload, footer = strip_read_framing(output)

        if kind == "file":
            body = str(payload).strip()
            raw_body = strip_line_numbers(body)
            cache.set(file_path, raw_body)

            if settings.internal_read_suppress:
                description = classify_internal_read(rel_path)
                if description is not None:
                    is_partial = offset is not None or limit is not None
                    suffix = " (partial)" if is_partial else ""
                    self.sink.write_text(C.header(f"read [{description}]{suffix}"))
                    return True

            self.sink.write_text(C.header(f"read {rel_path}"))
            if offset is not None and limit is not None:
                self.sink.write_text(f"  lines {offset}..{offset + limit - 1}")
            self._render_truncated_body_plain(raw_body, settings.read_display_lines, footer)
            return True

        self.sink.write_text(C.header(f"read {rel_path}"))
        if offset is not None and limit is not None:
            self.sink.write_text(f"  lines {offset}..{offset + limit - 1}")

        if kind == "directory":
            entries = payload if isinstance(payload, list) else []
            for entry in entries:
                self.sink.write_text(f"  {entry}")
            if footer:
                self.sink.write_text(f"  {footer}")
        else:
            self.sink.write_text(output.strip())

        return True

    def _render_truncated_body_plain(self, body: str, cap: int, footer: str | None) -> None:
        body_lines = body.split("\n")
        total = len(body_lines)
        for line in body_lines[:cap]:
            self.sink.write_text(line)
        leftover = max(0, total - cap)
        if leftover > 0:
            self.sink.write_text(f"  ... {leftover} more lines")
        if footer:
            self.sink.write_text(f"  {footer}")
