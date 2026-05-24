# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
CodeCome core package: config, session, runner, graceful, transcript, version.
"""

from __future__ import annotations

from codecome.config import (
    load_prompt,
    resolve_color_mode,
    resolve_model_and_variant,
    resolve_runtime_model_for_banner,
    resolve_thinking_decision,
    show_model_table,
    truthy_env,
)
from codecome.graceful import (
    build_frontmatter_resume_prompt,
    build_phase_resume_prompt,
    build_resume_command,
    check_phase_graceful_completion,
    phase_checklist_lines,
)
from codecome.session import (
    create_chat_session,
    create_session,
    send_prompt_to_session,
)
from codecome.transcript import (
    close_transcript,
    open_chat_transcript,
    open_phase_transcript,
)
from codecome.version import check_opencode_version

__all__ = [
    # config
    "truthy_env",
    "resolve_color_mode",
    "load_prompt",
    "resolve_model_and_variant",
    "resolve_runtime_model_for_banner",
    "resolve_thinking_decision",
    "show_model_table",
    # session
    "create_session",
    "create_chat_session",
    "send_prompt_to_session",
    # graceful
    "check_phase_graceful_completion",
    "phase_checklist_lines",
    "build_phase_resume_prompt",
    "build_frontmatter_resume_prompt",
    "build_resume_command",
    # transcript
    "open_phase_transcript",
    "open_chat_transcript",
    "close_transcript",
    # version
    "check_opencode_version",
]
