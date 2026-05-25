# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _colors as C

from findings import constants as _C
from findings.constants import ROOT, FINDING_ID_STRICT_RE


def validate_finding_id(finding_id: str) -> str:
    stripped = finding_id.strip()
    if not FINDING_ID_STRICT_RE.fullmatch(stripped):
        print(C.fail(f"Invalid finding id format: {finding_id!r} (expected CC-NNNN)"))
        raise SystemExit(2)
    return stripped


def discover_files(
    finding_id: str,
    *,
    itemdb: Optional[Path] = None,
    evidence_root: Optional[Path] = None,
) -> list[Path]:
    itemdb = itemdb if itemdb is not None else _C.ROOT / "itemdb"
    evidence_root = evidence_root if evidence_root is not None else _C.EVIDENCE_ROOT
    zip_path = evidence_root / f"{finding_id}.zip"

    matches: list[Path] = []

    if itemdb.exists():
        for path in itemdb.rglob("*"):
            if not path.is_file():
                continue
            if path == zip_path:
                continue
            if finding_id in str(path.relative_to(itemdb)):
                matches.append(path)

    matches.sort()
    return matches


def create_bundle(
    finding_id: str,
    files: list[Path],
    dry_run: bool = False,
    *,
    evidence_root: Optional[Path] = None,
    root: Optional[Path] = None,
) -> Path:
    evidence_root = evidence_root if evidence_root is not None else _C.EVIDENCE_ROOT
    root = root if root is not None else _C.ROOT
    zip_path = evidence_root / f"{finding_id}.zip"

    if dry_run:
        print(C.info(f"Would create {zip_path} from {len(files)} file(s)"))
        for f in files:
            print(f"  {f.relative_to(root)}")
        return zip_path

    evidence_root.mkdir(parents=True, exist_ok=True)

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            arcname = str(file_path.relative_to(root))
            zf.write(file_path, arcname)
            print(C.ok(f"  added: {arcname}"))

    return zip_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Package all itemdb artifacts for a finding into a zip file.",
    )

    parser.add_argument("finding", help="Finding ID (e.g. CC-0001)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be bundled without creating the zip.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    finding_id = validate_finding_id(args.finding)
    files = discover_files(finding_id)

    if not files:
        print(C.warn(f"No files found for {finding_id} under itemdb/"), file=sys.stderr)
        return 1

    print(C.info(f"Bundling {len(files)} file(s) for {finding_id}..."))
    zip_path = create_bundle(finding_id, files, dry_run=args.dry_run)

    if not args.dry_run:
        print(C.ok(f"Created {zip_path.relative_to(ROOT)}"))

    return 0
