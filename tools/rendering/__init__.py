# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Rendering package: tool/event renderer classes, render context, sinks, cache.

Renderers receive normalized dict events/tool-states and write through
a RenderSink to plain stdout, a Rich Console, or a Textual RichLog.
"""

from __future__ import annotations

from rendering.base import BaseRenderer
from rendering.cache import SnapshotCache
from rendering.context import RenderContext
from rendering.events import EventRenderer, UnknownEventRenderer
from rendering.registry import RendererRegistry
from rendering.settings import RenderSettings
from rendering.sink import PlainSink, RichConsoleSink, RenderSink, TextualRichLogSink
from rendering.tools.base import FallbackToolRenderer, ToolRenderer

__all__ = [
    "BaseRenderer",
    "RenderContext",
    "RenderSettings",
    "SnapshotCache",
    "RenderSink",
    "PlainSink",
    "RichConsoleSink",
    "TextualRichLogSink",
    "RendererRegistry",
    "EventRenderer",
    "UnknownEventRenderer",
    "ToolRenderer",
    "FallbackToolRenderer",
]
