# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""ToolUseEventRenderer — dispatches tool_use events to specific tool renderers."""

from __future__ import annotations

from typing import Any

from rendering.events.base import EventRenderer


class ToolUseEventRenderer(EventRenderer):
    event_types = ("tool_use",)

    # Map of canonical tool names to their renderer classes (lazy-imported).
    # Keys that map to the same renderer share the cached instance.
    _TOOL_RENDERER_CLASSES: dict[str, str] = {
        "todowrite": "rendering.tools.todo.TodoRenderer",
        "read": "rendering.tools.read.ReadRenderer",
        "write": "rendering.tools.write.WriteRenderer",
        "edit": "rendering.tools.edit.EditRenderer",
        "apply_patch": "rendering.tools.apply_patch.ApplyPatchRenderer",
        "applypatch": "rendering.tools.apply_patch.ApplyPatchRenderer",
        "apply-patch": "rendering.tools.apply_patch.ApplyPatchRenderer",
        "glob": "rendering.tools.glob.GlobRenderer",
        "grep": "rendering.tools.grep.GrepRenderer",
        "bash": "rendering.tools.command.CommandRenderer",
        "skill": "rendering.tools.skill.SkillRenderer",
        "task": "rendering.tools.task.TaskRenderer",
    }

    def __init__(self, context):
        super().__init__(context)
        from rendering.tools.base import FallbackToolRenderer
        self._fallback = FallbackToolRenderer(context)
        # Cache renderer instances keyed by their fully-qualified class path.
        self._renderer_cache: dict[str, Any] = {}

    def _get_renderer(self, tool_lower: str) -> Any | None:
        """Return a cached renderer for *tool_lower*, or None for fallback."""
        class_path = self._TOOL_RENDERER_CLASSES.get(tool_lower)
        if class_path is None:
            return None
        if class_path in self._renderer_cache:
            return self._renderer_cache[class_path]
        # Lazy-import and instantiate once, then cache.
        module_path, class_name = class_path.rsplit(".", 1)
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        instance = cls(self.context)
        self._renderer_cache[class_path] = instance
        return instance

    def render(self, event: dict[str, Any]) -> bool:
        part = event.get("part", {})
        tool = str(part.get("tool", "unknown"))
        state = part.get("state", {}) if isinstance(part.get("state"), dict) else {}
        tool_lower = tool.strip().lower()

        renderer = self._get_renderer(tool_lower)
        if renderer is not None and renderer.render(tool, state):
            return True

        return self._fallback.render(tool, state)
