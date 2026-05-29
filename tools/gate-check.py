#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Check readiness gates for a CodeCome phase.

Usage:

    ./tools/gate-check.py 1           # Check Phase 1 readiness
    ./tools/gate-check.py 2           # Check Phase 2 readiness
    ./tools/gate-check.py 3           # Check Phase 3 readiness
    ./tools/gate-check.py 4 CC-0001   # Check Phase 4 readiness for a specific finding
    ./tools/gate-check.py 5 CC-0001   # Check Phase 5 readiness for a specific finding
    ./tools/gate-check.py 6           # Check Phase 6 readiness

Returns exit code 0 if ready, 1 if not.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow importing sibling modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phases.gates import run_from_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check readiness gates for a CodeCome phase.",
    )
    parser.add_argument(
        "phase",
        help="Phase number (1-6) or subphase (1a, 1b, 1c).",
    )
    parser.add_argument("finding_id", nargs="?", help="Finding ID or path (required for Phase 4 and 5).")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return run_from_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
