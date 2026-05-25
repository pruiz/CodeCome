# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""ErrorEventRenderer — renders error events."""

from __future__ import annotations

from typing import Any

from rendering.events.base import EventRenderer
import _colors as C


class ErrorEventRenderer(EventRenderer):
    event_types = ("error",)

    def render(self, event: dict[str, Any]) -> bool:
        err = event.get("error")
        msg_parts: list[str] = []
        if isinstance(err, dict):
            name = err.get("name")
            if isinstance(name, str) and name:
                msg_parts.append(name)
            data = err.get("data")
            if isinstance(data, dict):
                data_msg = data.get("message")
                if isinstance(data_msg, str) and data_msg:
                    msg_parts.append(data_msg)
            elif isinstance(err.get("message"), str):
                msg_parts.append(err["message"])
        elif isinstance(err, str):
            msg_parts.append(err)
        text = ": ".join(msg_parts) if msg_parts else "(no error message)"
        if self.rich:
            from rich.panel import Panel
            from rich.text import Text
            self.sink.write(Panel(Text(text, style="red"), title="Error", border_style="yellow", expand=True))
        elif self.plain:
            self.sink.write_text(C.warn("Error"))
            self.sink.write_text(C.fail(text))
        return True
