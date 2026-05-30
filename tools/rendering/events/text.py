# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""TextEventRenderer — renders text (assistant markdown) events."""

from __future__ import annotations

from typing import Any

from rendering.events.base import EventRenderer, _clear_hidden_reasoning_state
import _colors as C


class TextEventRenderer(EventRenderer):
    event_types = ("text",)

    def render(self, event: dict[str, Any]) -> bool:
        part = event.get("part", {})
        text = str(part.get("text", "")).strip()
        if not text:
            return True
        _clear_hidden_reasoning_state(self.context)
        if self.rich:
            from rich.markdown import Markdown
            from rich.panel import Panel
            self.sink.write(Panel(Markdown(text), title="Assistant", border_style="blue", expand=True))
        elif self.plain:
            self.sink.write_text(C.header("Assistant"))
            self.sink.write_text(text)
        return True
