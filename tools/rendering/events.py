# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Event renderer classes — one per SSE event family.

Each renderer handles its event type(s) and writes through the
render context's sink.
"""

from __future__ import annotations

import json
import time as _time
from typing import Any

from rendering.base import BaseRenderer


# ---------------------------------------------------------------------------
# Finish reason classification
# ---------------------------------------------------------------------------

_FINISH_TERMINAL_OK = {"stop", "end_turn"}
_FINISH_MID_TURN = {"tool-calls", "tool_use"}
_FINISH_FAILURE = {"content-filter", "content_filter", "length", "max_tokens", "error"}

# Per-session dedup state for subagent update events.
_SUBAGENT_LAST_STATE: dict[str, tuple[dict[str, Any], float]] = {}


# ---------------------------------------------------------------------------
# EventRenderer base
# ---------------------------------------------------------------------------

class EventRenderer(BaseRenderer):
    event_types: tuple[str, ...] = ()

    def render(self, event: dict[str, Any]) -> bool:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Specific renderers
# ---------------------------------------------------------------------------

class StepStartRenderer(EventRenderer):
    event_types = ("step_start",)

    def __init__(self, context, *, phase: str = "", label: str = ""):
        super().__init__(context)
        self.phase = phase
        self.label = label

    def render(self, event: dict[str, Any]) -> bool:
        step_type = event.get("part", {}).get("type", "step-start")
        if self.rich:
            from rich.text import Text
            self.sink.write(Text(f"[{self.phase}] {self.label}: {step_type}", style="cyan"))
        elif self.plain:
            import _colors as C
            self.sink.write_text(C.info(f"[{self.phase}] {self.label}: {step_type}"))
        return True


class TextEventRenderer(EventRenderer):
    event_types = ("text",)

    def render(self, event: dict[str, Any]) -> bool:
        part = event.get("part", {})
        text = str(part.get("text", "")).strip()
        if not text:
            return False
        if self.rich:
            from rich.markdown import Markdown
            from rich.panel import Panel
            self.sink.write(Panel(Markdown(text), title="Assistant", border_style="blue", expand=True))
        elif self.plain:
            import _colors as C
            self.sink.write_text(C.header("Assistant"))
            self.sink.write_text(text)
        return True


class ReasoningEventRenderer(EventRenderer):
    event_types = ("reasoning",)

    def render(self, event: dict[str, Any]) -> bool:
        if not self.context.settings.render_reasoning:
            return False
        part = event.get("part", {})
        text = str(part.get("text", "")).strip()
        if not text:
            return False

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
            import _colors as C
            self.sink.write_text(C.header("Thinking"))
            self.sink.write_text(text)
            if truncated_note:
                self.sink.write_text(truncated_note.strip())
        return True


class ToolUseEventRenderer(EventRenderer):
    event_types = ("tool_use",)

    def render(self, event: dict[str, Any]) -> bool:
        part = event.get("part", {})
        tool = str(part.get("tool", "unknown"))
        state = part.get("state", {}) if isinstance(part.get("state"), dict) else {}
        from rendering.tools.base import FallbackToolRenderer
        return FallbackToolRenderer(self.context).render(tool, state)


class StepFinishRenderer(EventRenderer):
    event_types = ("step_finish",)

    def render(self, event: dict[str, Any]) -> bool:
        part = event.get("part", {})
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
            import _colors as C
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
            import _colors as C
            self.sink.write_text(C.warn("Error"))
            self.sink.write_text(C.fail(text))
        return True


class SessionStatusRenderer(EventRenderer):
    event_types = ("session.status",)

    def render(self, event: dict[str, Any]) -> bool:
        properties = event.get("properties", {})
        status = properties.get("status", {})
        status_type = status.get("type")
        if status_type == "retry":
            attempt = status.get("attempt", 1)
            message = status.get("message", "Unknown error")
            text = f"\u23f3 Waiting for LLM provider response (retry attempt {attempt}): {message}"
            if self.rich:
                from rich.text import Text
                self.sink.write(Text(text, style="bold yellow"))
            elif self.plain:
                import _colors as C
                self.sink.write_text(C.warn(text))
        elif status_type == "busy":
            text = "session status: busy"
            if self.rich:
                from rich.text import Text
                self.sink.write(Text(text, style="dim"))
            elif self.plain:
                import _colors as C
                self.sink.write_text(C.info(text))
        elif status_type == "idle":
            text = "session status: idle"
            if self.rich:
                from rich.text import Text
                self.sink.write(Text(text, style="dim"))
            elif self.plain:
                import _colors as C
                self.sink.write_text(C.info(text))
        return True


class ServerConnectedRenderer(EventRenderer):
    event_types = ("server.connected",)

    def render(self, event: dict[str, Any]) -> bool:
        message = "connected to opencode event stream"
        if self.rich:
            from rich.text import Text
            self.sink.write(Text(message, style="dim"))
        elif self.plain:
            import _colors as C
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
            import _colors as C
            self.sink.write_text(C.info(message))
        return True


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
            import _colors as C
            self.sink.write_text(C.info(message))
        return True


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
            import _colors as C
            self.sink.write_text(C.header(message))
        return True


class SubagentStatusRenderer(EventRenderer):
    event_types = ("subagent.status",)

    def render(self, event: dict[str, Any]) -> bool:
        if not self.context.settings.render_subagent_updates:
            return False

        properties = event.get("properties", {})
        status_type = str(properties.get("statusType", ""))
        session_id = str(properties.get("sessionID", ""))
        title = str(properties.get("title", "(untitled)"))
        summary = properties.get("summary")
        elapsed_ms = properties.get("elapsedMs")

        if status_type == "updated":
            snapshot: dict[str, Any] = {"title": title}
            if isinstance(summary, dict):
                snapshot["additions"] = summary.get("additions")
                snapshot["deletions"] = summary.get("deletions")
                snapshot["files"] = summary.get("files")

            last_snapshot, last_time = _SUBAGENT_LAST_STATE.get(session_id, ({}, 0.0))
            now = _time.time()
            if (
                last_snapshot == snapshot
                and (now - last_time) < self.context.settings.subagent_update_throttle_s
            ):
                return False
            _SUBAGENT_LAST_STATE[session_id] = (snapshot, now)

        if self.rich:
            self._render_rich(status_type, title, summary, elapsed_ms)
        elif self.plain:
            self._render_plain(status_type, title, summary, elapsed_ms)
        return True

    def _render_rich(self, status_type: str, title: str, summary, elapsed_ms) -> None:
        from rich.panel import Panel
        from rich.text import Text
        if status_type == "created":
            self.sink.write(Panel(Text(title, style="bold cyan"), title="Subagent started", border_style="cyan", expand=True))
        elif status_type == "finished":
            self.sink.write(Panel(Text(title, style="bold cyan"), title="Subagent finished", border_style="green", expand=True))
        elif status_type == "heartbeat" and elapsed_ms is not None:
            elapsed_s = elapsed_ms // 1000
            self.sink.write(Text(f"\u23f3 Subagent \u00b7 {title} still running ({elapsed_s}s)", style="bold yellow"))
        elif status_type == "updated":
            summary_text = self._format_subagent_summary(summary)
            line = f"Subagent \u00b7 {title}"
            if summary_text:
                line += f"  {summary_text}"
            self.sink.write(Text(line, style="dim"))

    def _render_plain(self, status_type: str, title: str, summary, elapsed_ms) -> None:
        import _colors as C
        if status_type == "created":
            self.sink.write_text(C.header(f"[subagent] started: {title}"))
        elif status_type == "finished":
            self.sink.write_text(C.ok(f"[subagent] finished: {title}"))
        elif status_type == "heartbeat" and elapsed_ms is not None:
            elapsed_s = elapsed_ms // 1000
            self.sink.write_text(C.warn(f"\u23f3 Subagent \u00b7 {title} still running ({elapsed_s}s"))
        elif status_type == "updated":
            summary_text = self._format_subagent_summary(summary)
            line = f"Subagent \u00b7 {title}"
            if summary_text:
                line += f"  {summary_text}"
            self.sink.write_text(f"  {line}")

    @staticmethod
    def _format_subagent_summary(summary: Any) -> str:
        if not isinstance(summary, dict):
            return ""
        additions = summary.get("additions")
        deletions = summary.get("deletions")
        files = summary.get("files")
        parts: list[str] = []
        if additions is not None or deletions is not None:
            parts.append(f"+{additions or 0} -{deletions or 0}")
        if files is not None:
            parts.append(f"{files} file(s)")
        return "  ".join(parts)


class UnknownEventRenderer(EventRenderer):
    """Fallback renderer for unrecognised event types."""

    def render(self, event: dict[str, Any]) -> bool:
        event_type = event.get("type", "<missing>")
        if event_type == "message.part.updated":
            part_type = event.get("part", {}).get("type", "<missing>")
            message = f"unknown part type: {part_type}"
        else:
            message = f"unknown event type: {event_type}"
        self.sink.write_text(message)
        if self.context.settings.debug_unknown_events:
            self.sink.write_text(json.dumps(event, indent=2, default=str))
        return True
