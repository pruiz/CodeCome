# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
WriteRenderer — diff-aware panel for write tool output.
"""

from __future__ import annotations

from typing import Any

from rendering.tools.base import ToolRenderer
from rendering.utils import (
    compute_diff, count_lines_and_bytes, detect_lexer,
    relativize_path, truncate_diff,
)


class WriteRenderer(ToolRenderer):
    tool_names = ("write",)

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        inp = state.get("input")
        output = state.get("output")
        if not isinstance(inp, dict):
            return False

        file_path = str(inp.get("filePath", ""))
        new_content = str(inp.get("content", ""))
        output_str = str(output) if output is not None else ""

        if not file_path:
            return False

        if self.rich:
            return self._render_rich(file_path, new_content, output_str, output, state)
        else:
            return self._render_plain(file_path, new_content, output_str, output, state)

    # ------------------------------------------------------------------
    # Rich
    # ------------------------------------------------------------------

    def _render_rich(self, file_path: str, new_content: str, output_str: str, output, state) -> bool:
        from rich.console import Group
        from rich.panel import Panel
        from rich.syntax import Syntax
        from rich.text import Text

        settings = self.context.settings
        cache = self.context.cache
        rel_path = relativize_path(file_path, self.context.root)
        n_lines, n_bytes = count_lines_and_bytes(new_content)
        is_error = output is not None and not output_str.startswith("Wrote file")
        border = "red" if is_error else "green"

        sections: list[Any] = [
            Text(rel_path, style="bold cyan"),
            Text(f"{n_lines} lines, {n_bytes} bytes", style="dim"),
        ]

        if is_error:
            sections.append(Text())
            sections.append(Text(output_str.strip(), style="red"))
            self.sink.write(Panel(Group(*sections), title="Write", border_style=border, expand=True))
            return True

        prev = cache.get(file_path)
        lexer = detect_lexer(file_path)
        status_text = output_str.strip()

        if prev is not None:
            diff_lines = compute_diff(prev, new_content)
            if not diff_lines:
                sections.append(Text("(no changes)", style="dim"))
            else:
                added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
                removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
                sections.append(Text(f"diff: -{removed} +{added}", style="dim"))
                sections.append(Text())
                truncated, leftover = truncate_diff(diff_lines, settings.write_diff_limit)
                diff_text = "".join(truncated)
                sections.append(Syntax(diff_text, "diff", theme="monokai", word_wrap=True))
                if leftover > 0:
                    sections.append(Text(f"... {leftover} more lines", style="dim"))
        else:
            sections.append(Text("(new file)", style="dim"))
            sections.append(Text())
            self._render_body_rich(sections, new_content, settings.write_content_lines, lexer, settings.write_highlight_limit)

        sections.append(Text())
        sections.append(Text(status_text, style="green"))
        self.sink.write(Panel(Group(*sections), title="Write", border_style=border, expand=True))
        if state.get("status") == "completed" and not is_error:
            cache.set(file_path, new_content)
        return True

    def _render_body_rich(self, sections: list[Any], body: str, cap: int, lexer: str, highlight_limit: int) -> None:
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

    # ------------------------------------------------------------------
    # Plain
    # ------------------------------------------------------------------

    def _render_plain(self, file_path: str, new_content: str, output_str: str, output, state) -> bool:
        import _colors as C

        settings = self.context.settings
        cache = self.context.cache
        rel_path = relativize_path(file_path, self.context.root)
        n_lines, n_bytes = count_lines_and_bytes(new_content)

        self.sink.write_text(C.header(f"write {rel_path}"))
        self.sink.write_text(f"  {n_lines} lines, {n_bytes} bytes")

        is_error = output is not None and not output_str.startswith("Wrote file")
        if is_error:
            self.sink.write_text(C.fail(output_str.strip()))
            return True

        prev = cache.get(file_path)
        if prev is not None:
            diff_lines = compute_diff(prev, new_content)
            if not diff_lines:
                self.sink.write_text("  (no changes)")
            else:
                added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
                removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
                self.sink.write_text(f"  diff: -{removed} +{added}")
                truncated, leftover = truncate_diff(diff_lines, settings.write_diff_limit)
                for line in truncated:
                    self.sink.write_text(f"  {line}", end="")
                if leftover > 0:
                    self.sink.write_text(f"  ... {leftover} more lines")
        else:
            self.sink.write_text("  (new file)")
            self._render_body_plain(new_content, settings.write_content_lines)

        self.sink.write_text(f"  {output_str.strip()}")
        if state.get("status") == "completed" and not is_error:
            cache.set(file_path, new_content)
        return True

    def _render_body_plain(self, body: str, cap: int) -> None:
        body_lines = body.split("\n")
        total = len(body_lines)
        for line in body_lines[:cap]:
            self.sink.write_text(line)
        leftover = max(0, total - cap)
        if leftover > 0:
            self.sink.write_text(f"  ... {leftover} more lines")
