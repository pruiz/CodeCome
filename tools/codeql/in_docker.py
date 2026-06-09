# Copyright (C) 2025-2026 Pablo Ruiz Garcia <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL Docker execution: run CodeQL inside a sandbox container."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from codeql.platform import host_platform, container_platform, platforms_compatible


def check_platform(
    service: str,
    compose_file: str | Path,
    is_compiled: bool = False,
) -> tuple[bool, str]:
    """Verify that the CodeQL bundle can run inside the container.

    If host is Darwin arm64 and container is Linux aarch64, we can run CodeQL
    via Rosetta 2/QEMU, BUT CodeQL's amd64 tracer cannot LD_PRELOAD into aarch64
    compilers. Therefore, compiled languages must be skipped.
    """
    host_plat = host_platform()
    container_plat = container_platform(service, compose_file)

    if host_plat == "Darwin arm64" and container_plat == "Linux aarch64":
        if is_compiled:
            return False, (
                "CodeQL for Linux is amd64-only and cannot trace arm64 compilers via LD_PRELOAD. "
                "Options: configure sandbox platform as linux/amd64 to emulate, or skip CodeQL."
            )

    return True, container_plat


def exec_codeql(
    service: str,
    compose_file: str | Path,
    codeql_binary: str | Path,
    *args: str,
    timeout: int = 600,
    cwd: str | None = None,
    progress: Callable[[str], None] | None = None,
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

    if progress is None:
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

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except Exception as exc:
        return False, str(exc), -1

    lines: list[str] = []

    def _read_output() -> None:
        for line in process.stdout:
            stripped = line.rstrip()
            if stripped:
                lines.append(stripped)
                progress(f"CodeQL [sandbox]: {stripped}")

    reader = threading.Thread(target=_read_output, daemon=True)
    reader.start()

    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        reader.join(timeout=5)
        return False, f"CodeQL command timed out after {timeout}s", -1

    reader.join(timeout=5)
    return returncode == 0, "\n".join(lines[-40:]), returncode
