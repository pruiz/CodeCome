# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Optional

import _colors as C

from findings.constants import (
    FINDING_ID_STRICT_RE,
    ROOT,
    FindingsContext,
)


def finding_exists(
    finding_id: str,
    *,
    ctx: Optional[FindingsContext] = None,
) -> bool:
    ctx = ctx if ctx is not None else FindingsContext.default()
    return any(ctx.findings_root.rglob(f"{finding_id}-*.md"))


def create_evidence(
    finding_id: str,
    force: bool = False,
    *,
    ctx: Optional[FindingsContext] = None,
) -> Path:
    ctx = ctx if ctx is not None else FindingsContext.default()

    if not FINDING_ID_STRICT_RE.fullmatch(finding_id):
        raise ValueError(f"Invalid finding id: {finding_id}")

    if not finding_exists(finding_id, ctx=ctx):
        raise FileNotFoundError(f"Finding not found: {finding_id}")

    if not ctx.evidence_template_path.exists():
        raise FileNotFoundError(f"Template not found: {ctx.evidence_template_path}")

    evidence_dir = ctx.evidence_root / finding_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    readme_path = evidence_dir / "README.md"

    if readme_path.exists() and not force:
        raise FileExistsError(f"Evidence README already exists: {readme_path}")

    content = ctx.evidence_template_path.read_text(encoding="utf-8")
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
