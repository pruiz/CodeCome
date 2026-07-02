from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


def _transcript(tmp_path: Path):
    from codecome.transcript import Transcript

    path = tmp_path / "resume.jsonl"
    return Transcript(path, path.open("x", encoding="utf-8", buffering=1))


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_resume_status_none_with_healthy_server_waits_until_timeout(monkeypatch, tmp_path):
    from codecome import runner as runner_mod

    transcript = _transcript(tmp_path)
    monkeypatch.setenv("CODECOME_RESUME_IDLE_TIMEOUT", "0")
    monkeypatch.setattr(runner_mod, "get_session_status", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner_mod, "is_server_healthy", lambda *_a, **_kw: True)

    with pytest.raises(runner_mod.ResumeSessionNotReady):
        runner_mod._wait_for_resume_idle(
            "http://127.0.0.1:1", "ses_test", "pw", "/workspace", transcript
        )
    transcript.close()

    event_types = [event["type"] for event in _events(transcript.path)]
    assert "codecome.resume.status_unavailable_server_healthy" in event_types
    assert "codecome.resume.server_unreachable" not in event_types


def test_resume_status_none_with_unhealthy_server_raises_unreachable(monkeypatch, tmp_path):
    from codecome import runner as runner_mod

    transcript = _transcript(tmp_path)
    monkeypatch.setenv("CODECOME_RESUME_IDLE_TIMEOUT", "120")
    monkeypatch.setenv("CODECOME_RESUME_SERVER_UNAVAILABLE_THRESHOLD", "2")
    monkeypatch.setattr(runner_mod, "get_session_status", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner_mod, "is_server_healthy", lambda *_a, **_kw: False)
    monkeypatch.setattr(runner_mod.time, "sleep", lambda *_a, **_kw: None)

    with pytest.raises(runner_mod.ResumeSessionServerUnreachable):
        runner_mod._wait_for_resume_idle(
            "http://127.0.0.1:1", "ses_test", "pw", "/workspace", transcript
        )
    transcript.close()

    event_types = [event["type"] for event in _events(transcript.path)]
    assert "codecome.resume.server_unreachable" in event_types


def test_resume_status_none_with_live_process_does_not_kill_server(monkeypatch, tmp_path):
    """A busy/blocked control plane on a live process must NOT be server death.

    Regression for the case where /session/status and /global/health both block
    during a long busy turn while the opencode process is still alive. With a
    liveness_check reporting alive, we keep waiting and eventually time out as
    resume_not_ready instead of declaring the server unreachable.
    """
    from codecome import runner as runner_mod

    transcript = _transcript(tmp_path)
    monkeypatch.setenv("CODECOME_RESUME_IDLE_TIMEOUT", "0")
    # Health endpoint also blocked/unhealthy under load, but the process is alive.
    monkeypatch.setattr(runner_mod, "get_session_status", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner_mod, "is_server_healthy", lambda *_a, **_kw: False)

    with pytest.raises(runner_mod.ResumeSessionNotReady) as excinfo:
        runner_mod._wait_for_resume_idle(
            "http://127.0.0.1:1", "ses_test", "pw", "/workspace", transcript,
            liveness_check=lambda: True,
        )
    transcript.close()

    assert not isinstance(excinfo.value, runner_mod.ResumeSessionServerUnreachable)
    event_types = [event["type"] for event in _events(transcript.path)]
    assert "codecome.resume.status_unavailable_process_alive" in event_types
    assert "codecome.resume.blocked_unknown" not in event_types
    assert "codecome.resume.server_unreachable" not in event_types


def test_resume_status_none_with_dead_process_raises_unreachable(monkeypatch, tmp_path):
    """When liveness_check reports the process exited, declare it unreachable."""
    from codecome import runner as runner_mod

    transcript = _transcript(tmp_path)
    monkeypatch.setenv("CODECOME_RESUME_IDLE_TIMEOUT", "120")
    monkeypatch.setattr(runner_mod, "get_session_status", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner_mod.time, "sleep", lambda *_a, **_kw: None)

    with pytest.raises(runner_mod.ResumeSessionServerUnreachable):
        runner_mod._wait_for_resume_idle(
            "http://127.0.0.1:1", "ses_test", "pw", "/workspace", transcript,
            liveness_check=lambda: False,
        )
    transcript.close()

    events = _events(transcript.path)
    unreachable = [e for e in events if e["type"] == "codecome.resume.server_unreachable"]
    assert unreachable
    assert unreachable[0]["properties"].get("processExited") is True


class _FakeProc:
    def __init__(self, returncode):
        self._returncode = returncode

    def poll(self):
        return self._returncode


class _FakeInfo:
    def __init__(self, returncode):
        self.proc = _FakeProc(returncode)


class _FakeRunner:
    def __init__(self, info):
        self.info = info


def test_make_liveness_check_uses_process_handle():
    from opencode.serve import make_liveness_check

    # poll() is None → process still running → alive
    assert make_liveness_check(_FakeRunner(_FakeInfo(None)))() is True
    # poll() returns an exit code → process exited → not alive
    assert make_liveness_check(_FakeRunner(_FakeInfo(-15)))() is False
    # no server info yet → not alive
    assert make_liveness_check(_FakeRunner(None))() is False


# ---------------------------------------------------------------------------
# Stall propagation: _run_subphase maps a stalled run to SESSION_STALLED
# ---------------------------------------------------------------------------

import argparse  # noqa: E402


class _FakeRuntimeConfig:
    model = "op/test"
    variant = None
    model_source = "stub"
    variant_source = "stub"
    thinking_on = False
    thinking_source = "stub"


def _stall_args(phase: str = "1b") -> argparse.Namespace:
    return argparse.Namespace(
        phase=phase, label="test", agent="recon",
        prompt_file="prompts/phase-1b-sandbox.md", finding=None,
        chat=False, show_model=False, debug=False, color="never", log_level="WARN",
        read_display_lines=None, write_content_lines=None,
        write_diff_limit=None, edit_diff_lines=None,
    )


def test_run_subphase_maps_stalled_runresult_to_session_stalled(monkeypatch):
    from codecome import phase_1 as p1
    from codecome.status import RunStatus
    from events.phase_loop import RunResult

    transcript = p1.ROOT / "tmp" / "fake.jsonl"
    stalled = RunResult(
        last_finish_reason="session_stalled",
        any_step_finish_seen=True,
        step_finish_count=3,
        session_stalled=True,
        last_session_id="ses_test",
    )

    runner = MagicMock()
    runner.info = _FakeInfo(None)
    runner.info.password = "pw"

    monkeypatch.setattr(p1, "load_prompt", lambda *_a, **_kw: "prompt")
    monkeypatch.setattr(p1, "resolve_runtime_config", lambda _agent: _FakeRuntimeConfig())
    monkeypatch.setattr(p1, "configure_rendering", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        p1, "_run_single_attempt",
        lambda *_a, **_kw: (RunStatus.OK, "ses_test", stalled, transcript),
    )

    rc = p1._run_subphase(
        args=_stall_args("1b"),
        console=None,
        rendering_ctx=None,
        runner=runner,
        base_url="http://localhost",
        phase_id="1b",
        label="test",
        agent="recon",
        prompt_file="prompts/phase-1b-sandbox.md",
    )

    assert rc == RunStatus.SESSION_STALLED
