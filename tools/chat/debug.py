# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Chat debug logging: per-process diagnostic log for --chat --debug.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _colors as C  # noqa: E402, F401 — used indirectly via other modules

_CHAT_DEBUG_FP: Any = None


def _chat_debug(msg: str) -> None:
    """Write a debug message if chat debug logging is active."""
    global _CHAT_DEBUG_FP
    if _CHAT_DEBUG_FP is None:
        return
    import threading as _threading
    _elapsed = time.time() - _CHAT_DEBUG_FP.start_time  # type: ignore[attr-defined]
    _thread = _threading.current_thread().name
    _line = f"[{_elapsed:07.3f}s] [{_thread}] {msg}\n"
    _CHAT_DEBUG_FP.write(_line)  # type: ignore[union-attr]
    _CHAT_DEBUG_FP.flush()  # type: ignore[union-attr]


def _setup_chat_debug() -> None:
    """Open tmp/chat-debug-<pid>-<ts>.log for chat diagnostic logging."""
    global _CHAT_DEBUG_FP
    ROOT = Path(__file__).resolve().parents[2]
    _stamp = time.strftime("%Y%m%d-%H%M%S")
    log_dir = ROOT / "tmp"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"chat-debug-{os.getpid()}-{_stamp}.log"
    _CHAT_DEBUG_FP = log_path.open("a", buffering=1)
    _CHAT_DEBUG_FP.start_time = time.time()  # type: ignore[attr-defined]
    _chat_debug(f"debug log opened: {log_path}")
    print(f"[chat-debug] writing diagnostics to {log_path}", file=sys.stderr)


def _close_chat_debug() -> None:
    """Close the chat debug log if open."""
    global _CHAT_DEBUG_FP
    if _CHAT_DEBUG_FP is not None:
        _chat_debug("debug log closing")
        _CHAT_DEBUG_FP.close()
        _CHAT_DEBUG_FP = None
