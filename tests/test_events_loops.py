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

    raw_events = []
    result = loop.run(render_fn, raw_events.append)

    assert isinstance(result, RunResult)
    assert result.any_step_finish_seen is True
    assert result.step_finish_count == 1
    assert result.last_finish_reason == "stop"
    assert result.last_finish_tokens == {"output": 3}
    assert rendered[-1][2]["properties"]["status"]["type"] == "idle"
    assert raw_events == events


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
    raw_events = []

    def render_fn(console, phase, label, event):
        rendered.append(event)

    loop._consumer_worker(render_fn, raw_events.append)

    assert synced in rendered
    assert any(event.get("type") == "session.status" and event.get("properties", {}).get("status", {}).get("type") == "idle" for event in rendered)
    assert loop.get_state(timeout=0.1)[0] == ChatState.BUSY
    assert loop.get_state(timeout=0.1)[0] == ChatState.IDLE
    assert raw_events == events


def test_finish_reason_unknown_is_mid_turn():
    """The 'unknown' finish reason must be classified as mid-turn so that
    interrupted phases offer a retry/resume path rather than failing hard."""
    from rendering.events import _FINISH_MID_TURN, _FINISH_TERMINAL_OK
    assert "unknown" in _FINISH_MID_TURN, f"'unknown' not in {_FINISH_MID_TURN}"
    assert "unknown" not in _FINISH_TERMINAL_OK


# ---------------------------------------------------------------------------
# Repetitive text-loop detection
# ---------------------------------------------------------------------------

def test_state_tracker_loop_detection_triggers_warning_at_threshold(monkeypatch):
    """When the same text delta repeats more than ``threshold`` times, a
    loop_warning event is emitted (warning fires at count > threshold, i.e.
    on the (threshold+1)-th occurrence)."""
    monkeypatch.setenv("CODECOME_LOOP_THRESHOLD", "3")
    monkeypatch.setenv("CODECOME_LOOP_WINDOW", "10")
    from events.state_tracker import StateTracker, _loop_detection_params
    assert _loop_detection_params() == (10, 3)

    tracker = StateTracker()
    part_id = "part-1"

    # With threshold=3, warning fires when count > 3 (4th occurrence).
    for i in range(3):
        result = tracker.ingest({
            "type": "message.part.delta",
            "properties": {"partID": part_id, "field": "text", "delta": "abc"},
            "timestamp": 1000 + i,
        })
        assert result == [], f"repeat {i+1}: expected no warning, got {result}"

    result = tracker.ingest({
        "type": "message.part.delta",
        "properties": {"partID": part_id, "field": "text", "delta": "abc"},
        "timestamp": 1004,
    })
    assert len(result) == 1
    assert result[0]["type"] == "text.loop_warning"
    assert result[0]["properties"]["repeatedText"] == "abc"
    assert result[0]["properties"]["count"] == 4


def test_state_tracker_loop_warning_emitted_only_once_per_part(monkeypatch):
    """Once a part emits a loop_warning, subsequent repeats do not re-trigger it."""
    monkeypatch.setenv("CODECOME_LOOP_THRESHOLD", "2")
    monkeypatch.setenv("CODECOME_LOOP_WINDOW", "10")
    from events.state_tracker import StateTracker

    tracker = StateTracker()
    part_id = "part-2"

    # With threshold=2, warning fires when count > 2 (3rd occurrence).
    for i in range(5):
        result = tracker.ingest({
            "type": "message.part.delta",
            "properties": {"partID": part_id, "field": "text", "delta": "xyz"},
            "timestamp": 2000 + i,
        })
        if i == 2:
            assert len(result) == 1 and result[0]["type"] == "text.loop_warning"
        else:
            assert result == []


def test_state_tracker_loop_state_cleared_on_finalize(monkeypatch):
    """Finalizing a part (message.part.updated) clears its loop detection state."""
    monkeypatch.setenv("CODECOME_LOOP_THRESHOLD", "2")
    monkeypatch.setenv("CODECOME_LOOP_WINDOW", "10")
    from events.state_tracker import StateTracker

    tracker = StateTracker()
    part_id = "part-3"

    # With threshold=2, warning fires on 3rd occurrence.
    for i in range(3):
        tracker.ingest({
            "type": "message.part.delta",
            "properties": {"partID": part_id, "field": "text", "delta": "loop"},
            "timestamp": 3000 + i,
        })

    tracker.ingest({
        "type": "message.part.updated",
        "properties": {
            "part": {
                "id": part_id,
                "type": "text",
                "text": "looplooploop",
                "time": {"start": 3000, "end": 3010},
            },
            "sessionID": "session-1",
        },
        "timestamp": 3011,
    })

    # After finalize, state is cleared — fresh tracker for this part.
    result = tracker.ingest({
        "type": "message.part.delta",
        "properties": {"partID": part_id, "field": "text", "delta": "loop"},
        "timestamp": 4000,
    })
    assert result == []  # only 1 repeat, below threshold=2


def test_state_tracker_non_text_deltas_ignored(monkeypatch):
    """Delta events for non-text fields do not participate in loop detection."""
    monkeypatch.setenv("CODECOME_LOOP_THRESHOLD", "2")
    monkeypatch.setenv("CODECOME_LOOP_WINDOW", "10")
    from events.state_tracker import StateTracker

    tracker = StateTracker()
    part_id = "part-4"

    # Send 3 repeats of a "reasoning" field delta — none should count.
    for i in range(3):
        result = tracker.ingest({
            "type": "message.part.delta",
            "properties": {"partID": part_id, "field": "reasoning", "delta": "thinking"},
            "timestamp": 4000 + i,
        })
        assert result == []

    # Now send one text delta — only 1 repeat, threshold=2 → no warning.
    result = tracker.ingest({
        "type": "message.part.delta",
        "properties": {"partID": part_id, "field": "text", "delta": "abc"},
        "timestamp": 4010,
    })
    assert result == []


def test_loop_detection_params_defaults(monkeypatch):
    """When env vars are absent, sensible defaults are returned."""
    monkeypatch.delenv("CODECOME_LOOP_WINDOW", raising=False)
    monkeypatch.delenv("CODECOME_LOOP_THRESHOLD", raising=False)
    from events.state_tracker import _loop_detection_params
    w, t = _loop_detection_params()
    assert w == 50
    assert t == 20


def test_loop_detection_params_invalid_env(monkeypatch):
    """Invalid env var values fall back to defaults; negative values clamp to 1."""
    monkeypatch.setenv("CODECOME_LOOP_WINDOW", "not-an-int")
    monkeypatch.setenv("CODECOME_LOOP_THRESHOLD", "-5")
    from events.state_tracker import _loop_detection_params
    w, t = _loop_detection_params()
    assert w == 50       # "not-an-int" → ValueError → default 50
    assert t == 1        # "-5" → int(-5) → max(-5,1)=1
