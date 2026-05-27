# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""WebRenderer - compact rendering for web fetch/search tool calls."""

from __future__ import annotations

from typing import Any

from rendering.tools.base import ToolRenderer


class WebRenderer(ToolRenderer):
    tool_names = ("webfetch", "web-search", "websearch")

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        inp = state.get("input")
        if not isinstance(inp, dict):
            return False

        normalized = tool_name.strip().lower()
        status = str(state.get("status", "unknown"))
        output = state.get("output")
        output_text = "" if output is None else str(output).strip()

        if normalized == "webfetch":
            title = "Web Fetch"
            subject = str(inp.get("url", "")).strip() or "(no URL)"
            details = []
            if inp.get("format"):
                details.append(f"format={inp.get('format')}")
            if inp.get("timeout"):
                details.append(f"timeout={inp.get('timeout')}s")
        else:
            title = "Web Search"
            subject = str(inp.get("query", "")).strip() or "(no query)"
            details = []

        preview = self._preview(output_text, 1200)
        if self.rich:
            return self._render_rich(title, subject, details, status, preview)
        return self._render_plain(title, subject, details, status, preview)

    @staticmethod
    def _preview(text: str, max_chars: int) -> str:
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + f"\n... ({len(text) - max_chars} chars truncated)"

    def _render_rich(self, title: str, subject: str, details: list[str], status: str, preview: str) -> bool:
        from rich.console import Group
        from rich.panel import Panel
        from rich.text import Text

        border = "green" if status == "completed" else "yellow"
        sections: list[Any] = [Text(subject, style="bold cyan")]
        if details:
            sections.append(Text("  " + "  ".join(details), style="dim"))
        if preview:
            sections.append(Text())
            sections.append(Text(preview, style="dim"))

        self.sink.write(Panel(Group(*sections), title=f"{title} [{status}]", border_style=border, expand=True))
        return True

    def _render_plain(self, title: str, subject: str, details: list[str], status: str, preview: str) -> bool:
        import _colors as C

        self.sink.write_text(C.header(f"{title.lower()} [{status}]"))
        self.sink.write_text(f"  {subject}")
        if details:
            self.sink.write_text("  " + "  ".join(details))
        if preview:
            self.sink.write_text(C.info("Output"))
            for line in preview.splitlines():
                self.sink.write_text(f"  {line}")
        return True
