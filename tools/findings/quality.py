# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

from pathlib import Path
from typing import Any

from findings.checks import load_sections, validate_finding
from findings.frontmatter import load_frontmatter_strict


PHASE2_CORE_SECTIONS = [
    "Summary",
    "Target context",
    "Affected code",
    "Vulnerability hypothesis",
    "Source-to-sink reasoning",
    "Attackability / trigger conditions",
    "Impact",
    "Validation plan",
]

PHASE2_REQUIRED_SECTIONS = PHASE2_CORE_SECTIONS + [
    "Counter-analysis",
    "Validation result",
    "Evidence",
]

_PLACEHOLDER_TEXT = {
    "",
    "pending.",
    "todo.",
    "tbd.",
    "not applicable.",
}

_TEMPLATE_MARKERS = [
    "Briefly describe the suspected vulnerability.",
    "Describe the relevant target type",
    "List the relevant files",
    "Explain the suspected vulnerability.",
    "This section must clearly distinguish what is known from what is assumed.",
    "Describe the path from attacker-controlled",
    "Explain how an attacker",
    "Explain the realistic security impact.",
    "Describe exactly how to prove or disprove the finding.",
    "Try to disprove the finding.",
]

_NON_FINDING_MARKERS = [
    "does not represent an actual vulnerability",
    "does not describe a real vulnerability",
    "does not contain a vulnerability",
    "no actual vulnerability",
    "this is a test finding",
    "test finding created to verify",
    "template system itself does not contain a vulnerability",
]


def _is_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().lower() in _PLACEHOLDER_TEXT


def _contains_template_marker(value: str) -> bool:
    lowered = value.lower()
    return any(marker.lower() in lowered for marker in _TEMPLATE_MARKERS)


def _contains_non_finding_marker(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _NON_FINDING_MARKERS)


def _list_is_populated(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    return isinstance(value, list) and any(str(item).strip() for item in value)


def _scalar_is_populated(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, str):
        return False
    return value.strip().lower() not in _PLACEHOLDER_TEXT | {"unknown", "unclassified"}


def validate_phase2_finding_quality(path: Path) -> list[str]:
    """Return Phase 2 quality errors for a candidate finding.

    This is intentionally stricter than frontmatter validation. A PENDING
    finding can be syntactically valid while still being unusable as a Phase 2
    durable artifact if it is mostly an untouched template.
    """
    errors: list[str] = []

    errors.extend(validate_finding(path))
    try:
        data = load_frontmatter_strict(path)
    except Exception as exc:
        return errors or [str(exc)]

    if data.get("status") != "PENDING":
        errors.append("Phase 2 findings must remain in PENDING status")

    title = str(data.get("title", "")).strip().lower()
    if title.startswith("test finding") or title.startswith("template test"):
        errors.append("Phase 2 findings must describe a target vulnerability, not a test/template artifact")

    for key in ("category", "target_area"):
        value = str(data.get(key, "")).strip().lower()
        if value in {"test", "testing", "template"}:
            errors.append(f"Phase 2 frontmatter field {key} describes a test/template artifact")

    for key in ("category", "language", "target_area", "trust_boundary"):
        if not _scalar_is_populated(data, key):
            errors.append(f"Phase 2 requires populated frontmatter field: {key}")

    for key in ("files", "sources", "sinks", "assets_at_risk"):
        if not _list_is_populated(data, key):
            errors.append(f"Phase 2 requires non-empty frontmatter list: {key}")

    if not (_list_is_populated(data, "symbols") or _list_is_populated(data, "entry_points")):
        errors.append("Phase 2 requires at least one symbol or entry point")

    sections = load_sections(path)
    combined_sections = "\n".join(str(value) for value in sections.values())
    if _contains_non_finding_marker(combined_sections):
        errors.append("Phase 2 finding text says it is not an actual target vulnerability")

    for section in PHASE2_REQUIRED_SECTIONS:
        body = sections.get(section)
        if body is None:
            errors.append(f"Phase 2 requires #{section} section")
            continue
        if section in PHASE2_CORE_SECTIONS:
            if _is_placeholder(body):
                errors.append(f"Phase 2 requires populated #{section} section")
            elif _contains_template_marker(body):
                errors.append(f"Phase 2 #{section} still contains template guidance")

    counter = sections.get("Counter-analysis", "")
    if counter and not _is_placeholder(counter) and _contains_template_marker(counter):
        errors.append("Phase 2 #Counter-analysis still contains template guidance")

    return errors


def phase2_summary_declares_no_findings(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False
    lowered = content.lower()
    if "# findings created" not in lowered:
        return False
    no_finding_markers = [
        "| - | none.",
        "| - | none |",
        "no findings created",
        "no new findings",
        "zero findings",
    ]
    return any(marker in lowered for marker in no_finding_markers)
