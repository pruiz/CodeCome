# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import _colors as C

from findings.constants import (
    EVIDENCE_ROOT,
    EVIDENCE_TEMPLATE_PATH,
    FINDINGS_ROOT,
    FINDING_ID_STRICT_RE,
    ROOT,
)


def finding_exists(
    finding_id: str,
    *,
    findings_root: Optional[Path] = None,
) -> bool:
    findings_root = findings_root if findings_root is not None else FINDINGS_ROOT
    return any(findings_root.rglob(f"{finding_id}-*.md"))


def create_evidence(
    finding_id: str,
    force: bool,
    *,
    findings_root: Optional[Path] = None,
    evidence_root: Optional[Path] = None,
    template_path: Optional[Path] = None,
) -> Path:
    findings_root = findings_root if findings_root is not None else FINDINGS_ROOT
    evidence_root = evidence_root if evidence_root is not None else EVIDENCE_ROOT
    template_path = template_path if template_path is not None else _C.EVIDENCE_TEMPLATE_PATH

    if not FINDING_ID_STRICT_RE.fullmatch(finding_id):
        raise ValueError(f"Invalid finding id: {finding_id}")

    if not finding_exists(finding_id, findings_root=findings_root):
        raise FileNotFoundError(f"Finding not found: {finding_id}")

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    evidence_dir = evidence_root / finding_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    readme_path = evidence_dir / "README.md"

    if readme_path.exists() and not force:
        raise FileExistsError(f"Evidence README already exists: {readme_path}")

    content = template_path.read_text(encoding="utf-8")
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
        print(C.fail(str(exc)))
        return 1
    except FileNotFoundError as exc:
        print(C.fail(str(exc)))
        return 1
    except FileExistsError as exc:
        print(C.fail(str(exc)))
        return 1
