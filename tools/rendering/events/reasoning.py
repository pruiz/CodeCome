# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""ReasoningEventRenderer — renders thinking/reasoning events."""

from __future__ import annotations

import time
from typing import Any

from rendering.events.base import EventRenderer, _clear_hidden_reasoning_state
import _colors as C


class ReasoningEventRenderer(EventRenderer):
    event_types = ("reasoning",)

    def render(self, event: dict[str, Any]) -> bool:
        if not self.context.settings.render_reasoning:
            return True
        part = event.get("part", {})
        text = str(part.get("text", "")).strip()
        metadata = part.get("metadata", {}) if isinstance(part.get("metadata"), dict) else {}
        openai_meta = metadata.get("openai", {}) if isinstance(metadata.get("openai"), dict) else {}
        has_hidden_reasoning = bool(openai_meta.get("reasoningEncryptedContent"))
        if not text:
            if has_hidden_reasoning:
                return self._render_hidden_reasoning()
            return True

        _clear_hidden_reasoning_state(self.context)

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

    def _render_hidden_reasoning(self) -> bool:
        now = time.monotonic()
        if not self.context.hidden_reasoning_active:
            self.context.hidden_reasoning_active = True
            self.context.hidden_reasoning_started_at = now
            self.context.last_hidden_reasoning_rendered_at = 0.0

        if self.sink.mode == "textual":
            return True

        throttle_s = self.context.settings.hidden_reasoning_throttle_s
        if (throttle_s > 0 and self.context.last_hidden_reasoning_rendered_at > 0 and
                now - self.context.last_hidden_reasoning_rendered_at < throttle_s):
            return True

        elapsed_s = max(now - self.context.hidden_reasoning_started_at, 0.0)
        self.context.last_hidden_reasoning_rendered_at = now
        message = f"Assistant reasoning [{elapsed_s:.1f}s so far]"
        if self.rich:
            from rich.text import Text
            self.sink.write(Text(message, style="dim"))
        elif self.plain:
            self.sink.write_text(C.info(message))
        return True
