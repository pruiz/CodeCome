# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""StepFinishRenderer — renders step_finish events."""

from __future__ import annotations

from typing import Any

from rendering.events.base import EventRenderer, _FINISH_FAILURE, _clear_hidden_reasoning_state
import _colors as C


class StepFinishRenderer(EventRenderer):
    event_types = ("step_finish",)

    def render(self, event: dict[str, Any]) -> bool:
        part = event.get("part", {})
        _clear_hidden_reasoning_state(self.context)
        reason = str(part.get("reason", "unknown"))
        tokens = self._format_tokens(part.get("tokens", {}))
        suffix = f" ({tokens})" if tokens else ""
        style = "dim"
        if reason in _FINISH_FAILURE:
            style = "bold red"
        if self.rich:
            from rich.text import Text
            self.sink.write(Text(f"step finished: {reason}{suffix}", style=style))
        elif self.plain:
            if reason in _FINISH_FAILURE:
                self.sink.write_text(C.fail(f"step finished: {reason}{suffix}"))
            else:
                self.sink.write_text(f"step finished: {reason}{suffix}")
        return True

    @staticmethod
    def _format_tokens(tokens: dict[str, Any]) -> str:
        if not isinstance(tokens, dict):
            return ""
        parts = []
        for key in ("input", "output", "reasoning", "total"):
            value = tokens.get(key)
            if value is not None:
                parts.append(f"{key}={value}")
        return ", ".join(parts)
