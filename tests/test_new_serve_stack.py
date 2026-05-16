from __future__ import annotations

import io
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from conftest import ROOT


def load_events():
    sys_path = str(ROOT / "tools")
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from events.sse_client import SseClient, SseClientError
    from events.state_tracker import StateTracker
    from events.emitters import emit_event
    from events import EventLoop, RunResult
    return SseClient, SseClientError, StateTracker, emit_event, EventLoop, RunResult


def load_serve():
    sys_path = str(ROOT / "tools")
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from opencode.serve import ServerRunner, ServerInfo, ServerRunnerError
    return ServerRunner, ServerInfo, ServerRunnerError


# ---------------------------------------------------------------------------
# StateTracker
# ---------------------------------------------------------------------------

class TestStateTracker:
    """Unit tests for events.state_tracker.StateTracker."""

    @pytest.fixture
    def tracker(self):
        return load_events()[2]()

    def test_empty_ingest_returns_empty(self, tracker):
        assert tracker.ingest({"type": "unknown"}) == [{"type": "unknown"}]

    def test_delta_accumulates_text(self, tracker):
        tracker.ingest({
            "type": "message.part.delta",
            "properties": {"partID": "abc", "field": "text", "delta": "Hello "},
        })
        tracker.ingest({
            "type": "message.part.delta",
            "properties": {"partID": "abc", "field": "text", "delta": "world"},
        })
        # Not finalized yet → no events
        assert tracker.ingest({"type": "server.heartbeat"}) == [{"type": "server.heartbeat"}]
        assert tracker._delta_buffers.get("abc") == "Hello world"

    def test_updated_emits_finalized_text(self, tracker):
        SseClient, SseClientError, StateTracker, emit_event, EventLoop, RunResult = load_events()
        tracker = StateTracker()
        tracker.ingest({
            "type": "message.part.delta",
            "properties": {"partID": "abc", "field": "text", "delta": "Hello"},
        })
        finalized = tracker.ingest({
            "type": "message.part.updated",
            "timestamp": 123,
            "properties": {
                "sessionID": "s1",
                "part": {"id": "abc", "type": "text", "time": {"start": 0, "end": 1}},
            },
        })
        assert len(finalized) == 1
        ev = finalized[0]
        assert ev["type"] == "text"
        assert ev["sessionID"] == "s1"
        assert ev["part"]["text"] == "Hello"
        assert ev["part"]["id"] == "abc"

    def test_step_start_finalized_immediately(self, tracker):
        finalized = tracker.ingest({
            "type": "message.part.updated",
            "timestamp": 1,
            "properties": {
                "sessionID": "s1",
                "part": {"id": "p1", "type": "step-start"},
            },
        })
        assert len(finalized) == 1
        assert finalized[0]["type"] == "step_start"

    def test_step_finish_finalized_immediately(self, tracker):
        finalized = tracker.ingest({
            "type": "message.part.updated",
            "timestamp": 2,
            "properties": {
                "sessionID": "s1",
                "part": {"id": "p2", "type": "step-finish", "reason": "stop", "tokens": {"input": 10}},
            },
        })
        assert len(finalized) == 1
        assert finalized[0]["type"] == "step_finish"
        assert finalized[0]["part"]["reason"] == "stop"

    def test_reasoning_part_requires_time_end(self, tracker):
        SseClient, SseClientError, StateTracker, emit_event, EventLoop, RunResult = load_events()
        tracker = StateTracker()
        # Without time.end → not finalized
        no_final = tracker.ingest({
            "type": "message.part.updated",
            "properties": {
                "sessionID": "s1",
                "part": {"id": "r1", "type": "reasoning"},
            },
        })
        assert len(no_final) == 0
        # With time.end → finalized
        finalized = tracker.ingest({
            "type": "message.part.updated",
            "properties": {
                "sessionID": "s1",
                "part": {"id": "r1", "type": "reasoning", "time": {"end": 1}},
            },
        })
        assert len(finalized) == 1
        assert finalized[0]["type"] == "reasoning"

    def test_tool_part_finalized_immediately(self, tracker):
        finalized = tracker.ingest({
            "type": "message.part.updated",
            "properties": {
                "sessionID": "s1",
                "part": {"id": "t1", "type": "tool", "state": {"tool": "read", "status": "completed"}},
            },
        })
        assert len(finalized) == 1
        assert finalized[0]["type"] == "tool_use"

    def test_seen_and_pending(self, tracker):
        tracker.ingest({
            "type": "message.part.delta",
            "properties": {"partID": "x", "field": "text", "delta": "hi"},
        })
        assert tracker.is_pending("x") is True
        assert tracker.has_seen("x") is False

        tracker.ingest({
            "type": "message.part.updated",
            "properties": {"sessionID": "s", "part": {"id": "x", "type": "text", "time": {"end": 1}}},
        })
        assert tracker.is_pending("x") is False
        assert tracker.has_seen("x") is True


