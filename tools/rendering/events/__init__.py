# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Event renderers package — one module per renderer family.

This ``__init__`` re-exports all public symbols so that existing
``from rendering.events import ...`` imports continue to work.
"""

from __future__ import annotations

# Base class + constants
from rendering.events.base import (
    EventRenderer,
    _FINISH_TERMINAL_OK,
    _FINISH_MID_TURN,
    _FINISH_FAILURE,
    _SUBAGENT_LAST_STATE,
    _reset_subagent_state,
)

# Individual renderers
from rendering.events.step_start import StepStartRenderer
from rendering.events.text import TextEventRenderer
from rendering.events.reasoning import ReasoningEventRenderer
from rendering.events.tool_use import ToolUseEventRenderer
from rendering.events.step_finish import StepFinishRenderer
from rendering.events.error import ErrorEventRenderer
from rendering.events.session_status import SessionStatusRenderer
from rendering.events.server import ServerConnectedRenderer, ServerHeartbeatRenderer
from rendering.events.session_diff import SessionDiffRenderer
from rendering.events.message import MessageUpdatedRenderer
from rendering.events.subagent import SubagentStatusRenderer
from rendering.events.unknown import UnknownEventRenderer

__all__ = [
    "EventRenderer",
    "_FINISH_TERMINAL_OK",
    "_FINISH_MID_TURN",
    "_FINISH_FAILURE",
    "_SUBAGENT_LAST_STATE",
    "_reset_subagent_state",
    "StepStartRenderer",
    "TextEventRenderer",
    "ReasoningEventRenderer",
    "ToolUseEventRenderer",
    "StepFinishRenderer",
    "ErrorEventRenderer",
    "SessionStatusRenderer",
    "ServerConnectedRenderer",
    "ServerHeartbeatRenderer",
    "SessionDiffRenderer",
    "MessageUpdatedRenderer",
    "SubagentStatusRenderer",
    "UnknownEventRenderer",
]
