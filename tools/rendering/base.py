# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
BaseRenderer — shared helpers for all renderers.

Every renderer receives a ``RenderContext`` at construction time and
inherits the ``sink``, ``rich``, and ``plain`` properties.
"""

from __future__ import annotations

from rendering.context import RenderContext
from rendering.sink import RenderSink


class BaseRenderer:
    """Shared base for EventRenderer and ToolRenderer.

    Provides convenience accessors so individual renderers never need to
    inspect the sink mode manually.
    """

    def __init__(self, context: RenderContext) -> None:
        self.context = context

    @property
    def sink(self) -> RenderSink:
        return self.context.sink

    @property
    def rich(self) -> bool:
        return self.context.sink.mode in ("rich", "textual")

    @property
    def plain(self) -> bool:
        return self.context.sink.mode == "plain"
