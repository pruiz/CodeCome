# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""ReasoningEventRenderer — renders thinking/reasoning events."""

from __future__ import annotations

from typing import Any

from rendering.events.base import EventRenderer
import _colors as C


class ReasoningEventRenderer(EventRenderer):
    event_types = ("reasoning",)

    def render(self, event: dict[str, Any]) -> bool:
        if not self.context.settings.render_reasoning:
            return True
        part = event.get("part", {})
        text = str(part.get("text", "")).strip()
        if not text:
            return True

        truncated_note = ""
        max_chars = self.context.settings.reasoning_max_chars
        if len(text) > max_chars:
            cut = len(text) - max_chars
            text = text[:max_chars]
            truncated_note = f"\n\n... ({cut} chars truncated)"

        if self.rich:
            from rich.console import Group
            from rich.markdown import Markdown
            from rich.panel import Panel
            from rich.text import Text
            body_md = Markdown(text)
            if truncated_note:
                body = Group(body_md, Text(truncated_note.strip(), style="dim"))
            else:
                body = body_md
            self.sink.write(Panel(body, title="Thinking", border_style="blue", expand=True, style="dim"))
        elif self.plain:
            self.sink.write_text(C.header("Thinking"))
            self.sink.write_text(text)
            if truncated_note:
                self.sink.write_text(truncated_note.strip())
        return True
