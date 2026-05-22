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
    "cvss_v4",
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

REQUIRED_CVSS_V4_FIELDS = [
    "vector",
    "score",
    "justification",
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
FINDING_FILENAME_RE = re.compile(r"^CC-\d{4}-[a-z0-9]+[-_a-z0-9]*\.md$", re.IGNORECASE)
SECTION_RE = re.compile(r"^# (?P<title>.+?)\n(?P<body>.*?)(?=^# |\Z)", re.MULTILINE | re.DOTALL)
CVSS_V4_VECTOR_RE = re.compile(r"^CVSS:4\.0/")

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


def severity_from_cvss_v4_score(score: float) -> str:
    if score == 0.0:
        return "INFO"
    if 0.1 <= score <= 3.9:
        return "LOW"
    if 4.0 <= score <= 6.9:
        return "MEDIUM"
    if 7.0 <= score <= 8.9:
        return "HIGH"
    if 9.0 <= score <= 10.0:
        return "CRITICAL"
    return ""


def validate_cvss_v4(data: Dict[str, object], status: object, severity: object) -> List[str]:
    errors: List[str] = []
    cvss_v4 = data.get("cvss_v4")

    if not isinstance(cvss_v4, dict):
        return ["cvss_v4 must be an object"]

    for field in REQUIRED_CVSS_V4_FIELDS:
        if field not in cvss_v4:
            errors.append(f"missing cvss_v4 field: cvss_v4.{field}")

    vector = cvss_v4.get("vector")
    score = cvss_v4.get("score")
    justification = cvss_v4.get("justification")

    if vector is not None and not isinstance(vector, str):
        errors.append("cvss_v4.vector must be a string")
    if justification is not None and not isinstance(justification, str):
        errors.append("cvss_v4.justification must be a string")
    if score is not None and not isinstance(score, (int, float)):
        errors.append("cvss_v4.score must be a number")

    if status in ("CONFIRMED", "EXPLOITED"):
        if not isinstance(vector, str) or is_placeholder(vector):
            errors.append(f"{status} status requires populated cvss_v4.vector")
        elif not CVSS_V4_VECTOR_RE.match(vector):
            errors.append("cvss_v4.vector must start with 'CVSS:4.0/'")

        if not isinstance(justification, str) or is_placeholder(justification):
            errors.append(f"{status} status requires populated cvss_v4.justification")

        if isinstance(score, (int, float)):
            expected_severity = severity_from_cvss_v4_score(float(score))
            if not expected_severity:
                errors.append("cvss_v4.score must be between 0.0 and 10.0")
            elif severity in SEVERITIES and severity != expected_severity:
                errors.append(
                    f"severity {severity!r} does not match cvss_v4.score {score!r} "
                    f"(expected {expected_severity!r})"
                )

    return errors


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

    filename = path.name
    if not FINDING_FILENAME_RE.match(filename):
        errors.append(
            f"filename must follow CC-XXXX-slug-title.md convention: "
            f"bare CC-XXXX.md names are not allowed (got {filename!r})"
        )

    severity = data.get("severity")
    if severity not in SEVERITIES:
        errors.append(f"invalid severity: {severity!r}")

    errors.extend(validate_cvss_v4(data, status, severity))

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


def validate_file_risk_index() -> List[str]:
    errors: List[str] = []
    index_path = ROOT / "itemdb" / "notes" / "file-risk-index.yml"
    
    if not index_path.exists():
        return errors # It is perfectly fine if the index hasn't been generated yet
        
    try:
        content = index_path.read_text(encoding="utf-8")
        data = yaml.safe_load(content) or {}
    except Exception as exc:
        return [f"file-risk-index.yml is invalid YAML: {exc}"]
        
    if not isinstance(data, dict):
        return ["file-risk-index.yml must contain a YAML object at the root"]
        
    files = data.get("files")
    if files is not None:
        if not isinstance(files, list):
            errors.append("file-risk-index.yml 'files' property must be a list")
        else:
            for i, entry in enumerate(files):
                if not isinstance(entry, dict):
                    errors.append(f"file-risk-index.yml files[{i}] must be an object")
                    continue
                path = entry.get("path")
                if not path or not isinstance(path, str):
                    errors.append(f"file-risk-index.yml files[{i}] missing string 'path' field")
                
                try:
                    int(entry.get("score", 0))
                except (ValueError, TypeError):
                    errors.append(f"file-risk-index.yml files[{i}] 'score' must be an integer")
    
    return errors


def iter_finding_files() -> List[Path]:
    return sorted(FINDINGS_ROOT.rglob("CC-*.md"))


def main() -> int:
    paths = iter_finding_files()

    total_errors = 0

    index_errors = validate_file_risk_index()
    if index_errors:
        total_errors += len(index_errors)
        print(C.fail("itemdb/notes/file-risk-index.yml"))
        for error in index_errors:
            print(f"  {C.SYM_BULLET} {error}")
    else:
        index_path = ROOT / "itemdb" / "notes" / "file-risk-index.yml"
        if index_path.exists():
            print(C.ok("itemdb/notes/file-risk-index.yml"))

    if not paths:
        if not index_path.exists():
            print(C.info("No findings or index to validate."))
        return 0 if total_errors == 0 else 1

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
