#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Create or initialize an evidence directory for a CodeCome finding.

Examples:

    ./tools/create-evidence.py CC-0001
    ./tools/create-evidence.py CC-0001 --force
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "templates" / "evidence-readme.md"
EVIDENCE_ROOT = ROOT / "itemdb" / "evidence"
FINDINGS_ROOT = ROOT / "itemdb" / "findings"

FINDING_ID_RE = re.compile(r"^CC-\d{4,}$")


def finding_exists(finding_id: str) -> bool:
    return any(FINDINGS_ROOT.rglob(f"{finding_id}-*.md"))


def create_evidence(finding_id: str, force: bool) -> Path:
    if not FINDING_ID_RE.fullmatch(finding_id):
        raise ValueError(f"Invalid finding id: {finding_id}")

    if not finding_exists(finding_id):
        raise FileNotFoundError(f"Finding not found: {finding_id}")

    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    evidence_dir = EVIDENCE_ROOT / finding_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    readme_path = evidence_dir / "README.md"

    if readme_path.exists() and not force:
        raise FileExistsError(f"Evidence README already exists: {readme_path}")

    content = TEMPLATE_PATH.read_text(encoding="utf-8")
    content = content.replace("CC-0000", finding_id)
    content = content.replace("YYYY-MM-DD", date.today().isoformat())

    readme_path.write_text(content, encoding="utf-8")
    return readme_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an evidence README for a CodeCome finding.",
    )

    parser.add_argument("finding_id", help="Finding id, for example CC-0001.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing evidence README.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        readme_path = create_evidence(args.finding_id, args.force)
        print(C.ok(str(readme_path.relative_to(ROOT))))
        return 0
    except ValueError as exc:
        print(f"{C.fail(str(exc))}")
        return 1
    except FileNotFoundError as exc:
        print(f"{C.fail(str(exc))}")
        return 1
    except FileExistsError as exc:
        print(f"{C.fail(str(exc))}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
