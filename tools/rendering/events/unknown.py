# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""UnknownEventRenderer — fallback renderer for unrecognised event types."""

from __future__ import annotations

import json
from typing import Any

from rendering.events.base import EventRenderer


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
            self.sink.write_text(json.dumps(event, indent=2, default=str))
        return True
