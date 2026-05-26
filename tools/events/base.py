# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
BaseEventLoop — shared SSE/session/dedup/permission logic.

Both PhaseEventLoop and ChatEventLoop inherit from this class.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from events.sse_client import SseClient
from events.state_tracker import StateTracker


class BaseEventLoop:
    """Shared mechanics for SSE consumption loops.

    Owns: session filtering, permission auto-reject, session message
    sync, idle detection, deduplication, and common HTTP headers.
    """

    def __init__(
        self,
        base_url: str,
        session_id: str,
        console: Any,
        *,
        auth_token: str | None = None,
        workspace_dir: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id
        self.console = console
        self.auth_token = auth_token
        self.workspace_dir = workspace_dir

        self._tracker = StateTracker()
        self._client: SseClient | None = None
        self._stopped = False
        self._seen_message_ids: set[str] = set()
        self._emitted_signatures: set[tuple[str, str]] = set()
        self._last_message_sync_at = 0.0

    # ------------------------------------------------------------------
    # Session filtering & idle detection
    # ------------------------------------------------------------------

    def _belongs_to_session(self, event: dict[str, Any]) -> bool:
        props = event.get("properties", {})
        sid = props.get("sessionID")
        if sid and sid != self.session_id:
            return False
        return True

    @staticmethod
    def _is_session_idle(event: dict[str, Any]) -> bool:
        event_type = event.get("type", "")
        if event_type == "session.idle":
            return True
        if event_type == "session.status":
            status = event.get("properties", {}).get("status", {})
            return status.get("type") == "idle"
        return False

    # ------------------------------------------------------------------
    # HTTP headers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            import base64
            encoded = base64.b64encode(f"opencode:{self.auth_token}".encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {encoded}"
        if self.workspace_dir:
            headers["x-opencode-directory"] = self.workspace_dir
        return headers

    # ------------------------------------------------------------------
    # Permission auto-reject
    # ------------------------------------------------------------------

    def _handle_permission(self, event: dict[str, Any]) -> None:
        props = event.get("properties", {})
        perm_id = props.get("id")
        if not perm_id:
            return
        url = f"{self.base_url}/permission/{perm_id}/reply"
        data = json.dumps({
            "reply": "reject",
            "message": "Auto-rejected by CodeCome configuration",
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers=self._get_headers(), method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10.0)
        except urllib.error.HTTPError:
            pass

    def _extract_permission_error(self, event: dict[str, Any]) -> str | None:
        props = event.get("properties", {})
        tool = props.get("tool", "tool")
        return f"tool permission rejected: {tool}"

    # ------------------------------------------------------------------
    # Session message sync (catch-up after reconnect / before idle)
    # ------------------------------------------------------------------

    _SYNC_DELAY_S = 0.05
    _SYNC_RETRIES = 3

    def _sync_session_messages(self) -> list[dict[str, Any]]:
        self._last_message_sync_at = time.time()

        for attempt in range(self._SYNC_RETRIES):
            if attempt > 0:
                time.sleep(self._SYNC_DELAY_S)

            events = self._fetch_session_messages()
            if not events:
                continue

            if self._has_unresolved_tool_output(events):
                continue

            return events

        return events

    @staticmethod
    def _has_unresolved_tool_output(events: list[dict[str, Any]]) -> bool:
        for ev in events:
            if ev.get("type") != "tool_use":
                continue
            part = ev.get("part", {})
            state = part.get("state", {})
            output = state.get("output", "")
            if output != "(no output)":
                continue
            metadata = state.get("metadata", {})
            if metadata.get("exit", 0) != 0:
                continue
            return True
        return False

    def _fetch_session_messages(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        try:
            req = urllib.request.Request(
                f"{self.base_url}/session/{self.session_id}/message",
                headers=self._get_headers(),
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                messages = json.loads(resp.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return []

        if not isinstance(messages, list):
            return []

        for item in messages:
            if not isinstance(item, dict):
                continue
            info = item.get("info")
            parts = item.get("parts")
            if not isinstance(info, dict) or not isinstance(parts, list):
                continue
            if info.get("role") != "assistant":
                continue
            if info.get("sessionID") != self.session_id:
                continue

            message_id = info.get("id")
            if isinstance(message_id, str) and message_id and message_id not in self._seen_message_ids:
                events.append({
                    "type": "message.updated",
                    "timestamp": int(time.time() * 1000),
                    "sessionID": self.session_id,
                    "info": info,
                })
                self._seen_message_ids.add(message_id)

            for part in parts:
                if not isinstance(part, dict):
                    continue
                part_id = part.get("id")
                if isinstance(part_id, str) and self._tracker.has_seen(part_id):
                    continue
                synthesized = {
                    "type": "message.part.updated",
                    "timestamp": int(time.time() * 1000),
                    "properties": {
                        "sessionID": self.session_id,
                        "part": part,
                    },
                }
                events.extend(self._tracker.ingest(synthesized))

        return events

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    def stop(self) -> None:
        self._stopped = True
        if self._client is not None:
            self._client.stop()
