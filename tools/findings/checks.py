# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

try:
    import yaml
except ImportError:
    yaml = None

from findings.constants import (
    CONFIDENCES,
    CVSS_V4_VECTOR_RE,
    FINDING_FILENAME_RE,
    FINDING_ID_FORMAT_RE,
    FINDINGS_ROOT,
    FRONTMATTER_RE,
    REQUIRED_CVSS_V4_FIELDS,
    REQUIRED_EXPLOITATION_FIELDS,
    REQUIRED_EXPLOITED_SECTIONS,
    REQUIRED_FIELDS,
    REQUIRED_VALIDATION_FIELDS,
    ROOT,
    SECTION_RE,
    SEVERITIES,
    STATUSES,
    STATUSES_SET,
    VALID_CONFIDENCES,
    VALID_SEVERITIES,
)
from findings.frontmatter import load_frontmatter_strict


PLACEHOLDER_VALUES = {"", "pending.", "todo.", "tbd."}


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


def load_sections(path: Path) -> Dict[str, str]:
    content = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)
    body = content[match.end() :] if match else content
    sections: Dict[str, str] = {}

    for section_match in SECTION_RE.finditer(body):
        title = section_match.group("title").strip()
        sections[title] = section_match.group("body").strip()

    return sections


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
        data = load_frontmatter_strict(path)
    except Exception as exc:
        return [str(exc)]

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing required field: {field}")

    finding_id = data.get("id")
    if not isinstance(finding_id, str) or not FINDING_ID_FORMAT_RE.fullmatch(finding_id):
        errors.append(f"invalid id: {finding_id!r}")

    status = data.get("status")
    if status not in STATUSES_SET:
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
        return errors

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


def iter_all_finding_files() -> List[Path]:
    return sorted(FINDINGS_ROOT.rglob("CC-*.md"))