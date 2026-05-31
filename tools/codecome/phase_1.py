# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Phase 1 subphase orchestration.

Runs Phase 1 as three subphases (1a / 1b / 1c) with gates and CodeQL
analysis between 1a and 1b.  The opencode server is started once and
reused across all three subphase sessions.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opencode.serve import ServerRunner, ServerRunnerError

from codecome.console import build_console, _emit_fatal_error
from codecome.config import ROOT, resolve_color_mode, load_prompt, resolve_runtime_config
from codecome.runner import _run_single_attempt
from phases.phase_1_gates import (
    check_phase_1a,
    check_phase_1b,
    check_phase_1c,
    count_findings_snapshot,
)
from rendering.dispatch import HAVE_RICH, _get_rendering_ctx, configure_rendering, render_event
from rendering.events import (
    _FINISH_TERMINAL_OK,
    _FINISH_MID_TURN,
    _FINISH_FAILURE,
    _reset_subagent_state,
)
from phases.completion import (
    check_phase_graceful_completion,
    build_phase_resume_prompt,
    build_frontmatter_resume_prompt,
    build_codeql_plan_resume_prompt,
    build_codeql_build_failure_resume_prompt,
)


@dataclass(frozen=True)
class _SubphaseOutcome:
    returncode: int
    session_id: str
    transcript_path: Path
# ---------------------------------------------------------------------------
# CodeQL analysis (between 1a gate and 1b)
# ---------------------------------------------------------------------------

def _run_codeql(console: Any) -> int:
    """Run full CodeQL pipeline and report results."""
    from codeql.config import resolve_config as _resolve_codeql_config

    config = _resolve_codeql_config()

    if HAVE_RICH:
        from rich.rule import Rule
        from rich.text import Text
        console.print(Rule(title="CodeQL", style="cyan"))
    else:
        import _colors as C
        print(C.header("CodeQL"))

    if not config.enabled:
        msg = "CodeQL disabled — skipping."
        from codeql.pipeline import record_skipped_run
        record_skipped_run(config, "CodeQL disabled for Phase 1")
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text(msg, style="yellow"))
        else:
            import _colors as C
            print(C.warn(msg))
        return 0

    if not config.phase_1_enabled:
        msg = "CodeQL phase 1 disabled — skipping."
        from codeql.pipeline import record_skipped_run
        record_skipped_run(config, "CodeQL phase 1 disabled")
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text(msg, style="yellow"))
        else:
            import _colors as C
            print(C.warn(msg))
        return 0

    if HAVE_RICH:
        from rich.text import Text
        console.print(Text("Running CodeQL analysis…", style="dim"))
    else:
        print("Running CodeQL analysis…")

    from codeql.pipeline import run_full_pipeline

    def progress(message: str) -> None:
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text(message, style="dim"))
        else:
            print(message, flush=True)

    try:
        manifest = run_full_pipeline(config, progress=progress)
    except Exception as exc:
        msg = f"CodeQL: FAILED — {exc}"
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text(msg, style="bold red"))
        else:
            import _colors as C
            print(C.fail(msg))
        if config.fail_policy == "hard":
            return 1
        return 0

    status = manifest["status"]
    warnings = manifest.get("warnings", [])
    failures = manifest.get("failures", [])

    if status == "completed":
        msg = f"CodeQL: analysis completed ({len(manifest.get('languages', []))} language(s))"
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text(msg, style="green"))
        else:
            import _colors as C
            print(C.ok(msg))
    elif status == "skipped":
        reason = failures[0] if failures else "no plan"
        msg = f"CodeQL: skipped — {reason}"
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text(msg, style="yellow"))
        else:
            import _colors as C
            print(C.warn(msg))
    elif status == "soft-failed":
        msg = "CodeQL: soft-failed — continuing"
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text(msg, style="yellow"))
        else:
            import _colors as C
            print(C.warn(msg))
        for w in warnings + failures:
            if HAVE_RICH:
                console.print(Text(f"  {w}", style="yellow"))
            else:
                print(C.warn(f"  {w}"))
    elif status == "failed":
        msg = "CodeQL: FAILED"
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text(msg, style="bold red"))
        else:
            import _colors as C
            print(C.fail(msg))
        for f in failures:
            if HAVE_RICH:
                console.print(Text(f"  {f}", style="red"))
            else:
                print(C.fail(f"  {f}"))
        if config.fail_policy == "hard":
            return 1

    return 0


