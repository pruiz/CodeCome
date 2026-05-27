# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""MessageUpdatedRenderer — renders message.updated events."""

from __future__ import annotations

import time
from typing import Any

from rendering.events.base import EventRenderer
import _colors as C


class MessageUpdatedRenderer(EventRenderer):
    event_types = ("message.updated",)

    def render(self, event: dict[str, Any]) -> bool:
        info = event.get("info")
        if not isinstance(info, dict):
            props = event.get("properties", {})
            info = props.get("info", {}) if isinstance(props, dict) else {}
        if not isinstance(info, dict):
            info = {}

        role = str(info.get("role", ""))
        tokens = info.get("tokens", {}) if isinstance(info.get("tokens"), dict) else {}
        has_tokens = isinstance(tokens, dict) and (
            tokens.get("input", 0) or tokens.get("output", 0) or tokens.get("reasoning", 0)
        )
        mcache = tokens.get("cache", {}) if isinstance(tokens, dict) else {}
        cost = info.get("cost", 0) or 0

        model_id = str(info.get("modelID", "")).strip()
        provider_id = str(info.get("providerID", "")).strip()
        if not model_id:
            mdl = info.get("model", {})
            if isinstance(mdl, dict):
                model_id = str(mdl.get("modelID", "")).strip()
                provider_id = str(mdl.get("providerID", "")).strip()
        model_label = f"{provider_id}/{model_id}" if provider_id and model_id else model_id

        if role == "user":
            self.context.last_assistant_header_rendered_at = 0.0
            message = "> User"
            style = "dim"
        elif role == "assistant":
            throttle_s = self.context.settings.assistant_header_throttle_s
            now = time.monotonic()
            if (throttle_s > 0 and self.context.last_assistant_header_rendered_at > 0 and
                    now - self.context.last_assistant_header_rendered_at < throttle_s):
                return True
            self.context.last_assistant_header_rendered_at = now
            if has_tokens:
                _in = tokens.get("input", 0)
                _out = tokens.get("output", 0)
                _reasoning = tokens.get("reasoning", 0)
                _cache_read = mcache.get("read", 0) if isinstance(mcache, dict) else 0
                token_parts = [f"\u2191{_in} \u2193{_out}"]
                if _reasoning:
                    token_parts.append(f"R{_reasoning}")
                if _cache_read:
                    token_parts.append(f"cache read {_cache_read}")
                token_str = ", ".join(token_parts)
                cost_str = f", ${cost:.4f}" if cost else ""
                message = f"> Assistant \u00b7 {model_label} ({token_str}{cost_str})"
                style = "bold blue"
            else:
                message = f"> Assistant \u00b7 {model_label}" if model_label else "> Assistant"
                style = "bold blue"
        else:
            self.context.last_assistant_header_rendered_at = 0.0
            agent = str(info.get("agent", "assistant"))
            message = f"> {agent} \u00b7 {model_label}" if model_label else f"> {agent}"
            style = "bold blue"

        if self.rich:
            from rich.text import Text
            self.sink.write(Text(message, style=style))
        elif self.plain:
            self.sink.write_text(C.header(message))
        return True
