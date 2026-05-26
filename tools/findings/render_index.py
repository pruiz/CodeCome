# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

from datetime import date

import _colors as C

from findings.constants import FindingsContext
from findings.frontmatter import load_frontmatter
from findings.ids import iter_findings, extract_id_from_path


def load_findings(
    *,
    ctx: FindingsContext,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for path in iter_findings(None, findings_root=ctx.findings_root, statuses=ctx.statuses):
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
                "finding_path": str(path.relative_to(ctx.root)),
            }
        )

    rows.sort(key=lambda row: row["id"])
    return rows


def count_by_status(rows: list[dict[str, str]], *, ctx: FindingsContext) -> dict[str, int]:
    counts: dict[str, int] = {s: 0 for s in ctx.statuses}
    for row in rows:
        s = row["status"]
        if s in counts:
            counts[s] += 1
    return counts


def render_index(rows: list[dict[str, str]], *, ctx: FindingsContext) -> str:
    counts = count_by_status(rows, ctx=ctx)
    statuses = ctx.statuses
    lines: list[str] = []
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
        status_counts: dict[str, int] = {}
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

    ctx = FindingsContext.default()
    rows = load_findings(ctx=ctx)
    output_path = ctx.root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(render_index(rows, ctx=ctx), encoding="utf-8")

    print(C.ok(f"Rendered {output_path.relative_to(ctx.root)}"))
    return 0