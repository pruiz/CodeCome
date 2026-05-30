# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""ToolUseEventRenderer — dispatches tool_use events to specific tool renderers."""

from __future__ import annotations

import os
from typing import Any

from rendering.events.base import EventRenderer, _clear_hidden_reasoning_state


def _is_write_like(inp: dict[str, Any]) -> bool:
    """Return True if the tool input looks like a write or edit (has filePath + content/oldString)."""
    fp = inp.get("filePath", "")
    if not isinstance(fp, str) or not fp.strip():
        return False
    return "content" in inp or "oldString" in inp


def _normalize_path(path: str) -> str:
    """Normalize a file path for consistent set membership."""
    if not path:
        return path
    return os.path.normpath(os.path.abspath(path))


class ToolUseEventRenderer(EventRenderer):
    event_types = ("tool_use",)

    def render(self, event: dict[str, Any]) -> bool:
        part = event.get("part", {})
        tool = str(part.get("tool", "unknown"))
        state = part.get("state", {}) if isinstance(part.get("state"), dict) else {}
        inp = state.get("input", {}) if isinstance(state.get("input"), dict) else {}
        status = state.get("status", "")

        if _is_write_like(inp):
            file_path = _normalize_path(str(inp["filePath"]))
            if status == "running":
                self.context.inflight_write_files.add(file_path)
            elif status in ("completed", "error"):
                self.context.inflight_write_files.discard(file_path)

        _clear_hidden_reasoning_state(self.context)
        self.context.registry.dispatch_tool(tool, state)
        return True
