from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codeql import config as config_module


def test_load_codecome_yml_reads_audit_static_analysis(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "codecome.yml"
    config_path.write_text(
        "audit:\n  static_analysis:\n    codeql:\n      candidate_mode: audit\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "ROOT", tmp_path)

    data = config_module._load_codecome_yml()
    assert data == {"candidate_mode": "audit"}


def test_load_codecome_yml_ignores_top_level_static_analysis(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "codecome.yml"
    config_path.write_text(
        "static_analysis:\n  codeql:\n    candidate_mode: top-level\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_module, "ROOT", tmp_path)

    data = config_module._load_codecome_yml()
    assert data is None


def test_load_codecome_yml_returns_none_for_invalid_yaml(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "codecome.yml"
    config_path.write_text("audit:\n  static_analysis: [\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "ROOT", tmp_path)

    data = config_module._load_codecome_yml()
    assert data is None


def test_resolve_config_falls_back_on_invalid_max_candidates(monkeypatch) -> None:
    monkeypatch.delenv("CODEQL", raising=False)
    monkeypatch.delenv("CODEQL_SKIP", raising=False)
    monkeypatch.setenv("CODEQL_MAX_CANDIDATES", "not-a-number")

    config = config_module.resolve_config()
    assert config.max_candidates == config_module.DEFAULTS["max_candidates"]
