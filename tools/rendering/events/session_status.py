# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""SessionStatusRenderer — renders session.status events."""

from __future__ import annotations

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
