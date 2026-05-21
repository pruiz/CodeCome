# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Thin wrappers that bridge mapped events to existing render_event() in run-agent.py.

This module avoids circular imports by accepting the render_event function
as a callable argument rather than importing it directly.
"""

from __future__ import annotations

from typing import Any, Callable


def emit_event(
    render_fn: Callable[[Any, str, str, dict[str, Any]], None],
    console: Any,
    phase: str,
    label: str,
    event: dict[str, Any],
) -> None:
    """ Forward a mapped ND-JSON event to the existing render_event().

    Args:
        render_fn: typically run_agent.render_event
        console: rich Console or None
        phase: phase number string
        label: human-readable phase label
        event: the mapped ND-JSON event dict
    """
    render_fn(console, phase, label, event)
