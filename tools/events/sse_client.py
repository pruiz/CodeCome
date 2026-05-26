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
import time
import urllib.request
from typing import Any, Callable, Iterator


# Exponential backoff config for reconnect.
_BACKOFF_INITIAL_S = 3.0
_BACKOFF_MAX_S = 30.0
_BACKOFF_MULTIPLIER = 2.0

# If no heartbeat for this long, treat as dead.
_HEARTBEAT_TIMEOUT_S = 15.0

# Read timeout for the SSE connection.
_SSE_READ_TIMEOUT_S = 30.0


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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.workspace_dir = workspace_dir
        self.reconnect = reconnect
        self.max_reconnects = max_reconnects
        self.on_reconnect = on_reconnect

        self._started = False
        self._stopped = False
        self._last_heartbeat = 0.0
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
                    self._on_event(event)
                    if notify_reconnect and self.on_reconnect:
                        self.on_reconnect()
                        notify_reconnect = False
                    self._first_connection_done = True
                    yield event
            except SseClientError:
                if not self.reconnect or self._stopped:
                    raise
                if self._reconnect_count >= self.max_reconnects:
                    raise SseClientError(
                        f"SSE reconnect budget exhausted ({self.max_reconnects} attempts)"
                    )
                self._reconnect_count += 1
                self._wait_backoff()
            except Exception as exc:  # noqa: BLE001
                # Unexpected error during stream consumption.
                if not self.reconnect or self._stopped:
                    raise SseClientError(f"SSE stream error: {exc}") from exc
                if self._reconnect_count >= self.max_reconnects:
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

    def _on_event(self, event: dict) -> None:
        """ Book-keeping on every consumed event. """
        if event.get("type") == "server.heartbeat":
            self._last_heartbeat = time.time()
            self._reconnect_count = 0  # Reset on successful read.

        # Heartbeat timeout check.
        elapsed = time.time() - self._last_heartbeat
        if elapsed > _HEARTBEAT_TIMEOUT_S:
            raise SseClientError(
                f"No server heartbeat for {elapsed:.1f}s (timeout {_HEARTBEAT_TIMEOUT_S}s)"
            )

    def _open_stream(self) -> Iterator[dict]:
        """ Open the SSE connection and yield parsed events. """
        req = _build_sse_request(self.base_url, self.auth_token, self.workspace_dir)
        try:
            resp = urllib.request.urlopen(req, timeout=_SSE_READ_TIMEOUT_S)
        except urllib.error.HTTPError as exc:
            raise SseClientError(f"HTTP {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise SseClientError(f"Connection failed: {exc.reason}") from exc

        # Read SSE lines.
        buffer = []
        try:
            for byte_line in resp:
                if self._stopped:
                    return
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
            resp.close()

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
