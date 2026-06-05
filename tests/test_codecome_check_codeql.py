from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import rendering.dispatch as rendering_dispatch
from codeql.config import CodeQLConfig


def _ensure_codecome_package():
    """Ensure 'codecome' is imported as the package (dir), not the module (.py).

    Some tests (e.g. test_codecome.py) import ``codecome.py`` as a module,
    which blocks accessing ``codecome.phase_1`` as a submodule. Remove the
    module from sys.modules so the package can be imported instead.
    """
    if "codecome" in sys.modules and not getattr(
        sys.modules["codecome"], "__path__", None
    ):
        del sys.modules["codecome"]


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


def test_check_codeql_artifacts_failed_soft_policy_returns_0(tmp_path: Path, capsys) -> None:
    """_check_codeql_artifacts with status=failed and soft fail_policy should return 0."""
    config = _config(tmp_path, enabled=True, fail_policy="soft")
    manifest_dir = config.abs_output_dir
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "run-manifest.yml").write_text(
        yaml.safe_dump(
            {
                "status": "failed",
                "codeql_enabled": True,
                "fail_policy": "soft",
                "failures": ["boom"],
            }
        ),
        encoding="utf-8",
    )

    _ensure_codecome_package()
    from codecome.phase_1 import _check_codeql_artifacts as _check
    import codecome.phase_1 as p1

    saved = rendering_dispatch.HAVE_RICH
    rendering_dispatch.HAVE_RICH = False
    rendering_dispatch.reset_rendering_context_cache()
    try:
        with patch("codeql.config.resolve_config", return_value=config):
            rc = _check(None)
    finally:
        rendering_dispatch.HAVE_RICH = saved
    rendering_dispatch.reset_rendering_context_cache()

    out = capsys.readouterr().out
    assert rc == 0
    assert "fail_policy is soft" in out


def test_check_codeql_artifacts_failed_hard_policy_returns_1(tmp_path: Path, capsys) -> None:
    """_check_codeql_artifacts with status=failed and hard fail_policy should return 1."""
    config = _config(tmp_path, enabled=True, fail_policy="hard")
    manifest_dir = config.abs_output_dir
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "run-manifest.yml").write_text(
        yaml.safe_dump(
            {
                "status": "failed",
                "codeql_enabled": True,
                "fail_policy": "hard",
                "failures": ["boom"],
            }
        ),
        encoding="utf-8",
    )

    _ensure_codecome_package()
    from codecome.phase_1 import _check_codeql_artifacts as _check
    import codecome.phase_1 as p1

    saved = rendering_dispatch.HAVE_RICH
    rendering_dispatch.HAVE_RICH = False
    rendering_dispatch.reset_rendering_context_cache()
    try:
        with patch("codeql.config.resolve_config", return_value=config):
            rc = _check(None)
    finally:
        rendering_dispatch.HAVE_RICH = saved
    rendering_dispatch.reset_rendering_context_cache()

    assert rc == 1


def test_codeql_repair_needed_for_autobuild_database_failure(tmp_path: Path) -> None:
    _ensure_codecome_package()
    from codecome.phase_1 import _codeql_repair_needed

    output_dir = tmp_path / "itemdb" / "codeql"
    output_dir.mkdir(parents=True)
    (output_dir / "run-manifest.yml").write_text(
        yaml.safe_dump(
            {
                "status": "soft-failed",
                "failures": ["Database create failed for c-cpp:\nNo supported build system detected."],
            }
        ),
        encoding="utf-8",
    )
    plan_path = tmp_path / "itemdb" / "notes" / "codeql-plan.yml"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "analysis_units": [
                    {
                        "id": "native",
                        "path": "./src/native",
                        "languages": [
                            {"id": "c-cpp", "build_mode": "autobuild", "packs": ["official"]}
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert _codeql_repair_needed(output_dir, plan_path) is True


def test_codeql_repair_needed_after_manual_database_failure(tmp_path: Path) -> None:
    _ensure_codecome_package()
    from codecome.phase_1 import _codeql_repair_needed

    output_dir = tmp_path / "itemdb" / "codeql"
    output_dir.mkdir(parents=True)
    (output_dir / "run-manifest.yml").write_text(
        yaml.safe_dump(
            {
                "status": "soft-failed",
                "failures": ["Database create failed for c-cpp:\nmanual build failed."],
            }
        ),
        encoding="utf-8",
    )
    plan_path = tmp_path / "itemdb" / "notes" / "codeql-plan.yml"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "analysis_units": [
                    {
                        "id": "native",
                        "path": "./src/native",
                        "languages": [
                            {"id": "c-cpp", "build_mode": "manual", "build_command": "make", "packs": ["official"]}
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert _codeql_repair_needed(output_dir, plan_path) is True


def test_phase_1_pipeline_structure() -> None:
    _ensure_codecome_package()
    import codecome.phase_1 as p1

    saved = rendering_dispatch.HAVE_RICH
    rendering_dispatch.HAVE_RICH = False
    rendering_dispatch.reset_rendering_context_cache()
    try:
        with patch.object(p1, "count_findings_snapshot", return_value={}), \
             patch.object(p1, "_run_subphase", return_value=0) as subphase, \
             patch.object(p1, "check_phase_1a", return_value=0), \
             patch.object(p1, "check_phase_1b", return_value=0), \
             patch.object(p1, "check_phase_1c", return_value=0), \
             patch.object(p1, "_run_codeql", return_value=None) as run_codeql, \
             patch.object(p1, "_run_codeql_repair_if_needed", return_value=0), \
             patch.object(p1, "_check_codeql_artifacts", return_value=0):
            rc = p1.run_phase_1(object(), None, None, object(), "http://127.0.0.1")
    finally:
        rendering_dispatch.HAVE_RICH = saved
    rendering_dispatch.reset_rendering_context_cache()

    assert rc == 0
    assert run_codeql.call_count == 1
    assert subphase.call_count == 3
