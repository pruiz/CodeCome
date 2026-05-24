# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
PermissionErrorRenderer — bold red panel for auto-rejected tool permissions.
"""

from __future__ import annotations

from rendering.base import BaseRenderer


class PermissionErrorRenderer(BaseRenderer):
    """Draws a permission-denied panel (rich) or error line (plain).

    Unlike tool renderers, this is called directly from the event loop
    when a permission is auto-rejected — it receives a plain message
    string rather than a tool state dict.
    """

    def render_message(self, message: str) -> None:
        if self.rich:
            from rich.panel import Panel
            from rich.text import Text
            self.sink.write(
                Panel(
                    Text(message, style="bold red"),
                    title="Permission Denied",
                    border_style="red",
                    expand=True,
                )
            )
        else:
            import _colors as C
            self.sink.write_text(C.fail("Permission Denied"))
            self.sink.write_text(C.fail(f"  {message}"))
