# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
ApplyPatchRenderer — multi-file patch panel with envelope/JSON/unified-diff parsing.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from rendering.tools.base import ToolRenderer
from rendering.utils import is_likely_error, relativize_path, truncate_diff

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_APPLY_PATCH_HEADER_RE = re.compile(
    r"^\*\*\*[ \t]*(Begin Patch|End Patch|Update File|Add File|Delete File|Rename File|Move File):?[ \t]*(.*)",
    re.MULTILINE,
)

_PATCH_TEXT_KEYS = ("patchText", "patch_text", "patch", "input", "content", "diff", "body")


# ---------------------------------------------------------------------------
# ParsedFilePatch
# ---------------------------------------------------------------------------

@dataclass
class _ParsedFilePatch:
    op: str  # add, update, delete, rename, unknown
    path: str
    old_path: str
    hunks: str  # unified-diff-ready text
    added: int
    removed: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_string(d: dict[str, Any], keys: tuple[str, ...]) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def _parse_apply_patch_envelope(text: str, root) -> list[_ParsedFilePatch]:
    results: list[_ParsedFilePatch] = []
    parts = _APPLY_PATCH_HEADER_RE.split(text)
    i = 1
    while i + 2 <= len(parts):
        directive = parts[i].strip()
        file_path = parts[i + 1].strip()
        body = parts[i + 2] if i + 2 < len(parts) else ""
        i += 3

        if directive in ("Begin Patch", "End Patch"):
            continue

        op_map = {
            "Update File": "update", "Add File": "add", "Delete File": "delete",
            "Rename File": "rename", "Move File": "rename",
        }
        op = op_map.get(directive, "unknown")
        old_path = ""
        if op == "rename" and " -> " in file_path:
            old_path, file_path = file_path.split(" -> ", 1)
            old_path = old_path.strip()
            file_path = file_path.strip()

        body_lines = body.split("\n")
        added = sum(1 for l in body_lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in body_lines if l.startswith("-") and not l.startswith("---"))

        rel = relativize_path(file_path, root)
        old_rel = relativize_path(old_path, root) if old_path else rel
        if op == "add":
            header = f"--- /dev/null\n+++ b/{rel}\n"
        elif op == "delete":
            header = f"--- a/{rel}\n+++ /dev/null\n"
        else:
            header = f"--- a/{old_rel}\n+++ b/{rel}\n"

        hunks = header + body.strip() + "\n"
        results.append(_ParsedFilePatch(op=op, path=file_path, old_path=old_path,
                                        hunks=hunks, added=added, removed=removed))
    return results


def _parse_apply_patch_json_list(patches: list[dict[str, Any]], root) -> list[_ParsedFilePatch]:
    results: list[_ParsedFilePatch] = []
    for p in patches:
        path = str(p.get("path", p.get("file", "")))
        diff_text = _first_string(p, ("diff", "patch", "patchText", "patch_text", "content", "body"))
        lines = diff_text.split("\n")
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        rel = relativize_path(path, root)
        header = f"--- a/{rel}\n+++ b/{rel}\n"
        hunks = header + diff_text.strip() + "\n"
        results.append(_ParsedFilePatch(op="update", path=path, old_path="",
                                        hunks=hunks, added=added, removed=removed))
    return results


def _extract_apply_patch_payload(state: dict[str, Any], root) -> tuple[str, list[_ParsedFilePatch], str]:
    inp = state.get("input")
    output = state.get("output")
    output_str = str(output) if output is not None else ""

    raw_text = ""
    if isinstance(inp, dict):
        raw_text = _first_string(inp, _PATCH_TEXT_KEYS)
        if not raw_text and isinstance(inp.get("patches"), list):
            patches = _parse_apply_patch_json_list(inp["patches"], root)
            return "", patches, output_str
    elif isinstance(inp, str):
        raw_text = inp

    if not raw_text:
        return "", [], output_str

    if "*** " in raw_text:
        patches = _parse_apply_patch_envelope(raw_text, root)
        if patches:
            return raw_text, patches, output_str

    if raw_text.lstrip().startswith(("--- ", "diff --git")):
        lines = raw_text.split("\n")
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        patches = [_ParsedFilePatch(op="unknown", path="(patch)", old_path="",
                                    hunks=raw_text, added=added, removed=removed)]
        return raw_text, patches, output_str

    return raw_text, [], output_str


# ---------------------------------------------------------------------------
# ApplyPatchRenderer
# ---------------------------------------------------------------------------

