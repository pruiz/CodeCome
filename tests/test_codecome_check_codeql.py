from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codeql.config import CodeQLConfig


def _load_codecome_cli():
    spec = importlib.util.spec_from_file_location("codecome_cli_script", ROOT / "tools" / "codecome.py")
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _config(tmp_path: Path, *, enabled: bool = True, fail_policy: str = "soft") -> CodeQLConfig:
    return CodeQLConfig(
        enabled=enabled,
        fail_policy=fail_policy,
        abs_install_path=tmp_path / ".tools" / "codeql" / "current" / "codeql",
        abs_pack_catalog=tmp_path / "templates" / "codeql-packs.yml",
        abs_output_dir=tmp_path / "itemdb" / "codeql",
        abs_database_dir=tmp_path / "itemdb" / "codeql" / "databases",
        abs_cache_dir=tmp_path / ".cache" / "codeql",
    )


def test_codeql_check_accepts_recorded_disabled_run(tmp_path: Path, capsys) -> None:
    module = _load_codecome_cli()
    config = _config(tmp_path, enabled=True)
    manifest_dir = config.abs_output_dir
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "run-manifest.yml").write_text(
        yaml.safe_dump(
            {
                "status": "skipped",
                "codeql_enabled": False,
                "skip_reason": "CodeQL disabled for Phase 1",
                "fail_policy": "soft",
                "failures": ["CodeQL disabled for Phase 1"],
            }
        ),
        encoding="utf-8",
    )

    with patch.object(module, "ROOT", tmp_path), patch("codeql.config.resolve_config", return_value=config):
        rc = module.check_codeql_status()

    out = capsys.readouterr().out
    assert rc == 0
    assert "last phase-1 CodeQL state: skipped" in out


def test_codeql_check_fails_failed_artifacts(tmp_path: Path, capsys) -> None:
    module = _load_codecome_cli()
    config = _config(tmp_path, enabled=True)
    config.abs_install_path.parent.mkdir(parents=True)
    config.abs_install_path.write_text("", encoding="utf-8")
    config.abs_pack_catalog.parent.mkdir(parents=True)
    config.abs_pack_catalog.write_text("schema_version: 1\npacks:\n  python:\n    official:\n      - codeql/python-queries\n", encoding="utf-8")
    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (notes / "codeql-plan.yml").write_text(
        "schema_version: 1\nanalysis_units:\n  - id: root\n    path: ./src\n    languages:\n      - id: python\n        packs:\n          - official\n",
        encoding="utf-8",
    )
    manifest_dir = config.abs_output_dir
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "run-manifest.yml").write_text(
        yaml.safe_dump({"status": "failed", "codeql_enabled": True, "fail_policy": "hard", "failures": ["boom"]}),
        encoding="utf-8",
    )

    with patch.object(module, "ROOT", tmp_path), patch("codeql.config.resolve_config", return_value=config):
        rc = module.check_codeql_status()

    out = capsys.readouterr().out
    assert rc == 1
    assert "artifacts: failed" in out
    assert "boom" in out
