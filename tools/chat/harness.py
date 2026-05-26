# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Chat mode harness: entry point that wires server, session, and TUI together.

Provides `run_harness(parser, args) -> int`, the main entry point
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
from codecome.console import build_console, _emit_fatal_error  # noqa: E402
from opencode.serve import ServerRunner, ServerRunnerError  # noqa: E402
from codecome.config import (  # noqa: E402
    ROOT,
    resolve_color_mode,
    load_prompt,
    resolve_runtime_config,
)
from codecome.session import create_chat_session  # noqa: E402
from codecome.transcript import Transcript  # noqa: E402
from rendering import dispatch as rendering_dispatch  # noqa: E402


def run_harness(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Launch the interactive chat harness."""
    if args.debug:
        _setup_chat_debug()
        _chat_debug("run_harness: entering (debug enabled)")

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
    rendering_dispatch.configure_rendering(console, render_reasoning=thinking_on)

    _chat_debug(f"run_harness: agent={args.agent} model={model} variant={variant} thinking={thinking_on}")

    if ChatApp is None:
        _emit_fatal_error(console, "Missing Dependency",
                          "The --chat flag requires the 'textual' package. Run 'make venv' to install it.")
        return 1

    # Start server
    _chat_debug("run_harness: starting opencode serve")
    runner = ServerRunner()
    try:
        server_info = runner.start(hostname="127.0.0.1", log_level=getattr(args, "log_level", "WARN"))
        _chat_debug(f"run_harness: server started pid={server_info.pid} url={server_info.base_url}")
    except ServerRunnerError as exc:
        _chat_debug(f"run_harness: server start failed: {exc}")
        _emit_fatal_error(console, "Server Error", str(exc))
        _close_chat_debug()
        return 1

    # Create session
    _chat_debug("run_harness: creating session")
    try:
        session_id = create_chat_session(
            server_info.base_url, args.agent, model, server_info.password, str(ROOT),
        )
        _chat_debug(f"run_harness: session created id={session_id}")
    except Exception as exc:
        _chat_debug(f"run_harness: session creation failed: {exc}")
        _emit_fatal_error(console, "Session Error", str(exc))
        runner.stop()
        _close_chat_debug()
        return 1

    # Open the chat transcript (parity with phase mode).
    try:
        transcript = Transcript.for_chat()
        _chat_debug(f"run_harness: opened transcript {transcript.path}")
    except OSError as exc:
        transcript = Transcript.null()
        transcript.path = ROOT / "tmp" / "last-chat-unknown.jsonl"
        _chat_debug(f"run_harness: could not open transcript: {exc}")

    _chat_debug("run_harness: creating ChatApp")
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
            transcript=transcript,
        )
        _chat_debug("run_harness: calling app.run()")
        app.run()
        _chat_debug("run_harness: app.run() returned")
    finally:
        _chat_debug("run_harness: cleaning up")
        if app is not None and getattr(app, "chat_loop", None) is not None:
            _chat_debug("run_harness: stopping chat loop")
            app.chat_loop.stop()
        runner.stop()
        transcript.close()

    # Final summary banner on the restored terminal.
    try:
        rel_path = transcript.path.relative_to(ROOT)
    except ValueError:
        rel_path = transcript.path
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
