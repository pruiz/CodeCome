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


def test_phase2_artifacts_accept_explicit_no_findings_summary(tmp_path: Path) -> None:
    from phases.artifact_checks import check_phase_2_artifacts

    runs = tmp_path / "runs"
    runs.mkdir(parents=True)
    (runs / "phase-2-summary-2026-06-16-120000.md").write_text(
        "# Findings created\n\n"
        "| ID | Title | Path |\n"
        "|---|---|---|\n"
        "| - | None. | - |\n",
        encoding="utf-8",
    )

    with patch("phases.artifact_checks.ROOT", tmp_path):
        assert check_phase_2_artifacts() == []


def test_phase2_artifacts_reject_stub_finding(tmp_path: Path) -> None:
    from phases.artifact_checks import check_phase_2_artifacts

    runs = tmp_path / "runs"
    pending = tmp_path / "itemdb" / "findings" / "PENDING"
    runs.mkdir(parents=True)
    pending.mkdir(parents=True)
    (runs / "phase-2-summary-2026-06-16-120000.md").write_text(
        "# Findings created\n\n"
        "| ID | Title | Path |\n"
        "|---|---|---|\n"
        "| CC-0001 | Stub | itemdb/findings/PENDING/CC-0001-stub.md |\n",
        encoding="utf-8",
    )
    (pending / "CC-0001-stub.md").write_text(
        "---\n"
        "id: \"CC-0001\"\n"
        "title: \"Stub\"\n"
        "status: \"PENDING\"\n"
        "severity: \"MEDIUM\"\n"
        "cvss_v4:\n  vector: \"\"\n  score: 0.0\n  justification: \"\"\n"
        "confidence: \"LOW\"\ncategory: \"Unclassified\"\ncwe: []\nlanguage: \"unknown\"\ntarget_area: \"unknown\"\n"
        "files: []\nsymbols: []\nentry_points: []\nsources: []\nsinks: []\ntrust_boundary: \"unknown\"\nassets_at_risk: []\n"
        "validation:\n  status: \"NOT_STARTED\"\n  methods: []\n  evidence_dir: \"itemdb/evidence/CC-0001\"\n  summary: \"\"\n"
        "exploitation:\n  status: \"NOT_STARTED\"\n  impact_demonstrated: \"\"\n  exploit_type: \"\"\n  severity_before: \"\"\n  severity_after: \"\"\n  artifacts_dir: \"itemdb/evidence/CC-0001/exploits\"\n  summary: \"\"\n"
        "created_at: \"2026-06-16\"\nupdated_at: \"2026-06-16\"\n---\n\n# Summary\n\nPending.\n",
        encoding="utf-8",
    )

    with patch("phases.artifact_checks.ROOT", tmp_path):
        errors = check_phase_2_artifacts()

    assert any("not a complete Phase 2 finding" in error for error in errors), errors


def test_phase2_artifacts_report_all_quality_errors(tmp_path: Path, monkeypatch) -> None:
    from phases.artifact_checks import check_phase_2_artifacts
    from findings import quality as quality_mod

    runs = tmp_path / "runs"
    pending = tmp_path / "itemdb" / "findings" / "PENDING"
    runs.mkdir(parents=True)
    pending.mkdir(parents=True)
    (runs / "phase-2-summary-2026-06-18-120000.md").write_text(
        "# Findings created\n\n"
        "| ID | Title | Path |\n"
        "|---|---|---|\n"
        "| CC-0099 | Many | itemdb/findings/PENDING/CC-0099-many-errors.md |\n",
        encoding="utf-8",
    )
    (pending / "CC-0099-many-errors.md").write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(
        quality_mod,
        "validate_phase2_finding_quality",
        lambda _path: [f"artifact-error-{i}" for i in range(7)],
    )

    with patch("phases.artifact_checks.ROOT", tmp_path):
        errors = check_phase_2_artifacts()

    joined = "\n".join(errors)
    for i in range(7):
        assert f"artifact-error-{i}" in joined
