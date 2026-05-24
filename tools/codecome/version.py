# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
OpenCode version checks.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MINIMUM_OPENCODE_VERSION = "1.14.50"


def check_opencode_version() -> None:
    try:
        result = subprocess.run(["opencode", "--version"], capture_output=True, text=True)
    except FileNotFoundError:
        print(_fail("OpenCode is not installed or not in PATH."), file=sys.stderr)
        sys.exit(1)

    if result.returncode != 0:
        print(_fail(f"Failed to check OpenCode version (exit code {result.returncode})."), file=sys.stderr)
        sys.exit(1)

    version_str = result.stdout.strip().split()[-1]

    def parse_ver(v: str) -> tuple[int, ...]:
        match = re.search(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", v)
        if match:
            return tuple(int(x) for x in match.groups() if x is not None)
        return (0,)

    actual = parse_ver(version_str)
    required = parse_ver(MINIMUM_OPENCODE_VERSION)

    if actual < required:
        print(_fail(f"OpenCode version is too old: found {version_str}, require >= {MINIMUM_OPENCODE_VERSION}"), file=sys.stderr)
        sys.exit(1)


# Minimal inline color helpers to avoid importing _colors (which lives in
# the parent tools/ directory, not here).
def _fail(message: str) -> str:
    if sys.stdout.isatty() and not _no_color():
        return f"\033[31m\u2718\033[0m {message}"
    return f"[FAIL] {message}"


def _no_color() -> bool:
    import os
    return os.environ.get("NO_COLOR") is not None
