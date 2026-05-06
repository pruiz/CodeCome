#!/usr/bin/env python3
"""
Render itemdb/index.md from current CodeCome findings.

Example:

    ./tools/render-index.py
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

ROOT = Path(__file__).resolve().parents[1]
FINDINGS_ROOT = ROOT / "itemdb" / "findings"
INDEX_PATH = ROOT / "itemdb" / "index.md"

STATUSES = [
    "NEEDS_VALIDATION",
    "CONFIRMED",
    "REJECTED",
    "DUPLICATE",
]

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def load_frontmatter(path: Path) -> Dict[str, object]:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: pip install -r requirements.txt")

    content = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)

    if not match:
        return {}

    data = yaml.safe_load(match.group(1))
    return data if isinstance(data, dict) else {}


def iter_finding_files() -> Iterable[Path]:
    for status in STATUSES:
        status_dir = FINDINGS_ROOT / status
        if not status_dir.exists():
            continue

        yield from sorted(status_dir.glob("CC-*.md"))


def load_findings() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    for path in iter_finding_files():
        frontmatter = load_frontmatter(path)
        finding_id = str(frontmatter.get("id", "-".join(path.stem.split("-", 2)[:2])))
        evidence_dir = ""

        validation = frontmatter.get("validation")
        if isinstance(validation, dict):
            evidence_dir = str(validation.get("evidence_dir", ""))

        rows.append(
            {
                "id": finding_id,
                "status": str(frontmatter.get("status", path.parent.name)),
                "severity": str(frontmatter.get("severity", "")),
                "confidence": str(frontmatter.get("confidence", "")),
                "title": str(frontmatter.get("title", path.stem)),
                "target_area": str(frontmatter.get("target_area", "")),
                "finding_path": str(path.relative_to(ROOT)),
                "evidence": evidence_dir,
            }
        )

    rows.sort(key=lambda row: row["id"])
    return rows


def markdown_link(label: str, path: str) -> str:
    if not path:
        return ""

    return f"[{label}]({path})"


def render_index(rows: List[Dict[str, str]]) -> str:
    counts = Counter(row["status"] for row in rows)

    lines: List[str] = []
    lines.append("# CodeCome Finding Index")
    lines.append("")
    lines.append(f"Generated: {date.today().isoformat()}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Status | Count |")
    lines.append("|---|---:|")

    for status in STATUSES:
        lines.append(f"| {status} | {counts.get(status, 0)} |")

    lines.append("")
    lines.append("## Findings")
    lines.append("")
    lines.append("| ID | Status | Severity | Confidence | Target area | Title | Finding | Evidence |")
    lines.append("|---|---|---|---|---|---|---|---|")

    if not rows:
        lines.append("| - | - | - | - | - | No findings yet. | - | - |")
    else:
        for row in rows:
            finding_link = markdown_link("finding", row["finding_path"])
            evidence_link = markdown_link("evidence", row["evidence"]) if row["evidence"] else ""

            lines.append(
                f"| {row['id']} "
                f"| {row['status']} "
                f"| {row['severity']} "
                f"| {row['confidence']} "
                f"| {row['target_area']} "
                f"| {row['title']} "
                f"| {finding_link} "
                f"| {evidence_link} |"
            )

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    rows = load_findings()
    INDEX_PATH.write_text(render_index(rows), encoding="utf-8")
    print(C.ok(f"Rendered {INDEX_PATH.relative_to(ROOT)}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
