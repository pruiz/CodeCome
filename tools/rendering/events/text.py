# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""TextEventRenderer — renders text (assistant markdown) events."""

from __future__ import annotations

from typing import Any

from rendering.events.base import EventRenderer, _clear_hidden_reasoning_state
import _colors as C


class TextEventRenderer(EventRenderer):
    event_types = ("text", "text.loop_warning")

    def render(self, event: dict[str, Any]) -> bool:
        if event.get("type") == "text.loop_warning":
            props = event.get("properties", {})
            ratio = props.get("uniqueRatio", 0)
            ratio_pct = round(ratio * 100, 1)
            window = props.get("windowSize", 0)
            total = props.get("totalDeltas", 0)
            msg = (
                f"WARNING: repetitive text loop detected — "
                f"only {ratio_pct}% unique deltas "
                f"in last {window}-delta window "
                f"({total} deltas total in this part). "
                f"The model may be stuck."
            )
            if self.rich:
                from rich.panel import Panel
                from rich.text import Text as RichText
                self.sink.write(Panel(RichText(msg, style="bold yellow"), title="Loop Warning", border_style="yellow"))
            elif self.plain:
                self.sink.write_text(C.warn(msg))
            return True

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
