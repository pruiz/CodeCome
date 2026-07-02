# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Phase harness: retry/resume loop, server lifecycle, and completion
reporting for phase-mode runs.

Parallel to ``chat.harness`` which owns the chat-mode lifecycle.
``cli.py`` dispatches to one of the two harnesses after parsing args.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from opencode.serve import ServerRunner, ServerRunnerError, make_liveness_check

from codecome.console import build_console, _emit_fatal_error
from rendering.dispatch import _get_rendering_ctx, configure_rendering, render_event
from rendering.output import get_output, T
from rendering.events import _FINISH_TERMINAL_OK, _FINISH_MID_TURN, _FINISH_BUDGET, _FINISH_FAILURE
from codecome.config import ROOT, resolve_color_mode, load_prompt, resolve_runtime_config
from codecome.status import RunStatus
from phases.completion import (
    check_phase_graceful_completion,
    build_phase_resume_prompt, build_frontmatter_resume_prompt,
    build_artifact_repair_resume_prompt,
)


def _pending_finding_count() -> int:
    pending_dir = ROOT / "itemdb" / "findings" / "PENDING"
    if not pending_dir.exists():
        return 0
    return sum(1 for p in pending_dir.glob("CC-*.md") if p.is_file())


def _write_phase3_noop_summary() -> Path:
    runs_dir = ROOT / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d-%H%M%S")
    path = runs_dir / f"phase-3-summary-{timestamp}.md"
    path.write_text(
        "# CodeCome Run Summary\n\n"
        f"Date: {now.date().isoformat()}  \n"
        "Phase: counter_analysis  \n"
        "Agent: reviewer  \n\n"
        "# Goal\n\n"
        "Review pending findings.\n\n"
        "# Prompt\n\n"
        "Phase 3 was requested, but there were no PENDING findings to review.\n\n"
        "# Files read\n\n"
        "- `itemdb/findings/PENDING/`\n\n"
        "# Files created\n\n"
        f"- `runs/{path.name}`\n\n"
        "# Files modified\n\n"
        "None.\n\n"
        "# Findings created\n\n"
        "| ID | Title | Path |\n"
        "|---|---|---|\n"
        "| - | None. | - |\n\n"
        "# Findings moved\n\n"
        "| ID | From | To | Reason |\n"
        "|---|---|---|---|\n"
        "| - | - | - | None. |\n\n"
        "# Findings updated\n\n"
        "| ID | Update summary |\n"
        "|---|---|\n"
        "| - | None. |\n\n"
        "# Evidence created\n\n"
        "None.\n\n"
        "# Important observations\n\n"
        "No PENDING findings were available, so Phase 3 had nothing to review.\n\n"
        "# Assumptions\n\n"
        "None.\n\n"
        "# Open questions for the user\n\n"
        "None.\n\n"
        "# Re-run prompt hints\n\n"
        "None.\n\n"
        "# Limitations\n\n"
        "No counter-analysis was performed because there were no PENDING findings.\n\n"
        "# Recommended next step\n\n"
        "Run Phase 2 if additional vulnerability hypotheses are needed.\n",
        encoding="utf-8",
    )
    return path


# Recovery conditions that are handled by restarting the opencode server and
# retrying. Maps the finish reason to its user-facing recovery wording.
_RECOVERABLE_RESTART_REASONS: dict[str, str] = {
    "server_unreachable": (
        "The opencode server is unreachable or unresponsive."
    ),
    "session_stalled": (
        "The model turn produced no activity for an extended period (stalled)."
    ),
}


def _restart_server(runner: ServerRunner, *, log_level: str) -> Any:
    """Restart the opencode server, returning the new ServerInfo.

    Centralizes the single stop/start invocation so the Phase 1 and Phase 2-6
    recovery paths never duplicate the restart call. Raises ServerRunnerError on
    failure (the caller decides how to surface it).
    """
    return runner.restart(hostname="127.0.0.1", log_level=log_level)


