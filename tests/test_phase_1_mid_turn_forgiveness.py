from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


class _FakeRuntimeConfig:
    model = "fake-model"
    variant = None
    thinking_on = False


def _mid_turn_run_result():
    from events.phase_loop import RunResult

    return RunResult(
        last_finish_reason="unknown",
        any_step_finish_seen=True,
        step_finish_count=24,
        last_permission_error=None,
    )


def test_mid_turn_cutoff_with_forgiveness_reaches_validation():
    """When graceful forgiveness grants returncode=0, the validation blocks run instead of failing."""
    from codecome.phase_1 import _run_subphase, ROOT as PHASE1_ROOT

    transcript = PHASE1_ROOT / "tmp" / "t.jsonl"

    with patch(
        "codecome.phase_1._run_single_attempt",
        return_value=(0, "ses_test", _mid_turn_run_result(), transcript),
    ), patch("codecome.config.load_prompt", return_value="# test prompt"), patch(
        "codecome.config.resolve_runtime_config", return_value=_FakeRuntimeConfig()
    ), patch(
        "codecome.phase_1.check_phase_graceful_completion", return_value=(True, [])
    ), patch(
        "findings.checks_entry.run_frontmatter_validation", return_value=(0, "")
    ), patch(
        "phases.artifact_checks.check_phase_1b_artifacts", return_value=[]
    ), patch(
        "codecome.phase_1.configure_rendering"
    ), patch(
        "rendering.dispatch.HAVE_RICH", False
    ):

        runner = MagicMock()
        runner.info = None

        rc = _run_subphase(
            args=argparse.Namespace(),
            console=None,
            rendering_ctx=None,
            runner=runner,
            base_url="http://localhost:0",
            phase_id="1b",
            label="test",
            agent="recon",
            prompt_file="prompts/phase-1c-recon.md",
        )

    # Validation blocks pass → returncode stays 0 after forgiveness + validation
    assert rc == 0


def test_mid_turn_cutoff_without_forgiveness_fails():
    """When graceful forgiveness is denied, the mid-turn retry path is entered and phase fails."""
    from codecome.phase_1 import _run_subphase, ROOT as PHASE1_ROOT

    transcript = PHASE1_ROOT / "tmp" / "t.jsonl"

    with patch(
        "codecome.phase_1._run_single_attempt",
        return_value=(0, "id", _mid_turn_run_result(), transcript),
    ), patch("codecome.config.load_prompt", return_value="# test prompt"), patch(
        "codecome.config.resolve_runtime_config", return_value=_FakeRuntimeConfig()
    ), patch(
        "codecome.phase_1.check_phase_graceful_completion", return_value=(False, ["missing artifact"])
    ), patch(
        "codecome.phase_1.configure_rendering"
    ), patch(
        "rendering.dispatch.HAVE_RICH", False
    ):

        runner = MagicMock()
        runner.info = None

        rc = _run_subphase(
            args=argparse.Namespace(),
            console=None,
            rendering_ctx=None,
            runner=runner,
            base_url="http://localhost:0",
            phase_id="1b",
            label="test",
            agent="recon",
            prompt_file="prompts/phase-1c-recon.md",
        )

    # Forgiveness denied → returncode=2 → mid-turn retry → no session ("id"→invalid) → fails
    assert rc != 0
