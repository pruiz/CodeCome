from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import yaml

from codeql.config import CodeQLConfig
from codeql.pipeline import record_skipped_run


def _make_config(tmp_path: Path) -> CodeQLConfig:
    """Create a minimal CodeQLConfig pointing at tmp_path."""
    output_dir = tmp_path / "itemdb" / "codeql"
    output_dir.mkdir(parents=True, exist_ok=True)
    return CodeQLConfig(
        enabled=True,
        phase_1_enabled=True,
        install_path=".tools/codeql/current/codeql",
        pack_catalog="codeql-pack-catalog.yml",
        output_dir="itemdb/codeql",
        database_dir="itemdb/codeql/databases",
        fail_policy="soft",
        abs_output_dir=output_dir,
        abs_install_path=tmp_path / ".tools" / "codeql" / "current" / "codeql",
        abs_pack_catalog=tmp_path / "codeql-pack-catalog.yml",
        abs_database_dir=tmp_path / "itemdb" / "codeql" / "databases",
        abs_cache_dir=tmp_path / ".cache" / "codeql",
    )


def test_pipeline_skipped_no_plan(tmp_path: Path) -> None:
    """When run_codeql returns skipped, pipeline returns manifest without calling normalize."""
    config = _make_config(tmp_path)

    skipped_manifest = {
        "schema_version": 1,
        "phase": "phase-1",
        "status": "skipped",
        "codeql_enabled": True,
        "codeql_version": "2.18.0",
        "started_at": "2025-01-01T00:00:00Z",
        "finished_at": "2025-01-01T00:00:01Z",
        "plan_file": "itemdb/notes/codeql-plan.yml",
        "pack_catalog": "codeql-pack-catalog.yml",
        "fail_policy": "soft",
        "languages": [],
        "warnings": [],
        "failures": ["codeql-plan.yml not found"],
    }

    with patch("codeql.runner.run_codeql", return_value=skipped_manifest) as mock_run, \
         patch("codeql.normalize.normalize_all") as mock_normalize, \
         patch("codeql.pipeline.ROOT", tmp_path):
        from codeql.pipeline import run_full_pipeline

        result = run_full_pipeline(config)

    assert result["status"] == "skipped"
    mock_run.assert_called_once_with(config, progress=None)
    mock_normalize.assert_not_called()


