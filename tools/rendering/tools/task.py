# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
TaskRenderer — preview panel for task (subagent) tool calls.
"""

from __future__ import annotations

from typing import Any

from rendering.tools.base import ToolRenderer


class TaskRenderer(ToolRenderer):
    tool_names = ("task",)

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        inp = state.get("input")
        if not isinstance(inp, dict):
            return False

        description = str(inp.get("description", ""))
        subagent_type = str(inp.get("subagent_type", inp.get("subagentType", "")))
        prompt = str(inp.get("prompt", ""))
        status = str(state.get("status", "unknown"))
        cap = self.context.settings.task_prompt_preview_lines

        if self.rich:
            return self._render_rich(description, subagent_type, prompt, status, cap, state)
        else:
            return self._render_plain(description, subagent_type, prompt, status, cap, state)

    def _render_rich(self, description: str, subagent_type: str, prompt: str,
                     status: str, cap: int, state: dict[str, Any]) -> bool:
        from rich.console import Group
        from rich.panel import Panel
        from rich.text import Text

        border = "green" if status == "completed" else "yellow"

        sections: list[Any] = []
        if description:
            type_tag = f"  [{subagent_type}]" if subagent_type else ""
            sections.append(Text(f"{description}{type_tag}", style="bold cyan"))

        if prompt:
            sections.append(Text())
            prompt_lines = prompt.split("\n")
            preview_lines = prompt_lines[:cap]
            leftover = max(0, len(prompt_lines) - cap)
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

        self.sink.write(
            Panel(Group(*sections), title=Text(f"Task [{status}]"), border_style=border, expand=True)
        )
        return True

    def _render_plain(self, description: str, subagent_type: str, prompt: str,
                      status: str, cap: int, state: dict[str, Any]) -> bool:
        import _colors as C

        type_tag = f" [{subagent_type}]" if subagent_type else ""
        self.sink.write_text(C.header(f"task {description}{type_tag} [{status}]"))

        if prompt:
            prompt_lines = prompt.split("\n")
            for line in prompt_lines[:cap]:
                self.sink.write_text(f"  {line}")
            leftover = max(0, len(prompt_lines) - cap)
            if leftover > 0:
                self.sink.write_text(f"  ... {leftover} more lines")

        output_data = state.get("output")
        if output_data is not None:
            self.sink.write_text(C.info("Output"))
            output_str = str(output_data)
            if len(output_str) > 200:
                output_str = output_str[:200] + "..."
            self.sink.write_text(f"  {output_str}")
        return True
