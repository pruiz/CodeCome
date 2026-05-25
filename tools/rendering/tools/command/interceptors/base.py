# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
CommandExecutionInterceptor — protocol for specialised bash rendering.

Interceptors receive a bash command string and the tool state dict.
They try to recognise and render the output with specialised styling
(sandbox-bootstrap JSON, rtk read/grep, rg, ls, find, tree, …).
When no interceptor matches, the generic bash renderer takes over.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from rendering.tools.base import ToolRenderer  # noqa: E402


@runtime_checkable
class CommandExecutionInterceptor(Protocol):
    """Protocol for specialised command rendering.

    Implementations are called in registration order by the
    CommandRenderer.  The first interceptor that returns True wins.
    """

    name: str

    def try_render(
        self,
        command: str,
        state: dict[str, Any],
        renderer: "ToolRenderer",
    ) -> bool:
        """Attempt to render *command* with *state*.

        Returns True if the interceptor handled the command.
        """
        ...
