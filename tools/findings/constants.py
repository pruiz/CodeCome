# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, List

ROOT = Path(__file__).resolve().parents[2]

FINDINGS_ROOT = ROOT / "itemdb" / "findings"
EVIDENCE_ROOT = ROOT / "itemdb" / "evidence"
NOTES_ROOT = ROOT / "itemdb" / "notes"
TEMPLATE_PATH = ROOT / "templates" / "finding.md"
EVIDENCE_TEMPLATE_PATH = ROOT / "templates" / "evidence-readme.md"
DEFAULT_STATUS = "PENDING"
DEFAULT_OUTPUT = ROOT / "itemdb" / "reports" / "report.md"

STATUSES = [
    "PENDING",
    "CONFIRMED",
    "EXPLOITED",
    "REJECTED",
    "DUPLICATE",
]

STATUSES_SET = frozenset(STATUSES)

VALID_SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"})
VALID_CONFIDENCES = frozenset({"LOW", "MEDIUM", "HIGH", "CONFIRMED"})

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

FINDING_ID_RE = re.compile(r"\bCC-(\d{4,})\b")
FINDING_ID_FORMAT_RE = re.compile(r"^CC-\d{4,}$")
FINDING_ID_STRICT_RE = re.compile(r"^CC-\d{4}$")
FINDING_FILENAME_RE = re.compile(r"^CC-\d{4}-[a-z0-9]+[-_a-z0-9]*\.md$", re.IGNORECASE)

SECTION_RE = re.compile(r"^# (?P<title>.+?)\n(?P<body>.*?)(?=^# |\Z)", re.MULTILINE | re.DOTALL)
CVSS_V4_VECTOR_RE = re.compile(r"^CVSS:4\.0/")

SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"})
CONFIDENCES = frozenset({"LOW", "MEDIUM", "HIGH", "CONFIRMED"})

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

REQUIRED_CVSS_V4_FIELDS = ["vector", "score", "justification"]

REQUIRED_VALIDATION_FIELDS = ["status", "methods", "evidence_dir", "summary"]

REQUIRED_EXPLOITATION_FIELDS = [
    "status",
    "impact_demonstrated",
    "exploit_type",
    "severity_before",
    "severity_after",
    "artifacts_dir",
    "summary",
]

REQUIRED_EXPLOITED_SECTIONS = [
    "Root cause analysis",
    "Data flow",
    "Inputs and preconditions",
    "Recording",
]


@dataclass(frozen=True)
class FindingsContext:
    root: Path
    findings_root: Path
    evidence_root: Path
    notes_root: Path
    template_path: Path
    evidence_template_path: Path
    statuses: List[str]
    statuses_set: FrozenSet[str]

    @classmethod
    def default(cls) -> FindingsContext:
        return cls(
            root=ROOT,
            findings_root=FINDINGS_ROOT,
            evidence_root=EVIDENCE_ROOT,
            notes_root=NOTES_ROOT,
            template_path=TEMPLATE_PATH,
            evidence_template_path=EVIDENCE_TEMPLATE_PATH,
            statuses=STATUSES,
            statuses_set=STATUSES_SET,
        )


@dataclass(frozen=True)
class FindingsContext:
    root: Path
    findings_root: Path
    evidence_root: Path
    notes_root: Path
    template_path: Path
    evidence_template_path: Path
    statuses: List[str]
    statuses_set: FrozenSet[str]

    @classmethod
    def default(cls) -> FindingsContext:
        return cls(
            root=ROOT,
            findings_root=FINDINGS_ROOT,
            evidence_root=EVIDENCE_ROOT,
            notes_root=NOTES_ROOT,
            template_path=TEMPLATE_PATH,
            evidence_template_path=EVIDENCE_TEMPLATE_PATH,
            statuses=STATUSES,
            statuses_set=STATUSES_SET,
        )