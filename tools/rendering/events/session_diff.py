# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""SessionDiffRenderer — renders session.diff events."""

from __future__ import annotations

from typing import Any

from rendering.events.base import EventRenderer
import _colors as C


class SessionDiffRenderer(EventRenderer):
    event_types = ("session.diff",)

    def render(self, event: dict[str, Any]) -> bool:
        properties = event.get("properties", {})
        diff = properties.get("diff", [])
        if not isinstance(diff, list) or not diff:
            return False
        count = len(diff)
        message = f"session diff updated: {count} file{'s' if count != 1 else ''}"
        if self.rich:
            from rich.text import Text
            self.sink.write(Text(message, style="dim"))
        elif self.plain:
            self.sink.write_text(C.info(message))
        return True
