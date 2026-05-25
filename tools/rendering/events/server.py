# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Server event renderers: ServerConnectedRenderer, ServerHeartbeatRenderer."""

from __future__ import annotations

from typing import Any

from rendering.events.base import EventRenderer
import _colors as C


class ServerConnectedRenderer(EventRenderer):
    event_types = ("server.connected",)

    def render(self, event: dict[str, Any]) -> bool:
        message = "connected to opencode event stream"
        if self.rich:
            from rich.text import Text
            self.sink.write(Text(message, style="dim"))
        elif self.plain:
            self.sink.write_text(C.info(message))
        return True


class ServerHeartbeatRenderer(EventRenderer):
    event_types = ("server.heartbeat",)

    def render(self, event: dict[str, Any]) -> bool:
        message = "server heartbeat"
        if self.rich:
            from rich.text import Text
            self.sink.write(Text(message, style="dim"))
        elif self.plain:
            self.sink.write_text(C.info(message))
        return True
