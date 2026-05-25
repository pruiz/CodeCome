# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Phase runner helpers: SSE event consumption and single-attempt orchestration."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _colors as C
from events.phase_loop import PhaseEventLoop, RunResult
from codecome.config import ROOT
from codecome.session import create_session, send_prompt_to_session
from codecome.transcript import open_phase_transcript, close_transcript


def _consume_events(
    base_url: str,
    session_id: str,
    console: Any,
    phase: str,
    label: str,
    args: argparse.Namespace,
    transcript_fp: Any | None,
    thinking_on: bool,
    auth_token: str | None,
    workspace_dir: str | None,
    render_event_fn: Callable[..., None],  # CLI/rendering event dispatcher
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

    def _render_and_log(console_: Any, phase_: str, label_: str, event: dict[str, Any]) -> None:
        if transcript_fp is not None:
            try:
                transcript_fp.write(json.dumps(event) + "\n")
            except OSError:
                pass
        if args.debug:
            sys.stderr.write(json.dumps(event) + "\n")
            sys.stderr.flush()
        if not thinking_on and event.get("type") == "reasoning":
            return
        render_event_fn(console_, phase_, label_, event)

    return event_loop.run(_render_and_log)


def _run_single_attempt(
    args: argparse.Namespace,
    console: Any,
    prompt: str,
    model: str | None,
    variant: str | None,
    thinking_on: bool,
    base_url: str,
    auth_token: str | None,
    workspace_dir: str | None,
    render_event_fn: Callable[..., None],  # CLI/rendering event dispatcher
    emit_fatal_error_fn: Callable[..., None] | None = None,
    existing_session_id: str | None = None,
) -> tuple[int, str, RunResult, Path]:

    transcript_fp = None
    try:
        transcript_path, transcript_fp = open_phase_transcript(str(args.phase), args.finding)
    except OSError as exc:
        finding_tag = (args.finding or "no-finding").replace("/", "_")
        transcript_path = ROOT / "tmp" / f"last-phase-{args.phase}-{finding_tag}-attempt-N.jsonl"
        try:
            console.print("warning: could not open transcript ", transcript_path, ": ", exc)
        except AttributeError:
            print(C.warn(f"warning: could not open transcript {transcript_path}: {exc}"))

    try:
        if existing_session_id:
            session_id = existing_session_id
        else:
            session_id = create_session(base_url, str(args.phase), args.agent, model, auth_token, workspace_dir)

        run_result_box: dict[str, Any] = {}
        consume_error_box: dict[str, Exception] = {}

        def _consume() -> None:
            try:
                run_result_box["result"] = _consume_events(
                    base_url, session_id, console,
                    str(args.phase), str(args.label), args,
                    transcript_fp, thinking_on,
                    auth_token, workspace_dir,
                    render_event_fn=render_event_fn,
                )
            except Exception as exc:  # noqa: BLE001
                consume_error_box["error"] = exc

        consumer = threading.Thread(target=_consume, name=f"codecome-events-{session_id}", daemon=True)
        consumer.start()

        send_prompt_to_session(base_url, session_id, prompt, args.agent, model, variant, auth_token, workspace_dir)
        consumer.join()

        if "error" in consume_error_box:
            raise consume_error_box["error"]
        run_result = run_result_box.get("result")
        if not isinstance(run_result, RunResult):
            raise RuntimeError("Event loop ended without a RunResult")
    except Exception as exc:
        if emit_fatal_error_fn:
            emit_fatal_error_fn(console, "Server Error", str(exc))
        else:
            try:
                console.print(f"Fatal error: {exc}")
            except Exception:
                print(C.error(f"Fatal error: {exc}"), file=sys.stderr)
        return 1, existing_session_id or "", RunResult(), transcript_path
    finally:
        close_transcript(transcript_fp)

    return 0, session_id, run_result, transcript_path
