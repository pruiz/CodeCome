# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
EditRenderer — diff panel for edit tool (oldString → newString).
"""

from __future__ import annotations

from typing import Any

from rendering.tools.base import ToolRenderer
from rendering.utils import compute_diff, is_likely_error, relativize_path, truncate_diff


class EditRenderer(ToolRenderer):
    tool_names = ("edit",)

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
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

        if self.rich:
            return self._render_rich(file_path, str(old_string), str(new_string), replace_all, output, state)
        else:
            return self._render_plain(file_path, str(old_string), str(new_string), replace_all, output, state)

    # ------------------------------------------------------------------
    # Rich
    # ------------------------------------------------------------------

    def _render_rich(self, file_path: str, old_string: str, new_string: str,
                     replace_all: bool, output, state: dict[str, Any]) -> bool:
        from rich.console import Group
        from rich.panel import Panel
        from rich.syntax import Syntax
        from rich.text import Text

        settings = self.context.settings
        cache = self.context.cache
        rel_path = relativize_path(file_path, self.context.root)
        output_str = str(output) if output is not None else ""
        is_error = is_likely_error(output_str) or (
            output is not None
            and "successfully" not in output_str.lower()
            and "applied" not in output_str.lower()
        )
        border = "red" if is_error else "green"
        scope = "replace all" if replace_all else "replace 1 occurrence"

        sections: list[Any] = [
            Text(rel_path, style="bold cyan"),
            Text(scope, style="dim"),
            Text(),
        ]

        diff_lines = compute_diff(old_string, new_string)
        if not diff_lines:
            sections.append(Text("(no changes in edit)", style="dim"))
        else:
            added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
            sections.append(Text(f"diff: -{removed} +{added}", style="dim"))
            sections.append(Text())
            truncated, leftover = truncate_diff(diff_lines, settings.edit_diff_lines)
            diff_text = "".join(truncated)
            sections.append(Syntax(diff_text, "diff", theme="monokai", word_wrap=True))
            if leftover > 0:
                sections.append(Text(f"... {leftover} more lines", style="dim"))

        sections.append(Text())
        sections.append(Text(output_str.strip(), style="red" if is_error else "green"))

        self.sink.write(Panel(Group(*sections), title="Edit", border_style=border, expand=True))

        if state.get("status") == "completed" and not is_error:
            cache.reread(file_path)
        return True

    # ------------------------------------------------------------------
    # Plain
    # ------------------------------------------------------------------

    def _render_plain(self, file_path: str, old_string: str, new_string: str,
                      replace_all: bool, output, state: dict[str, Any]) -> bool:
        import _colors as C

        settings = self.context.settings
        cache = self.context.cache
        rel_path = relativize_path(file_path, self.context.root)
        output_str = str(output) if output is not None else ""
        scope = "replace all" if replace_all else "replace 1 occurrence"

        self.sink.write_text(C.header(f"edit {rel_path}"))
        self.sink.write_text(f"  {scope}")

        diff_lines = compute_diff(old_string, new_string)
        if not diff_lines:
            self.sink.write_text("  (no changes in edit)")
        else:
            added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))
            self.sink.write_text(f"  diff: -{removed} +{added}")
            truncated, leftover = truncate_diff(diff_lines, settings.edit_diff_lines)
            for line in truncated:
                self.sink.write_text(f"  {line}", end="")
            if leftover > 0:
                self.sink.write_text(f"  ... {leftover} more lines")

        self.sink.write_text(f"  {output_str.strip()}")

        if state.get("status") == "completed" and not is_likely_error(output_str):
            cache.reread(file_path)
        return True
