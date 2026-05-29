# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Phase 1 subphase orchestration.

Runs Phase 1 as three subphases (1a / 1b / 1c) with gates and a CodeQL
placeholder between 1a and 1b.  The opencode server is started once and
reused across all three subphase sessions.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from opencode.serve import ServerRunner, ServerRunnerError

from codecome.console import build_console, _emit_fatal_error
from codecome.config import ROOT, resolve_color_mode, load_prompt, resolve_runtime_config
from codecome.runner import _run_single_attempt
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
)

# gate-check.py uses a hyphen and cannot be imported with a regular
# ``import`` statement.  Load it via importlib.
_gc_spec = importlib.util.spec_from_file_location(
    "gate_check",
    str(ROOT / "tools" / "gate-check.py"),
)
_gate_check = importlib.util.module_from_spec(_gc_spec)
_gc_spec.loader.exec_module(_gate_check)


# ---------------------------------------------------------------------------
# CodeQL placeholder (no-op until PR 5)
# ---------------------------------------------------------------------------

def _run_codeql_placeholder(console: Any) -> None:
    """Log that CodeQL is not yet implemented."""
    if HAVE_RICH:
        from rich.rule import Rule
        from rich.text import Text
        console.print(Rule(title="CodeQL", style="yellow"))
        console.print(Text(
            "CodeQL analysis not yet implemented — coming in a future PR. "
            "Proceeding to Phase 1b without CodeQL artifacts.",
            style="yellow",
        ))
    else:
        import _colors as C
        print(C.header("CodeQL"))
        print(C.warn(
            "CodeQL analysis not yet implemented — coming in a future PR. "
            "Proceeding to Phase 1b without CodeQL artifacts."
        ))
        print()


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
    findings_snapshot: dict[str, int] | None = None,
) -> tuple[int, dict[str, int] | None]:
    """Run a single subphase agent session with retry/resume.

    Returns (exit_code, cumulative_findings_snapshot).  The snapshot is
    updated after the session completes so that gate functions can detect
    unexpected finding creation.
    """
    prompt_path = ROOT / prompt_file
    prompt = load_prompt(prompt_path, finding, phase=phase_id)
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
    attempt_number = 0
    last_session_id: str = ""
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

        returncode, session_id, run_result, transcript_path = _run_single_attempt(
            args, console, prompt, model, variant, base_url,
            password, str(ROOT),
            render_event_fn=render_event,
            emit_fatal_error_fn=_emit_fatal_error,
            existing_session_id=last_session_id or None,
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
            validation_result = subprocess.run(
                [sys.executable, "tools/check-frontmatter.py"],
                cwd=ROOT,
                capture_output=True,
                text=True,
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

    # Update findings snapshot for gate check
    if findings_snapshot is not None and returncode == 0:
        from tools.gate_check import _count_findings_since
        pass  # snapshot is read by caller; we'll track in the orchestrator

    return returncode, findings_snapshot


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
    # Snapshot findings before 1a
    findings_snapshot = _gate_check._count_findings_since()

    # ---- Phase 1a: Target Profile ----
    rc, _ = _run_subphase(
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

    gate_rc = _gate_check.check_phase_1a(console)
    if gate_rc != 0:
        return gate_rc

    # ---- CodeQL placeholder ----
    _run_codeql_placeholder(console)

    # ---- Phase 1b: CodeQL-assisted Reconnaissance ----
    rc, _ = _run_subphase(
        args=args,
        console=console,
        rendering_ctx=rendering_ctx,
        runner=runner,
        base_url=base_url,
        phase_id="1b",
        label="CodeQL-assisted Reconnaissance",
        agent="recon",
        prompt_file="prompts/phase-1b-codeql-recon.md",
        findings_snapshot=findings_snapshot,
    )
    if rc != 0:
        return rc

    gate_rc = _gate_check.check_phase_1b(console, findings_snapshot=findings_snapshot)
    if gate_rc != 0:
        return gate_rc

    # ---- Phase 1c: Sandbox Bootstrap ----
    rc, _ = _run_subphase(
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

    gate_rc = _gate_check.check_phase_1c(console)
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
