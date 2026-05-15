#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Package all itemdb artifacts related to a finding into a zip file.

Usage:
    python tools/package-finding.py CC-0001

The zip is written to itemdb/evidence/CC-0001.zip and includes:
- The finding markdown file(s) from any status directory
- Evidence files under itemdb/evidence/CC-0001/
- Notes, reports, or index entries that reference the finding

The zip itself is excluded from the bundle to avoid recursive inclusion.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ITEMDB = ROOT / "itemdb"
EVIDENCE_DIR = ITEMDB / "evidence"
FINDING_ID_RE = re.compile(r"^CC-\d{4}$")


def _colorize(enabled: bool) -> dict[str, str]:
    if enabled and os.environ.get("NO_COLOR") is None:
        return {
            "bold": "\033[1m",
            "red": "\033[31m",
            "green": "\033[32m",
            "yellow": "\033[33m",
            "cyan": "\033[36m",
            "reset": "\033[0m",
        }
    return {k: "" for k in ("bold", "red", "green", "yellow", "cyan", "reset")}


def _error(msg: str, code: int = 1) -> None:
    c = _colorize(True)
    print(f"\n{c['bold']}{c['red']}[FAIL]{c['reset']} {msg}\n", file=sys.stderr)
    raise SystemExit(code)


def _warn(msg: str) -> None:
    c = _colorize(True)
    print(f"\n{c['bold']}{c['yellow']}[WARN]{c['reset']} {msg}\n", file=sys.stderr)


def _info(msg: str) -> None:
    c = _colorize(True)
    print(f"{c['bold']}{c['cyan']}[INFO]{c['reset']} {msg}")


def _ok(msg: str) -> None:
    c = _colorize(True)
    print(f"{c['bold']}{c['green']}[OK]{c['reset']} {msg}")


def validate_finding_id(finding_id: str) -> str:
    finding_id = finding_id.strip()
    if not FINDING_ID_RE.match(finding_id):
        _error(
            f"Invalid finding ID format: {finding_id!r}. Expected CC-NNNN (e.g. CC-0001).",
            code=2,
        )
    return finding_id


def discover_files(finding_id: str) -> list[Path]:
    """Return all itemdb paths that contain the finding ID, excluding the zip."""
    zip_path = EVIDENCE_DIR / f"{finding_id}.zip"
    matches: list[Path] = []

    if ITEMDB.exists():
        for path in ITEMDB.rglob("*"):
            if not path.is_file():
                continue
            if path == zip_path:
                continue
            # Match against the itemdb-relative path so that files inside
            # evidence/CC-0001/ are included even if their filename does not
            # contain the finding ID.
            if finding_id in str(path.relative_to(ITEMDB)):
                matches.append(path)

    # Sort for deterministic ordering
    matches.sort()
    return matches


def create_bundle(finding_id: str, files: list[Path], dry_run: bool = False) -> Path:
    zip_path = EVIDENCE_DIR / f"{finding_id}.zip"

    if dry_run:
        _info(f"Would create {zip_path} from {len(files)} file(s)")
        for f in files:
            print(f"  {f.relative_to(ROOT)}")
        return zip_path

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    # Overwrite existing zip cleanly
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            arcname = str(file_path.relative_to(ROOT))
            zf.write(file_path, arcname)

    return zip_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Package all itemdb artifacts for a finding into a zip file."
    )
    parser.add_argument("finding", help="Finding ID (e.g. CC-0001)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be bundled without creating the zip.",
    )
    args = parser.parse_args(argv)

    finding_id = validate_finding_id(args.finding)
    files = discover_files(finding_id)

    if not files:
        _warn(f"No files found for {finding_id} under itemdb/")
        return 1

    _info(f"Bundling {len(files)} file(s) for {finding_id}...")
    zip_path = create_bundle(finding_id, files, dry_run=args.dry_run)

    if not args.dry_run:
        _ok(f"Created {zip_path.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