def run_phase_mode(args: argparse.Namespace) -> int:
    """Run a single phase with auto-retry/resume.

    This is the phase-mode equivalent of ``chat.harness.run_harness``.
    """
    RUN_START_TIME = time.time()
    iteration_retry_count = 0
    fatal_retry_count = 0
    frontmatter_retry_count = 0

    color_mode = resolve_color_mode(args.color)
    console = build_console(color_mode)

    _rendering_ctx = _get_rendering_ctx(console)
    _overrides: dict[str, Any] = {}
    if args.read_display_lines is not None:
        _overrides["read_display_lines"] = args.read_display_lines
    if args.write_content_lines is not None:
        _overrides["write_content_lines"] = args.write_content_lines
    if args.write_diff_limit is not None:
        _overrides["write_diff_limit"] = args.write_diff_limit
    if args.edit_diff_lines is not None:
        _overrides["edit_diff_lines"] = args.edit_diff_lines
    if _overrides:
        _rendering_ctx.settings = dataclasses.replace(_rendering_ctx.settings, **_overrides)

    # ── Phase 1: subphase orchestration with own server lifecycle ──
    if str(args.phase) == "1":
        os.environ["_CODECOME_INSIDE_HARNESS"] = "1"
        _p1_runner = ServerRunner()
        try:
            _p1_server_info = _p1_runner.start(hostname="127.0.0.1", log_level=args.log_level)
        except ServerRunnerError as exc:
            _emit_fatal_error(console, "Server Error", str(exc))
            return 1

        def _p1_forward_signal(signum: int, _frame: Any) -> None:
            info = _p1_runner.info
            if info is not None:
                try:
                    os.killpg(info.pid, signum)
                except ProcessLookupError:
                    pass
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)

        _p1_prev_sigint = signal.signal(signal.SIGINT, _p1_forward_signal)
        _p1_prev_sigterm = signal.signal(signal.SIGTERM, _p1_forward_signal)
        try:
            from codecome.phase_1 import run_phase_1 as _run_phase_1
            _p1_base_url = _p1_server_info.base_url
            _p1_start_at = "1a"
            _p1_restart_count = 0
            _p1_max_server_restarts = int(os.environ.get("CODECOME_MAX_SERVER_RESTARTS", "2"))

            while True:
                outcome = _run_phase_1(
                    args,
                    console,
                    _rendering_ctx,
                    _p1_runner,
                    _p1_base_url,
                    start_at=_p1_start_at,
                )
                if outcome.status not in (RunStatus.SERVER_UNREACHABLE, RunStatus.SESSION_STALLED):
                    return int(outcome.status)

                if _p1_restart_count >= _p1_max_server_restarts:
                    get_output(console).error(
                        f"Server restart budget exhausted ({_p1_restart_count}/{_p1_max_server_restarts}). "
                        "Cannot continue Phase 1."
                    )
                    return int(RunStatus.ERROR)

                _p1_restart_count += 1
                _p1_start_at = outcome.failed_subphase or _p1_start_at
                _p1_reason = (
                    "session_stalled"
                    if outcome.status == RunStatus.SESSION_STALLED
                    else "server_unreachable"
                )
                get_output(console).warn(
                    f"\n[Auto-Recovery] {_RECOVERABLE_RESTART_REASONS[_p1_reason]} "
                    f"CodeCome will restart the opencode server and retry from Phase {_p1_start_at} "
                    f"(server restart {_p1_restart_count}/{_p1_max_server_restarts})."
                )
                try:
                    _p1_server_info = _restart_server(_p1_runner, log_level=args.log_level)
                except ServerRunnerError as exc:
                    _emit_fatal_error(console, "Server Restart Error", str(exc))
                    return int(RunStatus.ERROR)
                _p1_base_url = _p1_server_info.base_url
        finally:
            signal.signal(signal.SIGINT, _p1_prev_sigint)
            signal.signal(signal.SIGTERM, _p1_prev_sigterm)
            _p1_runner.stop()

    # ── Phases 2-6 below this point ──
    prompt_file = ROOT / args.prompt_file
    prompt = load_prompt(prompt_file, args.finding, phase=args.phase)
    rc = resolve_runtime_config(args.agent)
    model = rc.model
    variant = rc.variant
    thinking_on = rc.thinking_on
    configure_rendering(console, render_reasoning=thinking_on)
    out = get_output(console)

    model_label = model or "(unknown)"
    variant_label = variant or "(unknown)"

    parts = [f"agent={args.agent}", f"model={model_label}"]
    if variant is not None:
        parts.append(f"variant={variant_label}")
    parts.append(f"thinking={'on' if thinking_on else 'off'}")
    parts.append(f"prompt={args.prompt_file}")

    if variant is not None:
        sources_tail = (
            f"(model source: {rc.model_source}, variant source: {rc.variant_source}, "
            f"thinking source: {rc.thinking_source})"
        )
    else:
        sources_tail = f"(model source: {rc.model_source}, thinking source: {rc.thinking_source})"

    main_line = "  ".join(parts) + "  " + sources_tail

    out.header(f"Phase {args.phase}: {args.label}")
    out.detail(main_line)
    if args.finding:
        out.detail(f"finding={args.finding}")
    if console is None:
        out.warn("rich is not installed; using plain structured output fallback")

    if str(args.phase) == "3" and _pending_finding_count() == 0:
        summary_path = _write_phase3_noop_summary()
        out.separator(tone=T.SUCCESS)
        out.success("Phase 3 completed successfully", symbol=True)
        out.detail("  no PENDING findings; nothing to review")
        out.detail(f"  summary: {summary_path.relative_to(ROOT)}")
        return 0

    attempt_number = 0
    last_session_id: str = ""
    last_finish_reason: Optional[str] = None
    last_finish_tokens: dict[str, Any] = {}
    last_permission_error: Optional[str] = None
    any_step_finish_seen = False
    step_finish_count = 0
    transcript_path: Path = Path()
    finish_warning: Optional[str] = None
    phase_failures: list[str] = []
    phase_ok: bool = False  # defensive default; assigned in D.2 or D.3 before use in D.3b
    server_restart_count = 0
    max_server_restarts = int(os.environ.get("CODECOME_MAX_SERVER_RESTARTS", "2"))

    os.environ["_CODECOME_INSIDE_HARNESS"] = "1"

    runner = ServerRunner()
    server_info: Any = None
    try:
        server_info = runner.start(hostname="127.0.0.1", log_level=args.log_level)
    except ServerRunnerError as exc:
        _emit_fatal_error(console, "Server Error", str(exc))
        return 1

    base_url = server_info.base_url

    def _forward_signal(signum: int, _frame: Any) -> None:
        info = runner.info
        if info is not None:
            try:
                os.killpg(info.pid, signum)
            except ProcessLookupError:
                pass
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    previous_sigint = signal.signal(signal.SIGINT, _forward_signal)
    previous_sigterm = signal.signal(signal.SIGTERM, _forward_signal)

    from codecome.runner import _run_single_attempt
    from rendering.events import _reset_subagent_state
    liveness_check = make_liveness_check(runner)
    try:
        while True:
            attempt_number += 1
            phase_failures = []
            phase_ok = False
            finish_warning = None
            # Clear per-session dedup state so retries don't suppress updates.
            _reset_subagent_state()
            returncode, session_id, run_result, transcript_path = _run_single_attempt(
                args, console, prompt, model, variant, base_url,
                server_info.password, str(ROOT),
                render_event_fn=render_event,
                emit_fatal_error_fn=_emit_fatal_error,
                existing_session_id=last_session_id or None,
                liveness_check=liveness_check,
            )

            if returncode == RunStatus.INCOMPLETE and run_result.last_finish_reason == "resume_not_ready":
                last_session_id = session_id or last_session_id
                last_finish_reason = run_result.last_finish_reason
                finish_warning = (
                    "CodeCome waited for the existing session to become idle before sending a resume/repair prompt, "
                    "but the session never reported a ready status. No resume prompt was sent."
                )
                break

            _recovery_reason = None
            if returncode == RunStatus.INCOMPLETE and run_result.last_finish_reason == "server_unreachable":
                _recovery_reason = "server_unreachable"
            elif getattr(run_result, "session_stalled", False) or run_result.last_finish_reason == "session_stalled":
                _recovery_reason = "session_stalled"

            if _recovery_reason is not None:
                if returncode == RunStatus.OK:
                    returncode = RunStatus.INCOMPLETE
                if server_restart_count < max_server_restarts:
                    server_restart_count += 1
                    out.warn(
                        f"\n[Auto-Recovery] {_RECOVERABLE_RESTART_REASONS[_recovery_reason]} "
                        f"CodeCome will restart the opencode server and retry with a fresh session "
                        f"(server restart {server_restart_count}/{max_server_restarts})."
                    )
                    try:
                        server_info = _restart_server(runner, log_level=args.log_level)
                    except ServerRunnerError as exc:
                        _emit_fatal_error(console, "Server Restart Error", str(exc))
                        return int(RunStatus.ERROR)
                    base_url = server_info.base_url
                    last_session_id = ""
                    prompt = build_phase_resume_prompt(
                        str(args.phase), args.finding,
                        _recovery_reason, step_finish_count,
                        failure_details=phase_failures if phase_failures else None,
                    )
                    continue
                last_session_id = session_id or last_session_id
                last_finish_reason = _recovery_reason
                finish_warning = (
                    f"CodeCome attempted {server_restart_count} server restart(s) after a "
                    f"'{_recovery_reason}' condition, but the restart budget is exhausted. "
                    "The phase cannot continue."
                )
                break

            if returncode != RunStatus.OK:
                # Infrastructure/transient failure (timeout, connection error, etc.)
                # Retry with a separate budget so infra blips don't consume the
                # "model needs more turns" iteration retry budget.
                max_fatal_retries = int(os.environ.get("CODECOME_MAX_FATAL_RETRIES", "2"))
                if fatal_retry_count < max_fatal_retries and last_session_id:
                    fatal_retry_count += 1
                    msg = (
                        f"\n[Auto-Retry] The previous attempt failed with an infrastructure error (exit {returncode}). "
                        f"CodeCome will retry the same session (fatal retry {fatal_retry_count}/{max_fatal_retries})."
                    )
                    out.warn(msg)
                    # Brief pause before retrying to let transient issues settle.
                    time.sleep(5.0)
                    prompt = build_phase_resume_prompt(
                        str(args.phase), args.finding,
                        "infrastructure_error", step_finish_count,
                    )
                    continue
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
            elif last_finish_reason in _FINISH_BUDGET:
                finish_warning = (
                    f"CodeCome observed output budget exhaustion (finish reason '{last_finish_reason}'). "
                    f"The model/provider stopped after {step_finish_count} completed loops before producing all "
                    "required artifacts. Treating the run as incomplete."
                )
            elif last_finish_reason in _FINISH_FAILURE:
                finish_warning = (
                    f"CodeCome observed finish reason '{last_finish_reason}', which means the model/provider stopped "
                    "before completing the phase. Treating the run as incomplete rather than as a CodeCome logic error."
                )
            elif last_finish_reason in _FINISH_MID_TURN:
                if last_permission_error:
                    finish_warning = (
                        f"{last_permission_error}; CodeCome observed the model/provider stop mid-turn with finish "
                        f"reason '{last_finish_reason}', so the phase did not reach a final completion signal."
                    )
                else:
                    finish_warning = (
                        f"CodeCome observed the model/provider stop mid-turn with finish reason '{last_finish_reason}' "
                        f"after {step_finish_count} completed loops, without a terminal completion signal. Treating the "
                        "phase as incomplete because the model/provider cut off the response."
                    )
            elif last_finish_reason not in _FINISH_TERMINAL_OK:
                finish_warning = (
                    f"CodeCome observed an unrecognised model/provider finish reason '{last_finish_reason}'. Treating "
                    "the run as incomplete rather than assuming success."
                )

            if finish_warning is not None:
                if (
                    (last_finish_reason in _FINISH_MID_TURN or last_finish_reason in _FINISH_BUDGET)
                    and last_permission_error is None
                ):
                    phase_ok, phase_failures = check_phase_graceful_completion(
                        args.phase, args.finding, RUN_START_TIME)
                    if last_finish_reason in _FINISH_MID_TURN:
                        if phase_ok:
                            msg = (
                                f"CodeCome observed a mid-turn model/provider cutoff for Phase {args.phase} after {step_finish_count} "
                                "completed loops, but expected durable artifacts were written during "
                                "the run. Treating the phase as complete enough to run validation and auto-repair."
                            )
                            out.success(msg)
                            finish_warning = None
                            last_finish_reason = "graceful_forgiveness"
                        else:
                            returncode = RunStatus.INCOMPLETE
                    else:
                        # _FINISH_BUDGET: fail only if artifacts are incomplete
                        if not phase_ok:
                            returncode = RunStatus.INCOMPLETE
                        else:
                            finish_warning = None
                else:
                    returncode = RunStatus.INCOMPLETE

            if returncode == RunStatus.OK:
                if last_finish_reason in _FINISH_TERMINAL_OK:
                    phase_ok, phase_failures = check_phase_graceful_completion(
                        str(args.phase), args.finding, RUN_START_TIME)
                    if not phase_ok:
                        returncode = RunStatus.INCOMPLETE
                        finish_warning = (
                            f"Phase {args.phase} reported terminal finish reason '{last_finish_reason}', "
                            "but required durable artifacts were not produced. Treating as incomplete."
                        )

                if returncode == RunStatus.OK:
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
                                prompt = build_frontmatter_resume_prompt(args.phase, args.finding, validation_output)
                                continue
                            else:
                                returncode = RunStatus.INCOMPLETE
                                finish_warning = (
                                    "The model output failed local frontmatter validation, and CodeCome could not determine a "
                                    "session ID to resume for repair. Treating the phase as incomplete so the validator output "
                                    "can be reported back with the saved transcript."
                                )
                        else:
                            returncode = RunStatus.INCOMPLETE
                            finish_warning = (
                                f"The model output still fails local frontmatter validation after {max_frontmatter_retries} "
                                "auto-repair attempts. Treating the phase as incomplete so the validation errors can be reported back."
                            )
                            msg = f"\n[Warning] Frontmatter errors persist after {max_frontmatter_retries} auto-retries."
                            out.error(msg)
                            print(validation_output)
                        break
                if returncode == RunStatus.OK:
                    break

            if returncode == RunStatus.INCOMPLETE and (
                last_finish_reason in _FINISH_MID_TURN
                or last_finish_reason in _FINISH_BUDGET
                or (last_finish_reason in _FINISH_TERMINAL_OK and not phase_ok)
            ):
                max_iteration_retries = int(os.environ.get("CODECOME_MAX_ITERATION_RETRIES", "3"))
                if iteration_retry_count < max_iteration_retries:
                    iteration_retry_count += 1
                    if last_finish_reason in _FINISH_BUDGET:
                        msg = (
                            "\n[Auto-Resume] CodeCome observed output budget exhaustion and will resume the same "
                            f"session once to let the model finish the interrupted work "
                            f"(retry {iteration_retry_count}/{max_iteration_retries})."
                        )
                    else:
                        msg = (
                            "\n[Auto-Resume] CodeCome observed an incomplete run and will resume the same "
                            f"session once to let the model finish the interrupted work "
                            f"(retry {iteration_retry_count}/{max_iteration_retries})."
                        )
                    out.warn(msg)
                    if last_session_id and last_session_id != "id":
                        prompt = build_phase_resume_prompt(
                            args.phase, args.finding, last_finish_reason, step_finish_count,
                            failure_details=phase_failures if phase_failures else None,
                        )
                        continue
                    else:
                        finish_warning = (
                            "CodeCome correctly detected that the model/provider stopped before completing "
                            "the phase, but it could not determine a session ID for automatic continuation. "
                            "Treating the phase as incomplete."
                        )
                        out.error("Could not determine session ID to resume.", strong=False)
                break

            break
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        runner.stop()

    if returncode == RunStatus.OK:
        out.separator(tone=T.SUCCESS)
        out.success(f"Phase {args.phase} completed successfully", symbol=True)
        out.detail(
            f"  finish reason: {last_finish_reason!r}  "
            f"transcript: {transcript_path.relative_to(ROOT)}"
        )
    elif returncode == RunStatus.INTERRUPTED:
        out.separator(tone=T.WARNING)
        out.warn(f"Phase {args.phase} interrupted")
    else:
        out.separator(tone=T.ERROR)
        out.error(
            f"Phase {args.phase} did not complete cleanly (exit code {returncode})",
            symbol=True,
        )
        if finish_warning:
            out.error(f"  reason: {finish_warning}", strong=False)
        if phase_failures:
            out.error("  remaining gate failures:", strong=False)
            for failure in phase_failures:
                out.detail(f"    - {failure}")
        out.detail(f"  transcript: {transcript_path.relative_to(ROOT)}")
        out.warn(
            "  hint: the run is likely partial; rerun the phase or "
            "switch to a different model/provider before retrying"
        )

    return returncode
