from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from events.sse_client import SseClient, SseClientError
from events.phase_loop import PhaseEventLoop


# ---------------------------------------------------------------------------
# SseClient: should_continue keeps the stream alive past the reconnect budget
# ---------------------------------------------------------------------------

def _drop_after(events_per_stream, total_streams):
    """Build a fake _open_stream that yields a stream then raises a drop."""
    streams = iter([list(events_per_stream) for _ in range(total_streams)])

    def fake_open_stream():
        try:
            stream = next(streams)
        except StopIteration:
            raise SseClientError("no more streams")
        for event in stream:
            yield event
        raise SseClientError("drop")

    return fake_open_stream


def test_reconnect_budget_exhausted_without_should_continue():
    client = SseClient("http://localhost:8080", reconnect=True, max_reconnects=2)
    client._wait_backoff = lambda: None
    client._open_stream = _drop_after([{"type": "server.heartbeat"}], total_streams=10)

    with pytest.raises(SseClientError):
        list(client.events())
    # Budget was honored: stopped at max_reconnects.
    assert client._reconnect_count == client.max_reconnects


def test_should_continue_keeps_consuming_past_budget():
    """While should_continue() is True, the budget never terminates the stream."""
    client = SseClient("http://localhost:8080", reconnect=True, max_reconnects=2)
    client._wait_backoff = lambda: None

    # Allow plenty of reconnects, then flip should_continue to False so it stops.
    calls = {"n": 0}

    def should_continue():
        calls["n"] += 1
        return calls["n"] < 6  # keep going for the first few budget checks

    client.should_continue = should_continue
    client._open_stream = _drop_after([{"type": "server.heartbeat"}], total_streams=50)

    with pytest.raises(SseClientError):
        list(client.events())

    # We must have reconnected well past the nominal budget of 2.
    assert calls["n"] >= 6


def test_should_continue_exception_is_treated_as_stop():
    client = SseClient("http://localhost:8080", reconnect=True, max_reconnects=1)
    client._wait_backoff = lambda: None

    def should_continue():
        raise RuntimeError("boom")

    client.should_continue = should_continue
    client._open_stream = _drop_after([{"type": "server.heartbeat"}], total_streams=10)

    with pytest.raises(SseClientError):
        list(client.events())


# ---------------------------------------------------------------------------
# PhaseEventLoop: _should_keep_consuming combines busy-state + liveness
# ---------------------------------------------------------------------------

def _loop(liveness_check=None):
    return PhaseEventLoop(
        "http://localhost:8080", "sess-1", None, "1", "recon",
        liveness_check=liveness_check,
    )


def test_keep_consuming_false_when_not_busy():
    loop = _loop(liveness_check=lambda: True)
    assert loop._session_busy is False
    assert loop._should_keep_consuming() is False


def test_keep_consuming_true_when_busy_and_alive():
    loop = _loop(liveness_check=lambda: True)
    loop._track_session_busy(
        {"type": "session.status", "properties": {"status": {"type": "busy"}}}
    )
    assert loop._session_busy is True
    assert loop._should_keep_consuming() is True


def test_keep_consuming_false_when_busy_but_process_dead():
    loop = _loop(liveness_check=lambda: False)
    loop._track_session_busy(
        {"type": "session.status", "properties": {"status": {"type": "busy"}}}
    )
    assert loop._should_keep_consuming() is False
    assert loop._server_unreachable is True


def test_invalid_stall_env_values_fall_back(monkeypatch):
    monkeypatch.setenv("CODECOME_BUSY_STALL_TIMEOUT", "180s")
    monkeypatch.setenv("CODECOME_HEARTBEAT_STALL_TIMEOUT", "off")

    loop = _loop(liveness_check=lambda: True)

    assert loop._stall_timeout_s == 180.0
    assert loop._heartbeat_stall_timeout_s == 0.0


def test_keep_consuming_true_when_busy_and_no_liveness_signal():
    loop = _loop(liveness_check=None)
    loop._track_session_busy(
        {"type": "session.status", "properties": {"status": {"type": "busy"}}}
    )
    assert loop._should_keep_consuming() is True


def test_idle_status_clears_busy():
    loop = _loop(liveness_check=lambda: True)
    loop._track_session_busy(
        {"type": "session.status", "properties": {"status": {"type": "busy"}}}
    )
    assert loop._session_busy is True
    loop._track_session_busy(
        {"type": "session.status", "properties": {"status": {"type": "idle"}}}
    )
    assert loop._session_busy is False
    assert loop._should_keep_consuming() is False


