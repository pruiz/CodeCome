# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Phase runner helpers: SSE event consumption and single-attempt orchestration."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _colors as C
from events.phase_loop import PhaseEventLoop, RunResult
from codecome.config import ROOT
from codecome.session import create_session, get_session_status, send_prompt_to_session
from codecome.transcript import Transcript
from codecome.recording import EventRecorder


class ResumeSessionNotReady(RuntimeError):
    """Raised when an existing session is not ready for a resume prompt."""


def _consume_events(
    base_url: str,
    session_id: str,
    console: Any,
    phase: str,
    label: str,
    args: argparse.Namespace,
    transcript: Transcript,
    auth_token: str | None,
    workspace_dir: str | None,
    render_event_fn: Callable[..., None],
    event_loop_box: dict[str, Any] | None = None,
) -> RunResult:
    event_loop = PhaseEventLoop(
        base_url=base_url,
        session_id=session_id,
        console=console,
        phase=phase,
        label=label,
        auth_token=auth_token,
        workspace_dir=workspace_dir,
    )
    if event_loop_box is not None:
        event_loop_box["loop"] = event_loop

    recorder = EventRecorder(transcript, debug=args.debug)

    def _handle_event(console_: Any, phase_: str, label_: str, event: dict[str, Any]) -> None:
        render_event_fn(console_, phase_, label_, event)

    return event_loop.run(_handle_event, recorder.record)


def _record_codecome_event(transcript: Transcript, event_type: str, **properties: Any) -> None:
    transcript.write_event({
        "type": event_type,
        "timestamp": int(time.time() * 1000),
        "properties": properties,
    })


def _wait_for_resume_idle(
    base_url: str,
    session_id: str,
    auth_token: str | None,
    workspace_dir: str | None,
    transcript: Transcript,
) -> None:
    timeout_s = float(os.environ.get("CODECOME_RESUME_IDLE_TIMEOUT", "120"))
    poll_s = float(os.environ.get("CODECOME_RESUME_IDLE_POLL", "1"))
    deadline = time.monotonic() + max(timeout_s, 0.0)

    while True:
        status = get_session_status(base_url, session_id, auth_token, workspace_dir)
        if status == "idle":
            _record_codecome_event(transcript, "codecome.resume.status_ready", sessionID=session_id, status=status)
            return

        event_type = "codecome.resume.blocked_busy" if status == "busy" else "codecome.resume.blocked_unknown"
        _record_codecome_event(transcript, event_type, sessionID=session_id, status=status)
        if time.monotonic() >= deadline:
            _record_codecome_event(
                transcript,
                "codecome.resume.timeout",
                sessionID=session_id,
                status=status,
                timeoutSeconds=timeout_s,
            )
            detail = status if status is not None else "unknown"
            raise ResumeSessionNotReady(
                f"session {session_id} is not ready for resume after {timeout_s:g}s "
                f"(last status: {detail}); refusing to send resume prompt"
            )
        time.sleep(max(poll_s, 0.1))


def _run_single_attempt(
    args: argparse.Namespace,
    console: Any,
    prompt: str,
    model: str | None,
    variant: str | None,
    base_url: str,
    auth_token: str | None,
    workspace_dir: str | None,
    render_event_fn: Callable[..., None],
    emit_fatal_error_fn: Callable[..., None] | None = None,
    existing_session_id: str | None = None,
    transcript_phase: str | None = None,
    phase_override: str | None = None,
    label_override: str | None = None,
) -> tuple[int, str, RunResult, Path]:

    transcript: Transcript
    try:
        transcript = Transcript.for_phase(transcript_phase or str(args.phase), args.finding)
    except OSError as exc:
        finding_tag = (args.finding or "no-finding").replace("/", "_")
        transcript = Transcript.null()
        transcript.path = ROOT / "tmp" / f"last-phase-{transcript_phase or args.phase}-{finding_tag}-attempt-N.jsonl"
        try:
            console.print("warning: could not open transcript ", transcript.path, ": ", exc)
        except AttributeError:
            print(C.warn(f"warning: could not open transcript {transcript.path}: {exc}"))

    try:
        _record_codecome_event(
            transcript,
            "codecome.attempt.started",
            phase=transcript_phase or str(args.phase),
            label=str(args.label),
            existingSession=bool(existing_session_id),
        )
        if existing_session_id:
            session_id = existing_session_id
            _wait_for_resume_idle(base_url, session_id, auth_token, workspace_dir, transcript)
        else:
            session_id = create_session(base_url, str(args.phase), args.agent, model, auth_token, workspace_dir)

        _record_codecome_event(
            transcript,
            "codecome.session.ready",
            sessionID=session_id,
            existingSession=bool(existing_session_id),
        )

        run_result_box: dict[str, Any] = {}
        consume_error_box: dict[str, Exception] = {}
        event_loop_box: dict[str, Any] = {}

        def _consume() -> None:
            try:
                run_result_box["result"] = _consume_events(
                    base_url, session_id, console,
                    phase_override or str(args.phase),
                    label_override or str(args.label),
                    args,
                    transcript,
                    auth_token, workspace_dir,
                    render_event_fn=render_event_fn,
                    event_loop_box=event_loop_box,
                )
            except Exception as exc:  # noqa: BLE001
                consume_error_box["error"] = exc

        consumer = threading.Thread(target=_consume, name=f"codecome-events-{session_id}", daemon=True)
        consumer.start()

        _record_codecome_event(transcript, "codecome.prompt.send_started", sessionID=session_id)
        try:
            send_prompt_to_session(base_url, session_id, prompt, args.agent, model, variant, auth_token, workspace_dir)
        except Exception as exc:
            _record_codecome_event(
                transcript,
                "codecome.prompt.send_failed",
                sessionID=session_id,
                errorType=type(exc).__name__,
                message=str(exc),
            )
            loop = event_loop_box.get("loop")
            if loop is not None:
                try:
                    loop.stop()
                except Exception:
                    pass
            consumer.join(timeout=5.0)
            if consumer.is_alive():
                _record_codecome_event(transcript, "codecome.event_loop.stop_timeout", sessionID=session_id)
            raise
        _record_codecome_event(transcript, "codecome.prompt.send_completed", sessionID=session_id)
        consumer.join()

        if "error" in consume_error_box:
            exc = consume_error_box["error"]
            _record_codecome_event(
                transcript,
                "codecome.event_loop.failed",
                sessionID=session_id,
                errorType=type(exc).__name__,
                message=str(exc),
            )
            raise exc
        run_result = run_result_box.get("result")
        if not isinstance(run_result, RunResult):
            raise RuntimeError("Event loop ended without a RunResult")
    except ResumeSessionNotReady as exc:
        _record_codecome_event(
            transcript,
            "codecome.attempt.incomplete",
            errorType=type(exc).__name__,
            message=str(exc),
            existingSession=bool(existing_session_id),
        )
        return 2, existing_session_id or "", RunResult(
            last_finish_reason="resume_not_ready",
            last_session_id=existing_session_id,
        ), transcript.path
    except Exception as exc:
        _record_codecome_event(
            transcript,
            "codecome.attempt.failed",
            errorType=type(exc).__name__,
            message=str(exc),
            existingSession=bool(existing_session_id),
        )
        if emit_fatal_error_fn:
            emit_fatal_error_fn(console, "Server Error", str(exc))
        else:
            try:
                console.print(f"Fatal error: {exc}")
            except Exception:
                print(C.error(f"Fatal error: {exc}"), file=sys.stderr)
        return 1, existing_session_id or "", RunResult(), transcript.path
    finally:
        transcript.close()

    return 0, session_id, run_result, transcript.path
