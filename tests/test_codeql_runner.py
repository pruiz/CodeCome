from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codeql.config import CodeQLConfig
from codeql.runner import _lookup_build, _manifest, write_manifest


def test_manifest_completed() -> None:
    config = CodeQLConfig(enabled=True, fail_policy="soft")
    result = _manifest(
        "completed",
        "2025-01-01T00:00:00Z",
        config,
        ["2.20.0"],
        [],
        languages=["python"],
    )
    assert result["schema_version"] == 1
    assert result["status"] == "completed"
    assert result["codeql_version"] == "2.20.0"
    assert result["languages"] == ["python"]
    assert result["failures"] == []
    assert result["warnings"] == []
    assert "finished_at" in result
    assert "started_at" in result


def test_manifest_failed_with_failures() -> None:
    config = CodeQLConfig(enabled=True, fail_policy="hard")
    result = _manifest(
        "failed",
        "2025-01-01T00:00:00Z",
        config,
        ["2.20.0"],
        ["warn1"],
        failures=["fail1", "fail2"],
    )
    assert result["status"] == "failed"
    assert result["fail_policy"] == "hard"
    assert result["failures"] == ["fail1", "fail2"]
    assert result["warnings"] == ["warn1"]


def test_manifest_skipped_with_failures() -> None:
    config = CodeQLConfig(enabled=False)
    result = _manifest(
        "skipped",
        "2025-01-01T00:00:00Z",
        config,
        [],
        [],
        failures=["no plan"],
    )
    assert result["status"] == "skipped"
    assert result["codeql_enabled"] is False
    assert result["failures"] == ["no plan"]


def test_manifest_defaults() -> None:
    config = CodeQLConfig(enabled=True)
    result = _manifest(
        "completed",
        "2025-01-01T00:00:00Z",
        config,
        [],
        [],
    )
    assert result["languages"] == []
    assert result["failures"] == []
    assert result["warnings"] == []


def test_write_manifest(tmp_path: Path) -> None:
    config = CodeQLConfig(enabled=True)
    manifest = _manifest(
        "completed",
        "2025-01-01T00:00:00Z",
        config,
        ["2.21.0"],
        [],
        languages=["python", "c-cpp"],
    )
    out_dir = tmp_path / "codeql"
    path = write_manifest(manifest, out_dir)
    assert path == out_dir / "run-manifest.yml"
    assert path.is_file()

    import yaml
    data = yaml.safe_load(path.read_text())
    assert data["status"] == "completed"
    assert data["languages"] == ["python", "c-cpp"]


def test_lookup_build_match() -> None:
    plan = [
        {"id": "python", "build_mode": "none", "build_command": None},
        {"id": "c-cpp", "build_mode": "manual", "build_command": "make -C src"},
    ]
    mode, cmd = _lookup_build({"id": "c-cpp"}, plan)
    assert mode == "manual"
    assert cmd == "make -C src"


def test_lookup_build_fallback() -> None:
    plan: list = []
    mode, cmd = _lookup_build({"id": "python"}, plan)
    assert mode == "none"
    assert cmd is None


def test_lookup_build_no_match_within_plan() -> None:
    plan = [{"id": "go", "build_mode": "autobuild"}]
    mode, cmd = _lookup_build({"id": "python"}, plan)
    assert mode == "none"
    assert cmd is None
