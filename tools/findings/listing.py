# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import _colors as C
from pathlib import Path
from typing import Dict, List, Optional

from findings.constants import FINDINGS_ROOT, ROOT, STATUSES
from findings.frontmatter import load_frontmatter
from findings.ids import extract_id_from_path


def load_findings(
    status_filter: Optional[str],
    *,
    root: Optional[Path] = None,
    findings_root: Optional[Path] = None,
    statuses: Optional[List[str]] = None,
) -> List[Dict[str, object]]:
    """Load findings from the filesystem.
    
    Constants default to findings.constants values but can be overridden
    (e.g., by wrappers that need test-patched paths).
    """
    root = root if root is not None else ROOT
    findings_root = findings_root if findings_root is not None else FINDINGS_ROOT
    statuses = statuses if statuses is not None else STATUSES
    
    rows: List[Dict[str, object]] = []
    status_list = [status_filter] if status_filter else statuses

    for status in status_list:
        status_dir = findings_root / status
        if not status_dir.exists():
            continue

        for path in sorted(status_dir.glob("CC-*.md")):
            frontmatter = load_frontmatter(path)

            rows.append(
                {
                    "id": frontmatter.get("id", extract_id_from_path(path)),
                    "status": frontmatter.get("status", path.parent.name),
                    "severity": frontmatter.get("severity", ""),
                    "confidence": frontmatter.get("confidence", ""),
                    "exploitation_status": (
                        frontmatter.get("exploitation", {}).get("status", "")
                        if isinstance(frontmatter.get("exploitation"), dict)
                        else ""
                    ),
                    "title": frontmatter.get("title", path.stem),
                    "path": str(path.relative_to(root)),
                }
            )

    rows.sort(key=lambda row: str(row["id"]))
    return rows


def print_plain(rows: List[Dict[str, object]]) -> None:
    if not rows:
        print(C.info("No findings."))
        return

    for row in rows:
        sid = str(row["id"])
        sev = C.severity_color(str(row["severity"]))
        conf = C.confidence_color(str(row["confidence"]))
        stat = C.status_color(str(row["status"]))
        print(
            f'{C.BOLD}{sid}{C.RESET} '
            f'[{stat}] '
            f'{sev}/{conf} '
            f'- {row["title"]} '
            f'{C.DIM}({row["path"]}){C.RESET}'
        )


def print_markdown(rows: List[Dict[str, object]]) -> None:
    print("| ID | Status | Severity | Confidence | Title | Path |")
    print("|---|---|---|---|---|---|")

    if not rows:
        print("| - | - | - | - | No findings yet. | - |")
        return

    for row in rows:
        print(
            f'| {row["id"]} '
            f'| {row["status"]} '
            f'| {row["severity"]} '
            f'| {row["confidence"]} '
            f'| {row["title"]} '
            f'| `{row["path"]}` |'
        )


def print_ids(rows: List[Dict[str, object]]) -> None:
    for row in rows:
        print(row["id"])


def filter_eligible_for_exploit(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    eligible_statuses = {"", "NOT_STARTED", "IN_PROGRESS"}
    return [
        row
        for row in rows
        if row["status"] == "CONFIRMED" and str(row.get("exploitation_status", "")) in eligible_statuses
    ]


def build_parser():
    import argparse
    parser = argparse.ArgumentParser(description="List CodeCome findings.")

    parser.add_argument(
        "--status",
        choices=STATUSES,
        help="Only list findings with this status directory.",
    )

    parser.add_argument(
        "--format",
        choices=["plain", "markdown", "ids"],
        default="plain",
        help="Output format.",
    )

    parser.add_argument(
        "--eligible-for-exploit",
        action="store_true",
        help="Only list CONFIRMED findings that have not already been exploited or marked not feasible.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    rows = load_findings(args.status)

    if args.eligible_for_exploit:
        rows = filter_eligible_for_exploit(rows)

    if args.format == "markdown":
        print_markdown(rows)
    elif args.format == "ids":
        print_ids(rows)
    else:
        print_plain(rows)

    return 0