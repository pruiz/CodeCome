from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from events.phase_loop import RunResult


class _FakeRuntimeConfig:
    model = "op/test"
    variant = None
    model_source = "stub"
    variant_source = "stub"
    thinking_on = False
    thinking_source = "stub"


class _FakeServerRunner:
    def start(self, **_kw):
        return _FakeServerInfo()

    def stop(self):
        pass


class _FakeServerInfo:
    base_url = "http://localhost"
    password = "fake"
    pid = 1


def _args(phase: str = "2") -> argparse.Namespace:
    return argparse.Namespace(
        phase=phase,
        label="test",
        agent="auditor",
        prompt_file="prompts/phase-2.md",
        finding=None,
        chat=False,
        show_model=False,
        debug=False,
        color="never",
        log_level="WARN",
        read_display_lines=None,
        write_content_lines=None,
        write_diff_limit=None,
        edit_diff_lines=None,
    )


def _terminal_result() -> RunResult:
    return RunResult(
        last_finish_reason="stop",
        any_step_finish_seen=True,
        step_finish_count=1,
    )


def _permission_mid_turn_result() -> RunResult:
    return RunResult(
        last_finish_reason="unknown",
        any_step_finish_seen=True,
        step_finish_count=2,
        last_permission_error="permission denied",
    )


def _plain_mid_turn_result() -> RunResult:
    return RunResult(
        last_finish_reason="unknown",
        any_step_finish_seen=True,
        step_finish_count=2,
        last_permission_error=None,
    )


def _resume_not_ready_result() -> RunResult:
    return RunResult(last_finish_reason="resume_not_ready", last_session_id="ses_test")


def test_phase_mode_does_not_reuse_previous_attempt_failures(monkeypatch):
    from codecome import harness as harness_mod
    from codecome import runner as runner_mod

    transcript = harness_mod.ROOT / "tmp" / "fake.jsonl"
    attempts = iter([
        (0, "ses_test", _plain_mid_turn_result(), transcript),
        (0, "ses_test", _permission_mid_turn_result(), transcript),
        (2, "ses_test", _resume_not_ready_result(), transcript),
    ])
    captured: list[list[str] | None] = []

    def fake_resume_prompt(*_args, failure_details=None, **_kw):
        captured.append(failure_details)
        return "resume"

    monkeypatch.setattr(harness_mod, "ServerRunner", lambda: _FakeServerRunner())
    monkeypatch.setenv("CODECOME_MAX_ITERATION_RETRIES", "3")
    monkeypatch.setattr(harness_mod, "load_prompt", lambda *_a, **_kw: "prompt")
    monkeypatch.setattr(harness_mod, "resolve_runtime_config", lambda _agent: _FakeRuntimeConfig())
    monkeypatch.setattr(harness_mod, "configure_rendering", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner_mod, "_run_single_attempt", lambda *_a, **_kw: next(attempts))
    monkeypatch.setattr(
        harness_mod,
        "check_phase_graceful_completion",
        lambda *_a, **_kw: (False, ["stale failure from previous attempt"]),
    )
    monkeypatch.setattr(harness_mod, "build_phase_resume_prompt", fake_resume_prompt)

    rc = harness_mod.run_phase_mode(_args())

    assert rc == 2
    assert captured == [["stale failure from previous attempt"], None]


def test_phase1_subphase_does_not_reuse_previous_attempt_failures(monkeypatch):
    from codecome import phase_1 as p1

    transcript = p1.ROOT / "tmp" / "fake.jsonl"
    attempts = iter([
        (0, "ses_test", _plain_mid_turn_result(), transcript),
        (0, "ses_test", _permission_mid_turn_result(), transcript),
        (2, "ses_test", _resume_not_ready_result(), transcript),
    ])
    captured: list[list[str] | None] = []

    def fake_resume_prompt(*_args, failure_details=None, **_kw):
        captured.append(failure_details)
        return "resume"

    runner = MagicMock()
    runner.info = _FakeServerInfo()

    monkeypatch.setenv("CODECOME_MAX_ITERATION_RETRIES", "3")
    monkeypatch.setattr(p1, "load_prompt", lambda *_a, **_kw: "prompt")
    monkeypatch.setattr(p1, "resolve_runtime_config", lambda _agent: _FakeRuntimeConfig())
    monkeypatch.setattr(p1, "configure_rendering", lambda *_a, **_kw: None)
    monkeypatch.setattr(p1, "_run_single_attempt", lambda *_a, **_kw: next(attempts))
    monkeypatch.setattr(
        p1,
        "check_phase_graceful_completion",
        lambda *_a, **_kw: (False, ["stale failure from previous attempt"]),
    )
    monkeypatch.setattr(p1, "build_phase_resume_prompt", fake_resume_prompt)

    rc = p1._run_subphase(
        args=_args("1b"),
        console=None,
        rendering_ctx=None,
        runner=runner,
        base_url="http://localhost",
        phase_id="1b",
        label="test",
        agent="recon",
        prompt_file="prompts/phase-1b-recon.md",
    )

    assert rc == 2
    assert captured == [["stale failure from previous attempt"], None]
