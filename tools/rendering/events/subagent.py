# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""SubagentStatusRenderer — renders subagent.status events."""

from __future__ import annotations

import time as _time
from typing import Any

from rendering.events.base import EventRenderer, _SUBAGENT_LAST_STATE
import _colors as C


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
        if status_type == "created":
            self.sink.write_text(C.header(f"[subagent] started: {title}"))
        elif status_type == "finished":
            self.sink.write_text(C.ok(f"[subagent] finished: {title}"))
        elif status_type == "heartbeat" and elapsed_ms is not None:
            elapsed_s = elapsed_ms // 1000
            self.sink.write_text(C.warn(f"\u23f3 Subagent \u00b7 {title} still running ({elapsed_s}s)"))
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
