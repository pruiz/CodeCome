# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Command execution interceptors — specialised rendering for
CodeCome-aware bash invocations (sandbox-bootstrap, rtk, rg, ls, …).
"""

from __future__ import annotations

from rendering.tools.interceptors.base import CommandExecutionInterceptor
from rendering.tools.interceptors.rtk_grep import RtkGrepInterceptor
from rendering.tools.interceptors.rtk_read import RtkReadInterceptor
from rendering.tools.interceptors.sandbox_bootstrap import SandboxBootstrapInterceptor
from rendering.tools.interceptors.shell_listing import ShellListingInterceptor

__all__ = [
    "CommandExecutionInterceptor",
    "RtkGrepInterceptor",
    "RtkReadInterceptor",
    "SandboxBootstrapInterceptor",
    "ShellListingInterceptor",
]
