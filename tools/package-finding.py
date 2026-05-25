#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from findings.package import (
    validate_finding_id,
    discover_files as _discover_files,
    create_bundle as _create_bundle,
    build_parser,
)
from findings import EVIDENCE_ROOT

ROOT = Path(__file__).resolve().parents[1]
ITEMDB = ROOT / "itemdb"
FINDINGS_ROOT = ROOT / "itemdb" / "findings"
EVIDENCE_DIR = EVIDENCE_ROOT


def discover_files(finding_id: str) -> list[Path]:
    return _discover_files(finding_id, itemdb=ITEMDB, evidence_root=EVIDENCE_DIR)


def create_bundle(finding_id: str, files: list[Path], dry_run: bool = False) -> Path:
    return _create_bundle(finding_id, files, dry_run=dry_run, evidence_root=EVIDENCE_DIR, root=ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    finding_id = validate_finding_id(args.finding)
    files = discover_files(finding_id)

    if not files:
        import _colors as C
        print(C.warn(f"No files found for {finding_id} under itemdb/"), file=sys.stderr)
        return 1

    import _colors as C
    print(C.info(f"Bundling {len(files)} file(s) for {finding_id}..."))
    zip_path = create_bundle(finding_id, files, dry_run=args.dry_run)

    if not args.dry_run:
        print(C.ok(f"Created {zip_path.relative_to(ROOT)}"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
