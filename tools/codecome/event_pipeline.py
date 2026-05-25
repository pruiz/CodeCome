# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Shared event side-effect pipeline: transcript, debug, reasoning filter,
render.

Used by both phase mode (``codecome.runner._consume_events``) and
chat mode (``chat.app._chat_render_and_log``) to avoid duplicated
transcript/debug/filter/render logic.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from codecome.transcript import Transcript


def render_and_log_event(
    *,
    console: Any,
    phase: str,
    label: str,
    event: dict[str, Any],
    transcript: Transcript,
    debug: bool,
    thinking_on: bool,
    render_event_fn: Callable[..., None],
    debug_fn: Callable[[str], None] | None = None,
) -> None:
    """Run the full event side-effect pipeline for one SSE event.

    1. Write the raw event to the JSONL transcript.
    2. If *debug* is True, mirror the raw event JSON:
       - via *debug_fn* (chat mode — ``_chat_debug``);
       - via ``sys.stderr`` otherwise (phase mode).
    3. If *thinking_on* is False and the event type is ``reasoning``,
       skip rendering.
    4. Otherwise call ``render_event_fn(console, phase, label, event)``.
    """
    transcript.write_event(event)

    if debug:
        if debug_fn is not None:
            debug_fn(f"raw event: {json.dumps(event)}")
        else:
            sys.stderr.write(json.dumps(event) + "\n")
            sys.stderr.flush()

    if not thinking_on and event.get("type") == "reasoning":
        return

    render_event_fn(console, phase, label, event)
