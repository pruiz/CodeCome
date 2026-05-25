# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Chat package: Textual-based interactive chat TUI for CodeCome.

Provides:
  - chat.debug:  chat-specific debug logging helpers.
  - chat.app:    Textual UI classes (ChatApp, QuitScreen, TextualConsoleProxy).
  - chat.harness: chat-mode entry point (_run_chat_mode).
"""

from __future__ import annotations

from chat.debug import _setup_chat_debug, _chat_debug, _close_chat_debug
from chat.app import ChatApp, QuitScreen, TextualConsoleProxy
from chat.harness import _run_chat_mode

__all__ = [
    "_setup_chat_debug",
    "_chat_debug",
    "_close_chat_debug",
    "ChatApp",
    "QuitScreen",
    "TextualConsoleProxy",
    "_run_chat_mode",
]
