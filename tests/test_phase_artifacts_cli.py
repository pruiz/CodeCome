from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def test_check_phase_artifacts_invalid_phase(capsys) -> None:
    from phases.artifact_checks import check_phase_artifacts

    rc = check_phase_artifacts("badphase")
    out = capsys.readouterr().out
    assert rc == 1
    assert "Invalid phase" in out


def test_allow_missing_generated_skips_missing_artifacts(capsys, tmp_path: Path) -> None:
    """Clean checkout (no generated artifacts) should pass."""
    from phases.artifact_checks import check_phase_artifacts

    (tmp_path / "itemdb" / "notes").mkdir(parents=True)
    (tmp_path / "runs").mkdir()

    with patch("phases.artifact_checks.ROOT", tmp_path):
        rc = check_phase_artifacts("all", allow_missing_generated=True)

    out = capsys.readouterr().out
    assert rc == 0
    assert "passed" in out


def test_strict_mode_fails_on_missing_threat_model(capsys, tmp_path: Path) -> None:
    from phases.artifact_checks import check_phase_1c_artifacts

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "runs").mkdir()

    with patch("phases.artifact_checks.ROOT", tmp_path):
        errors = check_phase_1c_artifacts(allow_missing_generated=False)

    assert any("threat-model.md" in e for e in errors)


def test_allow_missing_generated_skips_threat_model(tmp_path: Path) -> None:
    from phases.artifact_checks import check_phase_1c_artifacts

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "runs").mkdir()

    with patch("phases.artifact_checks.ROOT", tmp_path):
        errors = check_phase_1c_artifacts(allow_missing_generated=True)

    # Missing threat-model.md is tolerated under the flag
    assert not any("threat-model.md" in e and "Missing" in e for e in errors)


def test_malformed_threat_model_fails_even_with_flag(tmp_path: Path) -> None:
    from phases.artifact_checks import check_phase_1c_artifacts

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "runs").mkdir()

    # threat-model.md exists but lacks required headings
    (notes / "threat-model.md").write_text("# Only An Intro\n\nSome content.\n", encoding="utf-8")

    with patch("phases.artifact_checks.ROOT", tmp_path):
        errors = check_phase_1c_artifacts(allow_missing_generated=True)

    assert any("missing headings" in e for e in errors)


def test_phase_1_runs_all_subphase_checks(capsys, tmp_path: Path) -> None:
    from phases.artifact_checks import check_phase_artifacts

    (tmp_path / "itemdb" / "notes").mkdir(parents=True)
    (tmp_path / "runs").mkdir()

    with patch("phases.artifact_checks.ROOT", tmp_path):
        rc = check_phase_artifacts("1", allow_missing_generated=True)

    out = capsys.readouterr().out
    assert rc == 0
    assert "passed" in out


def test_phase_all_runs_all_implemented(capsys, tmp_path: Path) -> None:
    from phases.artifact_checks import check_phase_artifacts

    (tmp_path / "itemdb" / "notes").mkdir(parents=True)
    (tmp_path / "runs").mkdir()

    with patch("phases.artifact_checks.ROOT", tmp_path):
        rc = check_phase_artifacts("all", allow_missing_generated=True)

    out = capsys.readouterr().out
    assert rc == 0
    assert "passed" in out


def test_threat_model_heading_validation(tmp_path: Path) -> None:
    from phases.artifact_checks import check_phase_1c_artifacts

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "runs").mkdir()

    # Valid threat model
    lines = [
        "# Threat Model Summary",
        "# Scope",
        "# System model",
        "# Assets and security objectives",
        "# Attacker model",
        "# Trust boundary summary",
        "# Existing controls",
        "# Abuse-path themes for Phase 2",
        "# Risk calibration for review focus",
        "# Open questions for the user",
        "# Re-run prompt hints",
        "",
        "Content here.",
    ]
    (notes / "threat-model.md").write_text("\n".join(lines), encoding="utf-8")

    with patch("phases.artifact_checks.ROOT", tmp_path):
        errors = check_phase_1c_artifacts(allow_missing_generated=True)

    heading_errors = [e for e in errors if "headings" in e]
    assert heading_errors == [], f"unexpected: {heading_errors}"


def test_threat_model_missing_one_heading(tmp_path: Path) -> None:
    from phases.artifact_checks import check_phase_1c_artifacts

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "runs").mkdir()

    # Missing "Attacker model" heading
    content = "\n".join(
        f"# Threat Model Summary\n# Scope\n# System model\n"
        f"# Assets and security objectives\n"
        f"# Trust boundary summary\n# Existing controls\n"
        f"# Abuse-path themes for Phase 2\n# Risk calibration for review focus\n"
        f"# Open questions for the user\n# Re-run prompt hints\n"
    )
    (notes / "threat-model.md").write_text(content, encoding="utf-8")

    with patch("phases.artifact_checks.ROOT", tmp_path):
        errors = check_phase_1c_artifacts(allow_missing_generated=True)

    assert any("Attacker model" in e for e in errors)


def test_phase_1b_notes_all_required(tmp_path: Path) -> None:
    from phases.artifact_checks import check_phase_1c_artifacts, PHASE_1C_REQUIRED_NOTES

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "runs").mkdir()

    # Create all required notes as empty files
    for name in PHASE_1C_REQUIRED_NOTES:
        (notes / name).write_text("", encoding="utf-8")

    # Create valid threat-model with all headings
    content = "\n".join(
        f"# {h.lstrip('# ')}\n" for h in [
            "# Threat Model Summary", "# Scope", "# System model",
            "# Assets and security objectives", "# Attacker model",
            "# Trust boundary summary", "# Existing controls",
            "# Abuse-path themes for Phase 2", "# Risk calibration for review focus",
            "# Open questions for the user", "# Re-run prompt hints",
        ]
    )
    (notes / "threat-model.md").write_text(content, encoding="utf-8")

    with patch("phases.artifact_checks.ROOT", tmp_path):
        errors = check_phase_1c_artifacts(allow_missing_generated=True)

    assert errors == [], f"unexpected errors: {errors}"


def test_has_valid_threat_model(tmp_path: Path) -> None:
    from phases.artifact_checks import has_valid_threat_model

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)

    content = "\n".join(
        f"# {h.lstrip('# ')}\n" for h in [
            "# Threat Model Summary", "# Scope", "# System model",
            "# Assets and security objectives", "# Attacker model",
            "# Trust boundary summary", "# Existing controls",
            "# Abuse-path themes for Phase 2", "# Risk calibration for review focus",
            "# Open questions for the user", "# Re-run prompt hints",
        ]
    )
    (notes / "threat-model.md").write_text(content, encoding="utf-8")

    with patch("phases.artifact_checks.ROOT", tmp_path):
        assert has_valid_threat_model()


def test_has_valid_threat_model_returns_false_when_missing(tmp_path: Path) -> None:
    from phases.artifact_checks import has_valid_threat_model

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)

    with patch("phases.artifact_checks.ROOT", tmp_path):
        assert not has_valid_threat_model()
