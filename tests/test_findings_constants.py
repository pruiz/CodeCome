from __future__ import annotations

import ast
from pathlib import Path

import pytest

from findings.constants import (
    FindingsContext,
    EVIDENCE_ROOT,
    FINDINGS_ROOT,
    NOTES_ROOT,
    REPORTS_ROOT,
    ITEMDB_ROOT,
    FILE_RISK_INDEX_PATH,
    STATUSES,
)


class TestFindingsContextDuplicate:
    def test_single_findings_context_class(self):
        code = Path("tools/findings/constants.py").read_text()
        tree = ast.parse(code)
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert classes.count("FindingsContext") == 1, (
            f"Expected 1 FindingsContext class, got {classes.count('FindingsContext')}"
        )

    def test_import_does_not_raise(self):
        from findings.constants import FindingsContext as _


class TestFindingsContextDefaultConstruction:
    def test_default_construction(self):
        ctx = FindingsContext()
        assert ctx.findings_root == FINDINGS_ROOT
        assert ctx.evidence_root == EVIDENCE_ROOT
        assert ctx.notes_root == NOTES_ROOT
        assert ctx.reports_root == REPORTS_ROOT

    def test_default_context_root(self):
        from findings.constants import ROOT as CONSTANTS_ROOT
        ctx = FindingsContext()
        assert ctx.root == CONSTANTS_ROOT

    def test_default_itemdb_root(self):
        ctx = FindingsContext()
        assert ctx.itemdb_root == ITEMDB_ROOT

    def test_default_statuses_not_empty(self):
        ctx = FindingsContext()
        assert len(ctx.statuses) > 0
        assert tuple(ctx.statuses) == tuple(STATUSES)

    def test_default_statuses_set(self):
        ctx = FindingsContext()
        assert ctx.statuses_set == frozenset(STATUSES)

    def test_default_method_returns_same_as_empty_call(self):
        ctx1 = FindingsContext()
        ctx2 = FindingsContext.default()
        assert ctx1.findings_root == ctx2.findings_root
        assert ctx1.evidence_root == ctx2.evidence_root
        assert ctx1.notes_root == ctx2.notes_root
        assert ctx1.reports_root == ctx2.reports_root
        assert ctx1.statuses == ctx2.statuses
        assert ctx1.statuses_set == ctx2.statuses_set


class TestPathConstants:
    def test_file_risk_index_path(self):
        assert FILE_RISK_INDEX_PATH == NOTES_ROOT / "file-risk-index.yml"

    def test_reports_root_under_itemdb(self):
        assert REPORTS_ROOT == ITEMDB_ROOT / "reports"

    def test_findings_root_under_itemdb(self):
        assert FINDINGS_ROOT == ITEMDB_ROOT / "findings"

    def test_evidence_root_under_itemdb(self):
        assert EVIDENCE_ROOT == ITEMDB_ROOT / "evidence"

    def test_index_path_under_itemdb(self):
        from findings.constants import INDEX_PATH
        assert INDEX_PATH == ITEMDB_ROOT / "index.md"


class TestHelperFunctions:
    def test_evidence_dir_for(self):
        from findings.constants import evidence_dir_for
        result = evidence_dir_for("CC-0001")
        assert result == EVIDENCE_ROOT / "CC-0001"

    def test_exploits_dir_for(self):
        from findings.constants import exploits_dir_for
        result = exploits_dir_for("CC-0001")
        assert result == EVIDENCE_ROOT / "CC-0001" / "exploits"

    def test_finding_status_dir(self):
        from findings.constants import finding_status_dir
        result = finding_status_dir("CONFIRMED")
        assert result == FINDINGS_ROOT / "CONFIRMED"