# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Accumulate SSE streaming deltas and track part state transitions.

The server sends `message.part.delta` events with tiny text fragments.
This module accumulates them by partID and produces finalized part
snapshots when the corresponding `message.part.updated` arrives.
"""

from __future__ import annotations

from typing import Any


class StateTracker:
    """ Accumulate deltas, track part versions, detect finalized parts. """

    def __init__(self) -> None:
        # Map partID -> accumulated text buffer.
        self._delta_buffers: dict[str, str] = {}
        # Set of partIDs we have already "finalized" (yielded as updated).
        self._seen_part_ids: set[str] = set()
        # Set of partIDs for which we saw delta but not yet updated.
        self._pending_part_ids: set[str] = set()

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
            self._handle_delta(event)
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

    def _handle_delta(self, event: dict[str, Any]) -> None:
        """ Append a text/field delta to the buffer for its partID. """
        props = event.get("properties", {})
        part_id = props.get("partID")
        field = props.get("field", "text")
        delta = props.get("delta", "")
        if not part_id or field != "text":
            return
        if delta:
            self._delta_buffers[part_id] = self._delta_buffers.get(part_id, "") + delta
            self._pending_part_ids.add(part_id)

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
                # Now it's safe to clear the buffer
                if part_id in self._delta_buffers:
                    del self._delta_buffers[part_id]
                    self._pending_part_ids.discard(part_id)
            return [finalized]
            
        return []

    def _build_finalized_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """ Convert a message.part.updated into the ND-JSON shape expected by render_event().

        Returns None for event types we don't translate yet (e.g. async progress).
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

        # Pass through unknown part types as raw event.
        return event

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

    def is_pending(self, part_id: str) -> bool:
        """ Return True if we have seen deltas but not yet the updated event. """
        return part_id in self._pending_part_ids

    def get_pending_part_ids(self) -> set[str]:
        """ Return set of partIDs with buffered deltas awaiting finalization. """
        return set(self._pending_part_ids)
