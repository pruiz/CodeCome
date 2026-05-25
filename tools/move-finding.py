#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from findings import _colors as C
from findings.ids import find_finding as _find_finding
from findings.move import (
    move_finding as _move_finding,
    build_parser,
)

ROOT = Path(__file__).resolve().parents[1]
FINDINGS_ROOT = ROOT / "itemdb" / "findings"
STATUSES = frozenset({"PENDING", "CONFIRMED", "EXPLOITED", "REJECTED", "DUPLICATE"})


def find_finding(identifier: str) -> Path:
    return _find_finding(identifier, findings_root=FINDINGS_ROOT, root=ROOT)


def move_finding(path: Path, status: str) -> Path:
    return _move_finding(path, status, findings_root=FINDINGS_ROOT, statuses_set=STATUSES)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        path = find_finding(args.finding)
        old_status = path.parent.name
        target_path = move_finding(path, args.status)

        print(f"{C.ok(str(target_path.relative_to(ROOT)))} {C.transition(old_status, args.status)}")
        return 0
    except FileNotFoundError as exc:
        print(C.fail(str(exc)))
        return 1
    except RuntimeError as exc:
        print(C.fail(str(exc)))
        return 1
    except ValueError as exc:
        print(C.fail(str(exc)))
        return 1
    except FileExistsError as exc:
        print(C.fail(str(exc)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
