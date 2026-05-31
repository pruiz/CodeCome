from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codeql.config import CodeQLConfig
from codeql.runner import (
    _create_database,
    _ensure_query_packs_available,
    _lookup_build,
    _lookup_timeout,
    _manifest,
    _run_analyze,
    run_codeql,
    write_manifest,
)


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
    assert mock_popen.call_args.kwargs["stdout"] == subprocess.DEVNULL


def test_create_database_uses_workspace_common_cache(tmp_path: Path) -> None:
    db_dir = tmp_path / "itemdb" / "codeql" / "databases" / "python"
    cache_dir = tmp_path / ".cache" / "codeql"
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.wait.return_value = 0
    mock_process.stderr = []

    with patch("codeql.runner.subprocess.Popen", return_value=mock_process) as mock_popen:
        ok, msg = _create_database(
            tmp_path / "codeql",
            "python",
            "./src",
            db_dir,
            "none",
            None,
            [],
            cache_dir,
        )

    assert ok is True
    assert msg == ""
    assert f"--common-caches={cache_dir}" in mock_popen.call_args.args[0]
    assert cache_dir.is_dir()


def test_run_analyze_uses_workspace_common_cache(tmp_path: Path) -> None:
    db_dir = tmp_path / "itemdb" / "codeql" / "databases" / "root" / "python"
    sarif_path = tmp_path / "itemdb" / "codeql" / "sarif" / "root.python.official.sarif"
    cache_dir = tmp_path / ".cache" / "codeql"
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.wait.return_value = 0
    mock_process.stderr = []

    with patch("codeql.runner.subprocess.Popen", return_value=mock_process) as mock_popen:
        ok, msg = _run_analyze(
            tmp_path / "codeql",
            db_dir,
            ["codeql/python-queries"],
            sarif_path,
            cache_dir,
        )

    assert ok is True
    assert msg == ""
    cmd = mock_popen.call_args.args[0]
    assert f"--common-caches={cache_dir}" in cmd
    assert cmd[-1] == "codeql/python-queries"
    assert cache_dir.is_dir()


def test_query_pack_resolution_uses_workspace_common_cache(tmp_path: Path) -> None:
    binary = tmp_path / "codeql"
    cache_dir = tmp_path / ".cache" / "codeql"
    config = CodeQLConfig(enabled=True, fail_policy="soft", abs_cache_dir=cache_dir)
    commands: list[list[str]] = []

    def fake_run_quiet(cmd, timeout):
        commands.append(cmd)
        return True, ""

    with patch("codeql.runner._run_quiet", side_effect=fake_run_quiet):
        ok, msg = _ensure_query_packs_available(binary, ["codeql/python-queries"], "official", config)

    assert ok is True
    assert msg == ""
    assert commands == [[
        str(binary),
        "resolve",
        "queries",
        "--format=json",
        f"--common-caches={cache_dir}",
        "--",
        "codeql/python-queries",
    ]]
    assert cache_dir.is_dir()


def test_query_pack_download_uses_workspace_common_cache(tmp_path: Path) -> None:
    binary = tmp_path / "codeql"
    cache_dir = tmp_path / ".cache" / "codeql"
    config = CodeQLConfig(enabled=True, fail_policy="soft", abs_cache_dir=cache_dir)
    commands: list[list[str]] = []

    def fake_run_quiet(cmd, timeout):
        commands.append(cmd)
        return (False, "pack missing") if len(commands) == 1 else (True, "")

    with patch("codeql.runner._run_quiet", side_effect=fake_run_quiet):
        ok, msg = _ensure_query_packs_available(binary, ["codeql/python-queries"], "official", config)

    assert ok is True
    assert msg == ""
    assert commands[1] == [
        str(binary),
        "pack",
        "download",
        f"--common-caches={cache_dir}",
        "--",
        "codeql/python-queries",
    ]
    assert commands[2] == commands[0]


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


def test_run_codeql_pack_resolver_error_soft_policy(tmp_path: Path) -> None:
    from codeql.packs import PackResolverError

    binary = tmp_path / ".tools" / "codeql" / "current" / "codeql"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")

    plan_path = tmp_path / "itemdb" / "notes" / "codeql-plan.yml"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("schema_version: 1\n", encoding="utf-8")

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
         patch("codeql.runner._get_codeql_version", return_value="2.25.5"), \
         patch("codeql.runner.load_pack_catalog", return_value={}), \
         patch("codeql.runner.load_codeql_plan", side_effect=PackResolverError("boom")):
        manifest = run_codeql(config)

    assert manifest["status"] == "soft-failed"
    assert manifest["fail_policy"] == "soft"


