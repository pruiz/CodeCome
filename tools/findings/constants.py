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
    "NEEDS_VALIDATION",
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

# Stable, source-derived root-cause identifier. Same root cause -> same
# fingerprint in every status and across re-runs. It must not embed a line
# number, run, agent, severity, or verdict. Example:
#   "authz:src/api/orders.py#OrderController.get:missing-owner-check"
FINGERPRINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+#-]*$")
FINGERPRINT_MAX_LEN = 200

# Statuses in which a root cause is still "live". Two live findings with the
# same fingerprint are duplicates and must be collapsed in Phase 3.
LIVE_STATUSES = frozenset({"PENDING", "NEEDS_VALIDATION", "CONFIRMED", "EXPLOITED"})

REQUIRED_NEEDS_VALIDATION_FIELDS = ["blockers", "local_check", "owner_check"]

CONFIDENCES = frozenset({"LOW", "MEDIUM", "HIGH", "CONFIRMED"})

VALID_CONFIDENCES = CONFIDENCES

REQUIRED_CAPABILITY_FIELDS = [
    "forbidden",
    "disposition",
    "exposure",
    "gate",
    "cooperation",
    "boundary",
    "effect",
    "scope",
    "durability",
]

REQUIRED_FIELDS = [
    "id",
    "title",
    "status",
    "capability",
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

REQUIRED_VALIDATION_FIELDS = ["status", "methods", "evidence_dir", "summary"]

REQUIRED_EXPLOITATION_FIELDS = [
    "status",
    "impact_demonstrated",
    "exploit_type",
    "capability_before",
    "capability_after",
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
