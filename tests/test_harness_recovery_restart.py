from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from events.phase_loop import RunResult


class _FakeRuntimeConfig:
    model = "op/test"
    variant = None
    model_source = "stub"
    variant_source = "stub"
    thinking_on = False
    thinking_source = "stub"


class _FakeServerInfo:
    base_url = "http://localhost"
    password = "fake"
    pid = 1


class _FakeServerRunner:
    def __init__(self):
        self.start_calls = 0
        self.restart_calls = 0

    def start(self, **_kw):
        self.start_calls += 1
        return _FakeServerInfo()

    def restart(self, **_kw):
        self.restart_calls += 1
        return _FakeServerInfo()

    def stop(self):
        pass

    @property
    def info(self):
        return _FakeServerInfo()


def _args(phase: str = "2") -> argparse.Namespace:
    return argparse.Namespace(
        phase=phase, label="test", agent="auditor",
        prompt_file="prompts/phase-2.md", finding=None, chat=False,
        show_model=False, debug=False, color="never", log_level="WARN",
        read_display_lines=None, write_content_lines=None,
        write_diff_limit=None, edit_diff_lines=None,
    )


def _server_unreachable_result() -> RunResult:
    return RunResult(last_finish_reason="server_unreachable", last_session_id="ses_x")


def _stalled_result() -> RunResult:
    return RunResult(
        last_finish_reason="session_stalled",
        any_step_finish_seen=True,
        step_finish_count=2,
        session_stalled=True,
        last_session_id="ses_x",
    )


def _terminal_ok_result() -> RunResult:
    return RunResult(last_finish_reason="stop", any_step_finish_seen=True, step_finish_count=1)


def _wire(monkeypatch, fake_runner, attempts):
    from codecome import harness as harness_mod
    from codecome import runner as runner_mod

    it = iter(attempts)
    monkeypatch.setattr(harness_mod, "ServerRunner", lambda: fake_runner)
    monkeypatch.setattr(harness_mod, "load_prompt", lambda *_a, **_kw: "prompt")
    monkeypatch.setattr(harness_mod, "resolve_runtime_config", lambda _agent: _FakeRuntimeConfig())
    monkeypatch.setattr(harness_mod, "configure_rendering", lambda *_a, **_kw: None)
    monkeypatch.setattr(harness_mod, "check_phase_graceful_completion", lambda *_a, **_kw: (True, []))
    monkeypatch.setattr(runner_mod, "_run_single_attempt", lambda *_a, **_kw: next(it))
    import subprocess
    from unittest.mock import MagicMock
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_kw: MagicMock(returncode=0))
    return harness_mod


def _t(harness_mod):
    return harness_mod.ROOT / "tmp" / "fake.jsonl"


def test_server_unreachable_triggers_restart_then_succeeds(monkeypatch):
    fake = _FakeServerRunner()
    from codecome import harness as harness_mod
    transcript = _t(harness_mod)
    harness_mod = _wire(monkeypatch, fake, [
        (2, "ses_x", _server_unreachable_result(), transcript),
        (0, "ses_x", _terminal_ok_result(), transcript),
    ])
    monkeypatch.setattr(harness_mod, "run_frontmatter_validation", lambda *_a, **_kw: (0, ""), raising=False)

    rc = harness_mod.run_phase_mode(_args())
    assert rc == 0
    assert fake.restart_calls == 1


def test_session_stalled_triggers_restart_then_succeeds(monkeypatch):
    fake = _FakeServerRunner()
    from codecome import harness as harness_mod
    transcript = _t(harness_mod)
    harness_mod = _wire(monkeypatch, fake, [
        (0, "ses_x", _stalled_result(), transcript),
        (0, "ses_x", _terminal_ok_result(), transcript),
    ])
    monkeypatch.setattr(harness_mod, "run_frontmatter_validation", lambda *_a, **_kw: (0, ""), raising=False)

    rc = harness_mod.run_phase_mode(_args())
    assert rc == 0
    assert fake.restart_calls == 1


def test_recovery_shares_budget_and_exhausts(monkeypatch):
    fake = _FakeServerRunner()
    from codecome import harness as harness_mod
    transcript = _t(harness_mod)
    monkeypatch.setenv("CODECOME_MAX_SERVER_RESTARTS", "2")
    # One stall + two unreachable = 3 recoverable conditions, budget is 2.
    harness_mod = _wire(monkeypatch, fake, [
        (0, "ses_x", _stalled_result(), transcript),
        (2, "ses_x", _server_unreachable_result(), transcript),
        (2, "ses_x", _server_unreachable_result(), transcript),
    ])

    rc = harness_mod.run_phase_mode(_args())
    # Budget exhausted after 2 restarts → non-zero terminal status.
    assert rc != 0
    assert fake.restart_calls == 2


def test_session_stalled_budget_exhaustion_is_non_success(monkeypatch):
    fake = _FakeServerRunner()
    from codecome import harness as harness_mod
    transcript = _t(harness_mod)
    monkeypatch.setenv("CODECOME_MAX_SERVER_RESTARTS", "0")
    harness_mod = _wire(monkeypatch, fake, [
        (0, "ses_x", _stalled_result(), transcript),
    ])

    rc = harness_mod.run_phase_mode(_args())

    assert rc != 0
    assert fake.restart_calls == 0
