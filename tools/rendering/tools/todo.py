# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
TodoRenderer — styled panel for todowrite tool calls.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from rendering.tools.base import ToolRenderer

_TODO_STATUS_ICONS = {
    "completed": "\u2714",
    "in_progress": "\u25cf",
    "pending": "\u25cb",
    "cancelled": "\u2716",
}

_TODO_STATUS_ASCII = {
    "completed": "[x]",
    "in_progress": "[~]",
    "pending": "[ ]",
    "cancelled": "[-]",
}

_TODO_PRIORITY_LETTERS = {
    "high": "H",
    "medium": "M",
    "low": "L",
}


def _extract_todos(state: dict[str, Any]) -> list[dict[str, str]] | None:
    output = state.get("output")
    if isinstance(output, list):
        items = output
    else:
        input_data = state.get("input")
        if isinstance(input_data, dict) and isinstance(input_data.get("todos"), list):
            items = input_data["todos"]
        else:
            return None

    result: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            return None
        result.append({
            "content": str(item.get("content", "")),
            "status": str(item.get("status", "?")),
            "priority": str(item.get("priority", "?")),
        })
    return result


def _todo_summary(todos: list[dict[str, str]]) -> str:
    counts = Counter(t["status"] for t in todos)
    parts = [f"{len(todos)} tasks"]
    for status in ("completed", "in_progress", "pending", "cancelled"):
        count = counts.get(status, 0)
        if count > 0:
            label = status.replace("_", " ")
            parts.append(f"{count} {label}")
    return " \u00b7 ".join(parts)


def _todo_border_style(todos: list[dict[str, str]]) -> str:
    statuses = {t["status"] for t in todos}
    if statuses == {"completed"}:
        return "green"
    if "in_progress" in statuses:
        return "yellow"
    return "dim"


class TodoRenderer(ToolRenderer):
    tool_names = ("todowrite",)

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        todos = _extract_todos(state)
        if todos is None:
            return False

        if self.rich:
            return self._render_rich(todos)
        else:
            return self._render_plain(todos)

    def _render_rich(self, todos: list[dict[str, str]]) -> bool:
        from rich.console import Group
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        if not todos:
            self.sink.write(Panel(Text("No todos.", style="dim"), title="Todos", border_style="dim", expand=True))
            return True

        summary = Text(_todo_summary(todos))
        border = _todo_border_style(todos)

        table = Table(show_header=False, show_edge=False, padding=(0, 1), expand=True)
        table.add_column(width=2, no_wrap=True)
        table.add_column(width=1, no_wrap=True)
        table.add_column(ratio=1)

        status_styles = {
            "completed": "bold green",
            "in_progress": "yellow",
            "pending": "dim",
            "cancelled": "dim strike",
        }
        priority_styles = {
            "high": "red",
            "medium": "yellow",
            "low": "dim",
        }

        for todo in todos:
            status = todo["status"]
            priority = todo["priority"]

            icon = _TODO_STATUS_ICONS.get(status, "?")
            icon_style = status_styles.get(status, "dim")
            pri_letter = _TODO_PRIORITY_LETTERS.get(priority, "?")
            pri_style = priority_styles.get(priority, "dim")

            table.add_row(
                Text(icon, style=icon_style),
                Text(pri_letter, style=pri_style),
                Text(todo["content"], style=status_styles.get(status, "")),
            )

        body = Group(summary, Text(), table)
        self.sink.write(Panel(body, title="Todos", border_style=border, expand=True))
        return True

    def _render_plain(self, todos: list[dict[str, str]]) -> bool:
        import _colors as C
        if not todos:
            self.sink.write_text(C.header("todos"))
            self.sink.write_text("  No todos.")
            return True

        self.sink.write_text(C.header("todos"))
        self.sink.write_text(f"  {_todo_summary(todos)}")
        for todo in todos:
            status = todo["status"]
            priority = todo["priority"]
            checkbox = _TODO_STATUS_ASCII.get(status, "[?]")
            pri_letter = _TODO_PRIORITY_LETTERS.get(priority, "?")
            content = todo["content"].replace("\n", " ")
            self.sink.write_text(f"  {checkbox} {pri_letter} {content}")
        return True
