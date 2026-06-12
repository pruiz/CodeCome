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


def _loop_detection_params() -> tuple[int, float, int, int]:
    """Return (min_deltas, window, ratio_threshold, streak) for loop detection.

    CODECOME_LOOP_MIN_DELTAS      — min deltas before detection activates (default 200)
    CODECOME_LOOP_RATIO_WINDOW    — sliding window size for computing unique ratio
                                    (default 500)
    CODECOME_LOOP_RATIO_THRESHOLD — unique/total ratio below which a window is
                                    considered low-diversity (default 0.10)
    CODECOME_LOOP_RATIO_STREAK    — consecutive low-ratio windows required to
                                    trigger a warning (default 3)

    Reads directly from ``os.environ`` on every call so that tests using
    ``monkeypatch.setenv`` work correctly regardless of import order.
    """
    try:
        min_deltas = int(os.environ.get("CODECOME_LOOP_MIN_DELTAS", "200"))
        min_deltas = max(min_deltas, 1)
    except (ValueError, TypeError):
        min_deltas = 200
    try:
        window = int(os.environ.get("CODECOME_LOOP_RATIO_WINDOW", "500"))
        window = max(window, 1)
    except (ValueError, TypeError):
        window = 500
    try:
        ratio_threshold = float(os.environ.get("CODECOME_LOOP_RATIO_THRESHOLD", "0.10"))
        if ratio_threshold <= 0:
            ratio_threshold = 0.10
        if ratio_threshold > 1:
            ratio_threshold = 1.0
    except (ValueError, TypeError):
        ratio_threshold = 0.10
    try:
        streak = int(os.environ.get("CODECOME_LOOP_RATIO_STREAK", "3"))
        streak = max(streak, 1)
    except (ValueError, TypeError):
        streak = 3
    return (min_deltas, window, ratio_threshold, streak)


class StateTracker:
    """ Accumulate deltas, track part versions, detect finalized parts. """

    def __init__(self) -> None:
        # Map partID -> accumulated text buffer.
        self._delta_buffers: dict[str, str] = {}
        # Set of partIDs we have already "finalized" (yielded as updated).
        self._seen_part_ids: set[str] = set()
        # Set of partIDs for which we saw delta but not yet updated.
        self._pending_part_ids: set[str] = set()

        # --- Repetitive text-loop detection (ratio-based) ---
        # Per-part sliding window of recent text delta strings.
        self._delta_windows: dict[str, deque[str]] = {}
        # Running count of total deltas received per part.
        self._total_delta_count: dict[str, int] = {}
        # Consecutive low-diversity window count per part.
        self._low_ratio_streak: dict[str, int] = {}
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

        if event_type in ("session.updated",
                          "plugin.added", "connector.updated",
                          "reference.updated"):
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

        # --- Loop detection (ratio-based) ---
        # Skip if we already warned on this part.
        if part_id in self._loop_warned:
            return []

        min_deltas, window_size, ratio_threshold, streak_req = _loop_detection_params()

        # Initialize per-part state on first delta.
        if part_id not in self._delta_windows:
            self._delta_windows[part_id] = deque(maxlen=window_size)
            self._total_delta_count[part_id] = 0
            self._low_ratio_streak[part_id] = 0

        self._delta_windows[part_id].append(delta)
        self._total_delta_count[part_id] += 1
        total = self._total_delta_count[part_id]

        # Do not inspect parts that are too short for a reliable signal.
        if total < min_deltas:
            return []

        # Check every check_interval deltas to avoid per-delta overhead.
        check_interval = max(1, window_size // 4)
        if total % check_interval != 0:
            return []

        recent = list(self._delta_windows[part_id])
        unique_count = len(set(recent))
        ratio = unique_count / len(recent) if recent else 1.0

        if ratio < ratio_threshold:
            self._low_ratio_streak[part_id] += 1
            if self._low_ratio_streak[part_id] >= streak_req:
                self._loop_warned.add(part_id)
                return [{
                    "type": "text.loop_warning",
                    "timestamp": event.get("timestamp", 0),
                    "sessionID": props.get("sessionID", ""),
                    "properties": {
                        "partID": part_id,
                        "uniqueRatio": round(ratio, 4),
                        "windowSize": len(recent),
                        "totalDeltas": total,
                    },
                }]
        else:
            # Ratio went back above threshold — reset streak.
            self._low_ratio_streak[part_id] = 0

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
                self._total_delta_count.pop(part_id, None)
                self._low_ratio_streak.pop(part_id, None)
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
