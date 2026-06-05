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
        import os
        import phases.completion as completion_mod

        orig_notes_root = completion_mod.NOTES_ROOT
        orig_sandbox_plan = completion_mod.SANDBOX_PLAN_PATH
        orig_root = completion_mod.ROOT

        completion_mod.NOTES_ROOT = tmp_path
        completion_mod.SANDBOX_PLAN_PATH = tmp_path / "sandbox-plan.md"
        completion_mod.ROOT = tmp_path / "codecome_workspace"

        fake_time = time.time()

        (completion_mod.ROOT / "sandbox").mkdir(parents=True)
        (completion_mod.ROOT / "sandbox" / "CODECOME-GENERATED.md").write_text("")
        os.utime(completion_mod.ROOT / "sandbox" / "CODECOME-GENERATED.md", (fake_time + 60, fake_time + 60))
        completion_mod.SANDBOX_PLAN_PATH.write_text("")
        os.utime(completion_mod.SANDBOX_PLAN_PATH, (fake_time + 60, fake_time + 60))

        for name in completion_mod._PHASE1_REQUIRED_ARTIFACT_NAMES:
            artifact = tmp_path / name
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("")
            os.utime(artifact, (fake_time + 60, fake_time + 60))

        # Create run summaries for each tested phase key
        for phase_id in ("1", "1c"):
            summary_dir = completion_mod.ROOT / "runs"
            summary_dir.mkdir(parents=True, exist_ok=True)
            summary = summary_dir / f"phase-{phase_id}-summary.md"
            summary.write_text("")
            os.utime(summary, (fake_time + 60, fake_time + 60))

        try:
            ok, failures = completion_mod.check_phase_graceful_completion("1", None, fake_time)
            assert ok is True, f"Phase 1 should succeed when all artifacts exist; failures={failures!r}"
            assert failures == []
            ok, failures = completion_mod.check_phase_graceful_completion("1c", None, fake_time)
            assert ok is True, f"Phase 1c should use the same artifact gate as Phase 1; failures={failures!r}"
            assert failures == []
        finally:
            completion_mod.NOTES_ROOT = orig_notes_root
            completion_mod.SANDBOX_PLAN_PATH = orig_sandbox_plan
            completion_mod.ROOT = orig_root

    def test_phase1c_accepts_fresh_sandbox_state_with_existing_notes(self, tmp_path):
        import os
        import phases.completion as completion_mod

        orig_notes_root = completion_mod.NOTES_ROOT
        orig_sandbox_plan = completion_mod.SANDBOX_PLAN_PATH
        orig_root = completion_mod.ROOT

        completion_mod.NOTES_ROOT = tmp_path / "notes"
        completion_mod.SANDBOX_PLAN_PATH = completion_mod.NOTES_ROOT / "sandbox-plan.md"
        completion_mod.ROOT = tmp_path / "codecome_workspace"

        run_start = time.time()

        for name in completion_mod._PHASE1_REQUIRED_ARTIFACT_NAMES:
            artifact = completion_mod.NOTES_ROOT / name
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("", encoding="utf-8")
            os.utime(artifact, (run_start - 60, run_start - 60))

        sandbox_generated = completion_mod.ROOT / "sandbox" / "CODECOME-GENERATED.md"
        sandbox_generated.parent.mkdir(parents=True)

        try:
            ok, failures = completion_mod.check_phase_graceful_completion("1", None, run_start)
            assert ok is False
            assert failures, "Expected failure details for phase 1 with no fresh artifacts"
            sandbox_generated.write_text("validated", encoding="utf-8")
            os.utime(sandbox_generated, (run_start + 60, run_start + 60))
            summary_dir = completion_mod.ROOT / "runs"
            summary_dir.mkdir(parents=True, exist_ok=True)
            summary = summary_dir / "phase-1c-summary.md"
            summary.write_text("", encoding="utf-8")
            os.utime(summary, (run_start + 60, run_start + 60))
            ok, failures = completion_mod.check_phase_graceful_completion("1c", None, run_start)
            assert ok is True, f"Phase 1c should pass; failures={failures!r}"
            assert failures == []
        finally:
            completion_mod.NOTES_ROOT = orig_notes_root
            completion_mod.SANDBOX_PLAN_PATH = orig_sandbox_plan
            completion_mod.ROOT = orig_root

    def test_phase2_accepts_summary_with_no_new_findings(self, tmp_path):
        """Phase 2 should pass when only the run summary is fresh (no new findings)."""
        import os
        import phases.completion as completion_mod

        orig_root = completion_mod.ROOT
        orig_findings_root = completion_mod.FINDINGS_ROOT
        completion_mod.ROOT = tmp_path
        completion_mod.FINDINGS_ROOT = tmp_path / "itemdb" / "findings"
        (tmp_path / "runs").mkdir(parents=True, exist_ok=True)
        summary = tmp_path / "runs" / "phase-2-summary-2026-06-05-143022.md"
        summary.write_text("", encoding="utf-8")
        run_start = time.time() - 60
        os.utime(summary, (run_start + 60, run_start + 60))

        try:
            ok, failures = completion_mod.check_phase_graceful_completion("2", None, run_start)
            assert ok is True, f"Phase 2 should pass with fresh summary alone; failures={failures!r}"
            assert failures == []
        finally:
            completion_mod.ROOT = orig_root
            completion_mod.FINDINGS_ROOT = orig_findings_root

    def test_phase2_failure_details_mention_run_summary(self, tmp_path):
        """Phase 2 should report missing run summary when nothing is freshened."""
        import phases.completion as completion_mod

        orig_root = completion_mod.ROOT
        orig_findings_root = completion_mod.FINDINGS_ROOT
        completion_mod.ROOT = tmp_path
        completion_mod.FINDINGS_ROOT = tmp_path / "itemdb" / "findings"
        (tmp_path / "runs").mkdir(parents=True, exist_ok=True)

        try:
            ok, failures = completion_mod.check_phase_graceful_completion("2", None, time.time())
            assert ok is False
            assert any("runs/phase-2-summary" in f for f in failures), (
                f"Expected failure detail to mention runs/phase-2-summary, got {failures!r}"
            )
        finally:
            completion_mod.ROOT = orig_root
            completion_mod.FINDINGS_ROOT = orig_findings_root

    def test_phase4_failure_details_mention_evidence_dir(self, tmp_path):
        """Phase 4 should report missing evidence dir and finding file when nothing is freshened."""
        import phases.completion as completion_mod

        orig_root = completion_mod.ROOT
        orig_findings_root = completion_mod.FINDINGS_ROOT
        orig_evidence_root = completion_mod.EVIDENCE_ROOT
        orig_reports_root = completion_mod.REPORTS_ROOT

        completion_mod.ROOT = tmp_path
        completion_mod.FINDINGS_ROOT = tmp_path / "itemdb" / "findings"
        completion_mod.EVIDENCE_ROOT = tmp_path / "itemdb" / "evidence"
        completion_mod.REPORTS_ROOT = tmp_path / "itemdb" / "reports"

        try:
            ok, failures = completion_mod.check_phase_graceful_completion("4", "CC-0001", time.time())
            assert ok is False
            assert any("itemdb/evidence/CC-0001" in f for f in failures), (
                f"Expected failure detail to mention evidence dir, got {failures!r}"
            )
            assert any("CC-0001" in f for f in failures), (
                f"Expected failure detail to mention finding id, got {failures!r}"
            )
        finally:
            completion_mod.ROOT = orig_root
            completion_mod.FINDINGS_ROOT = orig_findings_root
            completion_mod.EVIDENCE_ROOT = orig_evidence_root
            completion_mod.REPORTS_ROOT = orig_reports_root

    def test_phase6_failure_details_mention_reports_dir(self, tmp_path):
        """Phase 6 should report missing reports dir when nothing is freshened."""
        import phases.completion as completion_mod

        orig_root = completion_mod.ROOT
        orig_reports_root = completion_mod.REPORTS_ROOT
        completion_mod.ROOT = tmp_path
        completion_mod.REPORTS_ROOT = tmp_path / "itemdb" / "reports"

        try:
            ok, failures = completion_mod.check_phase_graceful_completion("6", None, time.time())
            assert ok is False
            assert any("itemdb/reports" in f for f in failures), (
                f"Expected failure detail to mention itemdb/reports, got {failures!r}"
            )
        finally:
            completion_mod.ROOT = orig_root
            completion_mod.REPORTS_ROOT = orig_reports_root

    def test_unknown_phase_returns_descriptive_failure(self):
        """Unknown phases should return a descriptive failure rather than bare (False, [])."""
        from phases.completion import check_phase_graceful_completion

        ok, failures = check_phase_graceful_completion("7", None, 0.0)
        assert ok is False
        assert failures, "Unknown phase should report a failure message"
        assert any("No completion gate defined" in f for f in failures), (
            f"Expected 'No completion gate defined' message, got {failures!r}"
        )

    def test_phase2_checklist_mentions_run_summary_and_no_new_findings(self):
        """The phase-2 checklist should make the run-summary obligation visible to resumed models."""
        from phases.completion import phase_checklist_lines

        lines = phase_checklist_lines("2", None)
        joined = "\n".join(lines)
        assert "phase-2-summary-YYYY-MM-DD-HHMMSS" in joined, (
            f"Expected checklist to mention timestamped summary path, got: {lines!r}"
        )
        assert "no new vulnerabilities" in joined.lower() or "no new finding" in joined.lower(), (
            f"Expected checklist to mention the no-new-findings guidance, got: {lines!r}"
        )

    def test_resume_prompt_with_failure_details_lists_missing_artifacts(self):
        """Resume prompt should include a 'Missing required artifacts:' block when given details."""
        from phases.completion import build_phase_resume_prompt

        prompt = build_phase_resume_prompt(
            "2", None, "stop", 1,
            failure_details=[
                "Missing: runs/phase-2-summary-*.md — run summary was not created or updated",
            ],
        )
        assert "Missing required artifacts:" in prompt
        assert "runs/phase-2-summary-*.md" in prompt
        assert "Fix only these missing items." in prompt

    def test_resume_prompt_without_failure_details_uses_generic_wording(self):
        """Resume prompt should use the generic reassess wording when no failure details given."""
        from phases.completion import build_phase_resume_prompt

        prompt = build_phase_resume_prompt("2", None, "stop", 1)
        assert "Missing required artifacts:" not in prompt
        assert "briefly reassess" in prompt

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
