#!/usr/bin/env python3
"""
Move a CodeCome finding to another status directory and update frontmatter.

Examples:

    ./tools/move-finding.py CC-0001 CONFIRMED
    ./tools/move-finding.py itemdb/findings/NEEDS_VALIDATION/CC-0001-test.md REJECTED
"""

from __future__ import annotations

import argparse
import re
import shutil
from datetime import date
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
FINDINGS_ROOT = ROOT / "itemdb" / "findings"

STATUSES = {
    "NEEDS_VALIDATION",
    "CONFIRMED",
    "REJECTED",
    "DUPLICATE",
}

FINDING_ID_RE = re.compile(r"\bCC-\d{4,}\b")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def find_finding(identifier: str) -> Path:
    candidate = Path(identifier)

    if candidate.exists():
        return candidate.resolve()

    if not FINDING_ID_RE.fullmatch(identifier):
        raise FileNotFoundError(f"Invalid finding id or path: {identifier}")

    matches = sorted(FINDINGS_ROOT.rglob(f"{identifier}-*.md"))

    if not matches:
        raise FileNotFoundError(f"Finding not found: {identifier}")

    if len(matches) > 1:
        paths = "\n".join(str(path.relative_to(ROOT)) for path in matches)
        raise RuntimeError(f"Multiple findings matched {identifier}:\n{paths}")

    return matches[0]


def replace_scalar_frontmatter(content: str, key: str, value: str) -> str:
    pattern = re.compile(rf'^{re.escape(key)}:\s*".*"$', re.MULTILINE)
    replacement = f'{key}: "{value}"'

    if pattern.search(content):
        return pattern.sub(replacement, content, count=1)

    return content


def replace_validation_status(content: str, value: str) -> str:
    validation_block_re = re.compile(r"^validation:\n(?P<body>(?:  .*\n?)*)", re.MULTILINE)
    match = validation_block_re.search(content)

    if not match:
        return content

    body = match.group("body")
    status_re = re.compile(r'^  status:\s*".*"$', re.MULTILINE)

    if not status_re.search(body):
        return content

    new_body = status_re.sub(f'  status: "{value}"', body, count=1)
    return content[: match.start("body")] + new_body + content[match.end("body") :]


def update_frontmatter(content: str, status: str, validation_status: Optional[str]) -> str:
    if not FRONTMATTER_RE.match(content):
        raise RuntimeError("Finding does not start with YAML frontmatter")

    today = date.today().isoformat()

    content = replace_scalar_frontmatter(content, "status", status)
    content = replace_scalar_frontmatter(content, "updated_at", today)

    if status == "CONFIRMED":
        content = replace_scalar_frontmatter(content, "confidence", "CONFIRMED")

    if validation_status:
        content = replace_validation_status(content, validation_status)

    return content


def move_finding(path: Path, status: str) -> Path:
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")

    content = path.read_text(encoding="utf-8")

    validation_status = None
    if status == "CONFIRMED":
        validation_status = "CONFIRMED"
    elif status == "REJECTED":
        validation_status = "REJECTED"

    content = update_frontmatter(content, status, validation_status)

    target_dir = FINDINGS_ROOT / status
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / path.name

    if target_path.exists() and target_path.resolve() != path.resolve():
        raise FileExistsError(f"Target already exists: {target_path}")

    path.write_text(content, encoding="utf-8")

    if target_path.resolve() != path.resolve():
        shutil.move(str(path), str(target_path))

    return target_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Move a CodeCome finding to another status directory.",
    )

    parser.add_argument("finding", help="Finding id, for example CC-0001, or path to finding file.")
    parser.add_argument("status", choices=sorted(STATUSES), help="Target status.")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    path = find_finding(args.finding)
    target_path = move_finding(path, args.status)

    print(target_path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
