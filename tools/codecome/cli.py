# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CLI entry point and argument parsing for the CodeCome phase runner."""

from __future__ import annotations

import argparse
import dataclasses
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _colors as C
from opencode.serve import ServerRunner, ServerRunnerError

from codecome.cli_render import (
    HAVE_RICH, Console, Panel, Rule, Text,
    build_console, _get_rendering_ctx, render_event, _emit_fatal_error,
    _FINISH_TERMINAL_OK, _FINISH_MID_TURN, _FINISH_FAILURE,
)
import codecome.cli_render as _clr
from codecome.version import check_opencode_version
from codecome.config import (
    truthy_env, resolve_color_mode, load_prompt,
    resolve_model_and_variant, resolve_thinking_decision, show_model_table,
)
from codecome.graceful import (
    check_phase_graceful_completion,
    build_phase_resume_prompt, build_frontmatter_resume_prompt,
)

# Legacy globals — still referenced by old renderers in run-agent.py.
# Re-exported for backward compatibility.
_READ_DISPLAY_LINES = 10
_WRITE_CONTENT_LINES = 25
_WRITE_DIFF_LIMIT = 50
_EDIT_DIFF_LINES = 25


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a CodeCome phase with structured output.")
    parser.add_argument("--phase", help="Phase number (required unless --show-model or --chat).")
    parser.add_argument("--label", help="Human-readable phase label (required unless --show-model).")
    parser.add_argument("--agent", help="OpenCode agent name.")
    parser.add_argument("--prompt-file", help="Prompt file path relative to repo root (required unless --show-model or --chat).")
    parser.add_argument("--prompt", help="Direct prompt text (used by --chat mode).")
    parser.add_argument("--chat", action="store_true", help="Launch interactive textual chat harness.")
    parser.add_argument("--finding", help="Finding id for prompt substitution.")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("--debug", action="store_true", help="Mirror raw JSON events to stderr.")
    parser.add_argument("--read-display-lines", type=int, help="Max lines shown in read output (default: 10, env: CODECOME_READ_DISPLAY_LINES).")
    parser.add_argument("--write-content-lines", type=int, help="Max lines shown for new-file write content (default: 25, env: CODECOME_WRITE_CONTENT_LINES).")
    parser.add_argument("--write-diff-limit", type=int, help="Max diff lines shown for write (default: 50, env: CODECOME_WRITE_DIFF_LIMIT).")
    parser.add_argument("--edit-diff-lines", type=int, help="Max diff lines shown for edit (default: 25, env: CODECOME_EDIT_DIFF_LINES).")
    parser.add_argument(
        "--show-model",
        action="store_true",
        help="Print the model-resolution table for --agent and exit. No phase is launched.",
    )
    return parser


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    RUN_START_TIME = time.time()
    iteration_retry_count = 0
    frontmatter_retry_count = 0
    check_opencode_version()

    parser = build_parser()
    args = parser.parse_args()

    if args.show_model:
        agent_name = args.agent or "recon"
        return show_model_table(agent_name)

    if args.chat:
        from chat.harness import _run_chat_mode as _chat_run
        return _chat_run(parser, args)

    missing = [n for n in ("phase", "label", "agent", "prompt_file") if getattr(args, n) is None]
    if missing:
        parser.error(
            "the following arguments are required when not using --show-model or --chat: "
            + ", ".join("--" + n.replace("_", "-") for n in missing)
        )

    # CLI flags override env var defaults for tunables.
    global _READ_DISPLAY_LINES, _WRITE_CONTENT_LINES, _WRITE_DIFF_LIMIT, _EDIT_DIFF_LINES
    if args.read_display_lines is not None:
        _READ_DISPLAY_LINES = args.read_display_lines
    if args.write_content_lines is not None:
        _WRITE_CONTENT_LINES = args.write_content_lines
    if args.write_diff_limit is not None:
        _WRITE_DIFF_LIMIT = args.write_diff_limit
    if args.edit_diff_lines is not None:
        _EDIT_DIFF_LINES = args.edit_diff_lines

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

    prompt_file = _clr.ROOT / args.prompt_file
    prompt = load_prompt(prompt_file, args.finding, phase=args.phase)
    extra_args = shlex.split(os.environ.get("OPENCODE_ARGS", ""))
    model, variant, model_source, variant_source = resolve_model_and_variant(
        args.agent, extra_args
    )
    thinking_on, thinking_source = resolve_thinking_decision(model, extra_args)

    model_label = model or "(unknown)"
    variant_label = variant or "(unknown)"

    parts = [f"agent={args.agent}", f"model={model_label}"]
    if variant is not None:
        parts.append(f"variant={variant_label}")
    parts.append(f"thinking={'on' if thinking_on else 'off'}")
    parts.append(f"prompt={args.prompt_file}")

    if variant is not None:
        sources_tail = (
            f"(model source: {model_source}, variant source: {variant_source}, "
            f"thinking source: {thinking_source})"
        )
    else:
        sources_tail = f"(model source: {model_source}, thinking source: {thinking_source})"

    main_line = "  ".join(parts) + "  " + sources_tail

    if HAVE_RICH:
        console.print(Rule(title=f"Phase {args.phase}: {args.label}", style="bold cyan"))
        console.print(Text(main_line, style="dim"))
        if args.finding:
            console.print(Text(f"finding={args.finding}", style="dim"))
        if str(args.phase) == "1":
            console.print(Text(
                "Phase 1 has two sub-stages: 1a recon notes, 1b sandbox bootstrap.",
                style="cyan",
            ))
    else:
        print(C.header(f"Phase {args.phase}: {args.label}"))
        print(C.info(main_line))
        if args.finding:
            print(C.info(f"finding={args.finding}"))
        if str(args.phase) == "1":
            print(C.info(
                "Phase 1 has two sub-stages: 1a recon notes, 1b sandbox bootstrap."
            ))
        print(C.warn("rich is not installed; using plain structured output fallback"))

    attempt_number = 0
    last_session_id: str = ""
    last_finish_reason: Optional[str] = None
    last_finish_tokens: dict[str, Any] = {}
    last_permission_error: Optional[str] = None
    any_step_finish_seen = False
    step_finish_count = 0
    transcript_path: Path = Path()
    finish_warning: Optional[str] = None

    os.environ["_CODECOME_INSIDE_HARNESS"] = "1"

    runner = ServerRunner()
    server_info: Any = None
    try:
        server_info = runner.start(hostname="127.0.0.1", log_level="WARN")
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
    try:
        while True:
            attempt_number += 1
            returncode, session_id, run_result, transcript_path = _run_single_attempt(
                args, console, prompt, model, variant, thinking_on, base_url,
                server_info.password, str(_clr.ROOT),
                render_event_fn=render_event,
                emit_fatal_error_fn=_emit_fatal_error,
                existing_session_id=last_session_id or None
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
                    last_finish_reason in _FINISH_MID_TURN
                    and last_permission_error is None
                    and check_phase_graceful_completion(args.phase, args.finding, RUN_START_TIME)
                ):
                    msg = (
                        f"CodeCome observed a mid-turn model/provider cutoff for Phase {args.phase} after {step_finish_count} "
                        "completed loops, but the required durable artifacts were already written. Treating the phase as complete."
                    )
                    if HAVE_RICH:
                        console.print(Text(msg, style="bold green"))
                    else:
                        print(C.ok(msg))
                    finish_warning = None
                    last_finish_reason = "graceful_forgiveness"
                else:
                    returncode = 2

            if returncode == 0:
                validation_result = subprocess.run(
                    [sys.executable, "tools/check-frontmatter.py"],
                    cwd=_clr.ROOT,
                    capture_output=True,
                    text=True
                )
                if validation_result.returncode != 0:
                    max_frontmatter_retries = 2
                    validation_output = (validation_result.stderr or validation_result.stdout).strip() or "(no validator output)"
                    if frontmatter_retry_count < max_frontmatter_retries:
                        frontmatter_retry_count += 1
                        msg = (
                            "\n[Auto-Correction] The model completed a turn, but its output failed local frontmatter "
                            f"validation. CodeCome will resume the same session and ask for a minimal repair "
                            f"(retry {frontmatter_retry_count}/{max_frontmatter_retries})."
                        )
                        if HAVE_RICH:
                            console.print(Text(msg, style="bold yellow"))
                        else:
                            print(C.warn(msg))
                        if last_session_id and last_session_id != "id":
                            prompt = build_frontmatter_resume_prompt(args.phase, args.finding, validation_output)
                            continue
                        else:
                            returncode = 2
                            finish_warning = (
                                "The model output failed local frontmatter validation, and CodeCome could not determine a "
                                "session ID to resume for repair. Treating the phase as incomplete so the validator output "
                                "can be reported back with the saved transcript."
                            )
                    else:
                        returncode = 2
                        finish_warning = (
                            f"The model output still fails local frontmatter validation after {max_frontmatter_retries} "
                            "auto-repair attempts. Treating the phase as incomplete so the validation errors can be reported back."
                        )
                        msg = f"\n[Warning] Frontmatter errors persist after {max_frontmatter_retries} auto-retries."
                        if HAVE_RICH:
                            console.print(Text(msg, style="bold red"))
                        else:
                            print(C.fail(msg))
                        print(validation_output)
                    break
                break

            if returncode == 2 and last_finish_reason in _FINISH_MID_TURN:
                max_iteration_retries = int(os.environ.get("CODECOME_MAX_ITERATION_RETRIES", "1"))
                if iteration_retry_count < max_iteration_retries:
                    iteration_retry_count += 1
                    msg = (
                        "\n[Auto-Resume] CodeCome observed a mid-turn model/provider cutoff and will resume the same "
                        f"session once to let the model finish the interrupted work (retry {iteration_retry_count}/{max_iteration_retries})."
                    )
                    if HAVE_RICH:
                        console.print(Text(msg, style="bold yellow"))
                    else:
                        print(C.warn(msg))
                    if last_session_id and last_session_id != "id":
                        prompt = build_phase_resume_prompt(
                            args.phase, args.finding, last_finish_reason, step_finish_count
                        )
                        continue
                    else:
                        finish_warning = (
                            "CodeCome correctly detected that the model/provider stopped mid-turn, but it could not determine "
                            "a session ID for automatic continuation. Treating the phase as incomplete."
                        )
                        if HAVE_RICH:
                            console.print(Text("Could not determine session ID to resume.", style="red"))
                        else:
                            print(C.fail("Could not determine session ID to resume."))
                break

            break
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
        runner.stop()

    if returncode == 0:
        if HAVE_RICH:
            console.print(Rule(style="green"))
            console.print(Text(f"{C.SYM_OK} Phase {args.phase} completed successfully", style="green"))
            console.print(Text(
                f"  finish reason: {last_finish_reason!r}  "
                f"transcript: {transcript_path.relative_to(_clr.ROOT)}",
                style="dim",
            ))
        else:
            print(C.ok(f"Phase {args.phase} completed successfully"))
            print(f"  finish reason: {last_finish_reason!r}  transcript: {transcript_path.relative_to(_clr.ROOT)}")
    elif returncode == 130:
        if HAVE_RICH:
            console.print(Rule(style="yellow"))
            console.print(Text(f"{C.SYM_WARN} Phase {args.phase} interrupted", style="yellow"))
        else:
            print(C.warn(f"Phase {args.phase} interrupted"))
    else:
        if HAVE_RICH:
            console.print(Rule(style="red"))
            console.print(Text(
                f"{C.SYM_FAIL} Phase {args.phase} did not complete cleanly (exit code {returncode})",
                style="red",
            ))
            if finish_warning:
                console.print(Text(f"  reason: {finish_warning}", style="red"))
            console.print(Text(f"  transcript: {transcript_path.relative_to(_clr.ROOT)}", style="dim"))
            console.print(Text(
                "  hint: the run is likely partial; rerun the phase or "
                "switch to a different model/provider before retrying",
                style="yellow",
            ))
        else:
            print(C.fail(f"Phase {args.phase} did not complete cleanly (exit code {returncode})"))
            if finish_warning:
                print(C.fail(f"  reason: {finish_warning}"))
            print(f"  transcript: {transcript_path.relative_to(_clr.ROOT)}")
            print(C.warn(
                "  hint: the run is likely partial; rerun the phase or "
                "switch to a different model/provider before retrying"
            ))

    return returncode
