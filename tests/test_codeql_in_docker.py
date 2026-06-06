from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codeql.in_docker import check_platform, exec_codeql


def test_check_platform_mount_host_bundle_compatible() -> None:
    with patch("codeql.in_docker.host_platform", return_value="Linux x86_64"), \
         patch("codeql.in_docker.container_platform", return_value="Linux x86_64"):
        ok, msg = check_platform("app", "dc.yml", "mount-host-bundle")
        assert ok is True
        assert msg == ""


def test_check_platform_mount_host_bundle_incompatible() -> None:
    with patch("codeql.in_docker.host_platform", return_value="Darwin arm64"), \
         patch("codeql.in_docker.container_platform", return_value="Linux x86_64"):
        ok, msg = check_platform("app", "dc.yml", "mount-host-bundle")
        assert ok is False
        assert "cross platforms" in msg
        assert "mount-host-bundle" in msg


def test_check_platform_unknown_strategy_returns_ok() -> None:
    ok, msg = check_platform("app", "dc.yml", "download-in-container")
    assert ok is True


def test_exec_codeql_mocked() -> None:
    with patch("codeql.in_docker.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "CodeQL output\n"
        mock_run.return_value.stderr = ""

        ok, out, rc = exec_codeql("app", "dc.yml", "/opt/codeql/codeql", "database", "create", "--help")
        assert ok is True
        assert "CodeQL output" in out
        assert rc == 0


def test_exec_codeql_timeout() -> None:
    import subprocess

    with patch("codeql.in_docker.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=1)):
        ok, out, rc = exec_codeql("app", "dc.yml", "/opt/codeql/codeql", "version")
        assert ok is False
        assert "timed out" in out.lower()
        assert rc == -1


def test_exec_codeql_error() -> None:
    with patch("codeql.in_docker.subprocess.run", side_effect=OSError("no docker")):
        ok, out, rc = exec_codeql("app", "dc.yml", "/opt/codeql/codeql", "version")
        assert ok is False
        assert "no docker" in out
        assert rc == -1
