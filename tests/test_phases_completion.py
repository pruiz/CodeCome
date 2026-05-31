"""Tests for phases/completion.py constants cleanup (P18)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from findings.constants import (
    FINDINGS_ROOT,
    EVIDENCE_ROOT,
    NOTES_ROOT,
    REPORTS_ROOT,
    SANDBOX_PLAN_PATH,
    evidence_dir_for,
    exploits_dir_for,
    finding_status_dir,
)


class TestImportsFromFindingsConstants:
    def test_completion_module_compiles(self):
        import py_compile
        py_compile.compile(str(ROOT / "tools" / "phases" / "completion.py"), doraise=True)

    def test_completion_imports_findings_constants(self):
        from phases.completion import (
            FINDINGS_ROOT as CG_FINDINGS_ROOT,
            EVIDENCE_ROOT as CG_EVIDENCE_ROOT,
            NOTES_ROOT as CG_NOTES_ROOT,
            REPORTS_ROOT as CG_REPORTS_ROOT,
            SANDBOX_PLAN_PATH as CG_SANDBOX_PLAN_PATH,
            evidence_dir_for,
            exploits_dir_for,
            finding_status_dir,
        )
        assert CG_FINDINGS_ROOT == FINDINGS_ROOT
        assert CG_EVIDENCE_ROOT == EVIDENCE_ROOT
        assert CG_NOTES_ROOT == NOTES_ROOT
        assert CG_REPORTS_ROOT == REPORTS_ROOT
        assert CG_SANDBOX_PLAN_PATH == SANDBOX_PLAN_PATH

    def test_no_hardcoded_itemdb_paths_in_completion_check(self):
        from phases.completion import check_phase_graceful_completion
        import ast

        source = (ROOT / "tools" / "phases" / "completion.py").read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name != "check_phase_graceful_completion":
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.Constant) or not isinstance(child.value, str):
                    continue
                if "itemdb" in child.value and "/itemdb/" in child.value:
                    pytest.fail(
                        f"Found hardcoded itemdb path in check_phase_graceful_completion: {child.value!r}"
                    )


class TestCheckPhaseGracefulCompletionUsesConstants:
    def test_phase1_uses_notes_root_via_constant(self):
        import ast
        source = (ROOT / "tools" / "phases" / "completion.py").read_text()
        tree = ast.parse(source)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "findings.constants":
                imported_names.update(alias.asname or alias.name for alias in node.names)
        assert "NOTES_ROOT" in imported_names
        assert "SANDBOX_PLAN_PATH" in imported_names

    def test_phase1_check_patches_notes_root_and_sandbox_plan(self, tmp_path):
        import phases.completion as completion_mod

        orig_notes_root = completion_mod.NOTES_ROOT
        orig_sandbox_plan = completion_mod.SANDBOX_PLAN_PATH
        orig_root = completion_mod.ROOT

        completion_mod.NOTES_ROOT = tmp_path
        completion_mod.SANDBOX_PLAN_PATH = tmp_path / "sandbox-plan.md"
        completion_mod.ROOT = tmp_path / "codecome_workspace"

        fake_time = time.time() - 2

        (completion_mod.ROOT / "sandbox").mkdir(parents=True)
        (completion_mod.ROOT / "sandbox" / "CODECOME-GENERATED.md").write_text("")
        completion_mod.SANDBOX_PLAN_PATH.write_text("")

        for name in completion_mod._PHASE1_REQUIRED_ARTIFACT_NAMES:
            artifact = tmp_path / name
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("")

        try:
            result = completion_mod.check_phase_graceful_completion("1", None, fake_time)
            assert result is True, "Phase 1 should succeed when all artifacts exist under patched NOTES_ROOT"
            result = completion_mod.check_phase_graceful_completion("1c", None, fake_time)
            assert result is True, "Phase 1c should use the same artifact gate as Phase 1"
        finally:
            completion_mod.NOTES_ROOT = orig_notes_root
            completion_mod.SANDBOX_PLAN_PATH = orig_sandbox_plan
            completion_mod.ROOT = orig_root

    def test_phase1c_accepts_fresh_sandbox_state_with_existing_notes(self, tmp_path):
        import phases.completion as completion_mod

        orig_notes_root = completion_mod.NOTES_ROOT
        orig_sandbox_plan = completion_mod.SANDBOX_PLAN_PATH
        orig_root = completion_mod.ROOT

        completion_mod.NOTES_ROOT = tmp_path / "notes"
        completion_mod.SANDBOX_PLAN_PATH = completion_mod.NOTES_ROOT / "sandbox-plan.md"
        completion_mod.ROOT = tmp_path / "codecome_workspace"

        for name in completion_mod._PHASE1_REQUIRED_ARTIFACT_NAMES:
            artifact = completion_mod.NOTES_ROOT / name
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("", encoding="utf-8")

        run_start = time.time()
        sandbox_generated = completion_mod.ROOT / "sandbox" / "CODECOME-GENERATED.md"
        sandbox_generated.parent.mkdir(parents=True)

        try:
            assert completion_mod.check_phase_graceful_completion("1", None, run_start) is False
            sandbox_generated.write_text("validated", encoding="utf-8")
            assert completion_mod.check_phase_graceful_completion("1c", None, run_start) is True
        finally:
            completion_mod.NOTES_ROOT = orig_notes_root
            completion_mod.SANDBOX_PLAN_PATH = orig_sandbox_plan
            completion_mod.ROOT = orig_root

    def test_phase2_uses_finding_status_dir_via_ast(self):
        import ast
        source = (ROOT / "tools" / "phases" / "completion.py").read_text()
        tree = ast.parse(source)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "findings.constants":
                imported_names.update(alias.asname or alias.name for alias in node.names)
        assert "finding_status_dir" in imported_names

    def test_phase4_uses_evidence_dir_for_via_ast(self):
        import ast
        source = (ROOT / "tools" / "phases" / "completion.py").read_text()
        tree = ast.parse(source)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "findings.constants":
                imported_names.update(alias.asname or alias.name for alias in node.names)
        assert "evidence_dir_for" in imported_names

    def test_phase5_uses_exploits_dir_for_and_finding_status_dir_via_ast(self):
        import ast
        source = (ROOT / "tools" / "phases" / "completion.py").read_text()
        tree = ast.parse(source)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "findings.constants":
                imported_names.update(alias.asname or alias.name for alias in node.names)
        assert "exploits_dir_for" in imported_names
        assert "finding_status_dir" in imported_names

    def test_phase6_uses_reports_root_via_ast(self):
        import ast
        source = (ROOT / "tools" / "phases" / "completion.py").read_text()
        tree = ast.parse(source)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "findings.constants":
                imported_names.update(alias.asname or alias.name for alias in node.names)
        assert "REPORTS_ROOT" in imported_names


class TestPhaseChecklistLinesUsesConstants:
    def test_phase1_checklist_uses_notes_root_relative_path(self):
        from phases.completion import phase_checklist_lines

        lines = phase_checklist_lines("1", None)
        assert f"under {NOTES_ROOT.relative_to(ROOT)}/" in lines[0]

    def test_phase2_checklist_uses_findings_root_relative_path(self):
        from phases.completion import phase_checklist_lines

        lines = phase_checklist_lines("2", None)
        assert f"under {FINDINGS_ROOT.relative_to(ROOT)}/PENDING/" in lines[0]

    def test_phase4_checklist_uses_evidence_root_relative_path(self):
        from phases.completion import phase_checklist_lines

        lines = phase_checklist_lines("4", "CC-0001")
        assert f"under {EVIDENCE_ROOT.relative_to(ROOT)}/CC-0001/" in lines[0]

    def test_phase5_checklist_uses_evidence_root_relative_path(self):
        from phases.completion import phase_checklist_lines

        lines = phase_checklist_lines("5", "CC-0001")
        exploits_path = f"{EVIDENCE_ROOT.relative_to(ROOT)}/CC-0001/exploits/"
        assert exploits_path in lines[0], f"{exploits_path!r} not found in {lines[0]!r}"

    def test_phase6_checklist_uses_reports_root_relative_path(self):
        from phases.completion import phase_checklist_lines

        lines = phase_checklist_lines("6", None)
        assert f"under {REPORTS_ROOT.relative_to(ROOT)}/" in lines[0]


class TestNoReintroductionOfHardcodedPaths:
    def test_no_literal_itemdb_findings_in_source(self):
        source = (ROOT / "tools" / "phases" / "completion.py").read_text()
        lines_with_itemdb = []
        for i, line in enumerate(source.splitlines(), 1):
            if '"/itemdb/findings"' in line or "'/itemdb/findings'" in line:
                lines_with_itemdb.append(f"  line {i}: {line.strip()}")
        assert not lines_with_itemdb, "Found hardcoded /itemdb/findings paths:\n" + "\n".join(lines_with_itemdb)

    def test_no_literal_itemdb_evidence_in_source(self):
        source = (ROOT / "tools" / "phases" / "completion.py").read_text()
        lines_with_itemdb = []
        for i, line in enumerate(source.splitlines(), 1):
            if '"/itemdb/evidence"' in line or "'/itemdb/evidence'" in line:
                lines_with_itemdb.append(f"  line {i}: {line.strip()}")
        assert not lines_with_itemdb, "Found hardcoded /itemdb/evidence paths:\n" + "\n".join(lines_with_itemdb)

    def test_no_literal_itemdb_reports_in_source(self):
        source = (ROOT / "tools" / "phases" / "completion.py").read_text()
        lines_with_itemdb = []
        for i, line in enumerate(source.splitlines(), 1):
            if '"/itemdb/reports"' in line or "'/itemdb/reports'" in line:
                lines_with_itemdb.append(f"  line {i}: {line.strip()}")
        assert not lines_with_itemdb, "Found hardcoded /itemdb/reports paths:\n" + "\n".join(lines_with_itemdb)

    def test_no_literal_itemdb_notes_in_source(self):
        source = (ROOT / "tools" / "phases" / "completion.py").read_text()
        lines_with_itemdb = []
        for i, line in enumerate(source.splitlines(), 1):
            if '"/itemdb/notes"' in line or "'/itemdb/notes'" in line:
                lines_with_itemdb.append(f"  line {i}: {line.strip()}")
        assert not lines_with_itemdb, "Found hardcoded /itemdb/notes paths:\n" + "\n".join(lines_with_itemdb)
