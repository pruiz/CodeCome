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
    ) -> None:
        super().__init__(base_url, session_id, console,
                         auth_token=auth_token, workspace_dir=workspace_dir)
        self.phase = phase
        self.label = label
        self._pending_recovery_sync = False
        self._idle_event_to_sync_and_emit: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        render_fn: Callable[[Any, str, str, dict[str, Any]], None],
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
        )

        try:
            for event in self._client.events():
                if self._stopped:
                    break

                if not self._belongs_to_session(event):
                    continue

                if event.get("type") == "permission.asked":
                    self._handle_permission(event)
                    perm_err = self._extract_permission_error(event)
                    if perm_err:
                        _last_permission_error = perm_err
                    continue

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

                for fe in finalized_events:
                    sig = (fe.get("type", ""), fe.get("part", {}).get("id", ""))
                    if sig[1] and sig in self._emitted_signatures:
                        continue
                    self._emitted_signatures.add(sig)
                    _any_step_finish_seen, _step_finish_count, _last_finish_reason, _last_finish_tokens = self._update_result(
                        fe, _any_step_finish_seen, _step_finish_count, _last_finish_reason, _last_finish_tokens
                    )
                    emit_event(render_fn, self.console, self.phase, self.label, fe)

                if self._is_session_idle(event):
                    self._idle_event_to_sync_and_emit = None
                    self._sync_session_messages()
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

    # ------------------------------------------------------------------
    # Phase-specific helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_result(
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
