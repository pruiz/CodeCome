from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def test_phase_1a_graceful_completion_only_checks_1a_artifacts(tmp_path: Path) -> None:
    """Phase 1a should return True when 1a artifacts are fresh, even if 1b/1c artifacts are missing."""
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)

    now = time.time()
    (notes / "target-profile.md").write_text("content", encoding="utf-8")
    (notes / "build-model.md").write_text("content", encoding="utf-8")
    (notes / "codeql-plan.yml").write_text("schema_version: 1", encoding="utf-8")

    # touch to ensure mtimes are >= now
    (notes / "target-profile.md").touch()
    (notes / "build-model.md").touch()
    (notes / "codeql-plan.yml").touch()

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


def test_phase_1b_graceful_completion_only_checks_1b_artifacts(tmp_path: Path) -> None:
    """Phase 1b should return True when 1b artifacts are fresh, even if sandbox-plan.md is missing."""
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)

    now = time.time()

    # Write 1b artifacts but no sandbox-plan.md or 1a artifacts
    names_1b = [
        "attack-surface.md", "execution-model.md", "trust-boundaries.md",
        "data-flow.md", "threat-model.md", "validation-model.md",
        "interesting-files.md", "file-risk-index.yml", "security-assumptions.md",
    ]
    for name in names_1b:
        (notes / name).write_text("content", encoding="utf-8")
        (notes / name).touch()

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
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)

    now = time.time()

    # Only sandbox-plan.md exists (not a 1b artifact)
    (notes / "sandbox-plan.md").write_text("content", encoding="utf-8")
    (notes / "sandbox-plan.md").touch()

    with patch("phases.completion.ROOT", tmp_path):
        ok, failures = check_phase_graceful_completion("1b", None, now - 1)

    assert ok is False
    assert failures, "Expected failure details when only sandbox-plan.md is fresh for 1b"


def test_phase_1c_passes_with_fresh_sandbox_plan(tmp_path: Path) -> None:
    """Phase 1c should return True when sandbox-plan.md is fresh, no monolith check needed."""
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "sandbox").mkdir()

    now = time.time()
    (notes / "sandbox-plan.md").write_text("content", encoding="utf-8")
    (notes / "sandbox-plan.md").touch()

    with patch("phases.completion.ROOT", tmp_path):
        ok, failures = check_phase_graceful_completion("1c", None, now - 1)

    assert ok is True
    assert failures == []


def test_phase_1c_fails_without_sandbox_artifacts(tmp_path: Path) -> None:
    """Phase 1c should return False when neither sandbox-plan.md nor CODECOME-GENERATED.md is fresh."""
    import phases.completion as completion_mod
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "sandbox").mkdir()

    now = time.time()

    # Write all Phase 1 notes except sandbox-plan.md so the old files exist but aren't fresh
    from phases.completion import _PHASE1_REQUIRED_ARTIFACT_NAMES
    for name in _PHASE1_REQUIRED_ARTIFACT_NAMES:
        if name != "sandbox-plan.md":
            (notes / name).write_text("content", encoding="utf-8")

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
    assert any("sandbox-plan.md" in f or "CODECOME-GENERATED.md" in f for f in failures), (
        f"Expected failure detail to mention sandbox artifacts, got {failures!r}"
    )
