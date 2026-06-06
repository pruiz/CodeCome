# Copyright (C) 2025-2026 Pablo Ruiz Garcia <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL Docker execution: run CodeQL inside a sandbox container."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from codeql.platform import host_platform, container_platform, platforms_compatible


def check_platform(
    service: str,
    compose_file: str | Path,
    install_strategy: str,
) -> tuple[bool, str]:
    """Verify that the host CodeQL bundle can run inside the container.

    Returns (ok, message).  When *install_strategy* is ``mount-host-bundle``,
    the host and container platforms must be compatible (same OS/arch).
    """
    if install_strategy not in ("mount-host-bundle",):
        return True, ""

    host_plat = host_platform()
    container_plat = container_platform(service, compose_file)

    if not platforms_compatible(host_plat, container_plat):
        return False, (
            f"CodeQL bundle is for {host_plat}; sandbox service "
            f"{service!r} runs {container_plat}. "
            "install_strategy=mount-host-bundle cannot cross platforms. "
            "Use install_strategy=download-in-container or image-preinstalled "
            "(not yet supported)."
        )

    return True, ""


def exec_codeql(
    service: str,
    compose_file: str | Path,
    codeql_binary: str | Path,
    *args: str,
    timeout: int = 600,
    cwd: str | None = None,
) -> tuple[bool, str, int]:
    """Run a CodeQL command inside a Docker Compose service.

    Returns (success, stdout/stderr, returncode).
    """
    cmd = [
        "docker", "compose", "-f", str(compose_file),
        "exec", "-T",
    ]
    if cwd:
        cmd += ["-w", cwd]
    cmd += [service, str(codeql_binary), *args]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        output = result.stdout.strip() + "\n" + result.stderr.strip()
        return result.returncode == 0, output.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return False, f"CodeQL command timed out after {timeout}s", -1
    except Exception as exc:
        return False, str(exc), -1
