# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _colors as C

from findings.frontmatter import load_frontmatter
from findings.ids import iter_findings, extract_id_from_path


_findings_pkg = __import__("findings", fromlist=["ROOT"])


def _wrapper():
    return __import__("render_index", fromlist=["ROOT", "FINDINGS_ROOT", "STATUSES"])


def _get_root() -> Path:
    return _wrapper().ROOT


def _get_findings_root() -> Path:
    return _wrapper().FINDINGS_ROOT


def _get_statuses() -> List[str]:
    return _wrapper().STATUSES


def load_findings() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    for path in iter_findings(None):
        frontmatter = load_frontmatter(path)

        exploitation = frontmatter.get("exploitation")
        exploitation_status = ""
        if isinstance(exploitation, dict):
            exploitation_status = str(exploitation.get("status", ""))

        validation = frontmatter.get("validation")
        validation_status = ""
        if isinstance(validation, dict):
            validation_status = str(validation.get("status", ""))

        rows.append(
            {
                "id": str(frontmatter.get("id", extract_id_from_path(path))),
                "status": str(frontmatter.get("status", path.parent.name)),
                "severity": str(frontmatter.get("severity", "")),
                "confidence": str(frontmatter.get("confidence", "")),
                "exploitation_status": exploitation_status,
                "validation_status": validation_status,
                "title": str(frontmatter.get("title", path.stem)),
                "finding_path": str(path.relative_to(_get_root())),
            }
        )

    rows.sort(key=lambda row: row["id"])
    return rows


def count_by_status(rows: List[Dict[str, str]]) -> Dict[str, int]:
    statuses = _get_statuses()
    counts: Dict[str, int] = {s: 0 for s in statuses}
    for row in rows:
        s = row["status"]
        if s in counts:
            counts[s] += 1
    return counts


def render_index(rows: List[Dict[str, str]]) -> str:
    counts = count_by_status(rows)
    statuses = _get_statuses()
    lines: List[str] = []
    today = date.today().isoformat()

    lines.append("# CodeCome Finding Index")
    lines.append("")
    lines.append(f"_Generated: {today}_")
    lines.append("")
    lines.append("## Summary")
    lines.append("")

    total = sum(counts.values())
    lines.append(f"Total findings: **{total}**")
    lines.append("")

    for status in statuses:
        n = counts.get(status, 0)
        lines.append(f"- **{status}**: {n}")

    lines.append("")
    lines.append("## Index")
    lines.append("")
    lines.append("| Status | Count | Finding | Evidence |")
    lines.append("|---|---|---|---|")

    if not rows:
        lines.append("| - | - | - | - |")
    else:
        status_counts: Dict[str, int] = {}
        for row in rows:
            s = row["status"]
            status_counts[s] = status_counts.get(s, 0) + 1
        for status in statuses:
            n = status_counts.get(status, 0)
            example = next((r for r in rows if r["status"] == status), None)
            if example:
                evidence = example.get("evidence", "")
                evidence_link = f"[evidence]({evidence})" if evidence else "-"
                lines.append(
                    f"| {status} | {n} | [finding]({example['finding_path']}) | {evidence_link} |"
                )
            else:
                lines.append(f"| {status} | 0 | - | - |")

    lines.append("")
    return "\n".join(lines)


def build_parser():
    import argparse
    parser = argparse.ArgumentParser(description="Render a CodeCome finding index.")

    parser.add_argument(
        "--output",
        default="itemdb/index.md",
        help="Output index path.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    rows = load_findings()
    output_path = _get_root() / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(render_index(rows), encoding="utf-8")

    print(C.ok(f"Rendered {output_path.relative_to(_get_root())}"))
    return 0