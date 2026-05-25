# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Events package public exports.

PhaseEventLoop lives in events.phase_loop. EventLoop remains as a
backward-compatible alias for older imports. SseClient is also re-exported
for older tests and integrations that monkeypatch events.SseClient.
"""

from __future__ import annotations

from events.sse_client import SseClient, SseClientError
from events.phase_loop import PhaseEventLoop, RunResult

# Backward-compatibility alias.
EventLoop = PhaseEventLoop

__all__ = ["EventLoop", "PhaseEventLoop", "RunResult", "SseClient", "SseClientError"]
