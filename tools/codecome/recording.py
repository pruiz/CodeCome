# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
EventRecorder — record raw events to transcript and optional debug output.

This class intentionally does not render events and does not apply display
filtering. Rendering is handled separately by the rendering layer.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from codecome.transcript import Transcript


class EventRecorder:
    """Record raw events to transcript and optional debug output.

    This class intentionally does not render events and does not apply
    display filtering. Rendering is handled separately by the rendering layer.
    """

    def __init__(
        self,
        transcript: Transcript,
        *,
        debug: bool = False,
        debug_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.transcript = transcript
        self.debug = debug
        self.debug_fn = debug_fn

    def record(self, event: dict[str, Any]) -> None:
        self.transcript.write_event(event)
        if not self.debug:
            return

        raw = json.dumps(event)
        if self.debug_fn is not None:
            self.debug_fn(raw)
        else:
            sys.stderr.write(raw + "\n")
            sys.stderr.flush()