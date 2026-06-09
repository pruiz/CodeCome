from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codeql.platform import host_platform, container_platform, platforms_compatible


def test_host_platform_returns_string() -> None:
    plat = host_platform()
    assert isinstance(plat, str)
    assert len(plat) > 0


def test_host_platform_known_os() -> None:
    plat = host_platform()
    assert any(kw in plat.lower() for kw in ("linux", "darwin", "windows"))


def test_container_platform_mocked() -> None:
    with patch("codeql.platform.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Linux x86_64\n"
        mock_run.return_value.stderr = ""

        plat = container_platform("app", "docker-compose.yml")
        assert plat == "Linux x86_64"
        mock_run.assert_called_once()


def test_container_platform_returns_unknown_on_error() -> None:
    with patch("codeql.platform.subprocess.run", side_effect=OSError("no docker")):
        plat = container_platform("app", "docker-compose.yml")
        assert plat == "unknown"


def test_platforms_compatible_identical() -> None:
    assert platforms_compatible("Darwin arm64", "Darwin arm64") is True


def test_platforms_compatible_different() -> None:
    assert platforms_compatible("Darwin arm64", "Linux x86_64") is False


def test_platforms_compatible_unknown_is_true() -> None:
    assert platforms_compatible("unknown", "Linux x86_64") is True
    assert platforms_compatible("Darwin arm64", "unknown") is True
