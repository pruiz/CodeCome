# Copyright (C) 2025-2026 Pablo Ruiz Garcia <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL platform detection: host and container OS/arch."""

from __future__ import annotations

import subprocess
from pathlib import Path


def host_platform() -> str:
    """Return the host platform string, e.g. ``Darwin arm64`` or ``Linux x86_64``."""
    try:
        result = subprocess.run(
            ["uname", "-sm"], capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def container_platform(
    service: str, compose_file: str | Path, *, timeout: int = 30
) -> str:
    """Return the platform string from inside a Docker Compose service.

    Runs ``uname -sm`` via ``docker compose exec``.
    """
    try:
        result = subprocess.run(
            [
                "docker", "compose", "-f", str(compose_file),
                "exec", "-T", service,
                "uname", "-sm",
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception:
        return "unknown"


def platforms_compatible(host_plat: str, container_plat: str) -> bool:
    """Return whether host and container platforms are compatible for CodeQL."""
    if host_plat == "unknown" or container_plat == "unknown":
        return True  # assume compatible when unmeasurable
    return host_plat == container_plat
