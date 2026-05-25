# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Events package public exports.

Phase-specific imports should use events.phase_loop directly. EventLoop is
kept only as the public phase-loop alias used by the current runner.
"""

from __future__ import annotations

from events.phase_loop import PhaseEventLoop, RunResult

EventLoop = PhaseEventLoop

__all__ = ["EventLoop", "PhaseEventLoop", "RunResult"]
