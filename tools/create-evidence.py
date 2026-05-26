#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

from findings.evidence import (
    create_evidence as _create_evidence,
    build_parser,
)

ROOT = Path(__file__).resolve().parents[1]
FINDINGS_ROOT = ROOT / "itemdb" / "findings"
EVIDENCE_ROOT = ROOT / "itemdb" / "evidence"
TEMPLATE_PATH = ROOT / "templates" / "evidence-readme.md"


def create_evidence(finding_id: str, force: bool) -> Path:
    return _create_evidence(
        finding_id,
        force,
        findings_root=FINDINGS_ROOT,
        evidence_root=EVIDENCE_ROOT,
        template_path=TEMPLATE_PATH,
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        readme_path = create_evidence(args.finding_id, args.force)
        print(C.ok(str(readme_path.relative_to(ROOT))))
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
