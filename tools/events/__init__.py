# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Event loop coordinator: consumes SSE, accumulates state, maps events,
and emits them to the existing render pipeline.

Entry point:
    event_loop = EventLoop(base_url, session_id, console, phase, label)
    result = event_loop.run(render_event_fn)
"""

from __future__ import annotations

import dataclasses
import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from events.sse_client import SseClient, SseClientError
from events.state_tracker import StateTracker
from events.emitters import emit_event


@dataclasses.dataclass(frozen=True)
class RunResult:
    """ Signals returned by EventLoop.run() for termination logic. """
    any_step_finish_seen: bool = False
    step_finish_count: int = 0
    last_finish_reason: str | None = None
    last_finish_tokens: dict[str, Any] = dataclasses.field(default_factory=dict)
    last_permission_error: str | None = None
    last_session_id: str | None = None


class EventLoop:
    """ Consume the SSE stream for a single session and drive rendering. """

    def __init__(
        self,
        base_url: str,
        session_id: str,
        console: Any,
        phase: str,
        label: str,
        *,
        auth_token: str | None = None,
        workspace_dir: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id
        self.console = console
        self.phase = phase
        self.label = label
        self.auth_token = auth_token
        self.workspace_dir = workspace_dir

        self._tracker = StateTracker()
        self._client: SseClient | None = None
        self._stopped = False
        self._seen_message_ids: set[str] = set()
        self._last_message_sync_at = 0.0
        self._pending_recovery_sync = False
        self._emitted_signatures: set[tuple[str, str]] = set()
        self._idle_event_to_sync_and_emit: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        render_fn: Callable[[Any, str, str, dict[str, Any]], None],
    ) -> RunResult:
        """ Block until the session reaches idle or a terminal error.

        Args:
            render_fn: the existing render_event() function from run-agent.py

        Returns:
            RunResult with all signals needed by termination logic.
        """
        # Use a mutable builder for accumulation.
        _any_step_finish_seen = False
        _step_finish_count = 0
        _last_finish_reason: str | None = None
        _last_finish_tokens: dict[str, Any] = {}
        _last_permission_error: str | None = None

        self._client = SseClient(
            self.base_url,
            auth_token=self.auth_token,
            workspace_dir=self.workspace_dir,
            reconnect=True,
            max_reconnects=10,
            on_reconnect=self.trigger_recovery_sync,
        )

        try:
            for event in self._client.events():
                if self._stopped:
                    break

                # Filter by session (the global stream includes all sessions).
                if not self._belongs_to_session(event):
                    continue

                # Handle permissions first (need HTTP reply).
                if event.get("type") == "permission.asked":
                    self._handle_permission(event)
                    perm_err = self._extract_permission_error(event)
                    if perm_err:
                        _last_permission_error = perm_err
                    continue

                # Capture idle events for deferred sync-and-emit
                _is_idle = self._is_session_idle(event)
                if _is_idle and self._idle_event_to_sync_and_emit is None:
                    self._idle_event_to_sync_and_emit = event

                # Let the tracker accumulate deltas and produce finalized events.
                finalized_events = self._tracker.ingest(event)

                if self._should_sync_session_messages(event):
                    finalized_events.extend(self._sync_session_messages())

                # Filter out idle events from finalized_events if we have a deferred idle
                # (to avoid double-emitting: once from tracker, once from idle handler)
                if self._idle_event_to_sync_and_emit is not None:
                    finalized_events = [
                        fe for fe in finalized_events
                        if not (
                            fe.get("type") == "session.idle" or
                            (fe.get("type") == "session.status" and fe.get("properties", {}).get("status", {}).get("type") == "idle")
                        )
                    ]

                for fe in finalized_events:
                    sig = (fe.get("type", ""), fe.get("part", {}).get("id", ""))
                    if sig[1] and sig in self._emitted_signatures:
                        continue
                    self._emitted_signatures.add(sig)
                    _any_step_finish_seen, _step_finish_count, _last_finish_reason, _last_finish_tokens = self._update_result(
                        fe, _any_step_finish_seen, _step_finish_count, _last_finish_reason, _last_finish_tokens
                    )
                    emit_event(render_fn, self.console, self.phase, self.label, fe)

                # Stop consuming when session goes idle - but sync and then emit the idle event.
                if self._is_session_idle(event):
                    idle_event = self._idle_event_to_sync_and_emit
                    self._idle_event_to_sync_and_emit = None
                    # Sync to catch any final events SSE might have missed
                    self._sync_session_messages()
                    # Now emit the idle event
                    idle_sig = (event.get("type", ""), event.get("properties", {}).get("sessionID", ""))
                    if idle_sig[1] and idle_sig in self._emitted_signatures:
                        pass  # already emitted via finalize path
                    else:
                        if idle_sig[1]:
                            self._emitted_signatures.add(idle_sig)
                        emit_event(render_fn, self.console, self.phase, self.label, event)
                    return self._build_result(
                        _any_step_finish_seen,
                        _step_finish_count,
                        _last_finish_reason,
                        _last_finish_tokens,
                        _last_permission_error,
                        self.session_id,
                    )

        except SseClientError as exc:
            # Reconnect exhausted or fatal stream error.
            # We return what we have; caller decides whether to retry.
            pass

        return self._build_result(
            any_step_finish_seen=_any_step_finish_seen,
            step_finish_count=_step_finish_count,
            last_finish_reason=_last_finish_reason,
            last_finish_tokens=_last_finish_tokens,
            last_permission_error=_last_permission_error,
            last_session_id=self.session_id,
        )

    def stop(self) -> None:
        """ Signal the event loop to exit after the next event. """
        self._stopped = True
        if self._client is not None:
            self._client.stop()

    def trigger_recovery_sync(self) -> None:
        """ Signal that a recovery sync is needed after SSE reconnection. """
        self._pending_recovery_sync = True

    @staticmethod
    def _build_result(
        any_step_finish_seen: bool,
        step_finish_count: int,
        last_finish_reason: str | None,
        last_finish_tokens: dict[str, Any],
        last_permission_error: str | None,
        last_session_id: str | None,
    ) -> RunResult:
        """ Build a RunResult from accumulated signals. """
        return RunResult(
            any_step_finish_seen=any_step_finish_seen,
            step_finish_count=step_finish_count,
            last_finish_reason=last_finish_reason,
            last_finish_tokens=last_finish_tokens,
            last_permission_error=last_permission_error,
            last_session_id=last_session_id,
        )

    # ------------------------------------------------------------------
    # Internal
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

    @staticmethod
    def _is_session_idle(event: dict[str, Any]) -> bool:
        """Return True if this event signals the session reached idle.

        Supports both the canonical ``session.status`` with
        ``status.type == "idle"`` and the deprecated ``session.idle``.
        """
        event_type = event.get("type", "")
        if event_type == "session.idle":
            return True
        if event_type == "session.status":
            status = event.get("properties", {}).get("status", {})
            return status.get("type") == "idle"
        return False

    def _belongs_to_session(self, event: dict[str, Any]) -> bool:
        """ Return True if this event belongs to our tracked session. """
        props = event.get("properties", {})
        sid = props.get("sessionID")
        if sid and sid != self.session_id:
            return False
        # server.connected / server.heartbeat have no sessionID — pass through.
        return True

    def _handle_permission(self, event: dict[str, Any]) -> None:
        """ Auto-reject the permission via POST /permission/{requestID}/reply. """
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
            url,
            data=data,
            headers=self._get_headers(),
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10.0)
        except urllib.error.HTTPError:
            # Log but don't crash; the session may already have moved on.
            pass

    def _extract_permission_error(self, event: dict[str, Any]) -> str | None:
        """ Build a human-readable permission rejection summary. """
        props = event.get("properties", {})
        tool = props.get("tool", "tool")
        return f"tool permission rejected: {tool}"

    def _should_sync_session_messages(self, event: dict[str, Any]) -> bool:
        """Return True when a session snapshot sync may reveal finalized parts.

        Sync is only triggered in two cases:
        1. After SSE reconnection (recovery sync via _pending_recovery_sync flag)
        2. Explicit idle event - but caller handles idle emission, not us
        """
        if self._pending_recovery_sync:
            self._pending_recovery_sync = False
            return True

        event_type = event.get("type", "")
        if event_type == "session.idle":
            return True
        if event_type == "session.status":
            status = event.get("properties", {}).get("status", {})
            if status.get("type") == "idle":
                return True
        return False

    def _sync_session_messages(self) -> list[dict[str, Any]]:
        """Fetch current session messages and synthesize finalized compatibility events.

        The HTTP SSE stream may emit `message.part.delta` without corresponding
        `message.part.updated` events. The session snapshot API does contain the
        completed assistant messages and parts, so we poll it and emit unseen
        message/part events in the same ND-JSON-compatible shapes expected by
        the existing renderer.
        """
        self._last_message_sync_at = time.time()
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
                    self._tracker.mark_seen(part_id)
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

    def _update_result(
        self,
        event: dict[str, Any],
        any_step_finish_seen: bool,
        step_finish_count: int,
        last_finish_reason: str | None,
        last_finish_tokens: dict[str, Any],
    ) -> tuple[bool, int, str | None, dict[str, Any]]:
        """ Update mutable result signals based on the mapped event.

        Returns the updated tuple of (any_seen, count, reason, tokens).
        """
        event_type = event.get("type", "")
        if event_type == "step_finish":
            any_step_finish_seen = True
            step_finish_count += 1
            part = event.get("part", {})
            reason = part.get("reason")
            if isinstance(reason, str):
                last_finish_reason = reason
            tokens = part.get("tokens")
            if isinstance(tokens, dict):
                last_finish_tokens = tokens

        return any_step_finish_seen, step_finish_count, last_finish_reason, last_finish_tokens
