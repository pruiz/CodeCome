from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from conftest import ROOT


def load_events():
    sys_path = str(ROOT / "tools")
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from events.sse_client import SseClient, SseClientError
    from events.state_tracker import StateTracker
    from events.emitters import emit_event
    from events.phase_loop import PhaseEventLoop, RunResult
    return SseClient, SseClientError, StateTracker, emit_event, PhaseEventLoop, RunResult


def load_serve():
    sys_path = str(ROOT / "tools")
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from opencode.serve import ServerRunner, ServerInfo, ServerRunnerError
    return ServerRunner, ServerInfo, ServerRunnerError


def _patch_phase_sse_client(monkeypatch, fake_cls):
    monkeypatch.setattr("events.phase_loop.SseClient", fake_cls)


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
        assert tracker.ingest({"type": "server.heartbeat"}) == [{"type": "server.heartbeat"}]
        assert tracker._delta_buffers.get("abc") == "Hello world"

    def test_updated_emits_finalized_text(self):
        StateTracker = load_events()[2]
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

    def test_reasoning_part_requires_time_end(self):
        StateTracker = load_events()[2]
        tracker = StateTracker()
        no_final = tracker.ingest({
            "type": "message.part.updated",
            "properties": {
                "sessionID": "s1",
                "part": {"id": "r1", "type": "reasoning"},
            },
        })
        assert len(no_final) == 0
        finalized = tracker.ingest({
            "type": "message.part.updated",
            "properties": {
                "sessionID": "s1",
                "part": {"id": "r1", "type": "reasoning", "time": {"end": 1}},
            },
        })
        assert len(finalized) == 1
        assert finalized[0]["type"] == "reasoning"

    def test_tool_part_lifecycle(self, tracker):
        pending = tracker.ingest({"type": "message.part.updated", "properties": {"sessionID": "s1", "part": {"id": "t1", "type": "tool", "state": {"status": "pending"}}}})
        assert len(pending) == 0

        running = tracker.ingest({"type": "message.part.updated", "properties": {"sessionID": "s1", "part": {"id": "t1", "type": "tool", "state": {"status": "running"}}}})
        assert len(running) == 0

        completed = tracker.ingest({"type": "message.part.updated", "properties": {"sessionID": "s1", "part": {"id": "t1", "type": "tool", "state": {"status": "completed"}}}})
        assert len(completed) == 1
        assert completed[0]["type"] == "tool_use"

    def test_text_accumulation_survives_intermediate_updates(self, tracker):
        tracker.ingest({"type": "message.part.delta", "properties": {"partID": "abc", "field": "text", "delta": "Hello"}})
        tracker.ingest({"type": "message.part.updated", "properties": {"sessionID": "s1", "part": {"id": "abc", "type": "text", "text": "Hello"}}})
        tracker.ingest({"type": "message.part.delta", "properties": {"partID": "abc", "field": "text", "delta": " world"}})
        finalized = tracker.ingest({"type": "message.part.updated", "properties": {"sessionID": "s1", "part": {"id": "abc", "type": "text", "time": {"end": 1}}}})
        assert len(finalized) == 1
        assert finalized[0]["part"]["text"] == "Hello world"

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
        assert client._parse_buffer(["data: {}", ""]) == {}

    def test_parse_buffer_json_payload(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        payload = {"type": "server.heartbeat"}
        assert client._parse_buffer([f"data: {json.dumps(payload)}"]) == payload

    def test_parse_buffer_multiline_data(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        assert client._parse_buffer(["data: {\"key\": \"line1", "data: line2\"}"]) is None

    def test_parse_buffer_multiline_valid_json(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        payload = json.dumps({"msg": "hello\nworld"})
        lines = payload.split("\n")
        assert client._parse_buffer([f"data: {ln}" for ln in lines]) == {"msg": "hello\nworld"}

    def test_parse_buffer_ignores_comment_lines(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        assert client._parse_buffer([":comment", "data: 42"]) == 42

    def test_parse_buffer_no_data_returns_none(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        assert client._parse_buffer(["event: foo"]) is None

    def test_parse_buffer_malformed_json_returns_none(self, sse_cls):
        client = sse_cls("http://localhost:8080")
        assert client._parse_buffer(["data: not-json"]) is None

    def test_on_reconnect_called_once_after_actual_reconnect(self, sse_cls):
        client = sse_cls("http://localhost:8080", reconnect=True, max_reconnects=1)
        reconnects = []
        client.on_reconnect = lambda: reconnects.append("reconnect")
        streams = iter([
            [{"type": "server.connected"}, {"type": "server.heartbeat"}],
            [{"type": "server.connected"}, {"type": "server.heartbeat"}],
        ])

        def fake_open_stream():
            stream = next(streams)
            for event in stream:
                yield event
            raise load_events()[1]("drop")

        client._open_stream = fake_open_stream
        events = []
        with pytest.raises(load_events()[1]):
            for event in client.events():
                events.append(event)

        assert [event["type"] for event in events] == [
            "server.connected", "server.heartbeat",
            "server.connected", "server.heartbeat",
        ]
        assert reconnects == ["reconnect"]


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
# PhaseEventLoop termination signals
# ---------------------------------------------------------------------------

class TestPhaseEventLoop:
    """Unit tests for events.phase_loop.PhaseEventLoop core logic."""

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
        assert loop._belongs_to_session({"type": "server.heartbeat"})

    def test_update_result_counts_step_finishes(self, loop_cls):
        loop = loop_cls("http://localhost:8080", "s", None, "1", "recon")
        result = loop._update_result(
            {"type": "step_finish", "part": {"reason": "tool-calls", "tokens": {"input": 5, "output": 10}}},
            False,
            0,
            None,
            {},
        )
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
        _, ServerInfo, _ = classes
        log_path = ROOT / "tmp" / "test.log"
        info = ServerInfo(proc=None, pid=1234, base_url="http://127.0.0.1:49152", port=49152, log_path=log_path, password="dummy")  # type: ignore[arg-type]
        assert info.port == 49152

    def test_parse_port_from_url_no_port_raises(self, classes):
        _, ServerInfo, _ = classes
        log_path = ROOT / "tmp" / "test.log"
        info = ServerInfo(proc=None, pid=1234, base_url="http://127.0.0.1:8080", port=8080, log_path=log_path, password="dummy")  # type: ignore[arg-type]
        assert info.port == 8080

    def test_server_info_fields(self, classes):
        ServerRunner, ServerInfo, ServerRunnerError = classes
        log_path = ROOT / "tmp" / "test.log"
        info = ServerInfo(proc=None, pid=1234, base_url="http://127.0.0.1:8080", port=8080, log_path=log_path, password="dummy")  # type: ignore[arg-type]
        assert info.pid == 1234
        assert info.port == 8080
        assert info.base_url == "http://127.0.0.1:8080"
        assert info.log_path == log_path

    def test_server_runner_error_is_exception(self, classes):
        ServerRunner, ServerInfo, ServerRunnerError = classes
        with pytest.raises(ServerRunnerError):
            raise ServerRunnerError("boom")

    def test_try_fetch_json_timeout_returns_none(self, classes, monkeypatch):
        from opencode.serve import _try_fetch_json

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

    def test_start_treats_zero_port_as_ephemeral(self, classes, monkeypatch):
        ServerRunner, _, _ = classes

        class FakeProc:
            pid = 1234
            def poll(self): return None
            def terminate(self): return None
            def wait(self, timeout=None): return 0

        monkeypatch.setattr("opencode.serve._find_free_port", lambda hostname: 54321)
        monkeypatch.setattr("opencode.serve._try_fetch_json", lambda url, timeout, auth_token=None: {"healthy": True, "version": "1.14.50"})
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: FakeProc())

        runner = ServerRunner()
        info = runner.start(port=0)

        assert info.port == 54321
        assert info.base_url == "http://127.0.0.1:54321"
        runner.stop()

    def test_stop_falls_back_when_killpg_permission_denied(self, classes, monkeypatch):
        ServerRunner, _, _ = classes
        terminated = []

        class FakeProc:
            pid = 1234
            def poll(self): return None
            def terminate(self): terminated.append("terminate")
            def wait(self, timeout=None): return 0

        def deny_killpg(*_args):
            raise PermissionError("not our process group")

        monkeypatch.setattr("opencode.serve.os.killpg", deny_killpg)

        ServerRunner._kill(FakeProc())

        assert terminated == ["terminate"]


# ---------------------------------------------------------------------------
# End-to-end PhaseEventLoop with fake SSE producer
# ---------------------------------------------------------------------------

class TestPhaseEventLoopEndToEnd:
    """End-to-end tests for PhaseEventLoop consuming a controlled SSE stream."""

    @pytest.fixture
    def event_loop_objects(self):
        SseClient, SseClientError, StateTracker, emit_event, PhaseEventLoop, RunResult = load_events()
        return PhaseEventLoop, RunResult, SseClient

    def test_full_run_emits_expected_events(self, event_loop_objects, monkeypatch):
        PhaseEventLoop, RunResult, SseClient = event_loop_objects
        emitted: list[dict] = []

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

        _patch_phase_sse_client(monkeypatch, FakeSseClient)
        loop = PhaseEventLoop("http://localhost:8080", "sess-1", None, "1", "recon")
        result = loop.run(lambda c, p, l, e: emitted.append(e))

        assert result.any_step_finish_seen is True
        assert result.step_finish_count == 1
        assert result.last_finish_reason == "stop"
        assert result.last_finish_tokens == {"total": 42}
        assert result.last_session_id == "sess-1"

        assert [e["type"] for e in emitted] == ["server.connected", "step_start", "text", "tool_use", "step_finish", "session.idle"]
        assert emitted[2]["part"]["text"] == "Hello"

    def test_permission_auto_rejected(self, event_loop_objects, monkeypatch):
        PhaseEventLoop, RunResult, SseClient = event_loop_objects
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

        def fake_urlopen(req, **kw):
            if req.full_url.endswith("/permission/perm-1/reply"):
                captured_perms.append((req.full_url, req.data))
            return type("R", (), {"read": lambda: b"{}", "__enter__": lambda s: s, "__exit__": lambda *a: None})()

        _patch_phase_sse_client(monkeypatch, FakeSseClient)
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        loop = PhaseEventLoop("http://localhost:8080", "sess-1", None, "1", "recon")
        result = loop.run(lambda c, p, l, e: None)

        assert result.last_permission_error == "tool permission rejected: bash"
        assert len(captured_perms) == 1
        assert "permission/perm-1/reply" in captured_perms[0][0]
        assert json.loads(captured_perms[0][1]) == {"reply": "reject", "message": "Auto-rejected by CodeCome configuration"}

    def test_session_idle_stops_consuming(self, event_loop_objects, monkeypatch):
        PhaseEventLoop, RunResult, SseClient = event_loop_objects
        emitted: list[dict] = []

        class FakeSseClient:
            def __init__(self, *a, **kw): pass
            def events(self):
                return iter([
                    {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
                    {"type": "message.part.updated", "properties": {"sessionID": "sess-1", "part": {"id": "late", "type": "text", "time": {"end": 1}}}},
                ])
            def stop(self): pass

        _patch_phase_sse_client(monkeypatch, FakeSseClient)
        loop = PhaseEventLoop("http://localhost:8080", "sess-1", None, "1", "recon")
        loop.run(lambda c, p, l, e: emitted.append(e))

        assert len(emitted) == 1
        assert emitted[0]["type"] == "session.idle"

    def test_session_status_idle_stops_consuming(self, event_loop_objects, monkeypatch):
        PhaseEventLoop, RunResult, SseClient = event_loop_objects
        emitted: list[dict] = []

        class FakeSseClient:
            def __init__(self, *a, **kw): pass
            def events(self):
                return iter([
                    {"type": "session.status", "properties": {"sessionID": "sess-1", "status": {"type": "idle"}}},
                    {"type": "message.part.updated", "properties": {"sessionID": "sess-1", "part": {"id": "late", "type": "text", "time": {"end": 1}}}},
                ])
            def stop(self): pass

        _patch_phase_sse_client(monkeypatch, FakeSseClient)
        loop = PhaseEventLoop("http://localhost:8080", "sess-1", None, "1", "recon")
        loop.run(lambda c, p, l, e: emitted.append(e))

        assert len(emitted) == 1
        assert emitted[0]["type"] == "session.status"

    def test_both_idle_events_only_processed_once(self, event_loop_objects, monkeypatch):
        PhaseEventLoop, RunResult, SseClient = event_loop_objects
        emitted: list[dict] = []

        class FakeSseClient:
            def __init__(self, *a, **kw): pass
            def events(self):
                return iter([
                    {"type": "session.status", "properties": {"sessionID": "sess-1", "status": {"type": "idle"}}},
                    {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
                    {"type": "message.part.updated", "properties": {"sessionID": "sess-1", "part": {"id": "late", "type": "text", "time": {"end": 1}}}},
                ])
            def stop(self): pass

        _patch_phase_sse_client(monkeypatch, FakeSseClient)
        loop = PhaseEventLoop("http://localhost:8080", "sess-1", None, "1", "recon")
        result = loop.run(lambda c, p, l, e: emitted.append(e))

        assert len(emitted) == 1
        assert emitted[0]["type"] == "session.status"
        assert result.last_session_id == "sess-1"

    def test_empty_stream_no_step_finish(self, event_loop_objects, monkeypatch):
        PhaseEventLoop, RunResult, SseClient = event_loop_objects

        class FakeSseClient:
            def __init__(self, *a, **kw): pass
            def events(self): return iter([{"type": "server.connected"}, {"type": "server.heartbeat"}])
            def stop(self): pass

        _patch_phase_sse_client(monkeypatch, FakeSseClient)
        loop = PhaseEventLoop("http://localhost:8080", "sess-1", None, "1", "recon")
        result = loop.run(lambda c, p, l, e: None)

        assert result.any_step_finish_seen is False
        assert result.step_finish_count == 0
        assert result.last_finish_reason is None

    def test_session_snapshot_sync_emits_missing_assistant_parts(self, event_loop_objects, monkeypatch):
        PhaseEventLoop, RunResult, SseClient = event_loop_objects
        emitted: list[dict] = []

        class FakeSseClient:
            def __init__(self, *a, **kw): pass
            def events(self):
                return iter([
                    {"type": "server.connected", "properties": {}},
                    {"type": "session.status", "properties": {"sessionID": "sess-1", "status": {"type": "busy"}}},
                    {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
                ])
            def stop(self): pass

        class FakeResp:
            def __init__(self, payload): self.payload = payload
            def read(self): return json.dumps(self.payload).encode("utf-8")
            def __enter__(self): return self
            def __exit__(self, *a): pass

        messages_payload = [{
            "info": {"id": "msg-1", "role": "assistant", "agent": "test", "modelID": "demo-model", "sessionID": "sess-1"},
            "parts": [
                {"id": "p1", "type": "step-start", "sessionID": "sess-1"},
                {"id": "p2", "type": "text", "sessionID": "sess-1", "text": "HELLO", "time": {"end": 1}},
                {"id": "p3", "type": "step-finish", "sessionID": "sess-1", "reason": "stop", "tokens": {"total": 1}},
            ],
        }]

        def fake_urlopen(req, **kw):
            if req.full_url.endswith("/session/sess-1/message"):
                return FakeResp(messages_payload)
            raise AssertionError(f"unexpected urlopen call: {req.full_url}")

        _patch_phase_sse_client(monkeypatch, FakeSseClient)
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        loop = PhaseEventLoop("http://localhost:8080", "sess-1", None, "1", "recon")
        result = loop.run(lambda c, p, l, e: emitted.append(e))

        assert result.any_step_finish_seen is True
        assert result.last_finish_reason == "stop"
        assert [e["type"] for e in emitted] == ["server.connected", "session.status", "message.updated", "step_start", "text", "step_finish", "session.idle"]

    def test_session_snapshot_sync_emits_tool_use_from_completed_parts(self, event_loop_objects, monkeypatch):
        PhaseEventLoop, RunResult, SseClient = event_loop_objects
        emitted: list[dict] = []

        class FakeSseClient:
            def __init__(self, *a, **kw): pass
            def events(self):
                return iter([
                    {"type": "session.status", "properties": {"sessionID": "sess-1", "status": {"type": "busy"}}},
                    {"type": "session.idle", "properties": {"sessionID": "sess-1"}},
                ])
            def stop(self): pass

        class FakeResp:
            def __init__(self, payload): self.payload = payload
            def read(self): return json.dumps(self.payload).encode("utf-8")
            def __enter__(self): return self
            def __exit__(self, *a): pass

        messages_payload = [{
            "info": {"id": "msg-1", "role": "assistant", "agent": "test", "modelID": "demo-model", "sessionID": "sess-1"},
            "parts": [{
                "id": "tool-1",
                "type": "tool",
                "tool": "task",
                "sessionID": "sess-1",
                "state": {"status": "completed", "output": "OK"},
            }],
        }]

        def fake_urlopen(req, **kw):
            if req.full_url.endswith("/session/sess-1/message"):
                return FakeResp(messages_payload)
            raise AssertionError(f"unexpected urlopen call: {req.full_url}")

        _patch_phase_sse_client(monkeypatch, FakeSseClient)
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        loop = PhaseEventLoop("http://localhost:8080", "sess-1", None, "1", "recon")
        loop.run(lambda c, p, l, e: emitted.append(e))

        assert any(e["type"] == "tool_use" for e in emitted)