def _check_codeql_artifacts(console: Any) -> int:
    """Validate CodeQL artifacts; block 1b only on hard fail policy."""
    from codeql.config import resolve_config as _resolve_codeql_config
    from codeql.artifacts import check_artifacts

    config = _resolve_codeql_config()

    if not config.enabled or not config.phase_1_enabled:
        return 0

    status, warnings = check_artifacts(config.abs_output_dir)

    for w in warnings:
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text(f"  WARN: {w}", style="yellow"))
        else:
            import _colors as C
            print(C.warn(f"  WARN: {w}"))

    if config.fail_policy == "hard" and status == "failed":
        msg = "CodeQL artifact gate: FAILED — blocking Phase 1b"
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text(msg, style="bold red"))
        else:
            import _colors as C
            print(C.fail(msg))
        return 1

    if status == "failed" and config.fail_policy == "hard":
        msg = "CodeQL artifact gate: FAILED — execution crashed, blocking Phase 1b"
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text(msg, style="bold red"))
        else:
            import _colors as C
            print(C.fail(msg))
        return 1

    if status == "failed":
        # fail_policy is soft, so treat as a non-blocking warning
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text("CodeQL artifact gate: execution crashed but fail_policy is soft — continuing", style="yellow"))
        else:
            import _colors as C
            print(C.warn("CodeQL artifact gate: execution crashed but fail_policy is soft — continuing"))

    label = f"CodeQL artifact gate: {status}"
    if HAVE_RICH:
        from rich.text import Text
        style = "green" if status == "completed" else "yellow"
        console.print(Text(label, style=style))
    else:
        import _colors as C
        if status == "completed":
            print(C.ok(label))
        else:
            print(C.info(label))

    return 0


def _load_codeql_yaml(path: Path) -> dict[str, Any]:
    """Load a CodeQL YAML artifact as a mapping, returning {} on absence/errors."""
    if not path.is_file():
        return {}
    try:
        from codeql.packs import load_yaml_mapping

        return load_yaml_mapping(path, what=path.name)
    except Exception:
        return {}


def _validate_codeql_plan_for_repair() -> tuple[int, str]:
    """Validate the generated CodeQL plan, returning CLI-style (rc, output)."""
    plan_path = ROOT / "itemdb" / "notes" / "codeql-plan.yml"
    if not plan_path.exists():
        return 0, ""

    try:
        from codeql.packs import load_codeql_plan

        plan = load_codeql_plan(plan_path)
    except Exception as exc:
        return 1, f"itemdb/notes/codeql-plan.yml is invalid: {exc}"

    errors: list[str] = []
    for unit in plan.get("analysis_units", []):
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get("id", "<unknown>"))
        unit_path = unit.get("path")
        analysis_root = ROOT / unit_path if isinstance(unit_path, str) else ROOT
        languages = unit.get("languages", [])
        if not isinstance(languages, list):
            continue
        for language in languages:
            if not isinstance(language, dict):
                continue
            language_id = str(language.get("id", "<unknown>"))
            build_command = language.get("build_command")
            if not isinstance(build_command, str) or not build_command.strip():
                continue
            context = f"analysis unit {unit_id!r} language {language_id!r}"
            errors.extend(_validate_codeql_build_command(build_command, analysis_root, context))

    if errors:
        return 1, "itemdb/notes/codeql-plan.yml failed CodeQL build-command validation:\n" + "\n".join(
            f"- {error}" for error in errors
        )

    return 0, ""


