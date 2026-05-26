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
    DEFAULT_STATUS,
    FINDING_ID_FORMAT_RE,
    ROOT,
    VALID_CONFIDENCES,
    VALID_SEVERITIES,
)
from findings.constants import FindingsContext
from findings.ids import next_finding_id, slugify
from findings.frontmatter import replace_scalar_frontmatter, replace_nested_value


def create_finding(
    args: argparse.Namespace,
    *,
    ctx: Optional[FindingsContext] = None,
) -> Path:
    ctx = ctx if ctx is not None else FindingsContext.default()

    if args.severity not in VALID_SEVERITIES:
        raise ValueError(f"Invalid severity: {args.severity}")

    if args.confidence not in VALID_CONFIDENCES:
        raise ValueError(f"Invalid confidence: {args.confidence}")

    if not ctx.template_path.exists():
        raise FileNotFoundError(f"Template not found: {ctx.template_path}")

    finding_id = args.id or next_finding_id(findings_root=ctx.findings_root)

    if args.id and not FINDING_ID_FORMAT_RE.fullmatch(args.id):
        raise ValueError(f"Invalid finding id format: {args.id!r} (expected CC-NNNN)")
    slug = args.slug or slugify(args.title)
    today = date.today().isoformat()

    output_dir = ctx.findings_root / DEFAULT_STATUS
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{finding_id}-{slug}.md"

    if output_path.exists() and not args.force:
        raise FileExistsError(f"Finding already exists: {output_path}")

    content = ctx.template_path.read_text(encoding="utf-8")

    content = replace_scalar_frontmatter(content, "id", finding_id)
    content = replace_scalar_frontmatter(content, "title", args.title)
    content = replace_scalar_frontmatter(content, "status", DEFAULT_STATUS)
    content = replace_scalar_frontmatter(content, "severity", args.severity)
    content = replace_scalar_frontmatter(content, "confidence", args.confidence)
    content = replace_scalar_frontmatter(content, "category", args.category)
    content = replace_scalar_frontmatter(content, "language", args.language)
    content = replace_scalar_frontmatter(content, "target_area", args.target_area)
    content = replace_scalar_frontmatter(content, "created_at", today)
    content = replace_scalar_frontmatter(content, "updated_at", today)
    content = replace_nested_value(
        content,
        "evidence_dir",
        f"itemdb/evidence/{finding_id}",
    )
    content = replace_nested_value(
        content,
        "artifacts_dir",
        f"itemdb/evidence/{finding_id}/exploits",
    )

    content = content.replace(
        "Briefly describe the suspected vulnerability.",
        "Pending.",
        1,
    )

    output_path.write_text(content, encoding="utf-8")

    evidence_dir = ctx.evidence_root / finding_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a new CodeCome finding from the finding template.",
    )

    parser.add_argument("title", help="Finding title.")
    parser.add_argument("--id", help="Explicit finding id, for example CC-0007.")
    parser.add_argument("--slug", help="Explicit filename slug.")
    parser.add_argument("--severity", default="MEDIUM", choices=sorted(VALID_SEVERITIES))
    parser.add_argument("--confidence", default="LOW", choices=sorted(VALID_CONFIDENCES))
    parser.add_argument("--category", default="Unclassified")
    parser.add_argument("--language", default="unknown")
    parser.add_argument("--target-area", default="unknown")
    parser.add_argument("--force", action="store_true", help="Overwrite existing finding file.")

    return parser


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
