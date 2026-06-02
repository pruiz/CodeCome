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
# Repetitive text-loop detection (ratio-based)
# ---------------------------------------------------------------------------


def _make_delta(part_id: str, delta: str, timestamp: int = 1000):
    return {
        "type": "message.part.delta",
        "properties": {"partID": part_id, "field": "text", "delta": delta},
        "timestamp": timestamp,
    }


def _make_updated(part_id: str, text: str, timestamp: int = 2000):
    return {
        "type": "message.part.updated",
        "properties": {
            "part": {
                "id": part_id,
                "type": "text",
                "text": text,
                "time": {"start": 1000, "end": 2000},
            },
            "sessionID": "session-1",
        },
        "timestamp": timestamp,
    }


def test_loop_detection_params_defaults(monkeypatch):
    """When env vars are absent, sensible defaults are returned."""
    monkeypatch.delenv("CODECOME_LOOP_MIN_DELTAS", raising=False)
    monkeypatch.delenv("CODECOME_LOOP_RATIO_WINDOW", raising=False)
    monkeypatch.delenv("CODECOME_LOOP_RATIO_THRESHOLD", raising=False)
    monkeypatch.delenv("CODECOME_LOOP_RATIO_STREAK", raising=False)
    from events.state_tracker import _loop_detection_params
    min_d, win, ratio, streak = _loop_detection_params()
    assert min_d == 200
    assert win == 500
    assert ratio == 0.10
    assert streak == 3


def test_loop_detection_params_invalid_env(monkeypatch):
    """Invalid env var values fall back to defaults."""
    monkeypatch.setenv("CODECOME_LOOP_MIN_DELTAS", "not-an-int")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_WINDOW", "abc")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_THRESHOLD", "bad")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_STREAK", "xyz")
    from events.state_tracker import _loop_detection_params
    min_d, win, ratio, streak = _loop_detection_params()
    assert min_d == 200
    assert win == 500
    assert ratio == 0.10
    assert streak == 3


def test_loop_detection_params_clamp(monkeypatch):
    """Ratio clamps to [0, 1] range; negative values clamp to 1."""
    monkeypatch.setenv("CODECOME_LOOP_RATIO_THRESHOLD", "-0.5")
    monkeypatch.setenv("CODECOME_LOOP_MIN_DELTAS", "-10")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_STREAK", "-2")
    from events.state_tracker import _loop_detection_params
    min_d, win, ratio, streak = _loop_detection_params()
    assert ratio == 0.10   # negative → fallback
    assert min_d == 1      # max(-10,1)=1
    assert streak == 1     # max(-2,1)=1


def test_state_tracker_low_ratio_triggers_warning(monkeypatch):
    """Sustained low unique-delta ratio triggers a loop_warning."""
    # Small window & threshold for fast test.
    monkeypatch.setenv("CODECOME_LOOP_MIN_DELTAS", "50")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_WINDOW", "20")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_THRESHOLD", "0.30")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_STREAK", "2")
    from events.state_tracker import StateTracker

    tracker = StateTracker()
    part_id = "part-loop"

    # Use only 3 unique deltas in a tight cycle → ratio ~ 3/20 = 0.15 < 0.30.
    # check_interval = window // 4 = 5, so checks happen at deltas 5, 10, 15, ...
    # We need 2 streaks: at check 1 (delta 55) and check 2 (delta 60).
    # Wait: min_deltas=50, window=20. First check after 50: at delta 50 % check_interval?
    # delta 50 % 5 = 0, so first check at delta 50.
    # We need two consecutive low-ratio windows → fire at the second.
    deltas = ["aaa", "bbb", "ccc"] * 25  # 75 total, ratio ~ 3/20 = 0.15
    warnings = []
    for i, d in enumerate(deltas):
        result = tracker.ingest(_make_delta(part_id, d, timestamp=1000 + i))
        if result:
            warnings.extend(result)

    assert len(warnings) == 1
    w = warnings[0]
    assert w["type"] == "text.loop_warning"
    assert w["properties"]["uniqueRatio"] < 0.30
    assert w["properties"]["windowSize"] == 20


def test_state_tracker_diverse_text_no_false_positive(monkeypatch):
    """Diverse text with high unique ratio must not trigger a warning."""
    monkeypatch.setenv("CODECOME_LOOP_MIN_DELTAS", "50")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_WINDOW", "40")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_THRESHOLD", "0.30")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_STREAK", "2")
    from events.state_tracker import StateTracker

    tracker = StateTracker()
    part_id = "part-diverse"

    # All-unique deltas — ratio stays 1.0.
    for i in range(100):
        result = tracker.ingest(
            _make_delta(part_id, f"token-{i:04d}", timestamp=1000 + i)
        )
        assert result == []


