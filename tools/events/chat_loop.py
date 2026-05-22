# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Multi-turn chat event loop: consumes SSE, signals idle/ready, and sends
new prompts on demand.  Designed for the interactive --chat mode.

Usage:
    loop = ChatEventLoop(base_url, session_id, console, auth_token=..., workspace_dir=...)
    loop.start_consumer(render_fn)
    loop.send_prompt("Hello")
    # ... wait for idle signal ...
    loop.send_prompt("Follow-up")
    loop.stop()
"""

from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from events.sse_client import SseClient, SseClientError
from events.state_tracker import StateTracker
from events.emitters import emit_event


class ChatState:
    """Signals emitted by the chat consumer thread to the TUI."""

    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    STOPPED = "stopped"


class ChatEventLoop:
    """Multi-turn event loop for interactive chat mode.

    Runs the SSE consumer in a background thread.  When the session
    reaches idle, it signals the TUI via a queue so the input can be
    re-enabled.  The TUI calls send_prompt() to submit new messages.
    """

    def __init__(
        self,
        base_url: str,
        session_id: str,
        console: Any,
        *,
        auth_token: str | None = None,
        workspace_dir: str | None = None,
        debug: Callable[[str], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id
        self.console = console
        self.auth_token = auth_token
        self.workspace_dir = workspace_dir
        self.debug = debug

        self._tracker = StateTracker()
        self._client: SseClient | None = None
        self._stopped = False
        self._seen_message_ids: set[str] = set()
        self._emitted_signatures: set[tuple[str, str]] = set()

        # Coordination with TUI
        self._state_queue: queue.Queue[tuple[str, Any | None]] = queue.Queue()
        self._consumer_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_consumer(self, render_fn: Callable[[Any, str, str, dict[str, Any]], None]) -> None:
        """Start the SSE consumer in a background daemon thread."""
        self._consumer_thread = threading.Thread(
            target=self._consumer_worker,
            args=(render_fn,),
            name="codecome-chat-consumer",
            daemon=True,
        )
        self._consumer_thread.start()

    def send_prompt(
        self,
        text: str,
        agent: str | None = None,
        model: str | None = None,
        variant: str | None = None,
    ) -> None:
        """POST a new user prompt to the active session.

        Blocks until the HTTP request completes.  The SSE consumer
        thread will pick up the response events automatically.
        """
        if self.debug:
            self.debug(f"send_prompt: posting prompt len={len(text)}")
        payload: dict[str, Any] = {
            "parts": [{"type": "text", "text": text}],
        }
        if agent:
            payload["agent"] = agent
        if model and "/" in model:
            provider_id, model_id = model.split("/", 1)
            payload["model"] = {"providerID": provider_id, "modelID": model_id}
        if variant:
            payload["variant"] = variant

        url = f"{self.base_url}/session/{self.session_id}/prompt_async"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._get_headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                resp.read()
            if self.debug:
                self.debug("send_prompt: HTTP POST completed")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            msg = f"HTTP {exc.code}: {body}"
            if self.debug:
                self.debug(f"send_prompt: HTTP error: {msg}")
            self._state_queue.put((ChatState.ERROR, msg))

    def get_state(self, timeout: float | None = None) -> tuple[str, Any | None]:
        """Block until the consumer signals a state change.

        Returns (state, detail).  State is one of ChatState.*
        """
        return self._state_queue.get(timeout=timeout)

    def stop(self) -> None:
        """Signal the consumer thread to exit and wait for it."""
        self._stopped = True
        if self._client is not None:
            self._client.stop()
        if self._consumer_thread is not None and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=5.0)
        # Signal stopped in case the TUI is waiting
        self._state_queue.put((ChatState.STOPPED, None))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            import base64

            encoded = base64.b64encode(f"opencode:{self.auth_token}".encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {encoded}"
        if self.workspace_dir:
            headers["x-opencode-directory"] = self.workspace_dir
        return headers

    def _consumer_worker(self, render_fn: Callable[[Any, str, str, dict[str, Any]], None]) -> None:
        """Background thread: consume SSE, render events, signal idle."""
        if self.debug:
            self.debug("_consumer_worker: starting SSE client")
        self._client = SseClient(
            self.base_url,
            auth_token=self.auth_token,
            workspace_dir=self.workspace_dir,
            reconnect=True,
            max_reconnects=10,
            on_reconnect=self._trigger_recovery_sync,
        )

        try:
            event_count = 0
            if self.debug:
                self.debug("_consumer_worker: entering event loop")
            for event in self._client.events():
                if self._stopped:
                    if self.debug:
                        self.debug("_consumer_worker: stopped flag set, breaking")
                    break

                if not self._belongs_to_session(event):
                    continue

                event_count += 1
                if self.debug and (event_count <= 5 or event_count % 20 == 0):
                    self.debug(f"_consumer_worker: event #{event_count} type={event.get('type')}")

                # Track message IDs *and* token-state from the SSE
                # stream so neither _sync_session_messages nor the
                # stream itself emit duplicate message.updated events.
                # Composite key = (msg_id, has_input) lets the
                # "no-tokens → has-tokens" transition render (e.g. the
                # final token-summary line for an assistant turn).
                if event.get("type") == "message.updated":
                    info = event.get("properties", {}).get("info", {})
                    if isinstance(info, dict):
                        msg_id = info.get("id")
                        if isinstance(msg_id, str) and msg_id:
                            tokens = info.get("tokens", {})
                            has_input = bool(tokens.get("input", 0)) if isinstance(tokens, dict) else False
                            stream_key = f"{msg_id}:tok={1 if has_input else 0}"
                            if stream_key in self._seen_message_ids:
                                if self.debug:
                                    self.debug(f"_consumer_worker: suppressing duplicate msg {stream_key}")
                                continue
                            self._seen_message_ids.add(stream_key)
                            # Also keep the plain message ID so
                            # _sync_session_messages (which checks the
                            # plain string) doesn't re-emit on idle.
                            self._seen_message_ids.add(msg_id)

                # Handle permissions
                if event.get("type") == "permission.asked":
                    self._handle_permission(event)
                    continue

                # Track state transitions
                if self._is_session_idle(event):
                    if self.debug:
                        self.debug("_consumer_worker: session idle detected")
                    # Emit the idle event itself
                    self._emit_event(render_fn, event)
                    # Signal idle to TUI
                    self._state_queue.put((ChatState.IDLE, None))
                    continue

                if self._is_session_busy(event):
                    self._state_queue.put((ChatState.BUSY, None))

                # Track and render
                finalized_events = self._tracker.ingest(event)
                for fe in finalized_events:
                    sig = (fe.get("type", ""), fe.get("part", {}).get("id", ""))
                    if sig[1] and sig in self._emitted_signatures:
                        continue
                    self._emitted_signatures.add(sig)
                    self._emit_event(render_fn, fe)

        except SseClientError as exc:
            msg = f"SSE connection lost: {exc}"
            if self.debug:
                self.debug(f"_consumer_worker: SseClientError: {exc}")
            self._state_queue.put((ChatState.ERROR, msg))
        except Exception as exc:
            msg = f"Chat consumer error: {exc}"
            if self.debug:
                import traceback
                self.debug(f"_consumer_worker: unexpected exception: {traceback.format_exc()}")
            self._state_queue.put((ChatState.ERROR, msg))
        else:
            if self.debug:
                self.debug("_consumer_worker: event loop ended normally")
        finally:
            if self.debug:
                self.debug("_consumer_worker: exiting")
            if not self._stopped:
                self._state_queue.put((ChatState.STOPPED, None))

    def _belongs_to_session(self, event: dict[str, Any]) -> bool:
        props = event.get("properties", {})
        sid = props.get("sessionID")
        if sid and sid != self.session_id:
            return False
        return True

    @staticmethod
    def _is_session_idle(event: dict[str, Any]) -> bool:
        event_type = event.get("type", "")
        if event_type == "session.idle":
            return True
        if event_type == "session.status":
            status = event.get("properties", {}).get("status", {})
            return status.get("type") == "idle"
        return False

    @staticmethod
    def _is_session_busy(event: dict[str, Any]) -> bool:
        event_type = event.get("type", "")
        if event_type == "session.status":
            status = event.get("properties", {}).get("status", {})
            return status.get("type") == "busy"
        return False

    def _handle_permission(self, event: dict[str, Any]) -> None:
        props = event.get("properties", {})
        perm_id = props.get("id")
        if not perm_id:
            return
        url = f"{self.base_url}/permission/{perm_id}/reply"
        data = json.dumps({
            "reply": "reject",
            "message": "Auto-rejected by CodeCome configuration",
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._get_headers(),
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10.0)
        except urllib.error.HTTPError:
            pass

    def _emit_event(self, render_fn: Callable[[Any, str, str, dict[str, Any]], None], event: dict[str, Any]) -> None:
        """Emit a single event through the render pipeline."""
        emit_event(render_fn, self.console, "Chat", "Interactive Chat", event)

    def _trigger_recovery_sync(self) -> None:
        """Called by SseClient after reconnection.

        TODO: implement a catch-up sync via _sync_session_messages here.
        Currently sync-after-reconnect is a no-op; the SSE-stream-level
        dedup (_seen_message_ids composite keys) and the fact that
        sync was removed from the normal idle path mean we rely on the
        SSE stream itself to deliver all events after reconnect.
        """
        pass  # sync happens inline in consumer

    def _sync_session_messages(self, render_fn: Callable[[Any, str, str, dict[str, Any]], None]) -> list[dict[str, Any]]:
        """Fetch current session messages and emit any missed finalized parts."""
        events: list[dict[str, Any]] = []
        try:
            req = urllib.request.Request(
                f"{self.base_url}/session/{self.session_id}/message",
                headers=self._get_headers(),
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                messages = json.loads(resp.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return []

        if not isinstance(messages, list):
            return []

        for item in messages:
            if not isinstance(item, dict):
                continue
            info = item.get("info")
            parts = item.get("parts")
            if not isinstance(info, dict) or not isinstance(parts, list):
                continue
            if info.get("role") != "assistant":
                continue
            if info.get("sessionID") != self.session_id:
                continue

            message_id = info.get("id")
            if isinstance(message_id, str) and message_id and message_id not in self._seen_message_ids:
                events.append({
                    "type": "message.updated",
                    "timestamp": int(time.time() * 1000),
                    "sessionID": self.session_id,
                    "info": info,
                })
                self._seen_message_ids.add(message_id)

            for part in parts:
                if not isinstance(part, dict):
                    continue
                part_id = part.get("id")
                if isinstance(part_id, str) and self._tracker.has_seen(part_id):
                    self._tracker.mark_seen(part_id)
                    continue
                synthesized = {
                    "type": "message.part.updated",
                    "timestamp": int(time.time() * 1000),
                    "properties": {
                        "sessionID": self.session_id,
                        "part": part,
                    },
                }
                events.extend(self._tracker.ingest(synthesized))

        for fe in events:
            sig = (fe.get("type", ""), fe.get("part", {}).get("id", ""))
            if sig[1] and sig in self._emitted_signatures:
                continue
            self._emitted_signatures.add(sig)
            self._emit_event(render_fn, fe)

        return events
