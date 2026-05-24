# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
RenderContext — shared runtime state for the render pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rendering.cache import SnapshotCache
from rendering.settings import RenderSettings
from rendering.sink import RenderSink


@dataclass
class RenderContext:
    """Shared runtime context for all renderers in a single run.

    Created once at startup and passed to every renderer.  Carries the
    workspace root, the configured sink, display tunables, and the
    snapshot cache used by write/edit/apply_patch renderers.
    """

    root: Path
    sink: RenderSink
    settings: RenderSettings
    cache: SnapshotCache
