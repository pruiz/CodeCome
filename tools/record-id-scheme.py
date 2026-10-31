#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Record or show the finding-id scheme for this audit.

Called at the start of ``make phase-1``. With no arguments, prints the
saved scheme or the default ``CC-0001`` sequence.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from findings.ids import issued_numbers, next_finding_id
from findings.scheme import (
    IdSchemeError,
    bind_ledger,
    load_id_scheme,
    parse_id_scheme,
    preview_next_id,
    save_id_scheme,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record a finding-id scheme before reconnaissance.")
    parser.add_argument("--scheme", help="First id you want, for example CC-0142 or INT-0007.")
    parser.add_argument("--start", type=int, default=None, help="Override the counter in --scheme.")
    parser.add_argument("--ledger", type=Path, default=None, help="JSON ledger shared across audits.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.scheme:
            scheme = bind_ledger(parse_id_scheme(args.scheme, args.start), args.ledger)
            save_id_scheme(scheme)
            issued = issued_numbers(scheme)
            nxt, note = preview_next_id(scheme, issued)
            print(f"finding ids: {scheme.template}")
            print(f"next finding will be at least {nxt}")
            if note:
                print(note)
            return 0
        if args.start is not None or args.ledger is not None:
            raise IdSchemeError("ID_START and ID_LEDGER require ID_SCHEME.")
        saved = load_id_scheme()
        if saved is None:
            print("finding ids: CC-0001 (default)")
            return 0
        print(f"finding ids: {saved.template} (saved at phase 1)")
        print(f"next finding will be at least {next_finding_id()}")
        return 0
    except IdSchemeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
