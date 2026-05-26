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
from typing import Any

from codecome.config import ROOT

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


def _get_rendering_ctx(console: Any) -> Any:
    mode = "rich" if (HAVE_RICH and console is not None) else "plain"
    if mode in _RENDERING_CTX_CACHE:
        ctx = _RENDERING_CTX_CACHE[mode]
        ctx.cache.invalidate_stale()
        return ctx
    from rendering.cache import SnapshotCache
    from rendering.context import RenderContext
    from rendering.settings import RenderSettings
    from rendering.sink import PlainSink, RichConsoleSink

    if mode == "rich":
        sink = RichConsoleSink(console)
    else:
        sink = PlainSink()
    ctx = RenderContext(
        root=ROOT,
        sink=sink,
        settings=RenderSettings.from_env(),
        cache=SnapshotCache(),
    )
    from rendering import events as _evts
    ctx._renderers = {
        "server.connected": _evts.ServerConnectedRenderer(ctx),
        "server.heartbeat": _evts.ServerHeartbeatRenderer(ctx),
        "message.updated": _evts.MessageUpdatedRenderer(ctx),
        "text": _evts.TextEventRenderer(ctx),
        "reasoning": _evts.ReasoningEventRenderer(ctx),
        "tool_use": _evts.ToolUseEventRenderer(ctx),
        "step_start": _evts.StepStartRenderer(ctx),
        "step_finish": _evts.StepFinishRenderer(ctx),
        "error": _evts.ErrorEventRenderer(ctx),
        "session.status": _evts.SessionStatusRenderer(ctx),
        "session.diff": _evts.SessionDiffRenderer(ctx),
        "subagent.status": _evts.SubagentStatusRenderer(ctx),
        "unknown": _evts.UnknownEventRenderer(ctx),
    }
    _RENDERING_CTX_CACHE[mode] = ctx
    return ctx


def configure_rendering(console: Any, **settings_overrides) -> Any:
    """Apply runtime overrides to the shared rendering context.

    Call this after resolve_runtime_config() has resolved thinking_on,
    so the decision can flow into RenderSettings before events are rendered.
    """
    ctx = _get_rendering_ctx(console)
    if settings_overrides:
        ctx.settings = dataclasses.replace(ctx.settings, **settings_overrides)
    return ctx


# ---------------------------------------------------------------------------
# Event dispatcher
# ---------------------------------------------------------------------------

def render_event(console: Console, phase: str, label: str, event: dict[str, Any]) -> None:
    event_type = event.get("type")
    ctx = _get_rendering_ctx(console)
    renderers = getattr(ctx, "_renderers", {})

    if event_type == "step_start":
        renderer = renderers.get("step_start")
        if renderer:
            renderer.phase = phase
            renderer.label = label
            renderer.render(event)
        else:
            from rendering.events import StepStartRenderer
            StepStartRenderer(ctx, phase=phase, label=label).render(event)
    elif event_type in renderers:
        renderers[event_type].render(event)
    else:
        unknown = renderers.get("unknown")
        if unknown is None:
            from rendering.events import UnknownEventRenderer
            unknown = UnknownEventRenderer(ctx)
        unknown.render(event)
