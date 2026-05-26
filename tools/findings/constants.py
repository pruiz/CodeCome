# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet, List

ROOT = Path(__file__).resolve().parents[2]
ITEMDB_ROOT = ROOT / "itemdb"

FINDINGS_ROOT = ITEMDB_ROOT / "findings"
EVIDENCE_ROOT = ITEMDB_ROOT / "evidence"
NOTES_ROOT = ITEMDB_ROOT / "notes"
REPORTS_ROOT = ITEMDB_ROOT / "reports"
INDEX_PATH = ITEMDB_ROOT / "index.md"
TEMPLATE_PATH = ROOT / "templates" / "finding.md"
EVIDENCE_TEMPLATE_PATH = ROOT / "templates" / "evidence-readme.md"
FILE_RISK_INDEX_REL = Path("itemdb/notes/file-risk-index.yml")
FILE_RISK_INDEX_PATH = NOTES_ROOT / "file-risk-index.yml"
SANDBOX_PLAN_PATH = NOTES_ROOT / "sandbox-plan.md"
DEFAULT_STATUS = "PENDING"
DEFAULT_OUTPUT = REPORTS_ROOT / "report.md"

STATUSES = [
    "PENDING",
    "CONFIRMED",
    "EXPLOITED",
    "REJECTED",
    "DUPLICATE",
]

STATUSES_SET = frozenset(STATUSES)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

FINDING_ID_RE = re.compile(r"\bCC-(\d{4,})\b")
FINDING_ID_FORMAT_RE = re.compile(r"^CC-\d{4,}$")
FINDING_ID_STRICT_RE = re.compile(r"^CC-\d{4}$")
FINDING_FILENAME_RE = re.compile(r"^CC-\d{4}-[a-z0-9]+[-_a-z0-9]*\.md$", re.IGNORECASE)

SECTION_RE = re.compile(r"^# (?P<title>.+?)\n(?P<body>.*?)(?=^# |\Z)", re.MULTILINE | re.DOTALL)
CVSS_V4_VECTOR_RE = re.compile(r"^CVSS:4\.0/")

SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"})
CONFIDENCES = frozenset({"LOW", "MEDIUM", "HIGH", "CONFIRMED"})

VALID_SEVERITIES = SEVERITIES
VALID_CONFIDENCES = CONFIDENCES

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


def evidence_dir_for(finding_id: str) -> Path:
    return EVIDENCE_ROOT / finding_id


def exploits_dir_for(finding_id: str) -> Path:
    return EVIDENCE_ROOT / finding_id / "exploits"


def finding_status_dir(status: str) -> Path:
    return FINDINGS_ROOT / status


@dataclass(frozen=True)
class FindingsContext:
    root: Path = ROOT
    itemdb_root: Path = ITEMDB_ROOT
    findings_root: Path = FINDINGS_ROOT
    evidence_root: Path = EVIDENCE_ROOT
    notes_root: Path = NOTES_ROOT
    reports_root: Path = REPORTS_ROOT
    template_path: Path = TEMPLATE_PATH
    evidence_template_path: Path = EVIDENCE_TEMPLATE_PATH
    statuses: List[str] = field(default_factory=lambda: list(STATUSES))
    statuses_set: FrozenSet[str] = field(default_factory=lambda: frozenset(STATUSES))

    @classmethod
    def default(cls) -> "FindingsContext":
        return cls()