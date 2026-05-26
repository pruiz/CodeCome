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


class TestHasUnresolvedToolOutput:
    def _call(self, events):
        return BaseEventLoop._has_unresolved_tool_output(events)

    def test_no_tool_use_events(self):
        assert self._call([{"type": "text"}]) is False
        assert self._call([]) is False

    def test_unresolved_bash_echo_output(self):
        ev = {
            "type": "tool_use",
            "part": {
                "tool": "bash",
                "state": {
                    "output": "(no output)",
                    "status": "completed",
                    "metadata": {"exit": 0, "description": "Say hello"},
                },
            },
        }
        assert self._call([ev]) is True

    def test_resolved_echo_output(self):
        ev = {
            "type": "tool_use",
            "part": {
                "tool": "bash",
                "state": {
                    "output": "hello\n",
                    "status": "completed",
                    "metadata": {"exit": 0},
                },
            },
        }
        assert self._call([ev]) is False

    def test_failed_command_with_no_output_is_not_unresolved(self):
        ev = {
            "type": "tool_use",
            "part": {
                "tool": "bash",
                "state": {
                    "output": "(no output)",
                    "status": "completed",
                    "metadata": {"exit": 1},
                },
            },
        }
        assert self._call([ev]) is False

    def test_read_tool_with_no_output_not_unresolved(self):
        ev = {
            "type": "tool_use",
            "part": {
                "tool": "read",
                "state": {
                    "output": "(no output)",
                    "status": "completed",
                    "metadata": {"exit": 0},
                },
            },
        }
        assert self._call([ev]) is True

    def test_multiple_tool_events_one_unresolved(self):
        resolved = {
            "type": "tool_use",
            "part": {"tool": "read", "state": {"output": "file content", "metadata": {"exit": 0}}},
        }
        unresolved = {
            "type": "tool_use",
            "part": {"tool": "bash", "state": {"output": "(no output)", "metadata": {"exit": 0}}},
        }
        assert self._call([resolved, unresolved]) is True


class TestSyncSessionMessagesRetry:
    def test_retries_on_unresolved_output(self, monkeypatch):
        loop = BaseEventLoop("http://server", "session-1", console=None)

        calls = []

        def fake_fetch():
            calls.append(len(calls))
            if len(calls) == 1:
                return [{
                    "type": "tool_use",
                    "part": {
                        "tool": "bash",
                        "state": {"output": "(no output)", "metadata": {"exit": 0}},
                    },
                }]
            return [{
                "type": "tool_use",
                "part": {
                    "tool": "bash",
                    "state": {"output": "hello\n", "metadata": {"exit": 0}},
                },
            }]

        monkeypatch.setattr(loop, "_fetch_session_messages", fake_fetch)
        events = loop._sync_session_messages()

        assert len(calls) == 2
        assert len(events) == 1
        assert events[0]["part"]["state"]["output"] == "hello\n"

    def test_returns_immediately_when_no_unresolved_output(self, monkeypatch):
        loop = BaseEventLoop("http://server", "session-1", console=None)

        calls = []

        def fake_fetch():
            calls.append(len(calls))
            return [{
                "type": "tool_use",
                "part": {
                    "tool": "bash",
                    "state": {"output": "hello\n", "metadata": {"exit": 0}},
                },
            }]

        monkeypatch.setattr(loop, "_fetch_session_messages", fake_fetch)
        events = loop._sync_session_messages()

        assert len(calls) == 1
        assert events[0]["part"]["state"]["output"] == "hello\n"

    def test_exhausts_retries_and_returns_last(self, monkeypatch):
        loop = BaseEventLoop("http://server", "session-1", console=None)

        calls = []

        def fake_fetch():
            calls.append(len(calls))
            return [{
                "type": "tool_use",
                "part": {
                    "tool": "bash",
                    "state": {"output": "(no output)", "metadata": {"exit": 0}},
                },
            }]

        monkeypatch.setattr(loop, "_fetch_session_messages", fake_fetch)
        events = loop._sync_session_messages()

        assert len(calls) == 3
        assert len(events) == 1
        assert events[0]["part"]["state"]["output"] == "(no output)"
