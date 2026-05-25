# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Command execution interceptors — specialised rendering for
CodeCome-aware bash invocations (sandbox-bootstrap, rtk, rg, ls, …).
"""

from __future__ import annotations

from rendering.tools.command.interceptors.base import CommandExecutionInterceptor
from rendering.tools.command.interceptors.rtk_grep import RtkGrepInterceptor
from rendering.tools.command.interceptors.rtk_read import RtkReadInterceptor
from rendering.tools.command.interceptors.sandbox_bootstrap import SandboxBootstrapInterceptor
from rendering.tools.command.interceptors.shell_listing import ShellListingInterceptor

__all__ = [
    "CommandExecutionInterceptor",
    "RtkGrepInterceptor",
    "RtkReadInterceptor",
    "SandboxBootstrapInterceptor",
    "ShellListingInterceptor",
]
