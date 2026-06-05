from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import rendering.dispatch as rendering_dispatch
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
        "        build_mode: autobuild\n"
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


def _write_manual_plan(root: Path, build_command: str) -> None:
    plan = root / "itemdb" / "notes" / "codeql-plan.yml"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "analysis_units": [
                    {
                        "id": "native",
                        "path": "./src/native",
                        "languages": [
                            {
                                "id": "c-cpp",
                                "build_mode": "manual",
                                "build_command": build_command,
                                "packs": ["official"],
                            }
                        ],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


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

    saved_rich = rendering_dispatch.HAVE_RICH
    rendering_dispatch.HAVE_RICH = False
    rendering_dispatch.reset_rendering_context_cache()
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
        rendering_dispatch.HAVE_RICH = saved_rich
        rendering_dispatch.reset_rendering_context_cache()

    assert rc == 0
    assert len(calls) == 2
    assert calls[1][1] == "sess-1"


def test_subphase_fails_after_codeql_plan_auto_repair_retries_exhausted(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    transcript = tmp_path / "transcript.jsonl"

    def fake_run_single_attempt(*_args, **_kwargs):
        _write_invalid_plan(tmp_path)
        return 0, "sess-1", _ok_result(), transcript

    saved_rich = rendering_dispatch.HAVE_RICH
    rendering_dispatch.HAVE_RICH = False
    rendering_dispatch.reset_rendering_context_cache()
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
        rendering_dispatch.HAVE_RICH = saved_rich
        rendering_dispatch.reset_rendering_context_cache()

    assert rc == 2
    assert run_attempt.call_count == 3


def test_codeql_plan_validation_rejects_absolute_tmp_in_build_command(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    _write_manual_plan(tmp_path, "bash -c 'mkdir -p /tmp/codeql-build'")

    with patch.object(p1, "ROOT", tmp_path):
        rc, output = p1._validate_codeql_plan_for_repair()

    assert rc == 1
    assert "absolute /tmp/" in output


def test_codeql_plan_validation_rejects_shell_operators_in_build_command(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    _write_manual_plan(tmp_path, "mkdir -p out && gcc main.c -o out/app")

    with patch.object(p1, "ROOT", tmp_path):
        rc, output = p1._validate_codeql_plan_for_repair()

    assert rc == 1
    assert "shell operator" in output
    assert "helper script" in output


def test_codeql_plan_validation_rejects_multiline_and_comments_in_build_command(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    _write_manual_plan(tmp_path, "# build\nmkdir -p out\ngcc main.c -o out/app")

    with patch.object(p1, "ROOT", tmp_path):
        rc, output = p1._validate_codeql_plan_for_repair()

    assert rc == 1
    assert "multi-line" in output
    assert "shell comments" in output


def test_codeql_plan_validation_rejects_bash_c_build_command(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    _write_manual_plan(tmp_path, "bash -c 'mkdir -p out && gcc main.c -o out/app'")

    with patch.object(p1, "ROOT", tmp_path):
        rc, output = p1._validate_codeql_plan_for_repair()

    assert rc == 1
    assert "bash -c" in output


def test_codeql_plan_validation_checks_helper_from_analysis_root(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    analysis_root = tmp_path / "src" / "native"
    helper = tmp_path / "tmp" / "codeql-build.sh"
    analysis_root.mkdir(parents=True)
    helper.parent.mkdir(parents=True)
    helper.write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
    _write_manual_plan(tmp_path, "bash ../../tmp/codeql-build.sh")

    with patch.object(p1, "ROOT", tmp_path):
        rc, output = p1._validate_codeql_plan_for_repair()

    assert rc == 0, output


def test_codeql_plan_validation_rejects_missing_helper_from_analysis_root(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    (tmp_path / "src" / "native").mkdir(parents=True)
    _write_manual_plan(tmp_path, "bash tmp/codeql-build.sh")

    with patch.object(p1, "ROOT", tmp_path):
        rc, output = p1._validate_codeql_plan_for_repair()

    assert rc == 1
    assert "referenced helper script does not exist from analysis root" in output


def test_codeql_repair_loop_resumes_same_session_after_failed_rerun(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    output_dir = tmp_path / "itemdb" / "codeql"
    output_dir.mkdir(parents=True)
    (output_dir / "run-manifest.yml").write_text(
        yaml.safe_dump({"status": "soft-failed", "failures": ["Database create failed for c-cpp:\nautobuild failed"]}),
        encoding="utf-8",
    )
    _write_manual_plan(tmp_path, "make")
    config = SimpleNamespace(abs_output_dir=output_dir)
    calls: list[tuple[str | None, str | None]] = []

    def fake_subphase(**kwargs):
        calls.append((kwargs.get("existing_session_id"), kwargs.get("initial_prompt")))
        if len(calls) == 1:
            return p1._SubphaseOutcome(0, "repair-session", tmp_path / "one.jsonl")
        (output_dir / "run-manifest.yml").write_text(
            yaml.safe_dump({"status": "completed", "failures": []}),
            encoding="utf-8",
        )
        return p1._SubphaseOutcome(0, "repair-session", tmp_path / "two.jsonl")

    def fake_run_codeql(_console):
        if len(calls) == 1:
            (output_dir / "run-manifest.yml").write_text(
                yaml.safe_dump({"status": "soft-failed", "failures": ["Database create failed for c-cpp:\nmanual failed"]}),
                encoding="utf-8",
            )
        return None

    saved_rich = rendering_dispatch.HAVE_RICH
    rendering_dispatch.HAVE_RICH = False
    rendering_dispatch.reset_rendering_context_cache()
    try:
        with patch.object(p1, "ROOT", tmp_path), \
             patch("codeql.config.resolve_config", return_value=config), \
             patch.object(p1, "_run_subphase", side_effect=fake_subphase), \
             patch.object(p1, "_run_codeql", side_effect=fake_run_codeql):
            rc = p1._run_codeql_repair_if_needed(
                args=object(),
                console=None,
                rendering_ctx=None,
                runner=_runner(),
                base_url="http://127.0.0.1",
            )
    finally:
        rendering_dispatch.HAVE_RICH = saved_rich
        rendering_dispatch.reset_rendering_context_cache()

    assert rc == 0
    assert len(calls) == 2
    assert calls[0] == (None, None)
    assert calls[1][0] == "repair-session"
    assert calls[1][1] is not None
    assert "Latest CodeQL failure details" in calls[1][1]


def test_codeql_repair_loop_does_not_block_after_retries_exhausted(tmp_path: Path, monkeypatch) -> None:
    import codecome.phase_1 as p1

    output_dir = tmp_path / "itemdb" / "codeql"
    output_dir.mkdir(parents=True)
    (output_dir / "run-manifest.yml").write_text(
        yaml.safe_dump({"status": "soft-failed", "failures": ["Database create failed for c-cpp:\nautobuild failed"]}),
        encoding="utf-8",
    )
    _write_manual_plan(tmp_path, "make")
    config = SimpleNamespace(abs_output_dir=output_dir)

    def fake_subphase(**_kwargs):
        return p1._SubphaseOutcome(0, "repair-session", tmp_path / "repair.jsonl")

    def fake_run_codeql(_console):
        (output_dir / "run-manifest.yml").write_text(
            yaml.safe_dump({"status": "soft-failed", "failures": ["Database create failed for c-cpp:\nmanual failed"]}),
            encoding="utf-8",
        )
        return None

    monkeypatch.setenv("CODEQL_REPAIR_RETRIES", "1")
    saved_rich = rendering_dispatch.HAVE_RICH
    rendering_dispatch.HAVE_RICH = False
    rendering_dispatch.reset_rendering_context_cache()
    try:
        with patch.object(p1, "ROOT", tmp_path), \
             patch("codeql.config.resolve_config", return_value=config), \
             patch.object(p1, "_run_subphase", side_effect=fake_subphase), \
             patch.object(p1, "_run_codeql", side_effect=fake_run_codeql):
            rc = p1._run_codeql_repair_if_needed(
                args=object(),
                console=None,
                rendering_ctx=None,
                runner=_runner(),
                base_url="http://127.0.0.1",
            )
    finally:
        rendering_dispatch.HAVE_RICH = saved_rich
        rendering_dispatch.reset_rendering_context_cache()

    assert rc == 0


def _write_plan_with_build_mode(root: Path, build_mode: str | None, build_command: str | None = None) -> None:
    plan = root / "itemdb" / "notes" / "codeql-plan.yml"
    plan.parent.mkdir(parents=True, exist_ok=True)
    import yaml as _yaml

    data: dict = {
        "schema_version": 1,
        "analysis_units": [
            {
                "id": "native",
                "path": "./src/native",
                "languages": [
                    {"id": "c-cpp", "packs": ["official"]},
                ],
            }
        ],
    }
    if build_mode is not None:
        data["analysis_units"][0]["languages"][0]["build_mode"] = build_mode  # type: ignore[index]
    if build_command is not None:
        data["analysis_units"][0]["languages"][0]["build_command"] = build_command  # type: ignore[index]
    plan.write_text(_yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_codeql_plan_validation_rejects_unsupported_build_mode(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    _write_plan_with_build_mode(tmp_path, "none")

    with patch.object(p1, "ROOT", tmp_path):
        rc, output = p1._validate_codeql_plan_for_repair()

    assert rc == 1
    assert "unsupported build_mode" in output
    assert "'none'" in output


def test_codeql_plan_validation_rejects_missing_build_mode(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    _write_plan_with_build_mode(tmp_path, None)

    with patch.object(p1, "ROOT", tmp_path):
        rc, output = p1._validate_codeql_plan_for_repair()

    assert rc == 1
    assert "missing or invalid build_mode" in output


def test_codeql_plan_validation_rejects_manual_without_build_command(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    _write_plan_with_build_mode(tmp_path, "manual", build_command=None)

    with patch.object(p1, "ROOT", tmp_path):
        rc, output = p1._validate_codeql_plan_for_repair()

    assert rc == 1
    assert "no build_command provided" in output


def test_phase1c_accepts_no_step_finish_when_artifacts_are_fresh(tmp_path: Path) -> None:
    import codecome.phase_1 as p1

    transcript = tmp_path / "tmp" / "last-phase-1c-no-finding-attempt-1.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("", encoding="utf-8")

    args = SimpleNamespace(phase="1", finding=None, label="sandbox", debug=False)
    calls = []

    def fake_run_single_attempt(*_args, **_kwargs):
        calls.append(_kwargs)
        return 0, "session-1", RunResult(any_step_finish_seen=False), transcript

    saved_rich = rendering_dispatch.HAVE_RICH
    rendering_dispatch.HAVE_RICH = False
    rendering_dispatch.reset_rendering_context_cache()
    try:
        with patch.object(p1, "ROOT", tmp_path), \
             patch.object(p1, "load_prompt", return_value="prompt"), \
             patch.object(p1, "resolve_runtime_config", return_value=_runtime_config()), \
             patch.object(p1, "configure_rendering", return_value=None), \
             patch.object(p1, "_run_single_attempt", side_effect=fake_run_single_attempt), \
             patch.object(p1, "check_phase_graceful_completion", return_value=True), \
             patch("findings.checks_entry.run_frontmatter_validation", return_value=(0, "")):
            rc = p1._run_subphase(
                args=args,
                console=None,
                rendering_ctx=None,
                runner=_runner(),
                base_url="http://127.0.0.1",
                phase_id="1c",
                label="Sandbox",
                agent="recon",
                prompt_file="prompts/phase-1c-sandbox.md",
            )
    finally:
        rendering_dispatch.HAVE_RICH = saved_rich
        rendering_dispatch.reset_rendering_context_cache()

    assert rc == 0
    assert len(calls) == 1
