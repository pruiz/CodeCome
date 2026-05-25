# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Rendering infrastructure shared by the CLI entry point: Rich detection,
console construction, rendering context cache, and the event dispatcher.

This module is intentionally free of execution logic (no server, no
session, no phase loop).
"""

from __future__ import annotations

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
# Console builder
# ---------------------------------------------------------------------------

def build_console(color_mode: str) -> Console:
    if not HAVE_RICH:
        return None  # type: ignore[return-value]
    if color_mode == "always":
        return Console(force_terminal=True, highlight=False)
    if color_mode == "never":
        return Console(force_terminal=False, no_color=True, highlight=False)
    return Console(highlight=False)


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


# ---------------------------------------------------------------------------
# Fatal error display
# ---------------------------------------------------------------------------

def _emit_fatal_error(console: Any, title: str, message: str) -> None:
    import _colors as C
    formatted = C.fail(f"{title}: {message}")
    if HAVE_RICH:
        console.print(Panel(Text(message, style="red"), title=title, border_style="red"))
    print(formatted, file=__import__("sys").stderr)


# ---------------------------------------------------------------------------
# LLM finish reason classification (canonical definitions in rendering.events)
# ---------------------------------------------------------------------------

from rendering.events import (
    _FINISH_TERMINAL_OK,
    _FINISH_MID_TURN,
    _FINISH_FAILURE,
)