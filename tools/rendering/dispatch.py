# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Rendering dispatch: Rich availability detection, rendering context
construction, and the ``render_event()`` event dispatcher.

This module is the composition root for rendering — it wires specific
event renderers into a ``RenderContext`` and provides the single
``render_event()`` entry point used by both phase and chat paths.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Rich availability
# ---------------------------------------------------------------------------

try:
    from rich.console import Console, Group
    from rich.json import JSON
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.text import Text

    HAVE_RICH = True
except ImportError:  # pragma: no cover
    Console = Any  # type: ignore[assignment]
    Group = tuple  # type: ignore[assignment]
    JSON = None  # type: ignore[assignment]
    Markdown = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Rule = None  # type: ignore[assignment]
    Text = None  # type: ignore[assignment]
    HAVE_RICH = False


# ---------------------------------------------------------------------------
# Rendering context cache
# ---------------------------------------------------------------------------

_RENDERING_CTX_CACHE: dict[str, Any] = {}


def _make_sink(console: Any) -> Any:
    from rendering.sink import PlainSink, RichConsoleSink

    if HAVE_RICH and console is not None:
        return RichConsoleSink(console)
    return PlainSink()


def _get_rendering_ctx(console: Any, *, root: Path | None = None) -> Any:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    mode = "rich" if (HAVE_RICH and console is not None) else "plain"
    if mode in _RENDERING_CTX_CACHE:
        ctx = _RENDERING_CTX_CACHE[mode]
        ctx.cache.invalidate_stale()
        return ctx
    from rendering.cache import SnapshotCache
    from rendering.context import RenderContext
    from rendering.settings import RenderSettings
    sink = _make_sink(console)
    ctx = RenderContext(
        root=root,
        sink=sink,
        settings=RenderSettings.from_env(),
        cache=SnapshotCache(),
    )
    from rendering.registry import RendererRegistry
    registry = RendererRegistry(ctx)

    from rendering.events import (
        ServerConnectedRenderer,
        ServerHeartbeatRenderer,
        MessageUpdatedRenderer,
        TextEventRenderer,
        ReasoningEventRenderer,
        ToolUseEventRenderer,
        StepStartRenderer,
        StepFinishRenderer,
        ErrorEventRenderer,
        SessionStatusRenderer,
        SessionDiffRenderer,
        SubagentStatusRenderer,
        PatchRenderer,
    )
    registry.register_event(ServerConnectedRenderer(ctx))
    registry.register_event(ServerHeartbeatRenderer(ctx))
    registry.register_event(MessageUpdatedRenderer(ctx))
    registry.register_event(TextEventRenderer(ctx))
    registry.register_event(ReasoningEventRenderer(ctx))
    registry.register_event(ToolUseEventRenderer(ctx))
    registry.register_event(StepStartRenderer(ctx))
    registry.register_event(StepFinishRenderer(ctx))
    registry.register_event(ErrorEventRenderer(ctx))
    registry.register_event(SessionStatusRenderer(ctx))
    registry.register_event(SessionDiffRenderer(ctx))
    registry.register_event(SubagentStatusRenderer(ctx))
    registry.register_event(PatchRenderer(ctx))

    from rendering.tools import (
        ApplyPatchRenderer,
        CommandRenderer,
        EditRenderer,
        GlobRenderer,
        GrepRenderer,
        ReadRenderer,
        SkillRenderer,
        TaskRenderer,
        TodoRenderer,
        WebRenderer,
        WriteRenderer,
    )
    registry.register_tool(ReadRenderer(ctx))
    registry.register_tool(WriteRenderer(ctx))
    registry.register_tool(EditRenderer(ctx))
    registry.register_tool(GlobRenderer(ctx))
    registry.register_tool(GrepRenderer(ctx))
    registry.register_tool(TodoRenderer(ctx))
    registry.register_tool(TaskRenderer(ctx))
    registry.register_tool(SkillRenderer(ctx))
    registry.register_tool(CommandRenderer(ctx))
    registry.register_tool(ApplyPatchRenderer(ctx))
    registry.register_tool(WebRenderer(ctx))

    ctx.registry = registry
    _RENDERING_CTX_CACHE[mode] = ctx
    return ctx


def reset_rendering_context_cache() -> None:
    _RENDERING_CTX_CACHE.clear()


def configure_rendering(console: Any, **settings_overrides) -> Any:
    """Apply runtime overrides to the shared rendering context.

    Call this after resolve_runtime_config() has resolved thinking_on,
    so the decision can flow into RenderSettings before events are rendered.
    """
    ctx = _get_rendering_ctx(console)
    if settings_overrides:
        ctx.settings = dataclasses.replace(ctx.settings, **settings_overrides)
    return ctx


def reconfigure_rendering(console: Any, **settings_overrides) -> Any:
    """Rebind the cached rendering context to a new output sink.

    Chat mode creates its final Textual output proxy only after the app is
    mounted.  This updates the sink in-place without clearing caches or
    rebuilding the renderer registry.
    """
    ctx = _get_rendering_ctx(console)
    ctx.sink = _make_sink(console)
    if settings_overrides:
        ctx.settings = dataclasses.replace(ctx.settings, **settings_overrides)
    return ctx


# ---------------------------------------------------------------------------
# Event dispatcher
# ---------------------------------------------------------------------------

def render_event(console: Console, phase: str, label: str, event: dict[str, Any]) -> None:
    ctx = _get_rendering_ctx(console)
    ctx.phase = phase
    ctx.label = label
    ctx.registry.dispatch_event(event)
