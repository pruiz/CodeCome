import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from events.base import BaseEventLoop
from events.chat_loop import ChatEventLoop, ChatState
from events.phase_loop import PhaseEventLoop, RunResult


def test_base_event_loop_session_filter_and_idle_detection():
    loop = BaseEventLoop("http://server", "session-1", console=None)

    assert loop._belongs_to_session({"properties": {"sessionID": "session-1"}})
    assert not loop._belongs_to_session({"properties": {"sessionID": "other"}})
    assert loop._belongs_to_session({"properties": {}})

    assert loop._is_session_idle({"type": "session.idle"})
    assert loop._is_session_idle({"type": "session.status", "properties": {"status": {"type": "idle"}}})
    assert not loop._is_session_idle({"type": "session.status", "properties": {"status": {"type": "busy"}}})


def test_base_event_loop_headers_include_auth_and_workspace():
    loop = BaseEventLoop(
        "http://server",
        "session-1",
        console=None,
        auth_token="secret",
        workspace_dir="/tmp/workspace",
    )

    headers = loop._get_headers()

    assert headers["Content-Type"] == "application/json"
    assert headers["Authorization"].startswith("Basic ")
    assert headers["x-opencode-directory"] == "/tmp/workspace"


def test_phase_event_loop_returns_result_on_idle(monkeypatch):
    events = [
        {"type": "session.status", "properties": {"sessionID": "session-1", "status": {"type": "busy"}}},
        {"type": "step_finish", "part": {"id": "finish-1", "reason": "stop", "tokens": {"output": 3}}},
        {"type": "session.status", "properties": {"sessionID": "session-1", "status": {"type": "idle"}}},
    ]

    class FakeSseClient:
        def __init__(self, *args, **kwargs):
            pass

        def events(self):
            yield from events

        def stop(self):
            pass

    monkeypatch.setattr("events.phase_loop.SseClient", FakeSseClient)
    loop = PhaseEventLoop("http://server", "session-1", console=None, phase="1", label="Recon")
    monkeypatch.setattr(loop, "_sync_session_messages", lambda: [])

    rendered = []

    def render_fn(console, phase, label, event):
        rendered.append((phase, label, event))

    result = loop.run(render_fn)

    assert isinstance(result, RunResult)
    assert result.any_step_finish_seen is True
    assert result.step_finish_count == 1
    assert result.last_finish_reason == "stop"
    assert result.last_finish_tokens == {"output": 3}
    assert rendered[-1][2]["properties"]["status"]["type"] == "idle"


def test_chat_event_loop_recovery_sync_emits_synced_events(monkeypatch):
    events = [
        {"type": "session.status", "properties": {"sessionID": "session-1", "status": {"type": "busy"}}},
        {"type": "session.status", "properties": {"sessionID": "session-1", "status": {"type": "idle"}}},
    ]

    class FakeSseClient:
        def __init__(self, *args, **kwargs):
            self.on_reconnect = kwargs.get("on_reconnect")

        def events(self):
            if self.on_reconnect:
                self.on_reconnect()
            yield from events

        def stop(self):
            pass

    monkeypatch.setattr("events.chat_loop.SseClient", FakeSseClient)
    loop = ChatEventLoop("http://server", "session-1", console=None)
    synced = {"type": "text", "part": {"id": "synced-text"}, "content": "missed"}
    monkeypatch.setattr(loop, "_sync_session_messages", lambda: [synced])

    rendered = []

    def render_fn(console, phase, label, event):
        rendered.append(event)

    loop._consumer_worker(render_fn)

    assert synced in rendered
    assert any(event.get("type") == "session.status" and event.get("properties", {}).get("status", {}).get("type") == "idle" for event in rendered)
    assert loop.get_state(timeout=0.1)[0] == ChatState.BUSY
    assert loop.get_state(timeout=0.1)[0] == ChatState.IDLE
