from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from phases.phase_1_gates import _emit


def test_emit_plain_fallback_prints_formatted_text(capsys) -> None:
    _emit(None, "ok", "plain gate output")

    out = capsys.readouterr().out
    assert "plain gate output" in out


def test_unsupported_language_soft_policy_warns_not_fails(tmp_path: Path, capsys) -> None:
    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (notes / "target-profile.md").write_text("profile", encoding="utf-8")
    (notes / "build-model.md").write_text("model", encoding="utf-8")
    (notes / "codeql-plan.yml").write_text(
        "schema_version: 1\n"
        "recommended: true\n"
        "analysis_units:\n"
        "  - id: gilroy\n"
        "    path: ./src\n"
        "    languages:\n"
        "      - id: elixir\n"
        "        packs:\n"
        "          - official\n",
        encoding="utf-8",
    )

    (tmp_path / "src").mkdir()

    mock_config = type("cfg", (), {"fail_policy": "soft", "enabled": True})()

    from phases.phase_1_gates import check_phase_1a

    with patch("phases.phase_1_gates.ROOT", tmp_path), \
         patch("phases.phase_1_gates._resolve_codeql_config", return_value=mock_config):
        rc = check_phase_1a()

    out = capsys.readouterr().out
    assert rc == 0
    assert "will be skipped" in out


def test_unsupported_language_hard_policy_fails(tmp_path: Path, capsys) -> None:
    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (notes / "target-profile.md").write_text("profile", encoding="utf-8")
    (notes / "build-model.md").write_text("model", encoding="utf-8")
    (notes / "codeql-plan.yml").write_text(
        "schema_version: 1\n"
        "recommended: true\n"
        "analysis_units:\n"
        "  - id: gilroy\n"
        "    path: ./src\n"
        "    languages:\n"
        "      - id: elixir\n"
        "        packs:\n"
        "          - official\n",
        encoding="utf-8",
    )

    (tmp_path / "src").mkdir()

    mock_config = type("cfg", (), {"fail_policy": "hard", "enabled": True})()

    from phases.phase_1_gates import check_phase_1a

    with patch("phases.phase_1_gates.ROOT", tmp_path), \
         patch("phases.phase_1_gates._resolve_codeql_config", return_value=mock_config):
        rc = check_phase_1a()

    out = capsys.readouterr().out
    assert rc == 1
    assert "unsupported CodeQL language 'elixir'" in out


def test_non_recommended_unit_without_languages_is_skipped(tmp_path: Path, capsys) -> None:
    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (notes / "target-profile.md").write_text("profile", encoding="utf-8")
    (notes / "build-model.md").write_text("model", encoding="utf-8")
    (notes / "codeql-plan.yml").write_text(
        "schema_version: 1\n"
        "recommended: true\n"
        "analysis_units:\n"
        "  - id: api\n"
        "    path: ./src/api\n"
        "    languages:\n"
        "      - id: python\n"
        "        confidence: HIGH\n"
        "        build_mode: none\n"
        "        packs:\n"
        "          - official\n"
        "  - id: gilroy\n"
        "    path: ./src/gilroy\n"
        "    recommended: false\n",
        encoding="utf-8",
    )

    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "src" / "gilroy").mkdir(parents=True)

    mock_config = type("cfg", (), {"fail_policy": "hard", "enabled": True})()

    from phases.phase_1_gates import check_phase_1a

    with patch("phases.phase_1_gates.ROOT", tmp_path), \
         patch("phases.phase_1_gates._resolve_codeql_config", return_value=mock_config):
        rc = check_phase_1a()

    out = capsys.readouterr().out
    assert rc == 0
    assert "not recommended for CodeQL" in out
