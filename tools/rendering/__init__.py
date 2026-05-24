# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Rendering package: tool/event renderer classes, render context, sinks, cache.

Renderers receive normalized dict events/tool-states and write through
a RenderSink to plain stdout, a Rich Console, or a Textual RichLog.
"""

from __future__ import annotations
