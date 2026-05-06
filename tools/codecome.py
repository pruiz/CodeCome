#!/usr/bin/env python3
"""
CodeCome helper CLI.

This tool intentionally starts small. It provides basic workspace checks,
finding status counts, and next-id discovery for Markdown findings.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = [
    "README.md",
    "AGENTS.md",
    "codecome.yml",
    "src",
    "sandbox",
    "itemdb",
    "itemdb/findings/NEEDS_VALIDATION",
    "itemdb/findings/CONFIRMED",
    "itemdb/findings/REJECTED",
    "itemdb/findings/DUPLICATE",
    "itemdb/evidence",
    "itemdb/notes",
    "itemdb/reports",
    "runs",
    "templates",
    "templates/finding.md",
    "templates/target-recon.md",
    "tools",
    ".opencode/agents",
    ".opencode/skills",
]

FINDING_STATUS_DIRS = [
    "NEEDS_VALIDATION",
    "CONFIRMED",
    "REJECTED",
    "DUPLICATE",
]

FINDING_ID_RE = re.compile(r"\bCC-(\d{4,})\b")


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def load_config() -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: pip install -r requirements.txt")

    config_path = ROOT / "codecome.yml"
    with config_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise RuntimeError("codecome.yml did not parse as a YAML object")

    return data


def iter_finding_files() -> Iterable[Path]:
    findings_root = ROOT / "itemdb" / "findings"

    for status in FINDING_STATUS_DIRS:
        status_dir = findings_root / status
        if not status_dir.exists():
            continue

        yield from sorted(status_dir.glob("CC-*.md"))


def collect_finding_ids(paths: Iterable[Path]) -> List[int]:
    ids: List[int] = []

    for path in paths:
        match = FINDING_ID_RE.search(path.name)
        if match:
            ids.append(int(match.group(1)))

    return sorted(set(ids))


def count_findings() -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for status in FINDING_STATUS_DIRS:
        status_dir = ROOT / "itemdb" / "findings" / status
        counts[status] = len(list(status_dir.glob("CC-*.md"))) if status_dir.exists() else 0

    return counts


def command_check(_: argparse.Namespace) -> int:
    missing = []

    for relative_path in REQUIRED_PATHS:
        path = ROOT / relative_path
        if not path.exists():
            missing.append(relative_path)

    try:
        config = load_config()
    except Exception as exc:
        return fail(str(exc))

    if missing:
        print("Missing required paths:")
        for item in missing:
            print(f"  - {item}")
        return 1

    project_name = config.get("project", {}).get("name", "unknown")
    print(f"Workspace OK: {project_name}")
    return 0


def command_status(_: argparse.Namespace) -> int:
    try:
        config = load_config()
    except Exception as exc:
        return fail(str(exc))

    project_name = config.get("project", {}).get("name", "unknown")
    source_path = config.get("project", {}).get("source_path", "./src")

    print(f"Project: {project_name}")
    print(f"Source:  {source_path}")
    print()
    print("Findings:")

    for status, count in count_findings().items():
        print(f"  {status:16} {count}")

    return 0


def command_next_id(_: argparse.Namespace) -> int:
    ids = collect_finding_ids(iter_finding_files())
    next_id = max(ids, default=0) + 1
    print(f"CC-{next_id:04d}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codecome",
        description="Small helper CLI for the CodeCome workspace.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Validate the workspace structure and config.")
    check_parser.set_defaults(func=command_check)

    status_parser = subparsers.add_parser("status", help="Show a basic workspace status summary.")
    status_parser.set_defaults(func=command_status)

    next_id_parser = subparsers.add_parser("next-id", help="Print the next available finding id.")
    next_id_parser.set_defaults(func=command_next_id)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
