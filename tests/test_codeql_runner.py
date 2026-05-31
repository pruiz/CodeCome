from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codeql.config import CodeQLConfig
from codeql.runner import _create_database, _lookup_build, _lookup_timeout, _manifest, run_codeql, write_manifest


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
    languages = [
        {"id": "python", "build_mode": "none", "build_command": None},
        {"id": "c-cpp", "build_mode": "manual", "build_command": "make -C src"},
    ]
    mode, cmd = _lookup_build("c-cpp", languages)
    assert mode == "manual"
    assert cmd == "make -C src"


def test_lookup_build_fallback() -> None:
    languages: list = []
    mode, cmd = _lookup_build("python", languages)
    assert mode == "none"
    assert cmd is None


def test_lookup_build_no_match_within_plan() -> None:
    languages = [{"id": "go", "build_mode": "autobuild"}]
    mode, cmd = _lookup_build("python", languages)
    assert mode == "none"
    assert cmd is None


def test_create_database_creates_parent_dir(tmp_path: Path) -> None:
    db_dir = tmp_path / "itemdb" / "codeql" / "databases" / "c-cpp"
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.wait.return_value = 0
    mock_process.stderr = []

    with patch("codeql.runner.subprocess.Popen", return_value=mock_process) as mock_popen:
        ok, msg = _create_database(
            tmp_path / "codeql",
            "c-cpp",
            "./src",
            db_dir,
            "none",
            None,
            [],
        )

    assert ok is True
    assert msg == ""
    assert db_dir.parent.is_dir()
    assert mock_popen.call_args.args[0][3] == str(db_dir)
    assert "--build-mode=none" in mock_popen.call_args.args[0]


def test_create_database_manual_build_mode_and_command(tmp_path: Path) -> None:
    db_dir = tmp_path / "itemdb" / "codeql" / "databases" / "root" / "c-cpp"
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.wait.return_value = 0
    mock_process.stderr = []

    with patch("codeql.runner.subprocess.Popen", return_value=mock_process) as mock_popen:
        ok, msg = _create_database(
            tmp_path / "codeql",
            "c-cpp",
            "./src/native",
            db_dir,
            "manual",
            "make -C src/native",
            [],
        )

    assert ok is True
    assert msg == ""
    cmd = mock_popen.call_args.args[0]
    assert "--build-mode=manual" in cmd
    assert "-c" in cmd
    assert "make -C src/native" in cmd


def test_run_codeql_database_failure_honors_soft_policy(tmp_path: Path) -> None:
    binary = tmp_path / ".tools" / "codeql" / "current" / "codeql"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")

    plan_path = tmp_path / "itemdb" / "notes" / "codeql-plan.yml"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("schema_version: 1\n", encoding="utf-8")

    catalog = tmp_path / "templates" / "codeql-packs.yml"
    catalog.parent.mkdir(parents=True)
    catalog.write_text("schema_version: 1\n", encoding="utf-8")

    config = CodeQLConfig(
        enabled=True,
        fail_policy="soft",
        abs_install_path=binary,
        abs_pack_catalog=catalog,
        abs_output_dir=tmp_path / "itemdb" / "codeql",
        abs_database_dir=tmp_path / "itemdb" / "codeql" / "databases",
    )

    resolved = {
        "analysis_units": [
            {
                "id": "root",
                "path": "./src",
                "languages": [
                    {
                        "id": "c-cpp",
                        "profiles": ["official"],
                        "profile_packs": {"official": ["codeql/cpp-queries"]},
                    }
                ],
            }
        ]
    }

    with patch("codeql.runner.ROOT", tmp_path), \
         patch("codeql.runner._get_codeql_version", return_value="2.25.5"), \
         patch("codeql.runner.load_pack_catalog", return_value={}), \
         patch("codeql.runner.load_codeql_plan", return_value={"analysis_units": [{"id": "root", "path": "./src", "languages": [{"id": "c-cpp", "build_mode": "autobuild", "build_command": None}]}]}), \
         patch("codeql.runner.resolve_plan_packs", return_value=resolved), \
         patch("codeql.runner._create_database", return_value=(False, "db create failed")):
        manifest = run_codeql(config)

    assert manifest["status"] == "soft-failed"
    assert manifest["fail_policy"] == "soft"
    assert manifest["failures"] == ["db create failed"]
    assert manifest["analysis_units"] == ["root"]
    assert manifest["languages"] == ["root:c-cpp"]


def test_lookup_timeout_plan_takes_priority() -> None:
    languages = [
        {"id": "c-cpp", "db_create_timeout": 1800, "analyze_timeout": 900},
    ]
    assert _lookup_timeout("db_create_timeout", "c-cpp", languages, 600) == 1800
    assert _lookup_timeout("analyze_timeout", "c-cpp", languages, 600) == 900


def test_lookup_timeout_falls_back_to_default() -> None:
    languages = [{"id": "c-cpp"}]
    assert _lookup_timeout("db_create_timeout", "c-cpp", languages, 600) == 600
    assert _lookup_timeout("analyze_timeout", "c-cpp", [], 600) == 600


def test_create_database_streams_stderr_to_progress(tmp_path: Path) -> None:
    db_dir = tmp_path / "itemdb" / "codeql" / "databases" / "n" / "c-cpp"
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.wait.return_value = 0
    mock_process.stderr = ["extracting file\n", "compiling done\n"]

    messages: list[str] = []

    with patch("codeql.runner.subprocess.Popen", return_value=mock_process):
        ok, msg = _create_database(
            tmp_path / "codeql", "c-cpp", "./src", db_dir,
            "none", None, [], progress=messages.append,
        )

    assert ok is True
    assert "CodeQL: extracting file" in messages
    assert "CodeQL: compiling done" in messages


def test_run_codeql_empty_languages_returns_skipped(tmp_path: Path) -> None:
    binary = tmp_path / ".tools" / "codeql" / "current" / "codeql"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")

    plan_path = tmp_path / "itemdb" / "notes" / "codeql-plan.yml"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("schema_version: 1\nanalysis_units: []\n", encoding="utf-8")

    catalog = tmp_path / "templates" / "codeql-packs.yml"
    catalog.parent.mkdir(parents=True)
    catalog.write_text("schema_version: 1\npacks:\n  python:\n    official:\n      - codeql/python-queries\n", encoding="utf-8")

    config = CodeQLConfig(
        enabled=True,
        fail_policy="soft",
        abs_install_path=binary,
        abs_pack_catalog=catalog,
        abs_output_dir=tmp_path / "itemdb" / "codeql",
        abs_database_dir=tmp_path / "itemdb" / "codeql" / "databases",
    )

    with patch("codeql.runner.ROOT", tmp_path), \
         patch("codeql.runner._get_codeql_version", return_value="2.25.5"):
        manifest = run_codeql(config)

    assert manifest["status"] == "skipped"
    assert manifest["languages"] == []
    assert any("No languages resolved" in f for f in manifest["failures"])
