# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Server-Sent Events (SSE) client for opencode serve.

Consumes the global /event stream, parses data: lines,
reconnects on drops with exponential backoff,
and monitors heartbeats.
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.request
from typing import Any, Callable, Iterator


# Exponential backoff config for reconnect.
_BACKOFF_INITIAL_S = 3.0
_BACKOFF_MAX_S = 30.0
_BACKOFF_MULTIPLIER = 2.0

# Connect timeout for establishing the SSE connection.
_SSE_READ_TIMEOUT_S = 30.0


def _sse_read_tick() -> float:
    """Wall-clock cadence (seconds) at which a silent-but-open stream wakes.

    opencode schedules its ``server.heartbeat`` on the Effect runtime; when a
    model turn hangs, the runtime blocks and NO bytes flow on the open SSE
    connection. A plain blocking line read would wait forever. We set this as an
    explicit socket timeout so the read loop regains control every tick and can
    re-evaluate whether to keep consuming (e.g. the stall watchdog).
    """
    try:
        return max(1.0, float(os.environ.get("CODECOME_SSE_READ_TICK", "10")))
    except (TypeError, ValueError):
        return 10.0


import base64

def _build_sse_request(base_url: str, auth_token: str | None = None, workspace_dir: str | None = None) -> urllib.request.Request:
    """Return a GET /event request with SSE headers."""
    headers = {
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
    }
    if auth_token:
        encoded = base64.b64encode(f"opencode:{auth_token}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {encoded}"
    if workspace_dir:
        headers["x-opencode-directory"] = workspace_dir

    return urllib.request.Request(
        f"{base_url}/event",
        headers=headers,
        method="GET",
    )


class SseClientError(Exception):
    """ Raised when the SSE stream cannot be established or sustained. """
    pass


class SseClient:
    """ Open, consume, and auto-reconnect to the opencode SSE stream. """

    def __init__(
        self,
        base_url: str,
        *,
        auth_token: str | None = None,
        workspace_dir: str | None = None,
        reconnect: bool = True,
        max_reconnects: int = 10,
        on_reconnect: Callable[[], None] | None = None,
        should_continue: Callable[[], bool] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.workspace_dir = workspace_dir
        self.reconnect = reconnect
        self.max_reconnects = max_reconnects
        self.on_reconnect = on_reconnect
        # Optional predicate: when it returns True, the stream is kept alive
        # even past the normal reconnect budget / heartbeat timeout. This lets a
        # caller force continued consumption while the session is still busy and
        # the server process is alive (a long model turn must not be abandoned).
        self.should_continue = should_continue

        self._started = False
        self._stopped = False
        self._last_heartbeat = 0.0
        self._heartbeats_seen = False
        self._reconnect_count = 0
        self._first_connection_done = False

    def events(self) -> Iterator[dict]:
        """ Yield parsed SSE event JSON dicts.

        This is a blocking generator that stays alive until
        stop() is called or reconnect budget is exhausted.
        """
        if self._started:
            raise RuntimeError("events() can only be consumed once per instance")
        self._started = True
        self._last_heartbeat = time.time()

        while not self._stopped:
            notify_reconnect = self._first_connection_done
            try:
                for event in self._open_stream():
                    if self._stopped:
                        return
                    if event is None:
                        # Inactivity tick: the connection is open but no bytes
                        # arrived within the read tick. This is the ONLY chance
                        # to regain control on a silent-but-open stream (the
                        # opencode runtime can block and stop emitting events,
                        # including heartbeats). Let the caller decide whether to
                        # stop (e.g. stall watchdog) without treating it as an
                        # error or a reconnect.
                        if self.should_continue is not None and not self._should_continue_safe():
                            self.stop()
                            return
                        continue
                    self._on_event(event)
                    if notify_reconnect and self.on_reconnect:
                        self.on_reconnect()
                        notify_reconnect = False
                    self._first_connection_done = True
                    yield event
            except SseClientError:
                if not self.reconnect or self._stopped:
                    raise
                if self._reconnect_budget_exhausted():
                    raise SseClientError(
                        f"SSE reconnect budget exhausted ({self.max_reconnects} attempts)"
                    )
                self._reconnect_count += 1
                self._wait_backoff()
            except Exception as exc:  # noqa: BLE001
                # Unexpected error during stream consumption.
                if not self.reconnect or self._stopped:
                    raise SseClientError(f"SSE stream error: {exc}") from exc
                if self._reconnect_budget_exhausted():
                    raise SseClientError(
                        f"SSE reconnect budget exhausted ({self.max_reconnects} attempts)"
                    ) from exc
                self._reconnect_count += 1
                self._wait_backoff()

    def stop(self) -> None:
        """ Signal the generator to exit after the next event. """
        self._stopped = True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _should_continue_safe(self) -> bool:
        """Evaluate the should_continue predicate, defaulting to stop on error."""
        if self.should_continue is None:
            return True
        try:
            return bool(self.should_continue())
        except Exception:  # noqa: BLE001
            return False

    def _reconnect_budget_exhausted(self) -> bool:
        """Return True only when we should stop retrying.

        Normally the budget is ``max_reconnects``. But if ``should_continue``
        reports the session is still working (busy + process alive), we keep
        reconnecting indefinitely so a long model turn is never abandoned.
        """
        if self._reconnect_count < self.max_reconnects:
            return False
        if self.should_continue is not None:
            if self._should_continue_safe():
                # Keep going: reset the counter so backoff stays bounded.
                self._reconnect_count = 0
                return False
        return True

    def _on_event(self, event: dict) -> None:
        """ Book-keeping on every consumed event. """
        if event.get("type") == "server.heartbeat":
            self._last_heartbeat = time.time()
            self._heartbeats_seen = True
            self._reconnect_count = 0  # Reset on successful read.

        # A late non-heartbeat event is still useful progress. Do not raise here
        # for stale heartbeats: opencode may pause server.heartbeat while a valid
        # model/tool turn is still running, and raising would discard the very
        # event that proves the stream is alive. Silence is handled by the
        # read-tick + PhaseEventLoop stall watchdog instead.

    def seconds_since_heartbeat(self) -> float | None:
        """Seconds since the last heartbeat, or None if none seen yet."""
        if not self._heartbeats_seen:
            return None
        return time.time() - self._last_heartbeat

    def _open_stream(self) -> Iterator[dict | None]:
        """ Open the SSE connection and yield parsed events.

        Yields ``None`` as an inactivity *tick* whenever no bytes arrive within
        the read tick window, so the caller can re-evaluate liveness on a
        silent-but-open connection (opencode can block its runtime and stop
        emitting events entirely, including heartbeats).
        """
        req = _build_sse_request(self.base_url, self.auth_token, self.workspace_dir)
        try:
            resp = urllib.request.urlopen(req, timeout=_SSE_READ_TIMEOUT_S)
        except urllib.error.HTTPError as exc:
            raise SseClientError(f"HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise SseClientError(f"Connection failed: {exc.reason}") from exc

        # Force a bounded per-read socket timeout so a silent stream surfaces as
        # periodic socket.timeout ticks instead of blocking forever.
        tick = _sse_read_tick()
        self._set_stream_timeout(resp, tick)

        # Read SSE lines manually so we can convert read timeouts into ticks.
        buffer: list[str] = []
        try:
            while True:
                if self._stopped:
                    return
                try:
                    byte_line = resp.readline()
                except (socket.timeout, TimeoutError):
                    # No data within the tick window → emit an inactivity tick.
                    yield None
                    continue
                except (urllib.error.URLError, ConnectionError, OSError) as exc:
                    raise SseClientError(f"SSE read error: {exc}") from exc

                if byte_line == b"":
                    # EOF: server closed the connection.
                    raise SseClientError("SSE stream closed by server")

                line = byte_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if not line:
                    # Empty line → flush buffer.
                    if buffer:
                        event = self._parse_buffer(buffer)
                        buffer = []
                        if event is not None:
                            yield event
                    continue
                buffer.append(line)
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _set_stream_timeout(resp: Any, timeout: float) -> None:
        """Best-effort: set a per-read socket timeout on the response stream."""
        fp = getattr(resp, "fp", None)
        sock = None
        if fp is not None:
            raw = getattr(fp, "raw", None)
            sock = getattr(raw, "_sock", None) or getattr(fp, "_sock", None)
        if sock is None:
            sock = getattr(resp, "_sock", None)
        if sock is not None and hasattr(sock, "settimeout"):
            try:
                sock.settimeout(timeout)
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _parse_buffer(lines: list[str]) -> dict | None:
        """ Parse accumulated SSE lines into a JSON event dict.

        Returns None for comment lines or non-data events we don't care about.
        """
        data_parts: list[str] = []
        for line in lines:
            if line.startswith("data:"):
                data_parts.append(line[5:].lstrip())
            # We ignore event:, id:, retry: — the JSON payload is self-describing.
        if not data_parts:
            return None
        payload = "\n".join(data_parts)
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    def _wait_backoff(self) -> None:
        """ Sleep with exponential backoff before reconnect attempt. """
        delay = min(
            _BACKOFF_INITIAL_S * (_BACKOFF_MULTIPLIER ** (self._reconnect_count - 1)),
            _BACKOFF_MAX_S,
        )
        time.sleep(delay)
