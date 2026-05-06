#!/usr/bin/env python3
"""
List CodeCome findings.

Examples:

    ./tools/list-findings.py
    ./tools/list-findings.py --status CONFIRMED
    ./tools/list-findings.py --format markdown
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

ROOT = Path(__file__).resolve().parents[1]
FINDINGS_ROOT = ROOT / "itemdb" / "findings"

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


def iter_findings(status_filter: Optional[str] = None) -> Iterable[Path]:
    statuses = [status_filter] if status_filter else STATUSES

    for status in statuses:
        status_dir = FINDINGS_ROOT / status
        if not status_dir.exists():
            continue

        yield from sorted(status_dir.glob("CC-*.md"))


def load_findings(status_filter: Optional[str]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []

    for path in iter_findings(status_filter):
        frontmatter = load_frontmatter(path)

        rows.append(
            {
                "id": frontmatter.get("id", "-".join(path.stem.split("-", 2)[:2])),
                "status": frontmatter.get("status", path.parent.name),
                "severity": frontmatter.get("severity", ""),
                "confidence": frontmatter.get("confidence", ""),
                "title": frontmatter.get("title", path.stem),
                "path": str(path.relative_to(ROOT)),
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


def build_parser() -> argparse.ArgumentParser:
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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    rows = load_findings(args.status)

    if args.format == "markdown":
        print_markdown(rows)
    elif args.format == "ids":
        print_ids(rows)
    else:
        print_plain(rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
