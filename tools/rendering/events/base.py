# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""EventRenderer base class and shared constants."""

from __future__ import annotations

import json
import time as _time
from typing import Any

from rendering.base import BaseRenderer
import _colors as C


# ---------------------------------------------------------------------------
# Finish reason classification
# ---------------------------------------------------------------------------

# Terminal OK — model stopped cleanly with a complete response.
_FINISH_TERMINAL_OK = {"stop", "end_turn"}

# Mid-turn — model was cut off mid-generation.  The session may still go idle
# and the attempt may return exit 0, but no final completion signal was produced.
# "unknown" is emitted by some providers when the stop-token mechanism fails or
# the stream ends without a canonical reason; it is not a failure mode, just an
# incomplete signal that warrants retry/resume handling.
_FINISH_MID_TURN = {"tool-calls", "tool_use", "unknown"}

_FINISH_FAILURE = {"content-filter", "content_filter", "length", "max_tokens", "error"}

# Per-session dedup state for subagent update events.
_SUBAGENT_LAST_STATE: dict[str, tuple[dict[str, Any], float]] = {}


def _reset_subagent_state() -> None:
    """Clear per-session dedup state.  Call between tests or runs."""
    _SUBAGENT_LAST_STATE.clear()


# ---------------------------------------------------------------------------
# EventRenderer base
# ---------------------------------------------------------------------------

class EventRenderer(BaseRenderer):
    event_types: tuple[str, ...] = ()

    def render(self, event: dict[str, Any]) -> bool:
        raise NotImplementedError


def _clear_hidden_reasoning_state(context: Any) -> None:
    context.hidden_reasoning_active = False
    context.hidden_reasoning_started_at = 0.0
    context.last_hidden_reasoning_rendered_at = 0.0
