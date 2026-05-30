# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
JSONL event transcript.

Provides a ``Transcript`` class that manages the lifecycle of a JSONL
event log file: opening, writing individual events, and closing.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import IO, Any

from codecome.config import ROOT

_LOCK = threading.Lock()
_ATTEMPT_COUNTER: dict[str, int] = {}


def _transcript_dir() -> Path:
    """Return (and create) the workspace ``tmp/`` directory."""
    d = ROOT / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Transcript:
    """JSONL event transcript — handles open, write, close.

    Use the ``for_phase`` / ``for_chat`` class methods to create
    instances for the two run modes, or ``null`` for a no-op transcript
    when opening fails.
    """

    def __init__(self, path: Path, fp: IO[str] | None) -> None:
        self.path = path
        self._fp = fp

    # -- factory methods ---------------------------------------------------

    @classmethod
    def for_phase(cls, phase: str, finding: str | None) -> Transcript:
        """Open a JSONL transcript for a phase run."""
        finding_tag = (finding or "no-finding").replace("/", "_")
        key = f"{phase}-{finding_tag}"

        with _LOCK:
            counter = _ATTEMPT_COUNTER.get(key, 1)
            _ATTEMPT_COUNTER[key] = counter + 1

        path = _transcript_dir() / f"last-phase-{phase}-{finding_tag}-attempt-{counter}.jsonl"
        return cls(path, path.open("w", encoding="utf-8", buffering=1))

    @classmethod
    def for_chat(cls) -> Transcript:
        """Open a JSONL transcript for a chat session."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = _transcript_dir() / f"last-chat-{stamp}-pid{os.getpid()}.jsonl"
        return cls(path, path.open("w", encoding="utf-8", buffering=1))

    @classmethod
    def null(cls) -> Transcript:
        """Return a no-op transcript (writes are silently discarded)."""
        return cls(Path(), None)

    # -- write / close -----------------------------------------------------

    def write_event(self, event: dict[str, Any]) -> None:
        """Write one JSON-line event.  Silently ignores errors."""
        if self._fp is not None:
            try:
                self._fp.write(json.dumps(event) + "\n")
            except OSError:
                pass

    def close(self) -> None:
        """Flush and close.  Safe to call multiple times."""
        if self._fp is None:
            return
        try:
            self._fp.flush()
            self._fp.close()
        except OSError:
            pass
        self._fp = None
