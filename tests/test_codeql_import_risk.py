from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codeql.import_risk import import_risk


def _write_yaml(path: Path, data: dict) -> None:
    import yaml
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_import_risk_no_signals_file(tmp_path: Path) -> None:
    risk_path = tmp_path / "risk.yml"
    risk_path.write_text("files: []\n")
    status, warnings = import_risk(tmp_path / "missing.yml", risk_path)
    assert status is None
    assert any("not found" in w for w in warnings)


def test_import_risk_no_risk_index(tmp_path: Path) -> None:
    signals_path = tmp_path / "signals.yml"
    _write_yaml(signals_path, {"files": []})
    status, warnings = import_risk(signals_path, tmp_path / "missing.yml")
    assert status == "skipped"
    assert any("not found" in w for w in warnings)


def test_import_risk_adds_new_entry(tmp_path: Path) -> None:
    risk_path = tmp_path / "risk.yml"
    _write_yaml(
        risk_path,
        {
            "schema_version": 1,
            "files": [{"path": "src/existing.py", "score": 3, "reasons": ["old"]}],
        },
    )

    signals_path = tmp_path / "signals.yml"
    _write_yaml(
        signals_path,
        {
            "schema_version": 1,
            "files": [
                {
                    "path": "src/new.py",
                    "codeql_score_boost": 2,
                    "alerts": {"total": 2, "path_problems": 1, "high_precision": 1},
                    "rules": ["py/injection"],
                }
            ],
        },
    )

    status, warnings = import_risk(signals_path, risk_path)
    assert status is None
    assert len(warnings) == 0

    import yaml
    risk = yaml.safe_load(risk_path.read_text())
    files = risk["files"]
    assert len(files) == 2
    new_entry = [f for f in files if f["path"] == "src/new.py"][0]
    assert new_entry["score"] == 2
    assert new_entry["external_signals"]["codeql"]["alerts"] == 2
    assert new_entry["external_signals"]["codeql"]["rules"] == ["py/injection"]


def test_import_risk_updates_existing_entry(tmp_path: Path) -> None:
    risk_path = tmp_path / "risk.yml"
    _write_yaml(
        risk_path,
        {
            "schema_version": 1,
            "files": [
                {
                    "path": "src/upload.py",
                    "score": 3,
                    "reasons": ["manual review"],
                }
            ],
        },
    )

    signals_path = tmp_path / "signals.yml"
    _write_yaml(
        signals_path,
        {
            "schema_version": 1,
            "files": [
                {
                    "path": "src/upload.py",
                    "codeql_score_boost": 2,
                    "alerts": {"total": 3, "path_problems": 2, "high_precision": 1},
                    "rules": ["py/path-injection", "py/xss"],
                }
            ],
        },
    )

    status, _ = import_risk(signals_path, risk_path)
    assert status is None

    import yaml
    risk = yaml.safe_load(risk_path.read_text())
    files = risk["files"]
    assert len(files) == 1
    entry = files[0]
    assert entry["score"] == 5  # capped at 5
    assert "manual review" in entry["reasons"]
    assert entry["external_signals"]["codeql"]["alerts"] == 3
    assert entry["external_signals"]["codeql"]["rules"] == ["py/path-injection", "py/xss"]


def test_import_risk_caps_score(tmp_path: Path) -> None:
    risk_path = tmp_path / "risk.yml"
    _write_yaml(
        risk_path,
        {
            "schema_version": 1,
            "files": [{"path": "src/x.py", "score": 4, "reasons": []}],
        },
    )

    signals_path = tmp_path / "signals.yml"
    _write_yaml(
        signals_path,
        {
            "schema_version": 1,
            "files": [
                {"path": "src/x.py", "codeql_score_boost": 5, "alerts": {}}
            ],
        },
    )

    status, _ = import_risk(signals_path, risk_path)

    import yaml
    risk = yaml.safe_load(risk_path.read_text())
    assert risk["files"][0]["score"] == 5