def test_session_idle_event_clears_busy():
    loop = _loop(liveness_check=lambda: True)
    loop._track_session_busy(
        {"type": "session.status", "properties": {"status": {"type": "busy"}}}
    )
    loop._track_session_busy({"type": "session.idle", "properties": {"sessionID": "sess-1"}})
    assert loop._session_busy is False


# ---------------------------------------------------------------------------
# Stall watchdog: bounded busy-wait
# ---------------------------------------------------------------------------

def _busy(loop):
    loop._track_session_busy(
        {"type": "session.status", "properties": {"status": {"type": "busy"}}}
    )


def test_stall_detected_stops_consuming_even_when_busy_and_alive(monkeypatch):
    monkeypatch.setenv("CODECOME_BUSY_STALL_TIMEOUT", "180")
    loop = _loop(liveness_check=lambda: True)
    _busy(loop)
    loop._fetch_session_status = lambda timeout=2.0: "busy"
    assert loop._should_keep_consuming() is True

    # Advance the monotonic clock past the stall window with no progress.
    base = loop._last_progress_at
    monkeypatch.setattr("events.phase_loop.time.monotonic", lambda: base + 181.0)

    assert loop._should_keep_consuming() is False
    assert loop._session_stalled is True


def test_status_idle_prevents_false_stall(monkeypatch):
    monkeypatch.setenv("CODECOME_BUSY_STALL_TIMEOUT", "180")
    loop = _loop(liveness_check=lambda: True)
    _busy(loop)
    loop._fetch_session_status = lambda timeout=2.0: "idle"

    base = loop._last_progress_at
    monkeypatch.setattr("events.phase_loop.time.monotonic", lambda: base + 181.0)

    assert loop._should_keep_consuming() is False
    assert loop._session_stalled is False
    assert loop._session_busy is False
    assert loop._session_idle_via_status is True


def test_status_busy_still_allows_stall(monkeypatch):
    monkeypatch.setenv("CODECOME_BUSY_STALL_TIMEOUT", "180")
    loop = _loop(liveness_check=lambda: True)
    _busy(loop)
    loop._fetch_session_status = lambda timeout=2.0: "busy"

    base = loop._last_progress_at
    monkeypatch.setattr("events.phase_loop.time.monotonic", lambda: base + 181.0)

    assert loop._should_keep_consuming() is False
    assert loop._session_stalled is True


def test_non_heartbeat_event_resets_stall_timer(monkeypatch):
    loop = _loop(liveness_check=lambda: True)
    _busy(loop)
    base = loop._last_progress_at

    # Far in the future, but a meaningful event arrives → timer resets.
    monkeypatch.setattr("events.phase_loop.time.monotonic", lambda: base + 500.0)
    loop._note_progress({"type": "message.part.updated", "properties": {}})
    assert loop._stalled() is False


def test_heartbeat_and_connected_do_not_reset_stall_timer(monkeypatch):
    loop = _loop(liveness_check=lambda: True)
    _busy(loop)
    base = loop._last_progress_at

    monkeypatch.setattr("events.phase_loop.time.monotonic", lambda: base + 500.0)
    loop._note_progress({"type": "server.heartbeat", "properties": {}})
    loop._note_progress({"type": "server.connected", "properties": {}})
    # Neither counts as progress → still stalled.
    assert loop._stalled() is True


def test_stall_timeout_zero_disables_watchdog(monkeypatch):
    monkeypatch.setenv("CODECOME_BUSY_STALL_TIMEOUT", "0")
    loop = _loop(liveness_check=lambda: True)
    _busy(loop)
    base = loop._last_progress_at
    monkeypatch.setattr("events.phase_loop.time.monotonic", lambda: base + 10_000.0)
    assert loop._stalled() is False
    assert loop._should_keep_consuming() is True


def test_runresult_carries_session_stalled_default():
    from events.phase_loop import RunResult

    assert RunResult().session_stalled is False
    assert RunResult(session_stalled=True).session_stalled is True


# ---------------------------------------------------------------------------
# Read-tick: silent-but-open stream must not block forever
# ---------------------------------------------------------------------------

