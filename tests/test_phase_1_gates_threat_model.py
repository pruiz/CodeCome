from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def test_required_notes_1b_includes_threat_model() -> None:
    from phases.phase_1_gates import REQUIRED_NOTES_1B

    assert "threat-model.md" in REQUIRED_NOTES_1B


def test_check_phase_1b_missing_threat_model(tmp_path: Path, capsys) -> None:
    from phases.phase_1_gates import check_phase_1b

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)

    # Create all required notes except threat-model.md
    from phases.phase_1_gates import REQUIRED_NOTES_1B
    for name in REQUIRED_NOTES_1B:
        if name != "threat-model.md":
            (notes / name).write_text("", encoding="utf-8")

    with patch("phases.phase_1_gates.ROOT", tmp_path):
        rc = check_phase_1b()

    assert rc == 1


def test_check_phase_1b_has_detailed_reconnaissance_labels(tmp_path: Path, capsys) -> None:
    from phases.phase_1_gates import check_phase_1b

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)

    from phases.phase_1_gates import REQUIRED_NOTES_1B
    for name in REQUIRED_NOTES_1B:
        (notes / name).write_text("", encoding="utf-8")

    with patch("phases.phase_1_gates.ROOT", tmp_path):
        check_phase_1b()

    out = capsys.readouterr().out
    assert "Detailed Reconnaissance" in out
    assert "CodeQL-assisted Reconnaissance" not in out


def test_required_notes_includes_threat_model() -> None:
    from phases.gates import REQUIRED_NOTES

    assert "threat-model.md" in REQUIRED_NOTES


def test_phase_2_gate_checks_threat_model(tmp_path: Path, capsys) -> None:
    from phases.gates import gate_phase_2

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (notes / "target-profile.md").write_text("", encoding="utf-8")
    (notes / "attack-surface.md").write_text("", encoding="utf-8")

    with patch("phases.gates.ROOT", tmp_path):
        rc = gate_phase_2()

    # Should fail because threat-model.md is missing
    assert rc == 1
    out = capsys.readouterr().out
    assert "threat-model.md" in out


def test_phase_2_gate_passes_with_threat_model(tmp_path: Path, capsys) -> None:
    from phases.gates import gate_phase_2

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (notes / "target-profile.md").write_text("", encoding="utf-8")
    (notes / "attack-surface.md").write_text("", encoding="utf-8")
    (notes / "threat-model.md").write_text("", encoding="utf-8")

    with patch("phases.gates.ROOT", tmp_path):
        rc = gate_phase_2()

    assert rc == 0
