# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Shared terminal color and symbol utilities for CodeCome CLI tools.

Respects the NO_COLOR environment variable (https://no-color.org/)
and auto-detects whether stdout is a TTY.
"""

from __future__ import annotations

import os
import sys

# --- Auto-detection -----------------------------------------------------------

_COLOR_ENABLED: bool = (
    sys.stdout.isatty()
    and os.environ.get("NO_COLOR") is None
    and os.environ.get("TERM") != "dumb"
)


def color_enabled() -> bool:
    return _COLOR_ENABLED


# --- ANSI escape codes -------------------------------------------------------

if _COLOR_ENABLED:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BOLD_RED = "\033[1;31m"
    BOLD_GREEN = "\033[1;32m"
    BOLD_YELLOW = "\033[1;33m"
    BOLD_CYAN = "\033[1;36m"
else:
    RESET = ""
    BOLD = ""
    DIM = ""
    RED = ""
    GREEN = ""
    YELLOW = ""
    BLUE = ""
    MAGENTA = ""
    CYAN = ""
    WHITE = ""
    BOLD_RED = ""
    BOLD_GREEN = ""
    BOLD_YELLOW = ""
    BOLD_CYAN = ""


# --- Unicode symbols ----------------------------------------------------------

if _COLOR_ENABLED:
    SYM_OK = "\u2714"       # checkmark
    SYM_FAIL = "\u2718"     # cross
    SYM_WARN = "\u26a0"     # warning triangle
    SYM_BULLET = "\u2022"   # bullet
    SYM_ARROW = "\u2192"    # right arrow
    SYM_DASH = "\u2500"     # box drawing horizontal
else:
    SYM_OK = "[OK]"
    SYM_FAIL = "[FAIL]"
    SYM_WARN = "[WARN]"
    SYM_BULLET = "-"
    SYM_ARROW = "->"
    SYM_DASH = "-"


# --- Colorize helpers ---------------------------------------------------------

def colorize(text: str, color: str) -> str:
    """Wrap text in an ANSI color code with reset."""
    if not color:
        return text
    return f"{color}{text}{RESET}"


# --- Capability / Status coloring ---------------------------------------------

# Effect-band ranks from findings.capability.taxonomy.BANDS (higher = worse).
_EFFECT_BAND_COLORS = {
    4: BOLD_RED,  # execute-on-host
    3: RED,       # execute-in-app / actuate / impersonate / write-security / read-secrets
    2: YELLOW,    # destroy / write-data / read-sensitive
    1: CYAN,      # read-public
    0: DIM,       # none
}

_EFFECT_TO_BAND = {
    "execute-on-host": 4,
    "execute-in-app": 3,
    "actuate": 3,
    "impersonate": 3,
    "write-security": 3,
    "read-secrets": 3,
    "destroy": 2,
    "write-data": 2,
    "read-sensitive": 2,
    "read-public": 1,
    "none": 0,
}

_STATUS_COLORS = {
    "EXPLOITED": MAGENTA,
    "CONFIRMED": BOLD_GREEN,
    "PENDING": YELLOW,
    "REJECTED": DIM,
    "DUPLICATE": DIM,
}

_CONFIDENCE_COLORS = {
    "CONFIRMED": BOLD_GREEN,
    "HIGH": GREEN,
    "MEDIUM": YELLOW,
    "LOW": DIM,
}


def capability_color(label: str, *, effect: str = "") -> str:
    """Return the colored capability short class (effect/boundary)."""
    band = _EFFECT_TO_BAND.get(effect, _EFFECT_TO_BAND.get(label.split("/", 1)[0], -1))
    color = _EFFECT_BAND_COLORS.get(band, "")
    return colorize(label, color) if label else label


def severity_color(severity: str) -> str:
    """Deprecated alias: treat input as a capability short class or effect id."""
    return capability_color(severity)


def status_color(status: str) -> str:
    """Return the colored status string."""
    color = _STATUS_COLORS.get(status, "")
    return colorize(status, color)


def confidence_color(confidence: str) -> str:
    """Return the colored confidence string."""
    color = _CONFIDENCE_COLORS.get(confidence, "")
    return colorize(confidence, color)


# --- Message helpers ----------------------------------------------------------

def ok(message: str) -> str:
    """Format a success message."""
    return f"{GREEN}{SYM_OK}{RESET} {message}"


def fail(message: str) -> str:
    """Format an error message."""
    return f"{RED}{SYM_FAIL}{RESET} {message}"


def warn(message: str) -> str:
    """Format a warning message."""
    return f"{YELLOW}{SYM_WARN}{RESET} {message}"


def info(message: str) -> str:
    """Format an info message."""
    return f"{CYAN}{SYM_BULLET}{RESET} {message}"


def header(message: str) -> str:
    """Format a section header."""
    return f"{BOLD}{message}{RESET}"


def transition(from_status: str, to_status: str) -> str:
    """Format a status transition arrow."""
    return f"{status_color(from_status)} {SYM_ARROW} {status_color(to_status)}"
