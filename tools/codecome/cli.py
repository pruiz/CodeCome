# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CLI entry point and argument parsing for the CodeCome runner."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codecome.version import check_opencode_version
from codecome.config import show_model_table


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
        "--log-level",
        default=os.environ.get("OPENCODE_LOG_LEVEL", "WARN"),
        help="Log level for opencode serve (default: WARN, env: OPENCODE_LOG_LEVEL).",
    )
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
    check_opencode_version()

    parser = build_parser()
    args = parser.parse_args()

    if args.show_model:
        agent_name = args.agent or "recon"
        return show_model_table(agent_name)

    if args.chat:
        from chat.harness import run_harness
        return run_harness(parser, args)

    missing = [n for n in ("phase", "label", "agent", "prompt_file") if getattr(args, n) is None]
    if missing:
        parser.error(
            "the following arguments are required when not using --show-model or --chat: "
            + ", ".join("--" + n.replace("_", "-") for n in missing)
        )

    from codecome.harness import run_phase_mode
    return run_phase_mode(args)
