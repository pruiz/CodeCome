# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Chat mode harness: entry point that wires server, session, and TUI together.

Provides `_run_chat_mode(parser, args) -> int`, the main entry point
for `run-agent.py --chat`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _colors as C  # noqa: E402
from chat.debug import _setup_chat_debug, _chat_debug, _close_chat_debug  # noqa: E402
from chat.app import ChatApp, HAVE_RICH  # noqa: E402
from codecome.cli_render import build_console, _emit_fatal_error  # noqa: E402
from opencode.serve import ServerRunner, ServerRunnerError  # noqa: E402
from codecome.config import (  # noqa: E402
    ROOT,
    resolve_color_mode,
    load_prompt,
    resolve_runtime_config,
)
from codecome.session import create_chat_session  # noqa: E402
from codecome.transcript import open_chat_transcript, close_transcript  # noqa: E402


def _run_chat_mode(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Launch the interactive chat harness."""
    if args.debug:
        _setup_chat_debug()
        _chat_debug("_run_chat_mode: entering (debug enabled)")

    missing = [n for n in ("label", "agent") if getattr(args, n) is None]
    if missing:
        parser.error(
            "the following arguments are required for --chat: "
            + ", ".join("--" + n.replace("_", "-") for n in missing)
        )

    color_mode = resolve_color_mode(args.color)
    console = build_console(color_mode)

    # Resolve prompt
    if args.prompt_file:
        prompt_file = ROOT / args.prompt_file
        prompt = load_prompt(prompt_file, args.finding, phase=args.phase)
    elif args.prompt:
        prompt = args.prompt
    else:
        prompt = ""

    # Model resolution
    rc = resolve_runtime_config(args.agent)
    model = rc.model
    variant = rc.variant
    thinking_on = rc.thinking_on

    _chat_debug(f"_run_chat_mode: agent={args.agent} model={model} variant={variant} thinking={thinking_on}")

    if ChatApp is None:
        _emit_fatal_error(console, "Missing Dependency",
                          "The --chat flag requires the 'textual' package. Run 'make venv' to install it.")
        return 1

    # Start server
    _chat_debug("_run_chat_mode: starting opencode serve")
    runner = ServerRunner()
    try:
        server_info = runner.start(hostname="127.0.0.1", log_level=getattr(args, "log_level", "WARN"))
        _chat_debug(f"_run_chat_mode: server started pid={server_info.pid} url={server_info.base_url}")
    except ServerRunnerError as exc:
        _chat_debug(f"_run_chat_mode: server start failed: {exc}")
        _emit_fatal_error(console, "Server Error", str(exc))
        _close_chat_debug()
        return 1

    # Create session
    _chat_debug("_run_chat_mode: creating session")
    try:
        session_id = create_chat_session(
            server_info.base_url, args.agent, model, server_info.password, str(ROOT),
        )
        _chat_debug(f"_run_chat_mode: session created id={session_id}")
    except Exception as exc:
        _chat_debug(f"_run_chat_mode: session creation failed: {exc}")
        _emit_fatal_error(console, "Session Error", str(exc))
        runner.stop()
        _close_chat_debug()
        return 1

    # Open the chat transcript (parity with phase mode).
    transcript_path: Path = Path()
    transcript_fp = None
    try:
        transcript_path, transcript_fp = open_chat_transcript()
        _chat_debug(f"_run_chat_mode: opened transcript {transcript_path}")
    except OSError as exc:
        transcript_path = ROOT / "tmp" / "last-chat-unknown.jsonl"
        _chat_debug(f"_run_chat_mode: could not open transcript: {exc}")

    _chat_debug("_run_chat_mode: creating ChatApp")
    app = None
    try:
        app = ChatApp(
            server_info=server_info,
            session_id=session_id,
            initial_prompt=prompt,
            args=args,
            model=model,
            variant=variant,
            thinking_on=thinking_on,
            transcript_fp=transcript_fp,
        )
        _chat_debug("_run_chat_mode: calling app.run()")
        app.run()
        _chat_debug("_run_chat_mode: app.run() returned")
    finally:
        _chat_debug("_run_chat_mode: cleaning up")
        if app is not None and getattr(app, "chat_loop", None) is not None:
            _chat_debug("_run_chat_mode: stopping chat loop")
            app.chat_loop.stop()
        runner.stop()
        close_transcript(transcript_fp)

    # Final summary banner on the restored terminal.  Mirrors phase
    # mode's success-path summary.
    try:
        rel_path = transcript_path.relative_to(ROOT)
    except ValueError:
        rel_path = transcript_path
    if HAVE_RICH:
        from rich.rule import Rule  # noqa: E402
        from rich.text import Text  # noqa: E402

        console.print(Rule(style="green"))
        console.print(Text(f"{C.SYM_OK} Chat session ended", style="green"))
        console.print(Text(f"  transcript: {rel_path}", style="dim"))
    else:
        print(C.ok("Chat session ended"))
        print(f"  transcript: {rel_path}")

    _close_chat_debug()
    return 0
