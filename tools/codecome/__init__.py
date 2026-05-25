# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeCome core package.

Import concrete helpers from their owning modules, for example:

    from codecome.config import load_prompt
    from codecome.session import create_session
    from codecome.runner import _run_single_attempt

This package initializer intentionally stays lightweight to avoid hidden
import cycles between CLI, runner, rendering, chat, and event modules.
"""

from __future__ import annotations

__all__: list[str] = []