def test_run_codeql_skips_unsupported_languages_soft_policy(tmp_path: Path) -> None:
    binary = tmp_path / ".tools" / "codeql" / "current" / "codeql"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")

    plan_path = tmp_path / "itemdb" / "notes" / "codeql-plan.yml"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("schema_version: 1\n", encoding="utf-8")

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

    resolved = {
        "warnings": ["Skipping unsupported CodeQL language 'elixir' in analysis unit 'gilroy'"],
        "analysis_units": [],
    }

    with patch("codeql.runner.ROOT", tmp_path), \
         patch("codeql.runner._get_codeql_version", return_value="2.25.5"), \
         patch("codeql.runner.load_pack_catalog", return_value={"packs": {"python": {"official": ["codeql/python-queries"]}}}), \
         patch("codeql.runner.load_codeql_plan", return_value={"analysis_units": [{"id": "gilroy", "path": "./src", "languages": [{"id": "elixir", "packs": ["official"]}]}]}), \
         patch("codeql.runner.resolve_plan_packs", return_value=resolved):
        manifest = run_codeql(config)

    assert manifest["status"] == "skipped"
    assert "elixir" in manifest["warnings"][0]


def test_run_codeql_downloads_and_skips_unavailable_optional_profile_under_soft_policy(tmp_path: Path) -> None:
    binary = tmp_path / ".tools" / "codeql" / "current" / "codeql"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    plan_path = tmp_path / "itemdb" / "notes" / "codeql-plan.yml"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("schema_version: 1\nanalysis_units: []\n", encoding="utf-8")
    catalog_path = tmp_path / "templates" / "codeql-packs.yml"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text("schema_version: 1\npacks:\n  c-cpp:\n    official:\n      - codeql/cpp-queries\n", encoding="utf-8")

    config = CodeQLConfig(
        enabled=True,
        fail_policy="soft",
        abs_install_path=binary,
        abs_pack_catalog=catalog_path,
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
                        "profiles": ["official", "github-security-lab"],
                        "profile_packs": {
                            "official": ["codeql/cpp-queries"],
                            "github-security-lab": ["githubsecuritylab/codeql-cpp-queries"],
                        },
                    }
                ],
            }
        ]
    }

    def fake_run_quiet(cmd, timeout):
        joined = " ".join(cmd)
        if "githubsecuritylab/codeql-cpp-queries" in joined:
            return False, "pack missing"
        return True, ""

    with patch("codeql.runner.ROOT", tmp_path), \
         patch("codeql.runner._get_codeql_version", return_value="2.25.5"), \
         patch("codeql.runner.load_pack_catalog", return_value={}), \
         patch("codeql.runner.load_codeql_plan", return_value={"analysis_units": [{"id": "root", "path": "./src", "languages": [{"id": "c-cpp", "build_mode": "autobuild", "packs": ["official", "github-security-lab"]}]}]}), \
         patch("codeql.runner.resolve_plan_packs", return_value=resolved), \
         patch("codeql.runner._create_database", return_value=(True, "")), \
         patch("codeql.runner._run_analyze", return_value=(True, "")) as analyze, \
         patch("codeql.runner._run_quiet", side_effect=fake_run_quiet):
        manifest = run_codeql(config)

    assert manifest["status"] == "completed"
    assert any("githubsecuritylab/codeql-cpp-queries" in warning for warning in manifest["warnings"])
    assert analyze.call_count == 1
    assert analyze.call_args.args[2] == ["codeql/cpp-queries"]


