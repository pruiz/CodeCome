from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codeql.health import compute_health


def _run_dir(tmp_path: Path, **kwargs) -> Path:
    d = tmp_path / "runs" / "20250101T000000Z-abcdef01"
    d.mkdir(parents=True)
    for name in ("sarif", "normalized", "databases", "logs"):
        (d / name).mkdir(exist_ok=True)
    for sarif_name in kwargs.get("sarif_files", []):
        (d / "sarif" / sarif_name).write_text("{}", encoding="utf-8")
    for norm_name in kwargs.get("normalized_files", []):
        (d / "normalized" / norm_name).write_text("data", encoding="utf-8")
    for db_name in kwargs.get("db_dirs", []):
        (d / "databases" / db_name).mkdir(parents=True, exist_ok=True)
    return d


class TestHealthSkipsDisabled:
    def test_skipped(self, tmp_path: Path) -> None:
        d = _run_dir(tmp_path)
        manifest = {"status": "skipped", "languages": [], "failures": [], "warnings": []}
        result = compute_health(manifest=manifest, run_dir=d, output_dir=tmp_path)
        assert result["classification"] == "skipped"
        assert result["usable"] is False

    def test_disabled(self, tmp_path: Path) -> None:
        d = _run_dir(tmp_path)
        manifest = {"status": "disabled", "languages": [], "failures": [], "warnings": []}
        result = compute_health(manifest=manifest, run_dir=d, output_dir=tmp_path)
        assert result["classification"] == "disabled"


class TestHealthFailed:
    def test_failed_no_database(self, tmp_path: Path) -> None:
        d = _run_dir(tmp_path)
        manifest = {
            "status": "failed",
            "languages": ["python"],
            "failures": ["Database create failed: timeout"],
            "warnings": [],
        }
        result = compute_health(manifest=manifest, run_dir=d, output_dir=tmp_path)
        assert result["classification"] == "failed"
        assert result["usable"] is False

    def test_failed_no_sarif(self, tmp_path: Path) -> None:
        d = _run_dir(tmp_path, db_dirs=["root/python"])
        manifest = {
            "status": "completed",
            "languages": ["python"],
            "failures": [],
            "warnings": [],
        }
        result = compute_health(manifest=manifest, run_dir=d, output_dir=tmp_path)
        assert result["classification"] == "failed"


class TestHealthExtractionFailed:
    def test_compiled_with_no_extraction(self, tmp_path: Path) -> None:
        d = _run_dir(
            tmp_path,
            sarif_files=["root.c-cpp.official.sarif"],
            db_dirs=["root/c-cpp"],
            normalized_files=["alerts.yml", "file-signals.yml"],
        )
        manifest = {
            "status": "completed",
            "languages": ["c-cpp"],
            "failures": [],
            "warnings": [],
            "extractor_successes": 0,
        }
        plan = {
            "analysis_units": [
                {
                    "id": "root",
                    "path": "./src",
                    "languages": [{"id": "c-cpp"}],
                },
            ],
        }
        result = compute_health(
            manifest=manifest, run_dir=d, output_dir=tmp_path, resolved_plan=plan
        )
        assert result["classification"] == "extraction-failed"
        assert result["usable"] is False


class TestHealthUsableEmpty:
    def test_zero_alerts_but_fresh(self, tmp_path: Path) -> None:
        d = _run_dir(
            tmp_path,
            sarif_files=["root.python.official.sarif"],
            db_dirs=["root/python"],
            normalized_files=["alerts.yml", "file-signals.yml"],
        )
        manifest = {
            "status": "completed",
            "languages": ["python"],
            "failures": [],
            "warnings": [],
            "total_alerts": 0,
        }
        result = compute_health(manifest=manifest, run_dir=d, output_dir=tmp_path)
        assert result["classification"] == "completed-empty-valid"
        assert result["usable"] is True

    def test_zero_alerts_no_compiled_extractor_check(self, tmp_path: Path) -> None:
        d = _run_dir(
            tmp_path,
            sarif_files=["root.python.official.sarif"],
            db_dirs=["root/python"],
            normalized_files=["alerts.yml", "file-signals.yml"],
        )
        manifest = {
            "status": "completed",
            "languages": ["python"],
            "failures": [],
            "warnings": [],
            "total_alerts": 0,
            "extractor_successes": 0,
        }
        plan = {
            "analysis_units": [
                {"id": "root", "path": "./src", "languages": [{"id": "python"}]},
            ],
        }
        result = compute_health(
            manifest=manifest, run_dir=d, output_dir=tmp_path, resolved_plan=plan
        )
        assert result["classification"] == "completed-empty-valid"
        assert result["usable"] is True


class TestHealthCompletedWithSignals:
    def test_alerts_found(self, tmp_path: Path) -> None:
        d = _run_dir(
            tmp_path,
            sarif_files=["root.python.official.sarif"],
            db_dirs=["root/python"],
            normalized_files=["alerts.yml", "file-signals.yml"],
        )
        manifest = {
            "status": "completed",
            "languages": ["python"],
            "failures": [],
            "warnings": [],
            "total_alerts": 5,
        }
        result = compute_health(manifest=manifest, run_dir=d, output_dir=tmp_path)
        assert result["classification"] == "completed-with-signals"
        assert result["usable"] is True


class TestHealthAnalysisFailed:
    def test_no_profiles_succeeded(self, tmp_path: Path) -> None:
        d = _run_dir(
            tmp_path,
            db_dirs=["root/python"],
        )
        manifest = {
            "status": "completed",
            "languages": ["python"],
            "failures": ["Analyze failed for root/python"],
            "warnings": [],
        }
        result = compute_health(manifest=manifest, run_dir=d, output_dir=tmp_path)
        assert result["classification"] == "analysis-failed"
        assert result["usable"] is False


class TestHealthSoftFailed:
    def test_soft_failed_with_database_issues(self, tmp_path: Path) -> None:
        d = _run_dir(tmp_path)
        manifest = {
            "status": "soft-failed",
            "languages": ["python"],
            "failures": ["Database create failed: build error"],
            "warnings": [],
        }
        result = compute_health(manifest=manifest, run_dir=d, output_dir=tmp_path)
        assert result["classification"] == "soft-failed"
        assert result["usable"] is False


class TestHealthChecks:
    def test_checks_have_expected_keys(self, tmp_path: Path) -> None:
        d = _run_dir(tmp_path)
        manifest = {"status": "completed", "languages": [], "failures": [], "warnings": []}
        result = compute_health(manifest=manifest, run_dir=d, output_dir=tmp_path)
        assert isinstance(result["checks"], dict)
        assert "database_create_exit_zero" in result["checks"]
        assert "database_exists" in result["checks"]
        assert "sarif_fresh" in result["checks"]
        assert "normalized_fresh" in result["checks"]
        assert "has_compiled_languages" in result["checks"]
