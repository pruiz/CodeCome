# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
from typing import Optional

import _colors as C

from findings.constants import FINDING_ID_STRICT_RE, ROOT, FindingsContext


def validate_finding_id(finding_id: str) -> str:
    stripped = finding_id.strip()
    if not FINDING_ID_STRICT_RE.fullmatch(stripped):
        raise ValueError(f"Invalid finding id format: {finding_id!r} (expected CC-NNNN)")
    return stripped


def discover_files(
    finding_id: str,
    *,
    ctx: Optional[FindingsContext] = None,
) -> list[Path]:
    ctx = ctx if ctx is not None else FindingsContext.default()
    zip_path = ctx.evidence_root / f"{finding_id}.zip"

    matches: list[Path] = []

    if ctx.itemdb_root.exists():
        for path in ctx.itemdb_root.rglob("*"):
            if not path.is_file():
                continue
            if path == zip_path:
                continue
            if finding_id in str(path.relative_to(ctx.itemdb_root)):
                matches.append(path)

    matches.sort()
    return matches


def create_bundle(
    finding_id: str,
    files: list[Path],
    dry_run: bool = False,
    *,
    ctx: Optional[FindingsContext] = None,
) -> Path:
    ctx = ctx if ctx is not None else FindingsContext.default()
    zip_path = ctx.evidence_root / f"{finding_id}.zip"

    if dry_run:
        print(C.info(f"Would create {zip_path} from {len(files)} file(s)"))
        for f in files:
            print(f"  {f.relative_to(ctx.root)}")
        return zip_path

    ctx.evidence_root.mkdir(parents=True, exist_ok=True)

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            arcname = str(file_path.relative_to(ctx.root))
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

    try:
        finding_id = validate_finding_id(args.finding)
    except ValueError as exc:
        print(C.fail(str(exc)))
        return 2

    ctx = FindingsContext.default()
    files = discover_files(finding_id, ctx=ctx)

    if not files:
        print(C.warn(f"No files found for {finding_id} under itemdb/"), file=sys.stderr)
        return 1

    print(C.info(f"Bundling {len(files)} file(s) for {finding_id}..."))
    zip_path = create_bundle(finding_id, files, dry_run=args.dry_run, ctx=ctx)

    if not args.dry_run:
        print(C.ok(f"Created {zip_path.relative_to(ctx.root)}"))

    return 0
