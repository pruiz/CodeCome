"""Integration test: CLI tunable overrides reach RenderSettings via the
full ``codecome.harness.run_phase_mode`` path."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import argparse
from unittest.mock import MagicMock

import pytest

from codecome import harness as harness_mod
from codecome import runner as runner_mod
from rendering.dispatch import _get_rendering_ctx


@pytest.mark.unit
def test_cli_tunables_propagate_to_render_settings(monkeypatch):
    """Prove that --read-display-lines (etc.) reach RenderSettings
    when run through the real run_phase_mode() harness."""
    args = argparse.Namespace()
    args.phase = "2"
    args.label = "Hypothesis"
    args.agent = "auditor"
    args.prompt_file = "prompts/phase-2.md"
    args.finding = None
    args.chat = False
    args.show_model = False
    args.debug = False
    args.color = "never"
    args.log_level = "WARN"
    args.read_display_lines = 42
    args.write_content_lines = 7
    args.write_diff_limit = 99
    args.edit_diff_lines = 3

    monkeypatch.setattr(harness_mod, "ServerRunner", lambda: _FakeServerRunner())
    monkeypatch.setattr(runner_mod, "_run_single_attempt",
                        lambda *a, **kw: (0, "ses_ok", _FakeRunResult(),
                                          harness_mod.ROOT / "tmp" / "fake.jsonl"))
    monkeypatch.setattr(harness_mod, "load_prompt", lambda *a, **kw: "Fake prompt")
    monkeypatch.setattr(harness_mod, "resolve_runtime_config",
                        lambda agent: _FakeRuntimeConfig())
    monkeypatch.setattr(harness_mod, "check_phase_graceful_completion",
                        lambda *a, **kw: True)
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MagicMock(returncode=0))

    returncode = harness_mod.run_phase_mode(args)
    assert returncode == 0

    # run_phase_mode builds console via build_console, so check the same
    # mode the harness would have used.
    from codecome.cli_render import build_console
    console = build_console(args.color)
    ctx = _get_rendering_ctx(console)
    assert ctx.settings.read_display_lines == 42
    assert ctx.settings.write_content_lines == 7
    assert ctx.settings.write_diff_limit == 99
    assert ctx.settings.edit_diff_lines == 3


# -- Lightweight stubs -------------------------------------------------------

class _FakeServerRunner:
    class info:
        pid = 1
    def start(self, **kw):
        return _FakeServerInfo()
    def stop(self):
        pass


class _FakeServerInfo:
    base_url = "http://localhost"
    password = "fake"


class _FakeRunResult:
    any_step_finish_seen = True
    step_finish_count = 1
    last_finish_reason = "stop"
    last_finish_tokens = {}
    last_permission_error = None
    last_session_id = "ses_ok"


class _FakeRuntimeConfig:
    model = "op/test"
    variant = None
    model_source = "stub"
    variant_source = "stub"
    thinking_on = True
    thinking_source = "stub"
