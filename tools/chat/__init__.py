# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Chat package: Textual-based interactive chat TUI for CodeCome.

Submodules:
  - chat.debug:   chat-specific debug logging helpers.
  - chat.app:     Textual UI classes and render/log helpers.
  - chat.harness: chat-mode entry point.

Keep this package initializer lightweight. Importing `chat` should not
pull in Textual-adjacent modules or the chat harness eagerly.
"""

from __future__ import annotations

__all__ = []
