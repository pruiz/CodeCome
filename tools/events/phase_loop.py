# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
PhaseEventLoop — single-attempt phase SSE consumer.

Consumes the OpenCode SSE stream for one session, emits finalized events,
performs catch-up sync around reconnect/idle, and returns RunResult for
phase completion logic.
"""

from __future__ import annotations

import dataclasses
import os
import time
from typing import Any, Callable

from events.sse_client import SseClient, SseClientError
from events.base import BaseEventLoop
from events.emitters import emit_event


@dataclasses.dataclass(frozen=True)
class RunResult:
    """Signals returned by PhaseEventLoop.run() for termination logic."""

    any_step_finish_seen: bool = False
    step_finish_count: int = 0
    last_finish_reason: str | None = None
    last_finish_tokens: dict[str, Any] = dataclasses.field(default_factory=dict)
    last_permission_error: str | None = None
    last_session_id: str | None = None
    session_stalled: bool = False


class PhaseEventLoop(BaseEventLoop):
    """Consume the SSE stream for a single session and drive rendering."""

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
        liveness_check: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(base_url, session_id, console,
                         auth_token=auth_token, workspace_dir=workspace_dir)
        self.phase = phase
        self.label = label
        self._pending_recovery_sync = False
        self._idle_event_to_sync_and_emit: dict[str, Any] | None = None
        # liveness_check reports whether the server process is still alive.
        self._liveness_check = liveness_check
        # Tracks the last session status observed on the SSE stream so we can
        # decide whether a stream drop should be tolerated (still busy) or is a
        # genuine end-of-turn.
        self._session_busy = False
        # No-progress watchdog: when a busy turn produces no meaningful SSE
        # events for this long, treat the turn as stalled (hung model/provider)
        # so the harness can restart the server and retry instead of waiting
        # forever. server.heartbeat / server.connected do not count as progress.
        self._stall_timeout_s = float(os.environ.get("CODECOME_BUSY_STALL_TIMEOUT", "180"))
        # Optional diagnostic signal: opencode may pause server.heartbeat during
        # valid long turns, so heartbeat-gap stalls are disabled by default. When
        # explicitly enabled, they can flag runtime blockage sooner than the
        # primary no-progress timeout.
        self._heartbeat_stall_timeout_s = float(
            os.environ.get("CODECOME_HEARTBEAT_STALL_TIMEOUT", "0")
        )
        self._last_progress_at = time.monotonic()
        self._session_stalled = False
        self._session_idle_via_status = False
        try:
            self._status_probe_timeout_s = max(
                0.1, float(os.environ.get("CODECOME_RESUME_PROBE_TIMEOUT", "2"))
            )
        except (TypeError, ValueError):
            self._status_probe_timeout_s = 2.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        render_fn: Callable[[Any, str, str, dict[str, Any]], None],
        record_raw_event_fn: Callable[[dict[str, Any]], None] | None = None,
    ) -> RunResult:
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
            should_continue=self._should_keep_consuming,
        )

        try:
            def emit_finalized(finalized_events: list[dict[str, Any]]) -> None:
                nonlocal _any_step_finish_seen, _step_finish_count
                nonlocal _last_finish_reason, _last_finish_tokens
                for fe in finalized_events:
                    sig = (fe.get("type", ""), fe.get("part", {}).get("id", ""))
                    if sig[1] and sig in self._emitted_signatures:
                        continue
                    self._emitted_signatures.add(sig)
                    _any_step_finish_seen, _step_finish_count, _last_finish_reason, _last_finish_tokens = self._update_result(
                        fe, _any_step_finish_seen, _step_finish_count, _last_finish_reason, _last_finish_tokens
                    )
                    emit_event(render_fn, self.console, self.phase, self.label, fe)

            for event in self._client.events():
                if self._stopped:
                    break

                if not self._belongs_to_session(event):
                    continue

                self._note_progress(event)

                if record_raw_event_fn is not None:
                    record_raw_event_fn(event)

                if self._should_skip_message_updated(event):
                    continue

                if event.get("type") == "permission.asked":
                    self._handle_permission(event)
                    perm_err = self._extract_permission_error(event)
                    if perm_err:
                        _last_permission_error = perm_err
                    continue

                self._track_session_busy(event)

                _is_idle = self._is_session_idle(event)
                if _is_idle and self._idle_event_to_sync_and_emit is None:
                    self._idle_event_to_sync_and_emit = event

                finalized_events = self._tracker.ingest(event)

                if self._should_sync_session_messages(event):
                    finalized_events.extend(self._sync_session_messages())

                if self._idle_event_to_sync_and_emit is not None:
                    finalized_events = [
                        fe for fe in finalized_events
                        if not (
                            fe.get("type") == "session.idle" or
                            (fe.get("type") == "session.status" and
                             fe.get("properties", {}).get("status", {}).get("type") == "idle")
                        )
                    ]

                emit_finalized(finalized_events)

                if self._is_session_idle(event):
                    self._idle_event_to_sync_and_emit = None
                    idle_sig = (event.get("type", ""), event.get("properties", {}).get("sessionID", ""))
                    if idle_sig[1] and idle_sig in self._emitted_signatures:
                        pass
                    else:
                        if idle_sig[1]:
                            self._emitted_signatures.add(idle_sig)
                        emit_event(render_fn, self.console, self.phase, self.label, event)
                    return self._build_result(
                        _any_step_finish_seen, _step_finish_count,
                        _last_finish_reason, _last_finish_tokens,
                        _last_permission_error, self.session_id,
                    )

        except SseClientError:
            pass

        if self._session_idle_via_status:
            emit_finalized(self._sync_session_messages())
            idle_event = {
                "type": "session.status",
                "properties": {
                    "sessionID": self.session_id,
                    "status": {"type": "idle"},
                },
            }
            if record_raw_event_fn is not None:
                record_raw_event_fn(idle_event)
            emit_event(render_fn, self.console, self.phase, self.label, idle_event)
            return self._build_result(
                _any_step_finish_seen, _step_finish_count,
                _last_finish_reason, _last_finish_tokens,
                _last_permission_error, self.session_id,
            )

        if self._session_stalled and _last_finish_reason not in ("stop", "idle"):
            _last_finish_reason = "session_stalled"

        return self._build_result(
            any_step_finish_seen=_any_step_finish_seen,
            step_finish_count=_step_finish_count,
            last_finish_reason=_last_finish_reason,
            last_finish_tokens=_last_finish_tokens,
            last_permission_error=_last_permission_error,
            last_session_id=self.session_id,
        )

    def trigger_recovery_sync(self) -> None:
        self._pending_recovery_sync = True

    def _track_session_busy(self, event: dict[str, Any]) -> None:
        """Record the latest session busy/idle state seen on the SSE stream."""
        if event.get("type") == "session.status":
            status_type = event.get("properties", {}).get("status", {}).get("type")
            if status_type == "busy":
                self._session_busy = True
            elif status_type == "idle":
                self._session_busy = False
        elif event.get("type") == "session.idle":
            self._session_busy = False

    # Events that are pure connection lifecycle / keepalive and do NOT count as
    # turn progress for the stall watchdog.
    _NON_PROGRESS_EVENTS = frozenset({"server.heartbeat", "server.connected"})

    def _note_progress(self, event: dict[str, Any]) -> None:
        """Reset the no-progress watchdog on any meaningful SSE event."""
        if event.get("type") in self._NON_PROGRESS_EVENTS:
            return
        self._last_progress_at = time.monotonic()

    def _stalled(self) -> bool:
        """True once a busy turn looks hung.

        Primary signal: no meaningful (non-heartbeat) SSE event for
        CODECOME_BUSY_STALL_TIMEOUT seconds.

        Secondary signal: heartbeats were observed on this connection and then
        stopped for CODECOME_HEARTBEAT_STALL_TIMEOUT seconds. Because opencode
        schedules heartbeats on the same runtime that runs the model turn, a
        heartbeat gap is an early indicator the runtime has blocked.
        """
        if self._stall_timeout_s > 0:
            if (time.monotonic() - self._last_progress_at) >= self._stall_timeout_s:
                return True

        if self._heartbeat_stall_timeout_s > 0 and self._client is not None:
            since_hb = self._client.seconds_since_heartbeat()
            if since_hb is not None and since_hb >= self._heartbeat_stall_timeout_s:
                return True

        return False

    def _should_keep_consuming(self) -> bool:
        """Whether the SSE client should keep reconnecting past its budget.

        A long model turn must never be abandoned: while the session is still
        busy AND the server process is alive, keep consuming the stream so we
        observe the genuine terminal idle instead of misreading a transient
        stream drop as a mid-turn cutoff.

        However, a busy session that produces no meaningful events for
        CODECOME_BUSY_STALL_TIMEOUT seconds is treated as a hung turn: stop
        consuming so the harness can restart the server and retry.
        """
        if not self._session_busy:
            return False
        if self._stalled():
            if self._status_probe_reports_idle():
                return False
            self._session_stalled = True
            return False
        if self._liveness_check is None:
            # No liveness signal available: be conservative and keep consuming
            # while the session is busy (the prior behavior gave up too early).
            return True
        try:
            return bool(self._liveness_check())
        except Exception:  # noqa: BLE001
            return False

    def _status_probe_reports_idle(self) -> bool:
        """Confirm whether a stale busy SSE state actually became idle."""
        status = self._fetch_session_status(timeout=self._status_probe_timeout_s)
        if status == "idle":
            self._session_busy = False
            self._session_idle_via_status = True
            return True
        return False

    # ------------------------------------------------------------------
    # Phase-specific helpers
    # ------------------------------------------------------------------

    def _build_result(
        self,
        any_step_finish_seen: bool,
        step_finish_count: int,
        last_finish_reason: str | None,
        last_finish_tokens: dict[str, Any],
        last_permission_error: str | None,
        last_session_id: str | None,
    ) -> RunResult:
        return RunResult(
            any_step_finish_seen=any_step_finish_seen,
            step_finish_count=step_finish_count,
            last_finish_reason=last_finish_reason,
            last_finish_tokens=last_finish_tokens,
            last_permission_error=last_permission_error,
            last_session_id=last_session_id,
            session_stalled=self._session_stalled,
        )

    def _should_sync_session_messages(self, event: dict[str, Any]) -> bool:
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

    def _update_result(
        self,
        event: dict[str, Any],
        any_step_finish_seen: bool,
        step_finish_count: int,
        last_finish_reason: str | None,
        last_finish_tokens: dict[str, Any],
    ) -> tuple[bool, int, str | None, dict[str, Any]]:
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
