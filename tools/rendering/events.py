# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Base classes for generic (non-tool) event renderers.

Event renderers receive the full normalized event dict and write
output through the render context's sink.
"""

from __future__ import annotations

from typing import Any

from rendering.base import BaseRenderer


class EventRenderer(BaseRenderer):
    """Base class for renderers that handle generic SSE events.

    Subclasses declare which event types they handle via ``event_types``.
    The registry will dispatch each event to the first matching renderer.
    """

    event_types: tuple[str, ...] = ()

    def render(self, event: dict[str, Any]) -> bool:
        """Render *event*.  Return True if handled, False to fall through."""
        raise NotImplementedError


class UnknownEventRenderer(EventRenderer):
    """Fallback renderer for unrecognised event types."""

    def render(self, event: dict[str, Any]) -> bool:
        event_type = event.get("type", "<missing>")
        if event_type == "message.part.updated":
            part_type = event.get("part", {}).get("type", "<missing>")
            message = f"unknown part type: {part_type}"
        else:
            message = f"unknown event type: {event_type}"
        self.sink.write_text(message)
        if self.context.settings.debug_unknown_events:
            import json
            self.sink.write_text(json.dumps(event, indent=2, default=str))
        return True
