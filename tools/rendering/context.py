# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
RenderContext — shared runtime state for the render pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rendering.cache import SnapshotCache
from rendering.settings import RenderSettings
from rendering.sink import RenderSink


@dataclass
class RenderContext:
    """Shared runtime context for all renderers in a single run.

    Created once at startup and passed to every renderer.  Carries the
    workspace root, the configured sink, display tunables, the
    snapshot cache used by write/edit/apply_patch renderers, and the
    canonical renderer registry.
    """

    root: Path
    sink: RenderSink
    settings: RenderSettings
    cache: SnapshotCache
    phase: str = ""
    label: str = ""
    registry: "RendererRegistry | None" = None
    last_busy_status_rendered_at: float = 0.0
    last_assistant_header_rendered_at: float = 0.0
    hidden_reasoning_active: bool = False
    hidden_reasoning_started_at: float = 0.0
    last_hidden_reasoning_rendered_at: float = 0.0
    inflight_write_files: set[str] = field(default_factory=set)