def test_pipeline_emits_progress(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    messages: list[str] = []

    manifest = {
        "schema_version": 1,
        "phase": "phase-1",
        "status": "skipped",
        "codeql_enabled": True,
        "codeql_version": "2.18.0",
        "started_at": "2025-01-01T00:00:00Z",
        "finished_at": "2025-01-01T00:00:01Z",
        "plan_file": "itemdb/notes/codeql-plan.yml",
        "pack_catalog": "codeql-pack-catalog.yml",
        "fail_policy": "soft",
        "analysis_units": [],
        "languages": [],
        "warnings": [],
        "failures": ["codeql-plan.yml not found"],
    }

    with patch("codeql.runner.run_codeql", return_value=manifest) as mock_run, \
         patch("codeql.pipeline.ROOT", tmp_path):
        from codeql.pipeline import run_full_pipeline

        result = run_full_pipeline(config, progress=messages.append)

    assert result["status"] == "skipped"
    mock_run.assert_called_once()
    assert mock_run.call_args.args == (config,)
    assert mock_run.call_args.kwargs["progress"] is not None
    assert "CodeQL: manifest written" in messages
    assert "CodeQL: summary written" in messages


def test_pipeline_completed_writes_manifest(tmp_path: Path) -> None:
    """When run_codeql returns completed, manifest file is written."""
    config = _make_config(tmp_path)

    completed_manifest = {
        "schema_version": 1,
        "phase": "phase-1",
        "status": "completed",
        "codeql_enabled": True,
        "codeql_version": "2.18.0",
        "started_at": "2025-01-01T00:00:00Z",
        "finished_at": "2025-01-01T00:01:00Z",
        "plan_file": "itemdb/notes/codeql-plan.yml",
        "pack_catalog": "codeql-pack-catalog.yml",
        "fail_policy": "soft",
        "languages": ["python"],
        "warnings": [],
        "failures": [],
    }

    with patch("codeql.runner.run_codeql", return_value=completed_manifest), \
         patch("codeql.normalize.normalize_all") as mock_normalize, \
         patch("codeql.pipeline.ROOT", tmp_path):
        from codeql.pipeline import run_full_pipeline

        result = run_full_pipeline(config)

    assert result["status"] == "completed"
    manifest_path = config.abs_output_dir / "run-manifest.yml"
    assert manifest_path.is_file()
    data = yaml.safe_load(manifest_path.read_text())
    assert data["status"] == "completed"


def test_pipeline_soft_failed_continues(tmp_path: Path) -> None:
    """When run_codeql returns soft-failed, pipeline returns without raising."""
    config = _make_config(tmp_path)

    soft_failed_manifest = {
        "schema_version": 1,
        "phase": "phase-1",
        "status": "soft-failed",
        "codeql_enabled": True,
        "codeql_version": "2.18.0",
        "started_at": "2025-01-01T00:00:00Z",
        "finished_at": "2025-01-01T00:00:30Z",
        "plan_file": "itemdb/notes/codeql-plan.yml",
        "pack_catalog": "codeql-pack-catalog.yml",
        "fail_policy": "soft",
        "languages": ["python"],
        "warnings": ["analyze timed out"],
        "failures": [],
    }

    with patch("codeql.runner.run_codeql", return_value=soft_failed_manifest), \
         patch("codeql.pipeline.ROOT", tmp_path):
        from codeql.pipeline import run_full_pipeline

        result = run_full_pipeline(config)

    assert result["status"] == "soft-failed"
    # Should not raise


def test_pipeline_normalize_failure_marks_failed_for_hard_policy(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.fail_policy = "hard"
    (config.abs_output_dir / "selected-query-packs.yml").write_text(
        "schema_version: 1\nanalysis_units: []\n",
        encoding="utf-8",
    )
    sarif_dir = config.abs_output_dir / "sarif"
    sarif_dir.mkdir(parents=True)
    (sarif_dir / "root.python.official.sarif").write_text("{}", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "phase": "phase-1",
        "status": "completed",
        "codeql_enabled": True,
        "codeql_version": "2.18.0",
        "started_at": "2025-01-01T00:00:00Z",
        "finished_at": "2025-01-01T00:01:00Z",
        "plan_file": "itemdb/notes/codeql-plan.yml",
        "pack_catalog": "codeql-pack-catalog.yml",
        "fail_policy": "hard",
        "languages": ["root:python"],
        "warnings": [],
        "failures": [],
    }

    with patch("codeql.runner.run_codeql", return_value=manifest), \
         patch("codeql.normalize.normalize_all", side_effect=RuntimeError("bad sarif")), \
         patch("codeql.pipeline.ROOT", tmp_path):
        from codeql.pipeline import run_full_pipeline

        result = run_full_pipeline(config)

    assert result["status"] == "failed"
    assert "SARIF normalization failed: bad sarif" in result["warnings"]
    data = yaml.safe_load((config.abs_output_dir / "run-manifest.yml").read_text())
    assert data["status"] == "failed"


def test_pipeline_normalize_failure_marks_soft_failed_for_soft_policy(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    (config.abs_output_dir / "selected-query-packs.yml").write_text(
        "schema_version: 1\nanalysis_units: []\n",
        encoding="utf-8",
    )
    sarif_dir = config.abs_output_dir / "sarif"
    sarif_dir.mkdir(parents=True)
    (sarif_dir / "root.python.official.sarif").write_text("{}", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "phase": "phase-1",
        "status": "completed",
        "codeql_enabled": True,
        "codeql_version": "2.18.0",
        "started_at": "2025-01-01T00:00:00Z",
        "finished_at": "2025-01-01T00:01:00Z",
        "plan_file": "itemdb/notes/codeql-plan.yml",
        "pack_catalog": "codeql-pack-catalog.yml",
        "fail_policy": "soft",
        "languages": ["root:python"],
        "warnings": [],
        "failures": [],
    }

    with patch("codeql.runner.run_codeql", return_value=manifest), \
         patch("codeql.normalize.normalize_all", side_effect=RuntimeError("bad sarif")), \
         patch("codeql.pipeline.ROOT", tmp_path):
        from codeql.pipeline import run_full_pipeline

        result = run_full_pipeline(config)

    assert result["status"] == "soft-failed"
    assert "SARIF normalization failed: bad sarif" in result["warnings"]


def test_record_skipped_run_writes_manifest_and_summary(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.enabled = False

    manifest = record_skipped_run(config, "CodeQL disabled for Phase 1")

    assert manifest["status"] == "skipped"
    assert manifest["codeql_enabled"] is False
    assert manifest["skip_reason"] == "CodeQL disabled for Phase 1"
    assert (config.abs_output_dir / "run-manifest.yml").is_file()
    assert (config.abs_output_dir / "codeql-summary.md").is_file()
