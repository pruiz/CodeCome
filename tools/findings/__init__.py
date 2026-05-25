# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import _colors as C

sys.modules[__name__]._colors = C

from findings import constants as _constants
from findings.frontmatter import (
    extract_sections,
    load_frontmatter,
    load_frontmatter_strict,
    replace_nested_value,
    replace_scalar_frontmatter,
)
from findings.ids import (
    extract_id_from_path,
    find_finding,
    iter_finding_files,
    iter_findings,
    next_finding_id,
    slugify,
)
from findings.checks import (
    is_placeholder,
    has_remediation_code,
    severity_from_cvss_v4_score,
    validate_cvss_v4,
    validate_finding,
    validate_file_risk_index,
)

ROOT = _constants.ROOT
FINDINGS_ROOT = _constants.FINDINGS_ROOT
EVIDENCE_ROOT = _constants.EVIDENCE_ROOT
NOTES_ROOT = _constants.NOTES_ROOT
TEMPLATE_PATH = _constants.TEMPLATE_PATH
EVIDENCE_TEMPLATE_PATH = _constants.EVIDENCE_TEMPLATE_PATH
DEFAULT_STATUS = _constants.DEFAULT_STATUS
DEFAULT_OUTPUT = _constants.DEFAULT_OUTPUT
STATUSES = _constants.STATUSES
STATUSES_SET = _constants.STATUSES_SET
VALID_SEVERITIES = _constants.VALID_SEVERITIES
VALID_CONFIDENCES = _constants.VALID_CONFIDENCES
FRONTMATTER_RE = _constants.FRONTMATTER_RE
FINDING_ID_RE = _constants.FINDING_ID_RE
FINDING_ID_FORMAT_RE = _constants.FINDING_ID_FORMAT_RE
FINDING_ID_STRICT_RE = _constants.FINDING_ID_STRICT_RE
FINDING_FILENAME_RE = _constants.FINDING_FILENAME_RE
SECTION_RE = _constants.SECTION_RE
CVSS_V4_VECTOR_RE = _constants.CVSS_V4_VECTOR_RE
SEVERITIES = _constants.SEVERITIES
CONFIDENCES = _constants.CONFIDENCES
REQUIRED_FIELDS = _constants.REQUIRED_FIELDS
REQUIRED_CVSS_V4_FIELDS = _constants.REQUIRED_CVSS_V4_FIELDS
REQUIRED_VALIDATION_FIELDS = _constants.REQUIRED_VALIDATION_FIELDS
REQUIRED_EXPLOITATION_FIELDS = _constants.REQUIRED_EXPLOITATION_FIELDS
REQUIRED_EXPLOITED_SECTIONS = _constants.REQUIRED_EXPLOITED_SECTIONS

from findings.create import create_finding, build_parser as _create_parser, main as _create_main
from findings.move import move_finding, build_parser as _move_parser
from findings.listing import (
    load_findings,
    print_plain,
    print_markdown,
    print_ids,
    filter_eligible_for_exploit,
    build_parser as _listing_parser,
    main,
)
from findings.evidence import create_evidence, build_parser as _evidence_parser
from findings.package import (
    validate_finding_id,
    discover_files,
    create_bundle,
    build_parser as _package_parser,
    main as _package_main,
)
from findings.render_report import (
    load_findings as _report_load_findings,
    render_report,
    build_parser as _report_parser,
    main as _report_main,
)
from findings.render_index import (
    render_index,
    build_parser as _index_parser,
    main as _index_main,
)
from findings.checks_entry import (
    validate_finding as _checks_validate_finding,
    validate_file_risk_index as _checks_validate_file_risk_index,
    iter_all_finding_files as _checks_iter_finding_files,
    build_parser as _checks_parser,
    main as _checks_main,
)

__all__ = [
    "C",
    "ROOT",
    "FINDINGS_ROOT",
    "EVIDENCE_ROOT",
    "NOTES_ROOT",
    "TEMPLATE_PATH",
    "EVIDENCE_TEMPLATE_PATH",
    "DEFAULT_STATUS",
    "DEFAULT_OUTPUT",
    "STATUSES",
    "STATUSES_SET",
    "VALID_SEVERITIES",
    "VALID_CONFIDENCES",
    "FRONTMATTER_RE",
    "FINDING_ID_RE",
    "FINDING_ID_FORMAT_RE",
    "FINDING_ID_STRICT_RE",
    "FINDING_FILENAME_RE",
    "SECTION_RE",
    "CVSS_V4_VECTOR_RE",
    "SEVERITIES",
    "CONFIDENCES",
    "REQUIRED_FIELDS",
    "REQUIRED_CVSS_V4_FIELDS",
    "REQUIRED_VALIDATION_FIELDS",
    "REQUIRED_EXPLOITATION_FIELDS",
    "REQUIRED_EXPLOITED_SECTIONS",
    "extract_sections",
    "load_frontmatter",
    "load_frontmatter_strict",
    "replace_nested_value",
    "replace_scalar_frontmatter",
    "extract_id_from_path",
    "find_finding",
    "iter_finding_files",
    "iter_findings",
    "next_finding_id",
    "slugify",
    "is_placeholder",
    "has_remediation_code",
    "severity_from_cvss_v4_score",
    "validate_cvss_v4",
    "validate_finding",
    "validate_file_risk_index",
    "create_finding",
    "move_finding",
    "load_findings",
    "print_plain",
    "print_markdown",
    "print_ids",
    "filter_eligible_for_exploit",
    "create_evidence",
    "validate_finding_id",
    "discover_files",
    "create_bundle",
    "render_report",
]