# ---------------------------------------------------------------------------
# SSE Client internals (static parsing)
# ---------------------------------------------------------------------------

class TestSseClient:
    """Unit tests for events.sse_client.SseClient static parsing."""

    @pytest.fixture
    def sse_cls(self):
        return load_events()[0]

    def test_parse_buffer_single_data_line(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        buf = ["data: {}", ""]
        ev = client._parse_buffer(buf)  # type: ignore[misc]
        assert ev == {}

    def test_parse_buffer_json_payload(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        payload = {"type": "server.heartbeat"}
        buf = [f"data: {json.dumps(payload)}"]
        ev = client._parse_buffer(buf)  # type: ignore[misc]
        assert ev == payload

    def test_parse_buffer_multiline_data(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        buf = ["data: {\"key\": \"line1", "data: line2\"}"]
        ev = client._parse_buffer(buf)  # type: ignore[misc]
        assert ev is None  # joined string is not valid JSON; returns None

    def test_parse_buffer_multiline_valid_json(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        payload = json.dumps({"msg": "hello\nworld"})
        lines = payload.split("\n")
        buf = [f"data: {ln}" for ln in lines]
        ev = client._parse_buffer(buf)  # type: ignore[misc]
        assert ev == {"msg": "hello\nworld"}

    def test_parse_buffer_ignores_comment_lines(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        buf = [":comment", "data: 42"]
        ev = client._parse_buffer(buf)  # type: ignore[misc]
        assert ev == 42

    def test_parse_buffer_no_data_returns_none(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        buf = ["event: foo"]
        ev = client._parse_buffer(buf)  # type: ignore[misc]
        assert ev is None

    def test_parse_buffer_malformed_json_returns_none(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        buf = ["data: not-json"]
        ev = client._parse_buffer(buf)  # type: ignore[misc]
        assert ev is None


# ---------------------------------------------------------------------------
# emit_event bridge
# ---------------------------------------------------------------------------

class TestEmitters:
    """Unit tests for events.emitters.emit_event."""

    @pytest.fixture
    def emit(self):
        return load_events()[3]

    def test_emit_event_calls_render_fn(self, emit):
        called = []

        def fake_render(console, phase, label, event):
            called.append((console, phase, label, event))

        event = {"type": "text", "part": {"text": "hello"}}
        emit(fake_render, None, "1", "recon", event)

        assert len(called) == 1
        assert called[0][1] == "1"
        assert called[0][2] == "recon"
        assert called[0][3] == event


# ---------------------------------------------------------------------------
# EventLoop termination signals
# ---------------------------------------------------------------------------

class TestEventLoop:
    """Unit tests for events.EventLoop core logic."""

    @pytest.fixture
    def loop_cls(self):
        return load_events()[4]

    @pytest.fixture
    def run_result_cls(self):
        return load_events()[5]

    def test_belongs_to_session_filters_by_session_id(self, loop_cls):
        loop = loop_cls("http://localhost:8080", "sess-abc", None, "1", "recon")
        assert loop._belongs_to_session({"properties": {"sessionID": "sess-abc"}})
        assert not loop._belongs_to_session({"properties": {"sessionID": "other"}})
        # server events without sessionID pass through
        assert loop._belongs_to_session({"type": "server.heartbeat"})

    def test_update_result_counts_step_finishes(self, loop_cls):
        loop = loop_cls("http://localhost:8080", "s", None, "1", "recon")
        event = {
            "type": "step_finish",
            "part": {"reason": "tool-calls", "tokens": {"input": 5, "output": 10}},
        }
        result = loop._update_result(event, False, 0, None, {})  # type: ignore[misc]
        any_seen, count, reason, tokens = result
        assert any_seen is True
        assert count == 1
        assert reason == "tool-calls"
        assert tokens == {"input": 5, "output": 10}

    def test_run_result_defaults(self, run_result_cls):
        r = run_result_cls()
        assert r.any_step_finish_seen is False
        assert r.step_finish_count == 0
        assert r.last_finish_reason is None
        assert r.last_finish_tokens == {}


# ---------------------------------------------------------------------------
# ServerRunner internals (static helpers)
# ---------------------------------------------------------------------------

class TestServerRunner:
    """Unit tests for opencode.serve.ServerRunner static helpers."""

    @pytest.fixture
    def classes(self):
        return load_serve()

    def test_parse_port_from_url_standard(self, classes):
        _, _, _ = classes
        from opencode.serve import _parse_port_from_url
        assert _parse_port_from_url("http://127.0.0.1:49152") == 49152

    def test_parse_port_from_url_no_port_raises(self, classes):
        from opencode.serve import _parse_port_from_url
        with pytest.raises(ValueError):
            _parse_port_from_url("http://127.0.0.1")

    def test_server_info_fields(self, classes):
        ServerRunner, ServerInfo, ServerRunnerError = classes
        # Construct a minimal ServerInfo with a None proc (not used in tests)
        info = ServerInfo(proc=None, pid=1234, base_url="http://127.0.0.1:8080", port=8080)  # type: ignore[arg-type]
        assert info.pid == 1234
        assert info.port == 8080
        assert info.base_url == "http://127.0.0.1:8080"

    def test_server_runner_error_is_exception(self, classes):
        ServerRunner, ServerInfo, ServerRunnerError = classes
        with pytest.raises(ServerRunnerError):
            raise ServerRunnerError("boom")

    def test_try_fetch_json_timeout_returns_none(self, classes, monkeypatch):
        from opencode.serve import _try_fetch_json
        # Patch urlopen to always raise
        def boom(*a, **kw):
            raise urllib.error.URLError("timeout")
        monkeypatch.setattr(urllib.request, "urlopen", boom)
        assert _try_fetch_json("http://localhost:1/health", 0.1) is None

    def test_post_json_sends_post(self, classes, monkeypatch):
        from opencode.serve import _post_json
        captured = {}

        class FakeResp:
            def read(self):
                return b'{"ok": true}'
            def __enter__(self): return self
            def __exit__(self, *a): pass

        def fake_urlopen(req, **kw):
            captured["method"] = req.method
            captured["data"] = req.data
            captured["headers"] = dict(req.header_items())
            return FakeResp()

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        result = _post_json("http://localhost:8080", "/test", {"key": "val"})
        assert result == {"ok": True}
        assert captured["method"] == "POST"
        assert json.loads(captured["data"]) == {"key": "val"}
        assert captured["headers"]["Content-type"] == "application/json"


# ---------------------------------------------------------------------------
# End-to-end EventLoop with fake SSE producer
# ---------------------------------------------------------------------------

class TestEventLoopEndToEnd:
    """End-to-end tests for EventLoop consuming a controlled SSE stream."""

    @pytest.fixture
    def event_loop_objects(self):
        SseClient, SseClientError, StateTracker, emit_event, EventLoop, RunResult = load_events()
        return EventLoop, RunResult, SseClient

    def test_full_run_emits_expected_events(self, event_loop_objects):
        EventLoop, RunResult, SseClient = event_loop_objects

        emitted: list[dict] = []

        def fake_render(console, phase, label, event):
            emitted.append(event)

        # Create a fake SSE client that yields a canned sequence.
        class FakeSseClient:
            def __init__(self, *a, **kw):
                pass
            def events(self):
                return iter([
                    {"type": "server.connected"},
                    {"type": "message.part.updated", "properties": {"sessionID": "sess-1", "part": {"id": "p1", "type": "step-start"}}},
                    {"type": "message.part.delta", "properties": {"sessionID": "sess-1", "partID": "p2", "field": "text", "delta": "Hello"}},
                    {"type": "message.part.updated", "properties": {"sessionID": "sess-1", "part": {"id": "p2", "type": "text", "time": {"start": 0, "end": 1}}}},
                    {"type": "message.part.updated", "properties": {"sessionID": "sess-1", "part": {"id": "p3", "type": "tool", "state": {"tool": "write", "status": "completed"}}}},
                    {"type": "message.part.updated", "properties": {"sessionID": "sess-1", "part": {"id": "p4", "type": "step-finish", "reason": "stop", "tokens": {"total": 42}}}},
                    {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
                ])
            def stop(self):
                pass

        # Monkey-patch SseClient inside the events module for this test.
        import events as _events_mod
        orig = _events_mod.SseClient
        _events_mod.SseClient = FakeSseClient  # type: ignore[misc]
        try:
            loop = EventLoop("http://localhost:8080", "sess-1", None, "1", "recon")
            result = loop.run(fake_render)
        finally:
            _events_mod.SseClient = orig

        assert result.any_step_finish_seen is True
        assert result.step_finish_count == 1
        assert result.last_finish_reason == "stop"
        assert result.last_finish_tokens == {"total": 42}
        assert result.last_session_id == "sess-1"

        # Verify rendered event types in order (includes pass-through events)
        types = [e["type"] for e in emitted]
        assert types == ["server.connected", "step_start", "text", "tool_use", "step_finish", "session.idle"]

        # Verify text accumulation
        text_event = emitted[2]
        assert text_event["part"]["text"] == "Hello"

    def test_permission_auto_rejected(self, event_loop_objects, monkeypatch):
        EventLoop, RunResult, SseClient = event_loop_objects

        captured_perms: list[tuple] = []

        class FakeSseClient:
            def __init__(self, *a, **kw):
                pass
            def events(self):
                return iter([
                    {"type": "permission.asked", "properties": {"sessionID": "sess-1", "id": "perm-1", "tool": "bash"}},
                    {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
                ])
            def stop(self):
                pass

        import events as _events_mod
        orig = _events_mod.SseClient
        _events_mod.SseClient = FakeSseClient  # type: ignore[misc]

        # Capture permission POSTs
        def fake_urlopen(req, **kw):
            captured_perms.append((req.full_url, req.data))
            return type("R", (), {"read": lambda: b"{}", "__enter__": lambda s: s, "__exit__": lambda *a: None})()

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        try:
            loop = EventLoop("http://localhost:8080", "sess-1", None, "1", "recon")
            result = loop.run(lambda c, p, l, e: None)
        finally:
            _events_mod.SseClient = orig

        assert result.last_permission_error == "tool permission rejected: bash"
        assert len(captured_perms) == 1
        assert "permission/perm-1/reply" in captured_perms[0][0]
        assert json.loads(captured_perms[0][1]) == {"reply": "reject"}

    def test_session_idle_stops_consuming(self, event_loop_objects):
        EventLoop, RunResult, SseClient = event_loop_objects

        emitted: list[dict] = []

        class FakeSseClient:
            def __init__(self, *a, **kw):
                pass
            def events(self):
                return iter([
                    {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
                    {"type": "message.part.updated", "properties": {"sessionID": "sess-1", "part": {"id": "late", "type": "text", "time": {"end": 1}}}},
                ])
            def stop(self):
                pass

        import events as _events_mod
        orig = _events_mod.SseClient
        _events_mod.SseClient = FakeSseClient  # type: ignore[misc]
        try:
            loop = EventLoop("http://localhost:8080", "sess-1", None, "1", "recon")
            loop.run(lambda c, p, l, e: emitted.append(e))
        finally:
            _events_mod.SseClient = orig

        # Events after session.idle should be ignored, but session.idle itself is passed through
        assert len(emitted) == 1
        assert emitted[0]["type"] == "session.idle"

    def test_empty_stream_no_step_finish(self, event_loop_objects):
        EventLoop, RunResult, SseClient = event_loop_objects

        class FakeSseClient:
            def __init__(self, *a, **kw):
                pass
            def events(self):
                return iter([
                    {"type": "server.connected"},
                    {"type": "server.heartbeat"},
                ])
            def stop(self):
                pass

        import events as _events_mod
        orig = _events_mod.SseClient
        _events_mod.SseClient = FakeSseClient  # type: ignore[misc]
        try:
            loop = EventLoop("http://localhost:8080", "sess-1", None, "1", "recon")
            result = loop.run(lambda c, p, l, e: None)
        finally:
            _events_mod.SseClient = orig

        assert result.any_step_finish_seen is False
        assert result.step_finish_count == 0
        assert result.last_finish_reason is None
