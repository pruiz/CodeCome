# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Accumulate SSE streaming deltas and track part state transitions.

The server sends `message.part.delta` events with tiny text fragments.
This module accumulates them by partID and produces finalized part
snapshots when the corresponding `message.part.updated` arrives.
"""

from __future__ import annotations

import os
from collections import deque
from typing import Any


def _loop_detection_params() -> tuple[int, int]:
    """Return (window_size, threshold) for loop detection from environment.

    CODECOME_LOOP_WINDOW    — how many recent text-deltas to track (default 50)
    CODECOME_LOOP_THRESHOLD — repetitions of the same delta in the window that
                              trigger a warning (default 20)

    Reads directly from ``os.environ`` on every call so that tests using
    ``monkeypatch.setenv`` work correctly regardless of import order.
    """
    try:
        window = int(os.environ.get("CODECOME_LOOP_WINDOW", "50"))
        window = max(window, 1)
    except (ValueError, TypeError):
        window = 50
    try:
        threshold = int(os.environ.get("CODECOME_LOOP_THRESHOLD", "20"))
        threshold = max(threshold, 1)
    except (ValueError, TypeError):
        threshold = 20
    return window, threshold


class StateTracker:
    """ Accumulate deltas, track part versions, detect finalized parts. """

    def __init__(self) -> None:
        # Map partID -> accumulated text buffer.
        self._delta_buffers: dict[str, str] = {}
        # Set of partIDs we have already "finalized" (yielded as updated).
        self._seen_part_ids: set[str] = set()
        # Set of partIDs for which we saw delta but not yet updated.
        self._pending_part_ids: set[str] = set()

        # --- Repetitive text-loop detection ---
        # Per-part sliding window of recent text delta strings.
        self._delta_windows: dict[str, deque[str]] = {}
        # Counts of each delta text within the corresponding window.
        self._delta_counts: dict[str, dict[str, int]] = {}
        # Set of partIDs for which a loop warning has already been emitted.
        self._loop_warned: set[str] = set()

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """ Process one SSE event and return zero or more *finalized* events.

        A finalized event is one whose part has reached a stable state
        (e.g. text part with time.end, tool part with status completed,
        step-start, step-finish).
        """
        event_type = event.get("type", "")
        if event_type == "message.part.delta":
            finalized = self._handle_delta(event)
            if finalized:
                return finalized
            return []

        if event_type == "message.part.updated":
            finalized = self._handle_updated(event)
            return finalized

        if event_type == "session.error":
            props = event.get("properties", {})
            return [{
                "type": "error",
                "timestamp": event.get("timestamp", 0),
                "sessionID": props.get("sessionID", ""),
                "error": props.get("error"),
            }]

        if event_type == "session.diff":
            mapped = self._map_session_diff(event)
            return [mapped] if mapped else []

        if event_type == "session.updated":
            return []

        # Pass-through events that don't need accumulation.
        if event_type in ("session.status", "session.idle",
                         "permission.asked", "server.connected", "server.heartbeat"):
            return [event]

        # Unknown event type: pass through as-is so callers can decide.
        return [event]

    # ------------------------------------------------------------------
    # Delta accumulation
    # ------------------------------------------------------------------

    def _handle_delta(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """ Append a text/field delta to the buffer for its partID.

        Detects repetitive text loops (same tiny fragment repeated many times)
        using a per-part sliding window.  When a loop is detected, a
        ``text.loop_warning`` event is emitted once per part so that:
        - The console shows a visible warning to the operator
        - The transcript records the incident for post-hoc diagnosis
        - The model/provider is not disrupted — the phase continues to run
        """
        props = event.get("properties", {})
        part_id = props.get("partID")
        field = props.get("field", "text")
        delta = props.get("delta", "")
        if not part_id or field != "text":
            return []
        if not delta:
            return []

        self._delta_buffers[part_id] = self._delta_buffers.get(part_id, "") + delta
        self._pending_part_ids.add(part_id)

        # --- Loop detection ---
        # Skip if we already warned on this part.
        if part_id in self._loop_warned:
            return []

        # Get (or initialise) the per-part sliding window and counts.
        if part_id not in self._delta_windows:
            window_size, _ = _loop_detection_params()
            self._delta_windows[part_id] = deque(maxlen=window_size)
            self._delta_counts[part_id] = {}

        window = self._delta_windows[part_id]
        counts = self._delta_counts[part_id]

        # Record this delta in the window; update its repetition count.
        window.append(delta)
        counts[delta] = counts.get(delta, 0) + 1

        _, threshold = _loop_detection_params()
        if counts[delta] > threshold:
            # Mark warned so we emit at most one warning per part.
            self._loop_warned.add(part_id)
            return [{
                "type": "text.loop_warning",
                "timestamp": event.get("timestamp", 0),
                "sessionID": props.get("sessionID", ""),
                "properties": {
                    "partID": part_id,
                    "repeatedText": delta[:100],
                    "count": counts[delta],
                },
            }]

        return []

    def _handle_updated(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """ Inject accumulated deltas into the updated part and return finalized event(s). """
        props = event.get("properties", {})
        part = props.get("part", {})
        part_id = part.get("id")

        if part_id and part_id in self._delta_buffers:
            part["text"] = self._delta_buffers.get(part_id, "")

        # Build the finalized event.
        finalized = self._build_finalized_event(event)

        if finalized:
            # Track that we've seen this part so we don't re-emit on reconnect.
            if part_id:
                self._seen_part_ids.add(part_id)
                if part_id in self._delta_buffers:
                    del self._delta_buffers[part_id]
                    self._pending_part_ids.discard(part_id)
                # Clean up loop detection state — this part is now finalized
                # and any in-progress loop warning has already been emitted.
                self._delta_windows.pop(part_id, None)
                self._delta_counts.pop(part_id, None)
                self._loop_warned.discard(part_id)
            return [finalized]
            
        return []

    def _build_finalized_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Convert a message.part.updated into the ND-JSON shape expected by render_event().

        Returns None only for parts that are not yet finalized: text and reasoning
        parts without ``time.end``, and tool parts that are still pending/running.
        Unknown part types are normalized into a ``message.part.updated`` envelope
        with a top-level ``"part"`` key instead of returning None.
        """
        props = event.get("properties", {})
        part = props.get("part", {})
        part_type = part.get("type", "")

        if part_type == "step-start":
            return {
                "type": "step_start",
                "timestamp": event.get("timestamp", 0),
                "sessionID": props.get("sessionID", ""),
                "part": part,
            }

        if part_type == "step-finish":
            return {
                "type": "step_finish",
                "timestamp": event.get("timestamp", 0),
                "sessionID": props.get("sessionID", ""),
                "part": part,
            }

        if part_type == "text":
            # Only emit when finalized (time.end exists).
            if part.get("time", {}).get("end"):
                return {
                    "type": "text",
                    "timestamp": event.get("timestamp", 0),
                    "sessionID": props.get("sessionID", ""),
                    "part": part,
                }
            return None

        if part_type == "reasoning":
            if part.get("time", {}).get("end"):
                return {
                    "type": "reasoning",
                    "timestamp": event.get("timestamp", 0),
                    "sessionID": props.get("sessionID", ""),
                    "part": part,
                }
            return None

        if part_type == "tool":
            state = part.get("state", {})
            if state.get("status") in ("completed", "error"):
                return {
                    "type": "tool_use",
                    "timestamp": event.get("timestamp", 0),
                    "sessionID": props.get("sessionID", ""),
                    "part": part,
                }
            return None

        if part_type == "patch":
            return {
                "type": "patch",
                "timestamp": event.get("timestamp", 0),
                "sessionID": props.get("sessionID", ""),
                "part": part,
            }

        # Pass through unknown part types with a normalized envelope so that
        # downstream renderers always receive a top-level "part" key.
        return {
            "type": "message.part.updated",
            "timestamp": event.get("timestamp", 0),
            "sessionID": props.get("sessionID", ""),
            "part": part,
        }

    def _map_session_diff(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Map non-empty session.diff into a compact compatibility event."""
        props = event.get("properties", {})
        diff = props.get("diff")
        if not isinstance(diff, list) or not diff:
            return None
        return {
            "type": "session.diff",
            "timestamp": event.get("timestamp", 0),
            "sessionID": props.get("sessionID", ""),
            "properties": props,
        }

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def has_seen(self, part_id: str) -> bool:
        """ Return True if we have already processed a finalized event for this part. """
        return part_id in self._seen_part_ids

    def mark_seen(self, part_id: str) -> None:
        """ Record that we have processed this part. """
        self._seen_part_ids.add(part_id)

    def is_pending(self, part_id: str) -> bool:
        """ Return True if we have seen deltas but not yet the updated event. """
        return part_id in self._pending_part_ids

    def get_pending_part_ids(self) -> set[str]:
        """ Return set of partIDs with buffered deltas awaiting finalization. """
        return set(self._pending_part_ids)
