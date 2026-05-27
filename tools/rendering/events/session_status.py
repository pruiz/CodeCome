# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""SessionStatusRenderer — renders session.status events."""

from __future__ import annotations

import time
from typing import Any

from rendering.events.base import EventRenderer
import _colors as C


class SessionStatusRenderer(EventRenderer):
    event_types = ("session.status",)

    def render(self, event: dict[str, Any]) -> bool:
        properties = event.get("properties", {})
        status = properties.get("status", {})
        status_type = status.get("type")
        if status_type == "retry":
            attempt = status.get("attempt", 1)
            message = status.get("message", "Unknown error")
            text = f"\u23f3 Waiting for LLM provider response (retry attempt {attempt}): {message}"
            if self.rich:
                from rich.text import Text
                self.sink.write(Text(text, style="bold yellow"))
            elif self.plain:
                self.sink.write_text(C.warn(text))
        elif status_type == "busy":
            throttle_s = self.context.settings.session_busy_throttle_s
            now = time.monotonic()
            if (throttle_s > 0 and self.context.last_busy_status_rendered_at > 0 and
                    now - self.context.last_busy_status_rendered_at < throttle_s):
                return True
            self.context.last_busy_status_rendered_at = now
            text = "session status: busy"
            if self.rich:
                from rich.text import Text
                self.sink.write(Text(text, style="dim"))
            elif self.plain:
                self.sink.write_text(C.info(text))
        elif status_type == "idle":
            text = "session status: idle"
            if self.rich:
                from rich.text import Text
                self.sink.write(Text(text, style="dim"))
            elif self.plain:
                self.sink.write_text(C.info(text))
        return True
