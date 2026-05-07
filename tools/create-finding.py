#!/usr/bin/env python3
"""
Create a new CodeCome finding from templates/finding.md.

Example:

    ./tools/create-finding.py "Missing owner check in document download"

Optional:

    ./tools/create-finding.py "Stack buffer overflow in parser" \
      --severity HIGH \
      --confidence MEDIUM \
      --category "Memory Safety" \
      --language C
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "templates" / "finding.md"
FINDINGS_ROOT = ROOT / "itemdb" / "findings"
DEFAULT_STATUS = "PENDING"

VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
VALID_CONFIDENCES = {"LOW", "MEDIUM", "HIGH", "CONFIRMED"}
FINDING_ID_RE = re.compile(r"\bCC-(\d{4,})\b")
FINDING_ID_FORMAT_RE = re.compile(r"^CC-\d{4,}$")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value[:80] or "finding"


def iter_finding_files() -> List[Path]:
    files: List[Path] = []

    if not FINDINGS_ROOT.exists():
        return files

    for path in FINDINGS_ROOT.rglob("CC-*.md"):
        if path.is_file():
            files.append(path)

    return sorted(files)


def next_finding_id() -> str:
    ids = []

    for path in iter_finding_files():
        match = FINDING_ID_RE.search(path.name)
        if match:
            ids.append(int(match.group(1)))

    next_id = max(ids, default=0) + 1
    return f"CC-{next_id:04d}"


def replace_frontmatter_value(content: str, key: str, value: str) -> str:
    """Replace a quoted scalar value in YAML frontmatter only (not in body)."""
    fm_match = FRONTMATTER_RE.match(content)
    pattern = re.compile(rf'^{re.escape(key)}:\s*".*"$', re.MULTILINE)
    replacement = f'{key}: "{value}"'
    if fm_match:
        fm_block = content[: fm_match.end()]
        body = content[fm_match.end() :]
        fm_block = pattern.sub(replacement, fm_block, count=1)
        return fm_block + body
    # Fallback for templates: operate on whole content.
    return pattern.sub(replacement, content, count=1)


def replace_nested_validation_value(content: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^  {re.escape(key)}:\s*.*$", re.MULTILINE)
    replacement = f'  {key}: "{value}"'
    return pattern.sub(replacement, content, count=1)


def create_finding(args: argparse.Namespace) -> Path:
    if args.severity not in VALID_SEVERITIES:
        raise ValueError(f"Invalid severity: {args.severity}")

    if args.confidence not in VALID_CONFIDENCES:
        raise ValueError(f"Invalid confidence: {args.confidence}")

    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    finding_id = args.id or next_finding_id()

    if args.id and not FINDING_ID_FORMAT_RE.fullmatch(args.id):
        raise ValueError(f"Invalid finding id format: {args.id!r} (expected CC-NNNN)")
    slug = args.slug or slugify(args.title)
    today = date.today().isoformat()

    output_dir = FINDINGS_ROOT / DEFAULT_STATUS
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{finding_id}-{slug}.md"

    if output_path.exists() and not args.force:
        raise FileExistsError(f"Finding already exists: {output_path}")

    content = TEMPLATE_PATH.read_text(encoding="utf-8")

    content = replace_frontmatter_value(content, "id", finding_id)
    content = replace_frontmatter_value(content, "title", args.title)
    content = replace_frontmatter_value(content, "status", DEFAULT_STATUS)
    content = replace_frontmatter_value(content, "severity", args.severity)
    content = replace_frontmatter_value(content, "confidence", args.confidence)
    content = replace_frontmatter_value(content, "category", args.category)
    content = replace_frontmatter_value(content, "language", args.language)
    content = replace_frontmatter_value(content, "target_area", args.target_area)
    content = replace_frontmatter_value(content, "created_at", today)
    content = replace_frontmatter_value(content, "updated_at", today)
    content = replace_nested_validation_value(
        content,
        "evidence_dir",
        f"itemdb/evidence/{finding_id}",
    )

    # Update exploitation artifacts_dir.
    content = content.replace(
        "itemdb/evidence/CC-0000/exploits",
        f"itemdb/evidence/{finding_id}/exploits",
        1,
    )

    content = content.replace(
        "Briefly describe the suspected vulnerability.",
        "Pending.",
        1,
    )

    output_path.write_text(content, encoding="utf-8")

    evidence_dir = ROOT / "itemdb" / "evidence" / finding_id
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

    output_path = create_finding(args)
    relative_path = output_path.relative_to(ROOT)
    print(C.ok(str(relative_path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
