# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""MessageUpdatedRenderer — renders message.updated events."""

from __future__ import annotations

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
        has_summary = "summary" in info or "finish" in info
        if not has_summary and not has_tokens:
            return False

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
            message = "> User"
            style = "dim"
        elif role == "assistant":
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
            agent = str(info.get("agent", "assistant"))
            message = f"> {agent} \u00b7 {model_label}" if model_label else f"> {agent}"
            style = "bold blue"

        if self.rich:
            from rich.text import Text
            self.sink.write(Text(message, style=style))
        elif self.plain:
            self.sink.write_text(C.header(message))
        return True
