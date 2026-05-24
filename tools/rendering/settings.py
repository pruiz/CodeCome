# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
RenderSettings — all display tunables, initialised from env vars.

Replaces the ~30 module-level globals currently in run-agent.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _truthy_env(name: str) -> bool:
    value = os.environ.get(name)
    return value is not None and value not in {"", "0", "false", "False", "no", "No"}


@dataclass
class RenderSettings:
    """Immutable display tunables for the render pipeline.

    All values are resolved at creation time from environment variables.
    Individual renderers may also accept CLI-override values.

    Create with ``RenderSettings(override_kwargs...)`` for ad-hoc test configs.
    """

    # --- Read ------------------------------------------------------------
    read_display_lines: int = 10
    read_highlight_limit: int = 200 * 1024

    # --- Write -----------------------------------------------------------
    write_content_lines: int = 25
    write_diff_limit: int = 50

    # --- Edit ------------------------------------------------------------
    edit_diff_lines: int = 25

    # --- Apply-patch -----------------------------------------------------
    apply_patch_diff_lines: int = 25
    apply_patch_max_files: int = 10

    # --- Glob ------------------------------------------------------------
    glob_match_cap: int = 10

    # --- Grep ------------------------------------------------------------
    grep_file_cap: int = 50
    grep_line_cap_per_file: int = 5
    grep_total_line_cap: int = 200
    grep_highlight: bool = True

    # --- Reasoning -------------------------------------------------------
    reasoning_max_chars: int = 4000
    render_reasoning: bool = True

    # --- Debug -----------------------------------------------------------
    debug_unknown_events: bool = False

    # --- Sandbox ---------------------------------------------------------
    sandbox_render: bool = True
    sandbox_validate_stderr_lines: int = 20
    sandbox_files_cap: int = 15

    # --- Bash-shim -------------------------------------------------------
    bash_shim_render: bool = True
    bash_shim_ls_strip_long_format: bool = True

    # --- Internal read suppression ---------------------------------------
    internal_read_suppress: bool = True

    # --- Subagent --------------------------------------------------------
    subagent_heartbeat_interval_s: int = 30
    subagent_update_throttle_s: int = 5
    task_prompt_preview_lines: int = 5
    render_subagent_updates: bool = True

    # --- Snapshot cache --------------------------------------------------
    write_cache_enabled: bool = True
    write_cache_cap: int = 200

    @classmethod
    def from_env(cls) -> "RenderSettings":
        """Create settings from environment variables."""
        return cls(
            read_display_lines=int(os.environ.get("CODECOME_READ_DISPLAY_LINES", "10")),
            read_highlight_limit=int(os.environ.get("CODECOME_READ_HIGHLIGHT_LIMIT", str(200 * 1024))),
            write_content_lines=int(os.environ.get("CODECOME_WRITE_CONTENT_LINES", "25")),
            write_diff_limit=int(os.environ.get("CODECOME_WRITE_DIFF_LIMIT", "50")),
            edit_diff_lines=int(os.environ.get("CODECOME_EDIT_DIFF_LINES", "25")),
            apply_patch_diff_lines=int(os.environ.get(
                "CODECOME_APPLY_PATCH_DIFF_LINES",
                str(int(os.environ.get("CODECOME_EDIT_DIFF_LINES", "25"))),
            )),
            apply_patch_max_files=int(os.environ.get("CODECOME_APPLY_PATCH_MAX_FILES", "10")),
            glob_match_cap=int(os.environ.get("CODECOME_GLOB_MATCH_CAP", "10")),
            grep_file_cap=int(os.environ.get("CODECOME_GREP_FILE_CAP", "50")),
            grep_line_cap_per_file=int(os.environ.get("CODECOME_GREP_LINE_CAP_PER_FILE", "5")),
            grep_total_line_cap=int(os.environ.get("CODECOME_GREP_TOTAL_LINE_CAP", "200")),
            grep_highlight=_truthy_env("CODECOME_GREP_HIGHLIGHT")
            if "CODECOME_GREP_HIGHLIGHT" in os.environ
            else True,
            reasoning_max_chars=int(os.environ.get("CODECOME_REASONING_MAX_CHARS", "4000")),
            render_reasoning=_truthy_env("CODECOME_RENDER_REASONING")
            if "CODECOME_RENDER_REASONING" in os.environ
            else True,
            debug_unknown_events=_truthy_env("CODECOME_DEBUG_UNKNOWN_EVENTS")
            if "CODECOME_DEBUG_UNKNOWN_EVENTS" in os.environ
            else False,
            sandbox_render=_truthy_env("CODECOME_SANDBOX_RENDER")
            if "CODECOME_SANDBOX_RENDER" in os.environ
            else True,
            sandbox_validate_stderr_lines=int(os.environ.get("CODECOME_SANDBOX_VALIDATE_STDERR_LINES", "20")),
            sandbox_files_cap=int(os.environ.get("CODECOME_SANDBOX_FILES_CAP", "15")),
            bash_shim_render=_truthy_env("CODECOME_BASH_SHIM_RENDER")
            if "CODECOME_BASH_SHIM_RENDER" in os.environ
            else True,
            bash_shim_ls_strip_long_format=_truthy_env("CODECOME_BASH_SHIM_LS_STRIP_LONG_FORMAT")
            if "CODECOME_BASH_SHIM_LS_STRIP_LONG_FORMAT" in os.environ
            else True,
            internal_read_suppress=_truthy_env("CODECOME_INTERNAL_READ_SUPPRESS")
            if "CODECOME_INTERNAL_READ_SUPPRESS" in os.environ
            else True,
            subagent_heartbeat_interval_s=int(os.environ.get("CODECOME_SUBAGENT_HEARTBEAT_INTERVAL_S", "30")),
            subagent_update_throttle_s=int(os.environ.get("CODECOME_SUBAGENT_UPDATE_THROTTLE_S", "5")),
            task_prompt_preview_lines=int(os.environ.get("CODECOME_TASK_PROMPT_PREVIEW_LINES", "5")),
            render_subagent_updates=_truthy_env("CODECOME_RENDER_SUBAGENT_UPDATES")
            if "CODECOME_RENDER_SUBAGENT_UPDATES" in os.environ
            else True,
            write_cache_enabled=_truthy_env("CODECOME_WRITE_CACHE")
            if "CODECOME_WRITE_CACHE" in os.environ
            else True,
            write_cache_cap=int(os.environ.get("CODECOME_WRITE_CACHE_CAP", "200")),
        )
