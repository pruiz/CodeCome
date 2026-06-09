# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Phase 1 subphase orchestration.

Runs Phase 1 as three subphases (1a / 1b / 1c) with gates and CodeQL
analysis between 1b and 1c.  The opencode server is started once and
reused across all three subphase sessions.
"""

from __future__ import annotations

import os
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
from rendering.dispatch import _get_rendering_ctx, configure_rendering, render_event
from rendering.output import get_output, T
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
    build_artifact_repair_resume_prompt,
)


@dataclass(frozen=True)
class _SubphaseOutcome:
    returncode: int
    session_id: str
    transcript_path: Path
# ---------------------------------------------------------------------------
# CodeQL analysis (between 1a gate and 1b)
# ---------------------------------------------------------------------------

def _run_codeql(console: Any) -> None:
    """Run full CodeQL pipeline and report results.

    This function always succeeds (returns None). Pass/fail enforcement
    is handled separately by ``_check_codeql_artifacts``.
    """
    from codeql.config import resolve_config as _resolve_codeql_config

    config = _resolve_codeql_config()
    out = get_output(console)

    out.header("CodeQL")

    if not config.enabled:
        msg = "CodeQL disabled — skipping."
        from codeql.pipeline import record_skipped_run
        record_skipped_run(config, "CodeQL disabled for Phase 1")
        out.warn(msg)
        return

    if not config.phase_1_enabled:
        msg = "CodeQL phase 1 disabled — skipping."
        from codeql.pipeline import record_skipped_run
        record_skipped_run(config, "CodeQL phase 1 disabled")
        out.warn(msg)
        return

    out.detail("Running CodeQL analysis…")

    from codeql.pipeline import run_full_pipeline

    def progress(message: str) -> None:
        out.detail(message)

    try:
        manifest = run_full_pipeline(config, progress=progress)
    except Exception as exc:
        msg = f"CodeQL: FAILED — {exc}"
        out.error(msg)
        return

    status = manifest["status"]
    warnings = manifest.get("warnings", [])
    failures = manifest.get("failures", [])

    if status == "completed":
        msg = f"CodeQL: analysis completed ({len(manifest.get('languages', []))} language(s))"
        out.success(msg)
    elif status == "skipped":
        reason = failures[0] if failures else "no plan"
        msg = f"CodeQL: skipped — {reason}"
        out.warn(msg)
    elif status == "soft-failed":
        msg = "CodeQL: soft-failed — continuing"
        out.warn(msg)
        for w in warnings + failures:
            out.warn(f"  {w}")
    elif status == "failed":
        msg = "CodeQL: FAILED"
        out.error(msg)
        for f in failures:
            out.error(f"  {f}")


def _check_codeql_artifacts(console: Any) -> int:
    """Validate CodeQL artifacts; block 1b only on hard fail policy."""
    from codeql.config import resolve_config as _resolve_codeql_config
    from codeql.artifacts import check_artifacts

    config = _resolve_codeql_config()
    out = get_output(console)

    if not config.enabled or not config.phase_1_enabled:
        return 0

    status, warnings = check_artifacts(config.abs_output_dir)

    for w in warnings:
        out.warn(f"  WARN: {w}")

    if config.fail_policy == "hard" and status == "failed":
        msg = "CodeQL artifact gate: FAILED — blocking Phase 1b"
        out.error(msg)
        return 1

    if status == "failed":
        # fail_policy is soft, so treat as a non-blocking warning
        out.warn("CodeQL artifact gate: execution crashed but fail_policy is soft — continuing")

    label = f"CodeQL artifact gate: {status}"
    if status == "completed":
        out.success(label)
    else:
        out.info(label)

    return 0


def _phase_1a_codeql_plan_repair_output() -> str:
    return (
        "Gate 1a rejected itemdb/notes/codeql-plan.yml. Repair only that file.\n"
        "Please check the previous tool execution errors and correct the plan.\n"
        "Common fixes:\n"
        " - For every analysis unit whose languages list is empty, either remove the unit "
        "   from analysis_units or set recommended: false on that unit. Prefer moving "
        "   unsupported-language inventory such as Rust, Swift, Elixir, Zig, F#, VB6, "
        "   WebAssembly, and static-only components into the top-level notes list instead "
        "   of keeping active CodeQL analysis units with languages: [].\n"
        " - Ensure all analysis unit IDs are unique.\n"
        " - Ensure paths correctly map to existing directories under src/.\n"
        " - Ensure build_mode matches the CodeQL supported build modes for each language.\n"
        "Keep CodeQL-supported units with valid paths, valid build_mode, and non-empty languages lists.\n"
        "Do not modify target-profile.md, build-model.md, source code, or project configuration."
    )


def _validate_codeql_plan_for_repair() -> tuple[int, str]:
    """Validate codeql-plan.yml and return (rc, output).
    
    This is the implementation backing ``tools/codecome.py check-codeql-plan``.
    It reuses the same validation logic as the Phase 1a gate but collects
    output as a string tuple instead of writing to a rich console.
    """
    import io
    from pathlib import Path

    buf = io.StringIO()
    notes_dir = ROOT / "itemdb" / "notes"
    plan_path = notes_dir / "codeql-plan.yml"

    if not plan_path.exists():
        buf.write("ERROR: itemdb/notes/codeql-plan.yml does not exist\n")
        return 1, buf.getvalue()

    try:
        import yaml
    except ImportError:
        buf.write("WARN: PyYAML not available; cannot validate codeql-plan.yml\n")
        return 0, buf.getvalue()

    try:
        from codeql.packs import load_codeql_plan
        plan = load_codeql_plan(plan_path)
    except Exception as exc:
        buf.write(f"ERROR: codeql-plan.yml: {exc}\n")
        return 1, buf.getvalue()

    errors = _collect_plan_errors(plan, notes_dir)
    if errors:
        for err in errors:
            buf.write(f"ERROR: {err}\n")
        return 1, buf.getvalue()

    units = plan.get("analysis_units", [])
    buf.write(f"codeql-plan.yml: {len(units)} analysis unit(s) configured, all valid\n")
    return 0, buf.getvalue()


def _collect_plan_errors(plan: dict, notes_dir: Path) -> list[str]:
    """Return a list of validation error strings for codeql-plan.yml.
    
    Reuses the same logic as ``check_phase_1a()`` but returns strings
    instead of writing to a rendering output.
    """
    from codeql.capabilities import is_supported_language, supported_build_modes

    errors: list[str] = []

    if plan.get("recommended") is True:
        units = plan.get("analysis_units", [])
        if not isinstance(units, list) or len(units) == 0:
            errors.append("codeql-plan.yml: recommended=true but no analysis_units entries")
            return errors

        valid_confidences = {"HIGH", "MEDIUM", "LOW"}
        seen_unit_ids: set[str] = set()
        seen_databases: set[tuple[str, str]] = set()

        for i, unit in enumerate(units):
            if not isinstance(unit, dict):
                errors.append(f"codeql-plan.yml: analysis unit {i} is not a mapping")
                continue
            unit_id = unit.get("id")
            if not isinstance(unit_id, str) or not unit_id:
                errors.append(f"codeql-plan.yml: analysis unit {i} missing valid 'id'")
                continue
            if unit_id in seen_unit_ids:
                errors.append(f"codeql-plan.yml: duplicate analysis unit id '{unit_id}'")
            seen_unit_ids.add(unit_id)

            unit_path = unit.get("path")
            if not isinstance(unit_path, str) or not unit_path:
                errors.append(f"codeql-plan.yml: analysis unit '{unit_id}' missing valid 'path'")
                continue
            resolved_path = (ROOT / unit_path).resolve()
            src_root = (ROOT / "src").resolve()
            try:
                under_src = resolved_path == src_root or resolved_path.is_relative_to(src_root)
            except ValueError:
                under_src = False
            if not under_src:
                errors.append(f"codeql-plan.yml: analysis unit '{unit_id}' path must be under src/: {unit_path}")
            if "_codeql_detected_source_root" in resolved_path.parts:
                errors.append(f"codeql-plan.yml: analysis unit '{unit_id}' path uses CodeQL-generated helper path")
            if not resolved_path.exists():
                errors.append(f"codeql-plan.yml: analysis unit '{unit_id}' path does not exist: {unit_path}")

            languages = unit.get("languages")
            if unit.get("recommended") is False and (languages is None or languages == []):
                continue
            if not isinstance(languages, list):
                errors.append(f"codeql-plan.yml: analysis unit '{unit_id}' has no languages")
                continue
            if len(languages) == 0:
                errors.append(
                    f"codeql-plan.yml: analysis unit '{unit_id}' has no CodeQL languages and "
                    "is not marked recommended=false"
                )
                continue

            for j, lang in enumerate(languages):
                if not isinstance(lang, dict):
                    errors.append(
                        f"codeql-plan.yml: analysis unit '{unit_id}' language entry {j} is not a mapping"
                    )
                    continue
                language_id = lang.get("id")
                if not isinstance(language_id, str) or not language_id:
                    errors.append(
                        f"codeql-plan.yml: analysis unit '{unit_id}' language entry {j} missing valid 'id'"
                    )
                    continue
                if not is_supported_language(language_id):
                    errors.append(
                        f"codeql-plan.yml: unsupported CodeQL language '{language_id}' in analysis unit '{unit_id}'"
                    )
                    continue
                db_key = (unit_id, language_id)
                if db_key in seen_databases:
                    errors.append(
                        f"codeql-plan.yml: duplicate language '{language_id}' in analysis unit '{unit_id}'"
                    )
                seen_databases.add(db_key)
                if lang.get("confidence") not in valid_confidences:
                    errors.append(
                        f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' "
                        f"has unexpected confidence '{lang.get('confidence')}'"
                    )
                build_mode = lang.get("build_mode")
                supported_modes = supported_build_modes(language_id)
                if build_mode not in supported_modes:
                    errors.append(
                        f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' "
                        f"has unsupported build_mode '{build_mode}' "
                        f"(allowed: {', '.join(sorted(supported_modes))})"
                    )
                build_command = lang.get("build_command")
                build_provider = lang.get("build_provider")
                recipe_backed = build_provider == "sandbox-recipe"
                if build_mode == "manual" and not recipe_backed and not (isinstance(build_command, str) and build_command.strip()):
                    errors.append(
                        f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' "
                        "uses manual build without build_command"
                    )
                if "packs" not in lang:
                    errors.append(
                        f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' missing 'packs'"
                    )
                elif not isinstance(lang["packs"], list) or len(lang["packs"]) == 0:
                    errors.append(
                        f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' has empty packs list"
                    )
    return errors


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
    out = get_output(console)

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

    out.header(f"Phase {phase_id}: {label}")
    out.detail(main_line)
    if finding:
        out.detail(f"finding={finding}")

    iteration_retry_count = 0
    frontmatter_retry_count = 0
    artifact_retry_count = 0
    attempt_number = 0
    last_session_id: str = existing_session_id or ""
    last_finish_reason: str | None = None
    last_finish_tokens: dict[str, Any] = {}
    last_permission_error: str | None = None
    any_step_finish_seen = False
    step_finish_count = 0
    transcript_path: Path = Path()
    finish_warning: str | None = None
    phase_failures: list[str] = []
    phase_ok: bool = False  # defensive default; assigned in graceful-completion branch
    subphase_start_time = time.time()

    password = runner.info.password if runner.info else ""

    # --- Retry loop (mirrors harness.run_phase_mode) ---
    while True:
        attempt_number += 1
        phase_failures = []
        phase_ok = False
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

        if returncode == 2 and run_result.last_finish_reason == "resume_not_ready":
            last_session_id = session_id or last_session_id
            last_finish_reason = run_result.last_finish_reason
            finish_warning = (
                "CodeCome waited for the existing session to become idle before sending a resume/repair prompt, "
                "but the session never reported a ready status. No resume prompt was sent."
            )
            break

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
                (not any_step_finish_seen or last_finish_reason in _FINISH_MID_TURN)
                and last_permission_error is None
            ):
                phase_ok, phase_failures = check_phase_graceful_completion(
                    phase_id, finding, subphase_start_time)
                if phase_ok:
                    msg = (
                        f"CodeCome observed an incomplete model/provider completion signal for Phase {phase_id} after "
                        f"{step_finish_count} completed loops, but expected durable artifacts were written during "
                        "the run. Treating the subphase as complete enough to run validation and auto-repair."
                    )
                    out.success(msg)
                    finish_warning = None
                    last_finish_reason = "graceful_forgiveness"
                else:
                    returncode = 2
            else:
                returncode = 2

        if returncode == 0:
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
                    out.warn(msg)
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
                    out.error(msg)
                    print(validation_output)
                break

            if phase_id == "1b":
                from phases.artifact_checks import check_phase_1b_artifacts as _check_artifacts_1b
                artifact_errors = _check_artifacts_1b(allow_missing_generated=False)
                if artifact_errors:
                    max_artifact_retries = 2
                    if artifact_retry_count < max_artifact_retries:
                        artifact_retry_count += 1
                        validation_output = "\n".join(artifact_errors)
                        msg = (
                            "\n[Auto-Correction] The model completed a turn, but Phase 1b artifacts "
                            f"failed validation. CodeCome will resume the same session and ask for "
                            f"a minimal repair (retry {artifact_retry_count}/{max_artifact_retries})."
                        )
                        out.warn(msg)
                        if last_session_id and last_session_id != "id":
                            prompt = build_artifact_repair_resume_prompt(
                                phase_id, finding, validation_output
                            )
                            continue
                        else:
                            returncode = 2
                            finish_warning = (
                                "The model output failed Phase 1b artifact validation, and CodeCome "
                                "could not determine a session ID to resume for repair. Treating the "
                                "subphase as incomplete so the validation output can be reported back."
                            )
                    else:
                        returncode = 2
                        finish_warning = (
                            f"Phase 1b artifact validation still fails after {max_artifact_retries} "
                            "auto-repair attempts. Treating the subphase as incomplete so the "
                            "validation errors can be reported back."
                        )
                        validation_output = "\n".join(artifact_errors)
                        msg = f"\n[Warning] Phase 1b artifact errors persist after {max_artifact_retries} auto-retries."
                        out.error(msg)
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
                out.warn(msg)
                if last_session_id and last_session_id != "id":
                    prompt = build_phase_resume_prompt(
                        phase_id, finding, last_finish_reason, step_finish_count,
                        failure_details=phase_failures if phase_failures else None,
                    )
                    continue
                else:
                    finish_warning = (
                        "CodeCome correctly detected that the model/provider stopped mid-turn, but it could not determine "
                        "a session ID for automatic continuation. Treating the subphase as incomplete."
                    )
                    out.error("Could not determine session ID to resume.", strong=False)
            break

        break
    # --- end retry loop ---

    # Report subphase outcome
    if returncode == 0:
        out.separator(tone=T.SUCCESS)
        out.success(f"Phase {phase_id} completed successfully", symbol=True)
        out.detail(
            f"  finish reason: {last_finish_reason!r}  "
            f"transcript: {transcript_path.relative_to(ROOT) if transcript_path.name else 'N/A'}"
        )
    elif returncode == 130:
        out.separator(tone=T.WARNING)
        out.warn(f"Phase {phase_id} interrupted")
    else:
        out.separator(tone=T.ERROR)
        out.error(f"Phase {phase_id} did not complete cleanly (exit code {returncode})", symbol=True)
        if finish_warning:
            out.error(f"  reason: {finish_warning}", strong=False)
        out.detail(f"  transcript: {transcript_path.relative_to(ROOT) if transcript_path.name else 'N/A'}")

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
    out = get_output(console)
    # ---- Phase 1a: Target Profile ----
    findings_snapshot_1a = count_findings_snapshot()
    phase_1a_session_id: str | None = None
    phase_1a_prompt: str | None = None
    phase_1a_artifact_retries = 0
    while True:
        outcome = _run_subphase(
            args=args,
            console=console,
            rendering_ctx=rendering_ctx,
            runner=runner,
            base_url=base_url,
            phase_id="1a",
            label="Target Profile",
            agent="recon",
            prompt_file="prompts/phase-1a-profile.md",
            existing_session_id=phase_1a_session_id,
            initial_prompt=phase_1a_prompt,
            return_outcome=True,
        )
        if outcome.returncode != 0:
            return outcome.returncode

        gate_rc = check_phase_1a(console, findings_snapshot=findings_snapshot_1a)
        if gate_rc == 0:
            break

        max_artifact_retries = 2
        if phase_1a_artifact_retries >= max_artifact_retries or not outcome.session_id:
            return gate_rc

        phase_1a_artifact_retries += 1
        out.warn(
            "\n[Auto-Correction] Phase 1a artifacts failed Gate 1a validation. "
            "CodeCome will resume the same session and ask for a minimal CodeQL plan repair "
            f"(retry {phase_1a_artifact_retries}/{max_artifact_retries})."
        )
        phase_1a_session_id = outcome.session_id
        phase_1a_prompt = build_artifact_repair_resume_prompt(
            "1a", None, _phase_1a_codeql_plan_repair_output()
        )

    # ---- Phase 1b: Sandbox Bootstrap ----
    rc = _run_subphase(
        args=args,
        console=console,
        rendering_ctx=rendering_ctx,
        runner=runner,
        base_url=base_url,
        phase_id="1b",
        label="Sandbox Bootstrap",
        agent="recon",
        prompt_file="prompts/phase-1b-sandbox.md",
    )
    if rc != 0:
        return rc

    gate_rc = check_phase_1b(console)
    if gate_rc != 0:
        return gate_rc

    # ---- CodeQL analysis (post-sandbox) ----
    import subprocess
    has_sandbox = (ROOT / "sandbox").exists()
    if has_sandbox:
        out.info("Starting sandbox for CodeQL execution...")
        subprocess.run(["make", "sandbox-up"], cwd=str(ROOT), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
    try:
        _run_codeql(console)
        rc = _check_codeql_artifacts(console)
        if rc != 0:
            return rc
    finally:
        if has_sandbox:
            out.info("Stopping sandbox after CodeQL execution...")
            subprocess.run(["make", "sandbox-down"], cwd=str(ROOT), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Snapshot findings immediately before 1c so the warning scope matches 1c.
    findings_snapshot = count_findings_snapshot()

    # ---- Phase 1c: Detailed Reconnaissance ----
    rc = _run_subphase(
        args=args,
        console=console,
        rendering_ctx=rendering_ctx,
        runner=runner,
        base_url=base_url,
        phase_id="1c",
        label="Detailed Reconnaissance",
        agent="recon",
        prompt_file="prompts/phase-1c-recon.md",
    )
    if rc != 0:
        return rc

    gate_rc = check_phase_1c(console, findings_snapshot=findings_snapshot)
    if gate_rc != 0:
        return gate_rc

    # ---- Phase 1 complete ----
    out.separator(tone=T.SUCCESS)
    out.success("Phase 1 complete — all subphases passed.", symbol=True)

    return 0