def _validate_codeql_build_command(build_command: str, analysis_root: Path, context: str) -> list[str]:
    """Return generic portability/safety validation errors for a manual build command."""
    errors: list[str] = []
    if _contains_absolute_tmp(build_command):
        errors.append(f"{context}: build_command uses absolute /tmp/; use workspace-relative tmp/ instead")
    if str(ROOT) in build_command:
        errors.append(f"{context}: build_command embeds the absolute workspace path {ROOT}")

    try:
        tokens = shlex.split(build_command)
    except ValueError as exc:
        return errors + [f"{context}: build_command is not shell-parseable: {exc}"]

    for token in tokens:
        if not token.endswith(".sh"):
            continue
        script_path = Path(token)
        if not script_path.is_absolute():
            script_path = analysis_root / script_path
        if not script_path.is_file():
            errors.append(f"{context}: referenced helper script does not exist from analysis root: {token}")
            continue
        try:
            content = script_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{context}: referenced helper script cannot be read: {token}: {exc}")
            continue
        if _contains_absolute_tmp(content):
            errors.append(f"{context}: referenced helper script {token} uses absolute /tmp/; use workspace-relative tmp/")
        if str(ROOT) in content:
            errors.append(f"{context}: referenced helper script {token} embeds the absolute workspace path {ROOT}")
        result = subprocess.run(["bash", "-n", str(script_path)], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            suffix = f": {detail}" if detail else ""
            errors.append(f"{context}: referenced helper script {token} failed bash -n{suffix}")

    return errors


def _contains_absolute_tmp(text: str) -> bool:
    """Return whether text contains an absolute /tmp path, not a relative tmp/ component."""
    return re.search(r"(^|[\s\"'=])/(tmp)(/|$)", text) is not None


def _subphase_should_validate_codeql_plan(phase_id: str) -> bool:
    """Return whether a subphase is responsible for producing/editing codeql-plan.yml."""
    return phase_id in {"1a", "1-codeql-repair"}


def _codeql_repair_needed(output_dir: Path, plan_path: Path) -> bool:
    """Return whether a failed CodeQL run should get one model repair attempt."""
    manifest = _load_codeql_yaml(output_dir / "run-manifest.yml")
    status = manifest.get("status")
    if status not in {"soft-failed", "failed"}:
        return False

    failures = manifest.get("failures", [])
    if not isinstance(failures, list):
        return False
    if not any("Database create failed" in str(failure) for failure in failures):
        return False

    plan = _load_codeql_yaml(plan_path)
    for unit in plan.get("analysis_units", []) if isinstance(plan.get("analysis_units"), list) else []:
        languages = unit.get("languages", []) if isinstance(unit, dict) else []
        if not isinstance(languages, list):
            continue
        for language in languages:
            if isinstance(language, dict) and language.get("build_mode") in {"autobuild", "manual"}:
                return True
    return False


def _latest_codeql_database_log(output_dir: Path) -> Path | None:
    logs = [p for p in output_dir.glob("databases/**/log/database-create-*.log") if p.is_file()]
    if not logs:
        return None
    return max(logs, key=lambda p: p.stat().st_mtime)


def _codeql_repair_failure_context(output_dir: Path) -> str:
    """Return target-agnostic failure context for the repair model."""
    lines: list[str] = []
    manifest = _load_codeql_yaml(output_dir / "run-manifest.yml")
    failures = manifest.get("failures", [])
    if isinstance(failures, list) and failures:
        lines.append("Manifest failures:")
        lines.extend(str(failure) for failure in failures[-3:])

    latest_log = _latest_codeql_database_log(output_dir)
    if latest_log is not None:
        interesting: list[str] = []
        try:
            for line in latest_log.read_text(encoding="utf-8", errors="replace").splitlines():
                if any(marker in line for marker in ("[build-stderr]", "[build-stdout]", "[ERROR]", "Exception caught", "A fatal error")):
                    interesting.append(line)
        except OSError as exc:
            interesting.append(f"Failed to read latest database log {latest_log}: {exc}")
        if interesting:
            lines.append(f"Latest database-create log: {latest_log.relative_to(ROOT) if latest_log.is_relative_to(ROOT) else latest_log}")
            lines.extend(interesting[-40:])

    return "\n".join(lines) if lines else "CodeQL database creation failed; no additional log details were available."


def _file_digest(path: Path) -> str | None:
    """Return a stable digest for a file, or None when it cannot be read."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _run_codeql_repair_if_needed(
    *,
    args: Any,
    console: Any,
    rendering_ctx: Any,
    runner: ServerRunner,
    base_url: str,
) -> int:
    """Ask the model to repair CodeQL build instructions and rerun CodeQL until stable."""
    from codeql.config import resolve_config as _resolve_codeql_config

    max_retries = int(os.environ.get("CODEQL_REPAIR_RETRIES", "2"))
    if max_retries <= 0:
        return 0

    config = _resolve_codeql_config()
    plan_path = ROOT / "itemdb" / "notes" / "codeql-plan.yml"
    if not _codeql_repair_needed(config.abs_output_dir, plan_path):
        return 0

    msg = "CodeQL database creation failed; asking the model to repair build instructions."
    if HAVE_RICH:
        from rich.text import Text
        console.print(Text(msg, style="bold yellow"))
    else:
        import _colors as C
        print(C.warn(msg))

    plan_digest = _file_digest(plan_path)
    repair_session_id: str | None = None
    repair_prompt: str | None = None
    for attempt in range(1, max_retries + 1):
        outcome = _run_subphase(
            args=args,
            console=console,
            rendering_ctx=rendering_ctx,
            runner=runner,
            base_url=base_url,
            phase_id="1-codeql-repair",
            label=f"CodeQL Build Repair ({attempt}/{max_retries})",
            agent="recon",
            prompt_file="prompts/phase-1-codeql-repair.md",
            existing_session_id=repair_session_id,
            initial_prompt=repair_prompt,
            return_outcome=True,
        )
        assert isinstance(outcome, _SubphaseOutcome)
        repair_session_id = outcome.session_id or repair_session_id
        if outcome.returncode != 0:
            continue
        next_plan_digest = _file_digest(plan_path)
        if next_plan_digest == plan_digest:
            unchanged_msg = "CodeQL repair completed but did not change itemdb/notes/codeql-plan.yml."
            if HAVE_RICH:
                from rich.text import Text
                console.print(Text(unchanged_msg, style="yellow"))
            else:
                import _colors as C
                print(C.warn(unchanged_msg))
        plan_digest = next_plan_digest

        rc = _run_codeql(console)
        if rc != 0:
            return rc
        if not _codeql_repair_needed(config.abs_output_dir, plan_path):
            return 0

        repair_prompt = build_codeql_build_failure_resume_prompt(
            _codeql_repair_failure_context(config.abs_output_dir)
        )

    if _codeql_repair_needed(config.abs_output_dir, plan_path):
        msg = f"CodeQL database creation still fails after {max_retries} repair attempt(s); blocking Phase 1b."
        if HAVE_RICH:
            from rich.text import Text
            console.print(Text(msg, style="bold red"))
        else:
            import _colors as C
            print(C.fail(msg))
        return 1

    return 0


# ---------------------------------------------------------------------------
# Subphase runner
# ---------------------------------------------------------------------------

def _run_subphase(
    *,
    args: Any,
    console: Any,
    rendering_ctx: Any,
    runner: ServerRunner,
    base_url: str,
    phase_id: str,
    label: str,
    agent: str,
    prompt_file: str,
    finding: str | None = None,
    existing_session_id: str | None = None,
    initial_prompt: str | None = None,
    return_outcome: bool = False,
) -> int | _SubphaseOutcome:
    """Run a single subphase agent session with retry/resume."""
    prompt_path = ROOT / prompt_file
    prompt = initial_prompt if initial_prompt is not None else load_prompt(prompt_path, finding, phase=phase_id)
    rc = resolve_runtime_config(agent)
    model = rc.model
    variant = rc.variant
    thinking_on = rc.thinking_on
    configure_rendering(console, render_reasoning=thinking_on)

    model_label = model or "(unknown)"
    variant_label = variant or "(unknown)"

    parts = [f"agent={agent}", f"model={model_label}"]
    if variant is not None:
        parts.append(f"variant={variant_label}")
    parts.append(f"thinking={'on' if thinking_on else 'off'}")
    parts.append(f"prompt={prompt_file}")

    if variant is not None:
        sources_tail = (
            f"(model source: {rc.model_source}, variant source: {rc.variant_source}, "
            f"thinking source: {rc.thinking_source})"
        )
    else:
        sources_tail = f"(model source: {rc.model_source}, thinking source: {rc.thinking_source})"

    main_line = "  ".join(parts) + "  " + sources_tail

    if HAVE_RICH:
        from rich.rule import Rule
        from rich.text import Text
        console.print(Rule(title=f"Phase {phase_id}: {label}", style="bold cyan"))
        console.print(Text(main_line, style="dim"))
        if finding:
            console.print(Text(f"finding={finding}", style="dim"))
    else:
        import _colors as C
        print(C.header(f"Phase {phase_id}: {label}"))
        print(C.info(main_line))
        if finding:
            print(C.info(f"finding={finding}"))

    iteration_retry_count = 0
    frontmatter_retry_count = 0
    codeql_plan_retry_count = 0
    attempt_number = 0
    last_session_id: str = existing_session_id or ""
    last_finish_reason: str | None = None
    last_finish_tokens: dict[str, Any] = {}
    last_permission_error: str | None = None
    any_step_finish_seen = False
    step_finish_count = 0
    transcript_path: Path = Path()
    finish_warning: str | None = None
    subphase_start_time = time.time()

    password = runner.info.password if runner.info else ""

    # --- Retry loop (mirrors harness.run_phase_mode) ---
    while True:
        attempt_number += 1
        _reset_subagent_state()
        finish_warning = None

        returncode, session_id, run_result, transcript_path = _run_single_attempt(
            args, console, prompt, model, variant, base_url,
            password, str(ROOT),
            render_event_fn=render_event,
            emit_fatal_error_fn=_emit_fatal_error,
            existing_session_id=last_session_id or None,
            transcript_phase=phase_id,
            phase_override=phase_id,
            label_override=label,
        )

        if returncode != 0:
            break

        last_session_id = session_id
        last_finish_reason = run_result.last_finish_reason
        last_finish_tokens = run_result.last_finish_tokens
        last_permission_error = run_result.last_permission_error
        any_step_finish_seen = run_result.any_step_finish_seen
        step_finish_count = run_result.step_finish_count

        if not any_step_finish_seen:
            finish_warning = (
                "CodeCome observed no step_finish events in the JSON stream, so the model/provider did not emit a "
                "completion signal. Treating the run as incomplete."
            )
        elif last_finish_reason is None:
            finish_warning = (
                "CodeCome observed a step_finish event without a finish reason, so the model/provider completion "
                "state is ambiguous. Treating the run as incomplete."
            )
        elif last_finish_reason in _FINISH_FAILURE:
            finish_warning = (
                f"CodeCome observed finish reason '{last_finish_reason}', which means the model/provider stopped "
                "before completing the subphase. Treating the run as incomplete rather than as a CodeCome logic error."
            )
        elif last_finish_reason in _FINISH_MID_TURN:
            if last_permission_error:
                finish_warning = (
                    f"{last_permission_error}; CodeCome observed the model/provider stop mid-turn with finish "
                    f"reason '{last_finish_reason}', so the subphase did not reach a final completion signal."
                )
            else:
                finish_warning = (
                    f"CodeCome observed the model/provider stop mid-turn with finish reason '{last_finish_reason}' "
                    f"after {step_finish_count} completed loops, without a terminal completion signal. Treating the "
                    "subphase as incomplete because the model/provider cut off the response."
                )
        elif last_finish_reason not in _FINISH_TERMINAL_OK:
            finish_warning = (
                f"CodeCome observed an unrecognised model/provider finish reason '{last_finish_reason}'. Treating "
                "the run as incomplete rather than assuming success."
            )

        if finish_warning is not None:
            if (
                last_finish_reason in _FINISH_MID_TURN
                and last_permission_error is None
                and check_phase_graceful_completion(phase_id, finding, subphase_start_time)
            ):
                msg = (
                    f"CodeCome observed a mid-turn model/provider cutoff for Phase {phase_id} after {step_finish_count} "
                    "completed loops, but the required durable artifacts were already written. Treating the subphase as complete."
                )
                if HAVE_RICH:
                    from rich.text import Text
                    console.print(Text(msg, style="bold green"))
                else:
                    import _colors as C
                    print(C.ok(msg))
                finish_warning = None
                last_finish_reason = "graceful_forgiveness"
            else:
                returncode = 2

        if returncode == 0:
            if _subphase_should_validate_codeql_plan(phase_id):
                validation_rc, validation_output = _validate_codeql_plan_for_repair()
                if validation_rc != 0:
                    max_codeql_plan_retries = 2
                    if codeql_plan_retry_count < max_codeql_plan_retries:
                        codeql_plan_retry_count += 1
                        msg = (
                            "\n[Auto-Correction] The model completed a turn, but itemdb/notes/codeql-plan.yml "
                            "failed local CodeQL plan validation. CodeCome will resume the same session and ask "
                            f"for a minimal YAML/plan repair (retry {codeql_plan_retry_count}/{max_codeql_plan_retries})."
                        )
                        if HAVE_RICH:
                            from rich.text import Text
                            console.print(Text(msg, style="bold yellow"))
                        else:
                            import _colors as C
                            print(C.warn(msg))
                        if last_session_id and last_session_id != "id":
                            prompt = build_codeql_plan_resume_prompt(validation_output)
                            continue
                        else:
                            returncode = 2
                            finish_warning = (
                                "The model output failed CodeQL plan validation, and CodeCome could not determine "
                                "a session ID to resume for repair. Treating the subphase as incomplete so the "
                                "validator output can be reported back with the saved transcript."
                            )
                    else:
                        returncode = 2
                        finish_warning = (
                            f"itemdb/notes/codeql-plan.yml still fails validation after {max_codeql_plan_retries} "
                            "auto-repair attempts. Treating the subphase as incomplete so the validation errors "
                            "can be reported back."
                        )
                        msg = f"\n[Warning] CodeQL plan validation errors persist after {max_codeql_plan_retries} auto-retries."
                        if HAVE_RICH:
                            from rich.text import Text
                            console.print(Text(msg, style="bold red"))
                        else:
                            import _colors as C
                            print(C.fail(msg))
                        print(validation_output)
                    break

            from findings.checks_entry import run_frontmatter_validation

            validation_rc, validation_output = run_frontmatter_validation()
            if validation_rc != 0:
                max_frontmatter_retries = 2
                if frontmatter_retry_count < max_frontmatter_retries:
                    frontmatter_retry_count += 1
                    msg = (
                        "\n[Auto-Correction] The model completed a turn, but its output failed local frontmatter "
                        f"validation. CodeCome will resume the same session and ask for a minimal repair "
                        f"(retry {frontmatter_retry_count}/{max_frontmatter_retries})."
                    )
                    if HAVE_RICH:
                        from rich.text import Text
                        console.print(Text(msg, style="bold yellow"))
                    else:
                        import _colors as C
                        print(C.warn(msg))
                    if last_session_id and last_session_id != "id":
                        prompt = build_frontmatter_resume_prompt(phase_id, finding, validation_output)
                        continue
                    else:
                        returncode = 2
                        finish_warning = (
                            "The model output failed local frontmatter validation, and CodeCome could not determine a "
                            "session ID to resume for repair. Treating the subphase as incomplete so the validator output "
                            "can be reported back with the saved transcript."
                        )
                else:
                    returncode = 2
                    finish_warning = (
                        f"The model output still fails local frontmatter validation after {max_frontmatter_retries} "
                        "auto-repair attempts. Treating the subphase as incomplete so the validation errors can be reported back."
                    )
                    msg = f"\n[Warning] Frontmatter errors persist after {max_frontmatter_retries} auto-retries."
                    if HAVE_RICH:
                        from rich.text import Text
                        console.print(Text(msg, style="bold red"))
                    else:
                        import _colors as C
                        print(C.fail(msg))
                    print(validation_output)
                break
            break

        if returncode == 2 and last_finish_reason in _FINISH_MID_TURN:
            import os
            max_iteration_retries = int(os.environ.get("CODECOME_MAX_ITERATION_RETRIES", "1"))
            if iteration_retry_count < max_iteration_retries:
                iteration_retry_count += 1
                msg = (
                    "\n[Auto-Resume] CodeCome observed a mid-turn model/provider cutoff and will resume the same "
                    f"session once to let the model finish the interrupted work (retry {iteration_retry_count}/{max_iteration_retries})."
                )
                if HAVE_RICH:
                    from rich.text import Text
                    console.print(Text(msg, style="bold yellow"))
                else:
                    import _colors as C
                    print(C.warn(msg))
                if last_session_id and last_session_id != "id":
                    prompt = build_phase_resume_prompt(
                        phase_id, finding, last_finish_reason, step_finish_count,
                    )
                    continue
                else:
                    finish_warning = (
                        "CodeCome correctly detected that the model/provider stopped mid-turn, but it could not determine "
                        "a session ID for automatic continuation. Treating the subphase as incomplete."
                    )
                    if HAVE_RICH:
                        from rich.text import Text
                        console.print(Text("Could not determine session ID to resume.", style="red"))
                    else:
                        import _colors as C
                        print(C.fail("Could not determine session ID to resume."))
            break

        break
    # --- end retry loop ---

    # Report subphase outcome
    if returncode == 0:
        if HAVE_RICH:
            from rich.rule import Rule
            from rich.text import Text
            console.print(Rule(style="green"))
            console.print(Text(f"{'OK' if not HAVE_RICH else ''}Phase {phase_id} completed successfully", style="green"))
            console.print(Text(
                f"  finish reason: {last_finish_reason!r}  "
                f"transcript: {transcript_path.relative_to(ROOT) if transcript_path.name else 'N/A'}",
                style="dim",
            ))
        else:
            import _colors as C
            print(C.ok(f"Phase {phase_id} completed successfully"))
            print(f"  finish reason: {last_finish_reason!r}  transcript: {transcript_path.relative_to(ROOT) if transcript_path.name else 'N/A'}")
    elif returncode == 130:
        if HAVE_RICH:
            from rich.rule import Rule
            from rich.text import Text
            console.print(Rule(style="yellow"))
            console.print(Text(f"Phase {phase_id} interrupted", style="yellow"))
        else:
            import _colors as C
            print(C.warn(f"Phase {phase_id} interrupted"))
    else:
        if HAVE_RICH:
            from rich.rule import Rule
            from rich.text import Text
            console.print(Rule(style="red"))
            console.print(Text(
                f"Phase {phase_id} did not complete cleanly (exit code {returncode})",
                style="red",
            ))
            if finish_warning:
                console.print(Text(f"  reason: {finish_warning}", style="red"))
            console.print(Text(f"  transcript: {transcript_path.relative_to(ROOT) if transcript_path.name else 'N/A'}", style="dim"))
        else:
            import _colors as C
            print(C.fail(f"Phase {phase_id} did not complete cleanly (exit code {returncode})"))
            if finish_warning:
                print(C.fail(f"  reason: {finish_warning}"))
            print(f"  finish reason: {last_finish_reason!r}  transcript: {transcript_path.relative_to(ROOT) if transcript_path.name else 'N/A'}")

    if return_outcome:
        return _SubphaseOutcome(returncode=returncode, session_id=last_session_id, transcript_path=transcript_path)
    return returncode


# ---------------------------------------------------------------------------
# Phase 1 orchestration
# ---------------------------------------------------------------------------

def run_phase_1(
    args: Any,
    console: Any,
    rendering_ctx: Any,
    runner: ServerRunner,
    base_url: str,
) -> int:
    """Orchestrate Phase 1 subphases 1a → 1b → 1c with gates."""
    # ---- Phase 1a: Target Profile ----
    findings_snapshot_1a = count_findings_snapshot()
    rc = _run_subphase(
        args=args,
        console=console,
        rendering_ctx=rendering_ctx,
        runner=runner,
        base_url=base_url,
        phase_id="1a",
        label="Target Profile",
        agent="recon",
        prompt_file="prompts/phase-1a-profile.md",
    )
    if rc != 0:
        return rc

    gate_rc = check_phase_1a(console, findings_snapshot=findings_snapshot_1a)
    if gate_rc != 0:
        return gate_rc

    # ---- CodeQL analysis ----
    rc = _run_codeql(console)
    if rc != 0:
        return rc
    rc = _run_codeql_repair_if_needed(
        args=args,
        console=console,
        rendering_ctx=rendering_ctx,
        runner=runner,
        base_url=base_url,
    )
    if rc != 0:
        return rc
    rc = _check_codeql_artifacts(console)
    if rc != 0:
        return rc

    # Snapshot findings immediately before 1b so the warning scope matches 1b.
    findings_snapshot = count_findings_snapshot()

    # ---- Phase 1b: CodeQL-assisted Reconnaissance ----
    rc = _run_subphase(
        args=args,
        console=console,
        rendering_ctx=rendering_ctx,
        runner=runner,
        base_url=base_url,
        phase_id="1b",
        label="CodeQL-assisted Reconnaissance",
        agent="recon",
        prompt_file="prompts/phase-1b-codeql-recon.md",
    )
    if rc != 0:
        return rc

    gate_rc = check_phase_1b(console, findings_snapshot=findings_snapshot)
    if gate_rc != 0:
        return gate_rc

    # ---- Phase 1c: Sandbox Bootstrap ----
    rc = _run_subphase(
        args=args,
        console=console,
        rendering_ctx=rendering_ctx,
        runner=runner,
        base_url=base_url,
        phase_id="1c",
        label="Sandbox Bootstrap",
        agent="recon",
        prompt_file="prompts/phase-1c-sandbox.md",
    )
    if rc != 0:
        return rc

    gate_rc = check_phase_1c(console)
    if gate_rc != 0:
        return gate_rc

    # ---- Phase 1 complete ----
    if HAVE_RICH:
        from rich.rule import Rule
        from rich.text import Text
        console.print(Rule(style="bold green"))
        console.print(Text("Phase 1 complete — all subphases passed.", style="bold green"))
    else:
        import _colors as C
        print()
        print(C.ok("Phase 1 complete — all subphases passed."))

    return 0
