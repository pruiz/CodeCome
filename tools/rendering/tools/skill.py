# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
SkillRenderer — compact panel for skill-loading tool calls.
"""

from __future__ import annotations

from typing import Any

from rendering.tools.base import ToolRenderer


class SkillRenderer(ToolRenderer):
    tool_names = ("skill",)

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        inp = state.get("input")
        if not isinstance(inp, dict):
            return False

        name = str(inp.get("name", ""))

        if self.rich:
            return self._render_rich(name)
        else:
            return self._render_plain(name)

    def _render_rich(self, name: str) -> bool:
        from rich.panel import Panel
        from rich.text import Text

        if not name:
            label = "(unknown skill)"
            style = "dim"
        else:
            label = f"loaded skill: {name}"
            style = ""

        self.sink.write(Panel(Text(label, style=style), title="Skill", border_style="dim", expand=True))
        return True

    def _render_plain(self, name: str) -> bool:
        import _colors as C

        if not name:
            self.sink.write_text(C.header("skill (unknown)"))
        else:
            self.sink.write_text(C.header(f"skill {name}"))
        return True
