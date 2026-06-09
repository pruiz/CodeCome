from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def test_phase_1a_graceful_completion_only_checks_1a_artifacts(tmp_path: Path) -> None:
    """Phase 1a should return True when 1a artifacts and a fresh run summary are present."""
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    runs = tmp_path / "runs"
    runs.mkdir(parents=True)

    now = time.time()
    (notes / "target-profile.md").write_text("content", encoding="utf-8")
    (notes / "build-model.md").write_text("content", encoding="utf-8")
    (notes / "codeql-plan.yml").write_text("schema_version: 1", encoding="utf-8")

    # touch to ensure mtimes are >= now
    (notes / "target-profile.md").touch()
    (notes / "build-model.md").touch()
    (notes / "codeql-plan.yml").touch()

    summary = runs / "phase-1a-summary.md"
    summary.write_text("", encoding="utf-8")
    summary.touch()

    with patch("phases.completion.ROOT", tmp_path):
        ok, failures = check_phase_graceful_completion("1a", None, now - 1)

    assert ok is True
    assert failures == []


def test_phase_1a_graceful_completion_fails_if_no_1a_artifacts_fresh(tmp_path: Path) -> None:
    """Phase 1a should return False when no 1a artifacts are fresh."""
    import phases.completion as completion_mod
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "runs").mkdir(parents=True, exist_ok=True)

    now = time.time()

    orig_root = completion_mod.ROOT
    orig_notes_root = completion_mod.NOTES_ROOT
    completion_mod.ROOT = tmp_path
    completion_mod.NOTES_ROOT = tmp_path / "itemdb" / "notes"
    try:
        with patch("phases.completion.ROOT", tmp_path):
            ok, failures = check_phase_graceful_completion("1a", None, now)
    finally:
        completion_mod.ROOT = orig_root
        completion_mod.NOTES_ROOT = orig_notes_root

    assert ok is False
    assert failures, "Expected failure details when no 1a artifacts are fresh"
    assert any("itemdb/notes" in f for f in failures), (
        f"Expected failure detail to mention itemdb/notes, got {failures!r}"
    )
    assert any("runs/phase-1a-summary*.md" in f for f in failures), (
        f"Expected phase-1a summary failure, got {failures!r}"
    )


def test_phase_1b_graceful_completion_only_checks_1b_artifacts(tmp_path: Path) -> None:
    """Phase 1b should return True when sandbox bootstrap artifacts and a fresh run summary are present."""
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir(parents=True)
    runs = tmp_path / "runs"
    runs.mkdir(parents=True)

    now = time.time()

    (notes / "sandbox-plan.md").write_text("content", encoding="utf-8")
    (notes / "sandbox-plan.md").touch()
    (sandbox_dir / "CODECOME-GENERATED.md").write_text("content", encoding="utf-8")
    (sandbox_dir / "CODECOME-GENERATED.md").touch()

    summary = runs / "phase-1b-summary.md"
    summary.write_text("", encoding="utf-8")
    summary.touch()

    with patch("phases.completion.ROOT", tmp_path):
        ok, failures = check_phase_graceful_completion("1b", None, now - 1)

    assert ok is True
    assert failures == []


def test_phase_1b_graceful_completion_fails_if_no_1b_artifacts_fresh(tmp_path: Path) -> None:
    """Phase 1b should return False when no 1b artifacts are fresh."""
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)

    # Create only non-1b artifacts (1a + 1c) — excluded from 1b check
    now = time.time()
    (notes / "target-profile.md").write_text("", encoding="utf-8")
    (notes / "target-profile.md").touch()
    (notes / "sandbox-plan.md").write_text("", encoding="utf-8")
    (notes / "sandbox-plan.md").touch()

    with patch("phases.completion.ROOT", tmp_path):
        ok, failures = check_phase_graceful_completion("1b", None, now - 1)

    assert ok is False
    assert failures, "Expected failure details when no 1b artifacts are fresh"


def test_phase_1b_excludes_sandbox_plan_from_check(tmp_path: Path) -> None:
    """Fresh sandbox-plan.md should not count towards Phase 1b graceful completion."""
    import phases.completion as completion_mod
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "runs").mkdir(parents=True, exist_ok=True)

    now = time.time()

    # Only sandbox-plan.md exists (not a 1b artifact)
    (notes / "sandbox-plan.md").write_text("content", encoding="utf-8")
    (notes / "sandbox-plan.md").touch()

    orig_root = completion_mod.ROOT
    orig_notes_root = completion_mod.NOTES_ROOT
    completion_mod.ROOT = tmp_path
    completion_mod.NOTES_ROOT = tmp_path / "itemdb" / "notes"
    try:
        with patch("phases.completion.ROOT", tmp_path):
            ok, failures = check_phase_graceful_completion("1b", None, now - 1)
    finally:
        completion_mod.ROOT = orig_root
        completion_mod.NOTES_ROOT = orig_notes_root

    assert ok is False
    assert failures, "Expected failure details when only sandbox-plan.md is fresh for 1b"
    assert any("runs/phase-1b-summary*.md" in f for f in failures), (
        f"Expected phase-1b summary failure, got {failures!r}"
    )


def test_phase_1c_passes_with_fresh_sandbox_plan(tmp_path: Path) -> None:
    """Phase 1c should return True when recon notes and a fresh run summary are present."""
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    runs = tmp_path / "runs"
    runs.mkdir(parents=True)

    now = time.time()
    (notes / "attack-surface.md").write_text("content", encoding="utf-8")
    (notes / "attack-surface.md").touch()

    summary = runs / "phase-1c-summary.md"
    summary.write_text("", encoding="utf-8")
    summary.touch()

    with patch("phases.completion.ROOT", tmp_path):
        ok, failures = check_phase_graceful_completion("1c", None, now - 1)

    assert ok is True
    assert failures == []


def test_phase_1c_fails_without_sandbox_artifacts(tmp_path: Path) -> None:
    """Phase 1c should return False when no recon notes are fresh."""
    import phases.completion as completion_mod
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "sandbox").mkdir()
    (tmp_path / "runs").mkdir(parents=True, exist_ok=True)

    now = time.time()

    # Write sandbox artifacts but NOT recon notes
    (notes / "sandbox-plan.md").write_text("content", encoding="utf-8")
    (tmp_path / "sandbox" / "CODECOME-GENERATED.md").write_text("content", encoding="utf-8")

    orig_root = completion_mod.ROOT
    orig_notes_root = completion_mod.NOTES_ROOT
    completion_mod.ROOT = tmp_path
    completion_mod.NOTES_ROOT = tmp_path / "itemdb" / "notes"
    try:
        with patch("phases.completion.ROOT", tmp_path):
            ok, failures = check_phase_graceful_completion("1c", None, now)
    finally:
        completion_mod.ROOT = orig_root
        completion_mod.NOTES_ROOT = orig_notes_root

    assert ok is False
    assert failures, "Expected failure details when no 1c artifacts are fresh"
    assert any("phase-1c required notes" in f for f in failures), (
        f"Expected failure detail to mention recon notes, got {failures!r}"
    )
    assert any("runs/phase-1c-summary*.md" in f for f in failures), (
        f"Expected phase-1c summary failure, got {failures!r}"
    )