def test_tick_with_should_continue_false_stops_stream(monkeypatch):
    """A None tick + should_continue()==False makes events() stop cleanly."""
    client = SseClient("http://localhost:8080", reconnect=True, max_reconnects=10)
    client.should_continue = lambda: False  # e.g. stall watchdog tripped

    # Open stream yields one event, then nothing but inactivity ticks.
    def fake_open_stream():
        yield {"type": "session.status", "properties": {"status": {"type": "busy"}}}
        while True:
            yield None  # inactivity ticks

    client._open_stream = fake_open_stream
    out = list(client.events())
    # The busy event is delivered; the stream stops at the first tick.
    assert [e["type"] for e in out] == ["session.status"]
    assert client._stopped is True


def test_tick_with_should_continue_true_keeps_reading(monkeypatch):
    """A None tick + should_continue()==True keeps consuming (no error/stop)."""
    calls = {"ticks": 0}

    def should_continue():
        calls["ticks"] += 1
        return calls["ticks"] < 3  # keep going for 2 ticks, then stop

    client = SseClient("http://localhost:8080", reconnect=True, max_reconnects=10)
    client.should_continue = should_continue

    def fake_open_stream():
        while True:
            yield None

    client._open_stream = fake_open_stream
    out = list(client.events())
    assert out == []  # only ticks, no events
    assert calls["ticks"] >= 3
    assert client._stopped is True


def test_tick_with_no_should_continue_keeps_reading_then_event(monkeypatch):
    """Chat mode (should_continue=None): ticks are ignored, events still flow."""
    client = SseClient("http://localhost:8080", reconnect=False, max_reconnects=1)
    assert client.should_continue is None

    def fake_open_stream():
        yield None  # tick (ignored in chat mode)
        yield {"type": "session.status", "properties": {"status": {"type": "idle"}}}
        # Stream ends (server closed) → with reconnect=False this raises out.
        raise SseClientError("closed")

    client._open_stream = fake_open_stream
    out = []
    with pytest.raises(SseClientError):
        for e in client.events():
            out.append(e)
    assert [e["type"] for e in out] == ["session.status"]


# ---------------------------------------------------------------------------
# Heartbeat-loss secondary stall signal
# ---------------------------------------------------------------------------

class _FakeClientHB:
    def __init__(self, since_hb):
        self._since = since_hb

    def seconds_since_heartbeat(self):
        return self._since


def test_heartbeat_loss_triggers_stall(monkeypatch):
    loop = _loop(liveness_check=lambda: True)
    _busy(loop)
    # Primary no-progress timer is fresh, but heartbeats were seen and stopped.
    monkeypatch.setenv("CODECOME_HEARTBEAT_STALL_TIMEOUT", "45")
    loop._heartbeat_stall_timeout_s = 45.0
    loop._client = _FakeClientHB(since_hb=60.0)
    assert loop._stalled() is True


def test_heartbeat_never_seen_does_not_trigger_via_heartbeat_path(monkeypatch):
    loop = _loop(liveness_check=lambda: True)
    _busy(loop)
    loop._heartbeat_stall_timeout_s = 45.0
    loop._client = _FakeClientHB(since_hb=None)  # no heartbeats ever seen
    # Primary timer fresh, heartbeat path inactive → not stalled.
    assert loop._stalled() is False


def test_heartbeat_recent_does_not_trigger(monkeypatch):
    loop = _loop(liveness_check=lambda: True)
    _busy(loop)
    loop._heartbeat_stall_timeout_s = 45.0
    loop._client = _FakeClientHB(since_hb=12.0)  # heartbeat 12s ago, healthy
    assert loop._stalled() is False


def test_heartbeat_stall_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CODECOME_HEARTBEAT_STALL_TIMEOUT", raising=False)
    loop = _loop(liveness_check=lambda: True)
    _busy(loop)
    loop._client = _FakeClientHB(since_hb=10_000.0)
    assert loop._heartbeat_stall_timeout_s == 0.0
    assert loop._stalled() is False


# ---------------------------------------------------------------------------
# SseClient heartbeat bookkeeping
# ---------------------------------------------------------------------------

def test_on_event_no_false_heartbeat_timeout_when_none_seen():
    """Without any heartbeat, _on_event must not raise a heartbeat timeout."""
    import events.sse_client as sse_mod

    client = SseClient("http://localhost:8080")
    # Pretend a long time has passed but no heartbeat was ever observed.
    client._last_heartbeat = 0.0
    client._heartbeats_seen = False
    # Should not raise (silence handled by the read-tick path instead).
    client._on_event({"type": "session.status", "properties": {"status": {"type": "busy"}}})
    assert client.seconds_since_heartbeat() is None


