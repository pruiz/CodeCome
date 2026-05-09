#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

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

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C


ROOT = Path(__file__).resolve().parents[1]
FINDINGS_ROOT = ROOT / "itemdb" / "findings"

STATUSES = {
    "PENDING",
    "CONFIRMED",
    "EXPLOITED",
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
    "exploitation",
    "created_at",
    "updated_at",
]

REQUIRED_VALIDATION_FIELDS = [
    "status",
    "methods",
    "evidence_dir",
    "summary",
]

REQUIRED_EXPLOITATION_FIELDS = [
    "status",
    "impact_demonstrated",
    "exploit_type",
    "severity_before",
    "severity_after",
    "artifacts_dir",
    "summary",
]

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FINDING_ID_RE = re.compile(r"^CC-\d{4,}$")
SECTION_RE = re.compile(r"^# (?P<title>.+?)\n(?P<body>.*?)(?=^# |\Z)", re.MULTILINE | re.DOTALL)

REQUIRED_EXPLOITED_SECTIONS = [
    "Root cause analysis",
    "Data flow",
    "Inputs and preconditions",
    "Recording",
]

PLACEHOLDER_VALUES = {
    "",
    "pending.",
    "todo.",
    "tbd.",
}


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


def load_sections(path: Path) -> Dict[str, str]:
    content = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)
    body = content[match.end() :] if match else content
    sections: Dict[str, str] = {}

    for section_match in SECTION_RE.finditer(body):
        title = section_match.group("title").strip()
        sections[title] = section_match.group("body").strip()

    return sections


def is_placeholder(value: str) -> bool:
    return value.strip().lower() in PLACEHOLDER_VALUES


def has_remediation_code(value: str) -> bool:
    return "```diff" in value or "```patch" in value or "```c" in value or "```" in value


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

    if confidence == "CONFIRMED" and status not in ("CONFIRMED", "EXPLOITED"):
        errors.append("confidence CONFIRMED requires status CONFIRMED or EXPLOITED")

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

    cwe_value = data.get("cwe")
    if status == "EXPLOITED":
        if not isinstance(cwe_value, list) or not cwe_value:
            errors.append("EXPLOITED status requires at least one CWE id in cwe")
    if isinstance(cwe_value, list):
        for entry in cwe_value:
            if not isinstance(entry, str) or not re.fullmatch(r"CWE-\d+", entry):
                errors.append(f"invalid cwe entry: {entry!r} (expected 'CWE-NNN')")

    exploitation = data.get("exploitation")
    if isinstance(exploitation, dict):
        for field in REQUIRED_EXPLOITATION_FIELDS:
            if field not in exploitation:
                errors.append(f"missing exploitation field: exploitation.{field}")

        exploitation_status = exploitation.get("status")
        valid_exploitation_statuses = {"NOT_STARTED", "IN_PROGRESS", "DEMONSTRATED", "NOT_FEASIBLE"}
        if exploitation_status and exploitation_status not in valid_exploitation_statuses:
            errors.append(f"invalid exploitation.status: {exploitation_status!r}")

        artifacts_dir = exploitation.get("artifacts_dir")
        if artifacts_dir and not isinstance(artifacts_dir, str):
            errors.append("exploitation.artifacts_dir must be a string")

        if exploitation_status == "DEMONSTRATED":
            if not exploitation.get("impact_demonstrated"):
                errors.append("exploitation.status DEMONSTRATED requires exploitation.impact_demonstrated")
            if not exploitation.get("exploit_type"):
                errors.append("exploitation.status DEMONSTRATED requires exploitation.exploit_type")

        if status == "EXPLOITED":
            if exploitation_status != "DEMONSTRATED":
                errors.append("EXPLOITED status requires exploitation.status DEMONSTRATED")
            if not exploitation.get("impact_demonstrated"):
                errors.append("EXPLOITED status requires exploitation.impact_demonstrated")

    elif status == "EXPLOITED":
        errors.append("EXPLOITED status requires exploitation block")
    else:
        errors.append("missing required field: exploitation")

    sections = load_sections(path)
    if status == "EXPLOITED":
        for section in REQUIRED_EXPLOITED_SECTIONS:
            body = sections.get(section)
            if body is None:
                errors.append(f"EXPLOITED status requires #{section} section")
            elif is_placeholder(body):
                errors.append(f"EXPLOITED status requires populated #{section} section")

    if status in ("CONFIRMED", "EXPLOITED"):
        remediation = sections.get("Remediation idea")
        if remediation is None:
            errors.append(f"{status} status requires #Remediation idea section")
        elif is_placeholder(remediation):
            errors.append(f"{status} status requires populated #Remediation idea section")
        elif not has_remediation_code(remediation):
            errors.append(
                f"{status} status requires #Remediation idea with corrected-code excerpt or unified diff"
            )

    return errors


def iter_finding_files() -> List[Path]:
    return sorted(FINDINGS_ROOT.rglob("CC-*.md"))


def main() -> int:
    paths = iter_finding_files()

    if not paths:
        print(C.info("No findings to validate."))
        return 0

    total_errors = 0

    for path in paths:
        errors = validate_finding(path)

        if not errors:
            print(C.ok(str(path.relative_to(ROOT))))
            continue

        total_errors += len(errors)
        print(C.fail(str(path.relative_to(ROOT))))
        for error in errors:
            print(f"  {C.SYM_BULLET} {error}")

    if total_errors:
        print(f"\n{C.fail(f'Found {total_errors} frontmatter error(s).')}", file=sys.stderr)
        return 1

    print(f"\n{C.ok(f'Validated {len(paths)} finding(s).')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
