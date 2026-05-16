#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Manage opencode serve lifecycle (start, stop, health check).

Usage as a module:
    from opencode.serve import ServerRunner
    runner = ServerRunner()
    info = runner.start(port=0, hostname="127.0.0.1", log_level="WARN")
    ...
    runner.stop()

Convenience CLI:
    python -m opencode.serve start --port 8080 --log-level DEBUG
    python -m opencode.serve stop --pid 12345
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]

# How long to wait for the "listening on" line from opencode serve stdout.
_STARTUP_TIMEOUT_S = 20.0
# How long to poll /global/health before giving up.
_HEALTH_TIMEOUT_S = 10.0
# Delay between health poll attempts.
_HEALTH_INTERVAL_S = 0.3
# Graceful shutdown wait before SIGKILL.
_GRACEFUL_SHUTDOWN_S = 5.0

_LOG_LISTENING_RE = re.compile(
    r"opencode server listening on (http://[^\s]+)"
)


@dataclasses.dataclass(frozen=True)
class ServerInfo:
    """ immutable snapshot of a running opencode serve instance. """
    proc: subprocess.Popen[str]
    pid: int
    base_url: str
    port: int


class ServerRunnerError(Exception):
    """ Raised when the server cannot be started or reached. """
    pass

def _parse_port_from_url(url: str) -> int:
    """ Extract the numeric port from a URL like http://127.0.0.1:49152 """
    # urlsplit is overkill; simple regex works fine.
    m = re.search(r":(\d+)$", url)
    if not m:
        raise ValueError(f"Cannot parse port from URL: {url}")
    return int(m.group(1))


def _try_fetch_json(url: str, timeout: float) -> dict | None:
    """ Best-effort GET returning parsed JSON, or None on any failure. """
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None

def _post_json(base_url: str, path: str, payload: dict) -> dict:
    """ POST JSON and return parsed JSON response. """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        body = resp.read().decode("utf-8")
        if not body:
            return {}
        return json.loads(body)


def _patch_json(base_url: str, path: str, payload: dict) -> dict:
    """ PATCH JSON and return parsed JSON response. """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        body = resp.read().decode("utf-8")
        if not body:
            return {}
        return json.loads(body)


class ServerRunner:
    """ Spawn and manage a local opencode serve process. """

    _info: Optional[ServerInfo] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(
        self,
        *,
        hostname: str = "127.0.0.1",
        port: int = 0,
        log_level: str = "WARN",
        cwd: Optional[Path] = None,
    ) -> ServerInfo:
        """ Start opencode serve and return ServerInfo once healthy.

        Raises ServerRunnerError on startup failure.
        """
        if self._info is not None:
            raise ServerRunnerError("Server already started")

        cmd = [
            "opencode", "serve",
            "--hostname", hostname,
            "--port", str(port),
            "--log-level", log_level,
        ]

        # Start the server, capturing stdout to read the "listening on" line.
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd or ROOT,
            )
        except FileNotFoundError:
            raise ServerRunnerError(
                "opencode command not found. Is OpenCode installed and in PATH?"
            ) from None
        except OSError as exc:
            raise ServerRunnerError(
                f"Failed to start opencode serve: {exc}"
            ) from exc

        # Read stdout until we see the "listening on" line or timeout.
        base_url: Optional[str] = None
        deadline = time.time() + _STARTUP_TIMEOUT_S
        try:
            while proc.poll() is None and time.time() < deadline:
                assert proc.stdout is not None
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.05)
                    continue
                m = _LOG_LISTENING_RE.search(line)
                if m:
                    base_url = m.group(1).rstrip("/")
                    break
        except Exception as exc:  # noqa: BLE001
            self._kill(proc)
            raise ServerRunnerError(
                f"Error reading opencode serve stdout: {exc}"
            ) from exc

        if base_url is None:
            # Did we exit early?
            rc = proc.poll()
            self._kill(proc)
            err_detail = ""
            if rc is not None:
                err_detail = f" (exit code {rc})"
            raise ServerRunnerError(
                f"opencode serve did not emit a listening line within {_STARTUP_TIMEOUT_S}s{err_detail}"
            )

        # Health-check loop.
        health_url = f"{base_url}/global/health"
        health_deadline = time.time() + _HEALTH_TIMEOUT_S
        health_ok = False
        last_err: Optional[str] = None
        while time.time() < health_deadline:
            data = _try_fetch_json(health_url, timeout=2.0)
            if data and data.get("healthy") is True:
                health_ok = True
                break
            time.sleep(_HEALTH_INTERVAL_S)

        if not health_ok:
            self._kill(proc)
            raise ServerRunnerError(
                f"opencode serve started at {base_url} but /global/health never returned healthy. "
                f"Last error: {last_err or 'no response'}"
            )

        self._info = ServerInfo(
            proc=proc,
            pid=proc.pid,
            base_url=base_url,
            port=_parse_port_from_url(base_url),
        )
        return self._info

    def stop(self) -> None:
        """ Gracefully stop the server; no-op if not started. """
        info = self._info
        if info is None:
            return

        self._kill(info.proc)
        self._info = None

    @property
    def info(self) -> Optional[ServerInfo]:
        return self._info

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _kill(proc: subprocess.Popen[str]) -> None:
        """ Send SIGTERM, wait, then SIGKILL if still alive. """
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=_GRACEFUL_SHUTDOWN_S)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        except ProcessLookupError:
            pass


# ------------------------------------------------------------------
# Convenience CLI (not the primary entry point)
# ------------------------------------------------------------------

def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="Convenience CLI for opencode serve management"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    start_p = sub.add_parser("start", help="Start opencode serve")
    start_p.add_argument("--port", type=int, default=0)
    start_p.add_argument("--hostname", default="127.0.0.1")
    start_p.add_argument("--log-level", default="WARN")
    start_p.add_argument("--cwd", type=Path, default=ROOT)

    stop_p = sub.add_parser("stop", help="Stop opencode serve by PID")
    stop_p.add_argument("--pid", type=int, required=True)

    args = parser.parse_args()

    if args.cmd == "start":
        runner = ServerRunner()
        try:
            info = runner.start(
                hostname=args.hostname,
                port=args.port,
                log_level=args.log_level,
                cwd=args.cwd,
            )
            print(f"Server running at {info.base_url} (pid={info.pid})")
            print("Press Ctrl-C to stop...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                runner.stop()
                print("Server stopped.")
            return 0
        except ServerRunnerError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if args.cmd == "stop":
        try:
            os.kill(args.pid, signal.SIGTERM)
            print(f"Sent SIGTERM to pid {args.pid}")
            return 0
        except ProcessLookupError:
            print(f"No process with pid {args.pid}", file=sys.stderr)
            return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
