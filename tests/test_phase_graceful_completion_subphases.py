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
        result = check_phase_graceful_completion("1a", None, now - 1)

    assert result is True


def test_phase_1a_graceful_completion_fails_if_no_1a_artifacts_fresh(tmp_path: Path) -> None:
    """Phase 1a should return False when no 1a artifacts are fresh."""
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)

    now = time.time()

    with patch("phases.completion.ROOT", tmp_path):
        result = check_phase_graceful_completion("1a", None, now)

    assert result is False


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
        result = check_phase_graceful_completion("1b", None, now - 1)

    assert result is True


def test_phase_1b_graceful_completion_fails_if_no_1b_artifacts_fresh(tmp_path: Path) -> None:
    """Phase 1b should return False when no 1b artifacts are fresh."""
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)

    # Create only Phase 1a artifacts — which are excluded from 1b check
    now = time.time()
    (notes / "target-profile.md").write_text("", encoding="utf-8")
    (notes / "target-profile.md").touch()
    (notes / "sandbox-plan.md").write_text("", encoding="utf-8")
    (notes / "sandbox-plan.md").touch()

    with patch("phases.completion.ROOT", tmp_path):
        result = check_phase_graceful_completion("1b", None, now - 1)

    assert result is False


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
        result = check_phase_graceful_completion("1b", None, now - 1)

    assert result is False


def test_phase_1c_still_requires_sandbox_state(tmp_path: Path) -> None:
    """Phase 1c should require sandbox-plan.md and sandbox state."""
    from phases.completion import check_phase_graceful_completion

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "sandbox").mkdir()

    now = time.time()

    # Write all Phase 1 notes — needed because the monolith path requires all
    from phases.completion import _PHASE1_REQUIRED_ARTIFACT_NAMES
    for name in _PHASE1_REQUIRED_ARTIFACT_NAMES:
        (notes / name).write_text("content", encoding="utf-8")
        (notes / name).touch()

    # No CODECOME-GENERATED.md, no run summary — should fail for 1c
    with patch("phases.completion.ROOT", tmp_path):
        result = check_phase_graceful_completion("1c", None, now - 1)

    assert result is False