class ApplyPatchRenderer(ToolRenderer):
    tool_names = ("apply_patch", "applypatch", "apply-patch")

    def render(self, tool_name: str, state: dict[str, Any]) -> bool:
        raw_text, patches, output_str = _extract_apply_patch_payload(state, self.context.root)
        status = str(state.get("status", ""))

        if not patches and not raw_text:
            return False

        if self.rich:
            return self._render_rich(raw_text, patches, output_str, status)
        else:
            return self._render_plain(raw_text, patches, output_str, status)

    # ------------------------------------------------------------------
    # Rich
    # ------------------------------------------------------------------

    def _render_rich(self, raw_text: str, patches: list[_ParsedFilePatch],
                     output_str: str, status: str) -> bool:
        from rich.console import Group
        from rich.panel import Panel
        from rich.syntax import Syntax
        from rich.text import Text

        settings = self.context.settings
        cache = self.context.cache
        is_err = is_likely_error(output_str)
        border = "red" if is_err else ("green" if status == "completed" else "yellow")

        sections: list[Any] = []

        if not patches:
            byte_size = len(raw_text.encode("utf-8", errors="replace"))
            line_count = raw_text.count("\n")
            sections.append(Text(f"Raw patch: {line_count} lines, {byte_size} bytes", style="dim"))
            sections.append(Text())
            truncated_lines = raw_text.split("\n")[:settings.write_diff_limit]
            leftover = max(0, raw_text.count("\n") - settings.write_diff_limit)
            sections.append(Syntax("\n".join(truncated_lines), "diff", theme="monokai", word_wrap=True))
            if leftover > 0:
                sections.append(Text(f"... {leftover} more lines", style="dim"))
        else:
            total_added = sum(p.added for p in patches)
            total_removed = sum(p.removed for p in patches)
            sections.append(Text(f"{len(patches)} file(s) changed: +{total_added} -{total_removed}", style="dim"))
            sections.append(Text())

            shown = patches[:settings.apply_patch_max_files]
            for fp in shown:
                rel = relativize_path(fp.path, self.context.root)
                label = f"{fp.op:<8} {rel}  +{fp.added} -{fp.removed}"
                sections.append(Text(label, style="bold cyan"))

                diff_lines_list = fp.hunks.split("\n")
                diff_with_nl = [l + "\n" for l in diff_lines_list if l or diff_lines_list[-1:] != [l]]
                truncated, leftover = truncate_diff(diff_with_nl, settings.apply_patch_diff_lines)
                diff_text = "".join(truncated)
                if diff_text.strip():
                    sections.append(Syntax(diff_text, "diff", theme="monokai", word_wrap=True))
                if leftover > 0:
                    sections.append(Text(f"... {leftover} more lines", style="dim"))
                sections.append(Text())

            if len(patches) > settings.apply_patch_max_files:
                remaining = len(patches) - settings.apply_patch_max_files
                sections.append(Text(f"... and {remaining} more file(s)", style="dim"))

        if output_str.strip():
            sections.append(Text(output_str.strip(), style="red" if is_err else "green"))

        self.sink.write(Panel(Group(*sections), title="Apply patch", border_style=border, expand=True))

        if status == "completed" and not is_err:
            for fp in patches:
                full_path = fp.path
                if not os.path.isabs(full_path):
                    full_path = os.path.join(str(self.context.root), full_path)
                cache.reread(full_path)
        return True

    # ------------------------------------------------------------------
    # Plain
    # ------------------------------------------------------------------

    def _render_plain(self, raw_text: str, patches: list[_ParsedFilePatch],
                      output_str: str, status: str) -> bool:
        import _colors as C

        settings = self.context.settings
        cache = self.context.cache
        is_err = is_likely_error(output_str)

        if not patches:
            line_count = raw_text.count("\n")
            byte_size = len(raw_text.encode("utf-8", errors="replace"))
            self.sink.write_text(C.header(f"apply_patch (raw: {line_count} lines, {byte_size} bytes)"))
            truncated_lines = raw_text.split("\n")[:settings.write_diff_limit]
            for line in truncated_lines:
                self.sink.write_text(f"  {line}")
            leftover = max(0, raw_text.count("\n") - settings.write_diff_limit)
            if leftover > 0:
                self.sink.write_text(f"  ... {leftover} more lines")
        else:
            total_added = sum(p.added for p in patches)
            total_removed = sum(p.removed for p in patches)
            self.sink.write_text(C.header(f"apply_patch ({len(patches)} file(s): +{total_added} -{total_removed})"))

            shown = patches[:settings.apply_patch_max_files]
            for fp in shown:
                rel = relativize_path(fp.path, self.context.root)
                self.sink.write_text(f"  {fp.op:<8} {rel}  +{fp.added} -{fp.removed}")
                diff_with_nl = [l + "\n" for l in fp.hunks.split("\n")]
                truncated, leftover = truncate_diff(diff_with_nl, settings.apply_patch_diff_lines)
                for line in truncated:
                    self.sink.write_text(f"    {line}", end="")
                if leftover > 0:
                    self.sink.write_text(f"    ... {leftover} more lines")

            if len(patches) > settings.apply_patch_max_files:
                remaining = len(patches) - settings.apply_patch_max_files
                self.sink.write_text(f"  ... and {remaining} more file(s)")

        if output_str.strip():
            if is_err:
                self.sink.write_text(C.fail(output_str.strip()))
            else:
                self.sink.write_text(C.ok(output_str.strip()))

        if status == "completed" and not is_err:
            for fp in patches:
                full_path = fp.path
                if not os.path.isabs(full_path):
                    full_path = os.path.join(str(self.context.root), full_path)
                cache.reread(full_path)
        return True