def test_run_codeql_fails_unavailable_official_profile_under_soft_policy(tmp_path: Path) -> None:
    binary = tmp_path / ".tools" / "codeql" / "current" / "codeql"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    plan_path = tmp_path / "itemdb" / "notes" / "codeql-plan.yml"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("schema_version: 1\nanalysis_units: []\n", encoding="utf-8")
    catalog_path = tmp_path / "templates" / "codeql-packs.yml"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text("schema_version: 1\npacks:\n  c-cpp:\n    official:\n      - codeql/cpp-queries\n", encoding="utf-8")

    config = CodeQLConfig(
        enabled=True,
        fail_policy="soft",
        abs_install_path=binary,
        abs_pack_catalog=catalog_path,
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
         patch("codeql.runner.load_codeql_plan", return_value={"analysis_units": [{"id": "root", "path": "./src", "languages": [{"id": "c-cpp", "build_mode": "autobuild", "packs": ["official"]}]}]}), \
         patch("codeql.runner.resolve_plan_packs", return_value=resolved), \
         patch("codeql.runner._create_database", return_value=(True, "")), \
         patch("codeql.runner._run_analyze") as analyze, \
         patch("codeql.runner._run_quiet", return_value=(False, "pack missing")):
        manifest = run_codeql(config)

    assert manifest["status"] == "soft-failed"
    assert "required official profile" in manifest["failures"][0]
    analyze.assert_not_called()


def test_run_codeql_fails_unavailable_optional_profile_under_hard_policy(tmp_path: Path) -> None:
    binary = tmp_path / ".tools" / "codeql" / "current" / "codeql"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    plan_path = tmp_path / "itemdb" / "notes" / "codeql-plan.yml"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("schema_version: 1\nanalysis_units: []\n", encoding="utf-8")
    catalog_path = tmp_path / "templates" / "codeql-packs.yml"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text("schema_version: 1\npacks:\n  c-cpp:\n    github-security-lab:\n      - githubsecuritylab/codeql-cpp-queries\n", encoding="utf-8")

    config = CodeQLConfig(
        enabled=True,
        fail_policy="hard",
        abs_install_path=binary,
        abs_pack_catalog=catalog_path,
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
                        "profiles": ["github-security-lab"],
                        "profile_packs": {"github-security-lab": ["githubsecuritylab/codeql-cpp-queries"]},
                    }
                ],
            }
        ]
    }

    with patch("codeql.runner.ROOT", tmp_path), \
         patch("codeql.runner._get_codeql_version", return_value="2.25.5"), \
         patch("codeql.runner.load_pack_catalog", return_value={}), \
         patch("codeql.runner.load_codeql_plan", return_value={"analysis_units": [{"id": "root", "path": "./src", "languages": [{"id": "c-cpp", "build_mode": "autobuild", "packs": ["github-security-lab"]}]}]}), \
         patch("codeql.runner.resolve_plan_packs", return_value=resolved), \
         patch("codeql.runner._create_database", return_value=(True, "")), \
         patch("codeql.runner._run_analyze") as analyze, \
         patch("codeql.runner._run_quiet", return_value=(False, "pack missing")):
        manifest = run_codeql(config)

    assert manifest["status"] == "failed"
    assert "optional profile 'github-security-lab'" in manifest["failures"][0]
    analyze.assert_not_called()


def test_run_codeql_soft_fails_when_all_profiles_are_skipped(tmp_path: Path) -> None:
    binary = tmp_path / ".tools" / "codeql" / "current" / "codeql"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    plan_path = tmp_path / "itemdb" / "notes" / "codeql-plan.yml"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("schema_version: 1\nanalysis_units: []\n", encoding="utf-8")
    catalog_path = tmp_path / "templates" / "codeql-packs.yml"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text("schema_version: 1\npacks:\n  c-cpp:\n    github-security-lab:\n      - githubsecuritylab/codeql-cpp-queries\n", encoding="utf-8")

    config = CodeQLConfig(
        enabled=True,
        fail_policy="soft",
        abs_install_path=binary,
        abs_pack_catalog=catalog_path,
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
                        "profiles": ["github-security-lab"],
                        "profile_packs": {"github-security-lab": ["githubsecuritylab/codeql-cpp-queries"]},
                    }
                ],
            }
        ]
    }

    with patch("codeql.runner.ROOT", tmp_path), \
         patch("codeql.runner._get_codeql_version", return_value="2.25.5"), \
         patch("codeql.runner.load_pack_catalog", return_value={}), \
         patch("codeql.runner.load_codeql_plan", return_value={"analysis_units": [{"id": "root", "path": "./src", "languages": [{"id": "c-cpp", "build_mode": "autobuild", "packs": ["github-security-lab"]}]}]}), \
         patch("codeql.runner.resolve_plan_packs", return_value=resolved), \
         patch("codeql.runner._create_database", return_value=(True, "")), \
         patch("codeql.runner._run_analyze") as analyze, \
         patch("codeql.runner._run_quiet", return_value=(False, "pack missing")):
        manifest = run_codeql(config)

    assert manifest["status"] == "soft-failed"
    assert "No CodeQL query profiles ran successfully" in manifest["failures"][0]
    analyze.assert_not_called()
