# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""ToolUseEventRenderer — dispatches tool_use events to specific tool renderers."""

from __future__ import annotations

from typing import Any

from rendering.events.base import EventRenderer, _clear_hidden_reasoning_state


class ToolUseEventRenderer(EventRenderer):
    event_types = ("tool_use",)

    def render(self, event: dict[str, Any]) -> bool:
        part = event.get("part", {})
        tool = str(part.get("tool", "unknown"))
        state = part.get("state", {}) if isinstance(part.get("state"), dict) else {}
        _clear_hidden_reasoning_state(self.context)
        self.context.registry.dispatch_tool(tool, state)
        return True
