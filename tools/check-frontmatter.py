#!/usr/bin/env python3
"""
Validate CodeCome finding frontmatter.

Example:

    ./tools/check-frontmatter.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = Path(__file__).resolve().parents[1]
FINDINGS_ROOT = ROOT / "itemdb" / "findings"

STATUSES = {
    "NEEDS_VALIDATION",
    "CONFIRMED",
    "REJECTED",
    "DUPLICATE",
}

SEVERITIES = {
    "CRITICAL",
    "HIGH",
    "MEDIUM",
    "LOW",
    "INFO",
}

CONFIDENCES = {
    "LOW",
    "MEDIUM",
    "HIGH",
    "CONFIRMED",
}

REQUIRED_FIELDS = [
    "id",
    "title",
    "status",
    "severity",
    "confidence",
    "category",
    "cwe",
    "language",
    "target_area",
    "files",
    "symbols",
    "entry_points",
    "sources",
    "sinks",
    "trust_boundary",
    "assets_at_risk",
    "validation",
    "created_at",
    "updated_at",
]

REQUIRED_VALIDATION_FIELDS = [
    "status",
    "methods",
    "evidence_dir",
    "summary",
]

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FINDING_ID_RE = re.compile(r"^CC-\d{4,}$")


def load_frontmatter(path: Path) -> Dict[str, object]:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: pip install -r requirements.txt")

    content = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)

    if not match:
        raise ValueError("missing YAML frontmatter")

    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a YAML object")

    return data


def validate_finding(path: Path) -> List[str]:
    errors: List[str] = []

    try:
        data = load_frontmatter(path)
    except Exception as exc:
        return [str(exc)]

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")

    finding_id = data.get("id")
    if not isinstance(finding_id, str) or not FINDING_ID_RE.fullmatch(finding_id):
        errors.append(f"invalid id: {finding_id!r}")

    status = data.get("status")
    if status not in STATUSES:
        errors.append(f"invalid status: {status!r}")

    if status and path.parent.name != status:
        errors.append(f"status mismatch: frontmatter={status!r}, directory={path.parent.name!r}")

    severity = data.get("severity")
    if severity not in SEVERITIES:
        errors.append(f"invalid severity: {severity!r}")

    confidence = data.get("confidence")
    if confidence not in CONFIDENCES:
        errors.append(f"invalid confidence: {confidence!r}")

    if confidence == "CONFIRMED" and status != "CONFIRMED":
        errors.append("confidence CONFIRMED requires status CONFIRMED")

    validation = data.get("validation")
    if not isinstance(validation, dict):
        errors.append("validation must be an object")
    else:
        for field in REQUIRED_VALIDATION_FIELDS:
            if field not in validation:
                errors.append(f"missing validation field: validation.{field}")

    for list_field in ["cwe", "files", "symbols", "entry_points", "sources", "sinks", "assets_at_risk"]:
        if list_field in data and not isinstance(data[list_field], list):
            errors.append(f"{list_field} must be a list")

    return errors


def iter_finding_files() -> List[Path]:
    return sorted(FINDINGS_ROOT.rglob("CC-*.md"))


def main() -> int:
    paths = iter_finding_files()

    if not paths:
        print("No findings to validate.")
        return 0

    total_errors = 0

    for path in paths:
        errors = validate_finding(path)

        if not errors:
            print(f"OK: {path.relative_to(ROOT)}")
            continue

        total_errors += len(errors)
        print(f"ERROR: {path.relative_to(ROOT)}")
        for error in errors:
            print(f"  - {error}")

    if total_errors:
        print(f"\nFound {total_errors} frontmatter error(s).", file=sys.stderr)
        return 1

    print(f"\nValidated {len(paths)} finding(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
