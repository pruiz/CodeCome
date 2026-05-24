# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
CommandRenderer — generic bash command display.

Interceptors for sandbox-bootstrap, rtk, rg, ls, find, tree are wired
separately (Phase A3 batch 6).
"""

from __future__ import annotations

from typing import Any

from rendering.tools.base import ToolRenderer
from rendering.utils import is_likely_error


class CommandRenderer(ToolRenderer):
    tool_names = ("bash",)

    def __init__(self, context):
        super().__init__(context)
        self._interceptors = None

    @property
    def interceptors(self):
        if self._interceptors is None:
            from rendering.tools.interceptors.sandbox_bootstrap import SandboxBootstrapInterceptor
            from rendering.tools.interceptors.rtk_read import RtkReadInterceptor
            from rendering.tools.interceptors.rtk_grep import RtkGrepInterceptor
            from rendering.tools.interceptors.shell_listing import ShellListingInterceptor
            self._interceptors = [
                SandboxBootstrapInterceptor(),
                RtkReadInterceptor(),
                RtkGrepInterceptor(),
                ShellListingInterceptor(),
            ]
        return self._interceptors

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        inp = state.get("input")
        if not isinstance(inp, dict):
            return False

        command = str(inp.get("command", ""))
        if not command:
            return False

        # Try interceptors first (sandbox-bootstrap, rtk, rg, ls, find, tree).
        for interceptor in self.interceptors:
            if interceptor.try_render(command, state, self):
                return True

        # Fall through to generic bash rendering.
        description = inp.get("description", "")
        output = state.get("output")
        output_str = str(output) if output is not None else ""

        if self.rich:
            return self._render_rich(command, str(description), output_str, state)
        else:
            return self._render_plain(command, str(description), output_str, state)

    def _render_rich(self, command: str, description: str, output_str: str, state: dict[str, Any]) -> bool:
        from rich.console import Group
        from rich.panel import Panel
        from rich.text import Text

        err = is_likely_error(output_str)
        border = "red" if err else ("green" if state.get("status") == "completed" else "yellow")

        sections: list[Any] = [Text(f"$ {command}", style="bold cyan")]
        if description:
            sections.append(Text(description, style="dim italic"))

        sections.append(Text())

        if output_str.strip():
            sections.append(Text("Output", style="bold green"))
            sections.append(Text(output_str.strip()))
        else:
            sections.append(Text("(no output)", style="dim"))

        self.sink.write(Panel(Group(*sections), title="Bash", border_style=border, expand=True))
        return True

    def _render_plain(self, command: str, description: str, output_str: str, state: dict[str, Any]) -> bool:
        import _colors as C

        self.sink.write_text(C.header(f"bash $ {command}"))
        if description:
            self.sink.write_text(f"  # {description}")

        if output_str.strip():
            self.sink.write_text(output_str.strip())
        else:
            self.sink.write_text("  (no output)")
        return True
