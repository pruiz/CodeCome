from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import yaml

from codeql.artifacts import check_artifacts


def _write_manifest(output_dir: Path, manifest: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run-manifest.yml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )


def test_missing_manifest(tmp_path: Path) -> None:
    status, warnings = check_artifacts(tmp_path / "nonexistent")
    assert status == "missing"
    assert len(warnings) == 1
    assert "manifest" in warnings[0].lower()


def test_completed_all_present(tmp_path: Path) -> None:
    out = tmp_path / "codeql"
    _write_manifest(out, {"status": "completed", "failures": []})
    normalized = out / "normalized"
    normalized.mkdir()
    (normalized / "alerts.yml").write_text("alerts: []\n")
    (normalized / "file-signals.yml").write_text("files: []\n")

    status, warnings = check_artifacts(out)
    assert status == "completed"
    assert warnings == []


def test_completed_missing_normalized(tmp_path: Path) -> None:
    out = tmp_path / "codeql"
    _write_manifest(out, {"status": "completed", "languages": ["python"], "failures": []})

    status, warnings = check_artifacts(out)
    assert status == "completed"
    assert len(warnings) == 2
    assert any("alerts.yml" in w for w in warnings)
    assert any("file-signals.yml" in w for w in warnings)


def test_skipped(tmp_path: Path) -> None:
    out = tmp_path / "codeql"
    _write_manifest(out, {"status": "skipped", "failures": []})

    status, warnings = check_artifacts(out)
    assert status == "skipped"
    assert warnings == []


def test_soft_failed_with_failures(tmp_path: Path) -> None:
    out = tmp_path / "codeql"
    _write_manifest(out, {"status": "soft-failed", "failures": ["db create timed out"]})

    status, warnings = check_artifacts(out)
    assert status == "soft-failed"
    assert "db create timed out" in warnings


def test_failed(tmp_path: Path) -> None:
    out = tmp_path / "codeql"
    _write_manifest(out, {"status": "failed", "failures": ["binary not found"]})

    status, warnings = check_artifacts(out)
    assert status == "failed"
    assert "binary not found" in warnings


def test_invalid_status(tmp_path: Path) -> None:
    out = tmp_path / "codeql"
    _write_manifest(out, {"status": "bogus", "failures": []})

    status, warnings = check_artifacts(out)
    assert status == "unknown"
    assert any("bogus" in w for w in warnings)


def test_completed_empty_languages_skips_normalized_check(tmp_path: Path) -> None:
    out = tmp_path / "codeql"
    _write_manifest(out, {"status": "completed", "languages": [], "failures": []})

    status, warnings = check_artifacts(out)
    assert status == "completed"
    assert warnings == []
