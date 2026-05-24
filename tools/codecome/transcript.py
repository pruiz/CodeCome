# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Transcript path naming, opening, writing, and closing helpers.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import IO, Any

ROOT = Path(__file__).resolve().parents[2]

_LOCK = threading.Lock()
_ATTEMPT_COUNTER: dict[str, int] = {}


def _transcript_dir() -> Path:
    d = ROOT / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def open_phase_transcript(phase: str, finding: str | None) -> tuple[Path, IO[str] | None]:
    finding_tag = (finding or "no-finding").replace("/", "_")
    key = f"{phase}-{finding_tag}"

    with _LOCK:
        counter = _ATTEMPT_COUNTER.get(key, 1)
        _ATTEMPT_COUNTER[key] = counter + 1

    path = _transcript_dir() / f"last-phase-{phase}-{finding_tag}-attempt-{counter}.jsonl"
    try:
        return path, path.open("w", encoding="utf-8")
    except OSError:
        return path, None


def open_chat_transcript() -> tuple[Path, IO[str] | None]:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = _transcript_dir() / f"last-chat-{stamp}-pid{os.getpid()}.jsonl"
    try:
        return path, path.open("w", encoding="utf-8", buffering=1)
    except OSError:
        return path, None


def close_transcript(fp: IO[str] | None) -> None:
    if fp is None:
        return
    try:
        fp.flush()
        fp.close()
    except OSError:
        pass
