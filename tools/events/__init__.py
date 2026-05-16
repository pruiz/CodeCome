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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id
        self.console = console
        self.phase = phase
        self.label = label

        self._tracker = StateTracker()
        self._client: SseClient | None = None
        self._stopped = False

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
            reconnect=True,
            max_reconnects=10,
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

                # Let the tracker accumulate deltas and produce finalized events.
                finalized_events = self._tracker.ingest(event)

                for fe in finalized_events:
                    _any_step_finish_seen, _step_finish_count, _last_finish_reason, _last_finish_tokens = self._update_result(
                        fe, _any_step_finish_seen, _step_finish_count, _last_finish_reason, _last_finish_tokens
                    )
                    emit_event(render_fn, self.console, self.phase, self.label, fe)

                # Stop consuming when session goes idle.
                if event.get("type") == "session.idle":
                    return RunResult(
                        any_step_finish_seen=_any_step_finish_seen,
                        step_finish_count=_step_finish_count,
                        last_finish_reason=_last_finish_reason,
                        last_finish_tokens=_last_finish_tokens,
                        last_permission_error=_last_permission_error,
                        last_session_id=self.session_id,
                    )

        except SseClientError as exc:
            # Reconnect exhausted or fatal stream error.
            # We return what we have; caller decides whether to retry.
            pass

        return RunResult(
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

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _belongs_to_session(self, event: dict[str, Any]) -> bool:
        """ Return True if this event belongs to our tracked session. """
        props = event.get("properties", {})
        sid = props.get("sessionID")
        if sid and sid != self.session_id:
            return False
        # server.connected / server.heartbeat have no sessionID — pass through.
        return True

    def _handle_permission(self, event: dict[str, Any]) -> None:
        """ Auto-reject the permission via POST /permission/{id}/reply. """
        props = event.get("properties", {})
        perm_id = props.get("id")
        if not perm_id:
            return
        url = f"{self.base_url}/permission/{perm_id}/reply"
        data = json.dumps({"reply": "reject"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10.0)
        except urllib.error.HTTPError as exc:
            # Log but don't crash; the session may already have moved on.
            pass

    def _extract_permission_error(self, event: dict[str, Any]) -> str | None:
        """ Build a human-readable permission rejection summary. """
        props = event.get("properties", {})
        tool = props.get("tool", "tool")
        return f"tool permission rejected: {tool}"

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