def test_on_event_stale_heartbeat_does_not_drop_late_event(monkeypatch):
    import events.sse_client as sse_mod

    client = SseClient("http://localhost:8080")
    monkeypatch.setattr(sse_mod.time, "time", lambda: 1000.0)
    client._on_event({"type": "server.heartbeat", "properties": {}})
    monkeypatch.setattr(sse_mod.time, "time", lambda: 1100.0)

    # A non-heartbeat event after a long heartbeat gap is still valid progress;
    # it must not be discarded by raising SseClientError.
    client._on_event({"type": "session.status", "properties": {"status": {"type": "idle"}}})
    assert client.seconds_since_heartbeat() == 100.0


def test_seconds_since_heartbeat_after_heartbeat(monkeypatch):
    import events.sse_client as sse_mod

    client = SseClient("http://localhost:8080")
    monkeypatch.setattr(sse_mod.time, "time", lambda: 1000.0)
    client._on_event({"type": "server.heartbeat", "properties": {}})
    assert client._heartbeats_seen is True
    monkeypatch.setattr(sse_mod.time, "time", lambda: 1005.0)
    assert client.seconds_since_heartbeat() == 5.0


def test_run_status_idle_final_sync_recovers_terminal_finish(monkeypatch):
    monkeypatch.setenv("CODECOME_BUSY_STALL_TIMEOUT", "1")

    now = {"value": 0.0}
    monkeypatch.setattr("events.phase_loop.time.monotonic", lambda: now["value"])

    class FakeSseClient:
        def __init__(self, *args, should_continue=None, **kwargs):
            self.should_continue = should_continue

        def events(self):
            yield {
                "type": "session.status",
                "properties": {
                    "sessionID": "sess-1",
                    "status": {"type": "busy"},
                },
            }
            now["value"] = 2.0
            if self.should_continue is not None:
                self.should_continue()
            return

        def seconds_since_heartbeat(self):
            return None

        def stop(self):
            pass

    monkeypatch.setattr("events.phase_loop.SseClient", FakeSseClient)

    loop = _loop(liveness_check=lambda: True)
    loop._fetch_session_status = lambda timeout=2.0: "idle"
    loop._fetch_session_messages = lambda: [
        {
            "info": {
                "id": "msg-1",
                "role": "assistant",
                "sessionID": "sess-1",
                "tokens": {"input": 1},
            },
            "parts": [
                {
                    "id": "finish-1",
                    "type": "step-finish",
                    "reason": "stop",
                    "tokens": {"total": 1},
                }
            ],
        }
    ]

    rendered = []
    recorded = []
    result = loop.run(
        lambda console, phase, label, event: rendered.append(event),
        record_raw_event_fn=recorded.append,
    )

    assert result.session_stalled is False
    assert result.any_step_finish_seen is True
    assert result.last_finish_reason == "stop"
    assert any(event.get("type") == "step_finish" for event in rendered)
    assert recorded[-1]["properties"]["status"]["type"] == "idle"


def test_run_dead_process_reports_server_unreachable(monkeypatch):
    class FakeSseClient:
        def __init__(self, *args, should_continue=None, **kwargs):
            self.should_continue = should_continue

        def events(self):
            yield {
                "type": "session.status",
                "properties": {
                    "sessionID": "sess-1",
                    "status": {"type": "busy"},
                },
            }
            if self.should_continue is not None:
                self.should_continue()
            return

        def seconds_since_heartbeat(self):
            return None

        def stop(self):
            pass

    monkeypatch.setattr("events.phase_loop.SseClient", FakeSseClient)

    loop = _loop(liveness_check=lambda: False)
    result = loop.run(lambda *_a: None)

    assert result.last_finish_reason == "server_unreachable"
    assert result.session_stalled is False


def test_set_stream_timeout_warns_once_when_socket_missing(monkeypatch, capsys):
    import events.sse_client as sse_mod

    monkeypatch.setattr(sse_mod, "_STREAM_TIMEOUT_WARNING_EMITTED", False)
    resp = object()

    SseClient._set_stream_timeout(resp, 1.0)
    SseClient._set_stream_timeout(resp, 1.0)

    err = capsys.readouterr().err
    assert err.count("could not set SSE read timeout") == 1
