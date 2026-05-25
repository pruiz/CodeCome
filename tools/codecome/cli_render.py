# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
CLI rendering helpers: console construction and fatal error display.

The rendering dispatcher and context cache live in ``rendering.dispatch``.
This module re-exports key symbols for backward compatibility with
existing imports from ``codecome.cli_render``.
"""

from __future__ import annotations

import sys
from typing import Any

# Re-exports from rendering.dispatch — used by cli.py, chat/, runner.py
from rendering.dispatch import (  # noqa: F401 — re-export
    HAVE_RICH,
    _get_rendering_ctx,
    render_event,
)

from codecome.config import ROOT  # noqa: F401 — re-export

# Re-exports of finish constants (used by cli.py's retry loop)
from rendering.events import (  # noqa: F401 — re-export
    _FINISH_TERMINAL_OK,
    _FINISH_MID_TURN,
    _FINISH_FAILURE,
)


# ---------------------------------------------------------------------------
# Console builder (CLI concern — depends on Rich availability)
# ---------------------------------------------------------------------------

def build_console(color_mode: str) -> Any:
    """Build a Rich Console based on color mode, or None if Rich is unavailable."""
    if not HAVE_RICH:
        return None
    from rich.console import Console
    if color_mode == "always":
        return Console(force_terminal=True, highlight=False)
    if color_mode == "never":
        return Console(force_terminal=False, no_color=True, highlight=False)
    return Console(highlight=False)


# ---------------------------------------------------------------------------
# Fatal error display (CLI concern)
# ---------------------------------------------------------------------------

def _emit_fatal_error(console: Any, title: str, message: str) -> None:
    import _colors as C
    formatted = C.fail(f"{title}: {message}")
    if HAVE_RICH:
        from rich.panel import Panel
        from rich.text import Text
        console.print(Panel(Text(message, style="red"), title=title, border_style="red"))
    print(formatted, file=sys.stderr)
