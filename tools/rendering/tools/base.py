# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Base class for tool-specific renderers.

Tool renderers receive a tool name and a tool state dict extracted from
a ``tool_use`` event.  Renderers are instantiated once with the shared
``RenderContext``.
"""

from __future__ import annotations

from typing import Any

from rendering.context import RenderContext


class ToolRenderer:
    """Base class for per-tool renderers.

    Subclasses declare which tool names they handle via ``tool_names``
    (e.g. ``("read",)``, ``("bash",)``, ``("write", "edit")``).
    """

    tool_names: tuple[str, ...] = ()

    def __init__(self, context: RenderContext) -> None:
        self.context = context

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        """Render a tool call.  Return True if handled, False to fall through."""
        raise NotImplementedError


class FallbackToolRenderer(ToolRenderer):
    """Fallback renderer for tools that have no specific renderer.

    Emits the raw tool state as JSON for Rich mode, or a simple header
    for plain mode.
    """

    tool_names = ()  # catches all unhandled tools

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        import json

        status = str(state.get("status", "unknown"))
        input_data = state.get("input")
        output_data = state.get("output")

        if self.context.sink.mode in ("rich", "textual"):
            from rich.console import Group
            from rich.json import JSON
            from rich.panel import Panel
            from rich.text import Text

            sections: list[Any] = []
            if input_data is not None:
                sections.append(Text("Input", style="bold cyan"))
                try:
                    sections.append(JSON.from_data(input_data))
                except Exception:
                    sections.append(Text(str(input_data)))
            if output_data is not None:
                if sections:
                    sections.append(Text())
                sections.append(Text("Output", style="bold green"))
                if isinstance(output_data, (dict, list)):
                    try:
                        sections.append(JSON.from_data(output_data))
                    except Exception:
                        sections.append(Text(str(output_data)))
                else:
                    sections.append(Text(str(output_data)))

            body = Group(*sections) if sections else Text("No tool payload", style="dim")
            title = f"Tool: {tool_name} [{status}]"
            border = "green" if status == "completed" else "yellow"
            self.context.sink.write(Panel(body, title=title, border_style=border, expand=True))
        else:
            import _colors as C
            print(C.header(f"Tool: {tool_name} [{status}]"))
            if input_data is not None:
                print(C.info("Input"))
                print(json.dumps(input_data, indent=2) if isinstance(input_data, (dict, list)) else str(input_data))
            if output_data is not None:
                print(C.info("Output"))
                print(json.dumps(output_data, indent=2) if isinstance(output_data, (dict, list)) else str(output_data))
        return True