def test_state_tracker_loop_warning_emitted_only_once_per_part(monkeypatch):
    """Once a part emits a loop_warning, subsequent low-ratio windows are ignored."""
    monkeypatch.setenv("CODECOME_LOOP_MIN_DELTAS", "50")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_WINDOW", "20")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_THRESHOLD", "0.30")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_STREAK", "2")
    from events.state_tracker import StateTracker

    tracker = StateTracker()
    part_id = "part-once"

    # Generate enough low-ratio deltas to trigger, then keep going.
    deltas = ["aaa", "bbb", "ccc"] * 40  # 120 total
    warning_count = 0
    for i, d in enumerate(deltas):
        result = tracker.ingest(_make_delta(part_id, d, timestamp=1000 + i))
        if result:
            warning_count += 1
            for ev in result:
                assert ev["type"] == "text.loop_warning"

    assert warning_count == 1  # Only one warning, never re-fires.


def test_state_tracker_loop_state_cleared_on_finalize(monkeypatch):
    """Finalizing a part clears its loop detection state."""
    monkeypatch.setenv("CODECOME_LOOP_MIN_DELTAS", "50")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_WINDOW", "20")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_THRESHOLD", "0.30")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_STREAK", "2")
    from events.state_tracker import StateTracker

    tracker = StateTracker()
    part_id = "part-clear"

    # Trigger a warning.
    deltas = ["xxx", "yyy", "zzz"] * 30
    for i, d in enumerate(deltas):
        tracker.ingest(_make_delta(part_id, d, timestamp=1000 + i))

    # Finalize the part.
    tracker.ingest(_make_updated(part_id, "xxx" * 30))

    # Same part ID re-used — should start fresh, no warning without 2 streaks.
    for i in range(55):  # enough to hit min_deltas + 1 check, but only 1 streak
        result = tracker.ingest(
            _make_delta(part_id, f"fresh-{i:03d}", timestamp=3000 + i)
        )
    assert all(not r for r in [tracker.ingest(_make_delta(part_id, f"fresh-{i:03d}", timestamp=3100 + i)) for i in range(10)])


def test_state_tracker_non_text_deltas_ignored(monkeypatch):
    """Delta events for non-text fields do not participate in loop detection."""
    monkeypatch.setenv("CODECOME_LOOP_MIN_DELTAS", "50")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_WINDOW", "20")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_THRESHOLD", "0.30")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_STREAK", "2")
    from events.state_tracker import StateTracker

    tracker = StateTracker()
    part_id = "part-nontext"

    # Send 100 non-text deltas — ignored.
    for i in range(100):
        result = tracker.ingest({
            "type": "message.part.delta",
            "properties": {"partID": part_id, "field": "reasoning", "delta": "think"},
            "timestamp": 4000 + i,
        })
        assert result == []

    # Text deltas start fresh from zero.
    from events.state_tracker import _loop_detection_params
    min_d, _, _, _ = _loop_detection_params()
    # Re-import to pick up monkeypatched values.
    assert tracker._total_delta_count.get(part_id, 0) == 0


def test_state_tracker_streak_reset_on_recovery(monkeypatch):
    """When ratio recovers above threshold, the streak resets to 0."""
    monkeypatch.setenv("CODECOME_LOOP_MIN_DELTAS", "60")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_WINDOW", "20")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_THRESHOLD", "0.30")
    monkeypatch.setenv("CODECOME_LOOP_RATIO_STREAK", "4")
    from events.state_tracker import StateTracker

    tracker = StateTracker()
    part_id = "part-recovery"

    # Phase 1: low ratio for 3 checks (streak=3, not enough to fire with
    # streak=4).  With min_deltas=60 and check_interval=5, checks happen
    # at deltas 60, 65, 70.  Sending 70 deltas gives exactly 3 low-ratio
    # windows.
    deltas = ["aaa", "bbb", "ccc"] * 24  # 72 total; stop at 70
    for i, d in enumerate(deltas):
        if i >= 70:
            break
        result = tracker.ingest(_make_delta(part_id, d, timestamp=1000 + i))
        assert result == []

    assert tracker._low_ratio_streak.get(part_id, 0) >= 1

    # Phase 2: diverse deltas — flush low-ratio window, ratio recovers.
    for i in range(30):
        result = tracker.ingest(
            _make_delta(part_id, f"diversee-{i:04d}", timestamp=2000 + i)
        )
        assert result == []

    # After recovery the streak counter must be reset back to 0.
    assert tracker._low_ratio_streak.get(part_id, 0) == 0

    # Phase 3: low ratio again. Should need 4 fresh streaks to fire.
    deltas3 = ["xxx", "yyy", "zzz"] * 30  # enough to reach min_deltas+4 checks
    fired = False
    for i, d in enumerate(deltas3):
        result = tracker.ingest(_make_delta(part_id, d, timestamp=3000 + i))
        if result:
            fired = True
            assert result[0]["type"] == "text.loop_warning"
            break
    # With streak=4 and fresh start, the warning should eventually fire.
    assert fired
