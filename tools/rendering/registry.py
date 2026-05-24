# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
RendererRegistry — dispatches events to event/tool renderers.

Matches each event by type, then delegates to the first registered
renderer that declares a matching ``event_types`` or ``tool_names``.
"""

from __future__ import annotations

from typing import Any

from rendering.context import RenderContext
from rendering.events import EventRenderer, UnknownEventRenderer
from rendering.tools.base import FallbackToolRenderer, ToolRenderer


class RendererRegistry:
    """Dispatch events and tool calls to registered renderers.

    Registration order matters: the first matching renderer wins.
    The fallback renderers are registered last and catch anything
    that no specific renderer handled.
    """

    def __init__(self, context: RenderContext) -> None:
        self.context = context
        self._event_renderers: list[EventRenderer] = []
        self._tool_renderers: list[ToolRenderer] = []

        # Register fallbacks last (lowest priority).
        self._unknown = UnknownEventRenderer(context)
        self._fallback_tool = FallbackToolRenderer(context)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_event(self, renderer: EventRenderer) -> None:
        self._event_renderers.append(renderer)

    def register_tool(self, renderer: ToolRenderer) -> None:
        self._tool_renderers.append(renderer)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch_event(self, event: dict[str, Any]) -> None:
        """Render a generic event through the matching renderer."""
        event_type = event.get("type", "")
        for renderer in self._event_renderers:
            if not renderer.event_types or event_type in renderer.event_types:
                if renderer.render(event):
                    return
        self._unknown.render(event)

    def dispatch_tool(self, tool_name: str, state: dict[str, Any]) -> None:
        """Render a tool call through the matching renderer."""
        tool_lower = tool_name.strip().lower()
        for renderer in self._tool_renderers:
            if not renderer.tool_names or tool_lower in renderer.tool_names:
                if renderer.render(tool_name, state):
                    return
        self._fallback_tool.render(tool_name, state)
