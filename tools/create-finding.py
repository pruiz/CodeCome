#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

from findings.constants import FindingsContext
from findings.create import (
    create_finding as _create_finding,
    build_parser,
)

ROOT = Path(__file__).resolve().parents[1]
ITEMDB = ROOT / "itemdb"
FINDINGS_ROOT = ROOT / "itemdb" / "findings"
TEMPLATE_PATH = ROOT / "templates" / "finding.md"


def create_finding(args):
    ctx = FindingsContext(
        root=ROOT,
        findings_root=FINDINGS_ROOT,
        evidence_root=ROOT / "itemdb" / "evidence",
        notes_root=ROOT / "itemdb" / "notes",
        template_path=TEMPLATE_PATH,
        evidence_template_path=ROOT / "templates" / "evidence-readme.md",
        statuses=["PENDING", "CONFIRMED", "EXPLOITED", "REJECTED", "DUPLICATE"],
        statuses_set=frozenset({"PENDING", "CONFIRMED", "EXPLOITED", "REJECTED", "DUPLICATE"}),
    )
    return _create_finding(args, ctx=ctx)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        output_path = create_finding(args)
        print(C.ok(str(output_path.relative_to(ROOT))))
        return 0
    except ValueError as exc:
        print(C.fail(str(exc)))
        return 1
    except FileNotFoundError as exc:
        print(C.fail(str(exc)))
        return 1
    except FileExistsError as exc:
        print(C.fail(str(exc)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
