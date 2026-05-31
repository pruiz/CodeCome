from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from events.phase_loop import RunResult


def _write_invalid_plan(root: Path) -> None:
    plan = root / "itemdb" / "notes" / "codeql-plan.yml"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(
        "schema_version: 1\n"
        "analysis_units:\n"
        "  - id: native\n"
        "    path: ./src/native\n"
        "    languages:\n"
        "      - id: c-cpp\n"
        "        packs:\n"
        "          - official\n"
        "- outdented-note\n",
        encoding="utf-8",
    )


def _write_valid_plan(root: Path) -> None:
    plan = root / "itemdb" / "notes" / "codeql-plan.yml"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(
        "schema_version: 1\n"
        "analysis_units:\n"
        "  - id: native\n"
        "    path: ./src/native\n"
        "    languages:\n"
        "      - id: c-cpp\n"
        "        packs:\n"
        "          - official\n"
        "notes:\n"
        "  - repaired\n",
        encoding="utf-8",
    )


def _runtime_config() -> SimpleNamespace:
    return SimpleNamespace(
        model="test-model",
        variant=None,
        thinking_on=False,
        model_source="test",
        variant_source="test",
        thinking_source="test",
    )


def _runner() -> SimpleNamespace:
    return SimpleNamespace(info=SimpleNamespace(password=""))


def _ok_result() -> RunResult:
    return RunResult(any_step_finish_seen=True, step_finish_count=1, last_finish_reason="stop")


def test_subphase_resumes_same_session_to_repair_invalid_codeql_plan(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    transcript = tmp_path / "transcript.jsonl"
    calls: list[tuple[str, str | None]] = []

    def fake_run_single_attempt(_args, _console, prompt, *_rest, existing_session_id=None, **_kwargs):
        calls.append((prompt, existing_session_id))
        if len(calls) == 1:
            _write_invalid_plan(tmp_path)
            return 0, "sess-1", _ok_result(), transcript
        assert existing_session_id == "sess-1"
        assert "itemdb/notes/codeql-plan.yml" in prompt
        assert "Validation errors:" in prompt
        _write_valid_plan(tmp_path)
        return 0, "sess-1", _ok_result(), transcript

    saved_rich = p1.HAVE_RICH
    p1.HAVE_RICH = False
    try:
        with patch.object(p1, "ROOT", tmp_path), \
             patch.object(p1, "load_prompt", return_value="initial prompt"), \
             patch.object(p1, "resolve_runtime_config", return_value=_runtime_config()), \
             patch.object(p1, "configure_rendering"), \
             patch.object(p1, "_run_single_attempt", side_effect=fake_run_single_attempt), \
             patch("findings.checks_entry.run_frontmatter_validation", return_value=(0, "")):
            rc = p1._run_subphase(
                args=object(),
                console=None,
                rendering_ctx=None,
                runner=_runner(),
                base_url="http://127.0.0.1",
                phase_id="1a",
                label="Target Profile",
                agent="recon",
                prompt_file="prompts/phase-1a-profile.md",
            )
    finally:
        p1.HAVE_RICH = saved_rich

    assert rc == 0
    assert len(calls) == 2
    assert calls[1][1] == "sess-1"


def test_subphase_fails_after_codeql_plan_auto_repair_retries_exhausted(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    transcript = tmp_path / "transcript.jsonl"

    def fake_run_single_attempt(*_args, **_kwargs):
        _write_invalid_plan(tmp_path)
        return 0, "sess-1", _ok_result(), transcript

    saved_rich = p1.HAVE_RICH
    p1.HAVE_RICH = False
    try:
        with patch.object(p1, "ROOT", tmp_path), \
             patch.object(p1, "load_prompt", return_value="initial prompt"), \
             patch.object(p1, "resolve_runtime_config", return_value=_runtime_config()), \
             patch.object(p1, "configure_rendering"), \
             patch.object(p1, "_run_single_attempt", side_effect=fake_run_single_attempt) as run_attempt, \
             patch("findings.checks_entry.run_frontmatter_validation", return_value=(0, "")):
            rc = p1._run_subphase(
                args=object(),
                console=None,
                rendering_ctx=None,
                runner=_runner(),
                base_url="http://127.0.0.1",
                phase_id="1-codeql-repair",
                label="CodeQL Build Repair",
                agent="recon",
                prompt_file="prompts/phase-1-codeql-repair.md",
            )
    finally:
        p1.HAVE_RICH = saved_rich

    assert rc == 2
    assert run_attempt.call_count == 3
