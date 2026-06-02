# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""PatchRenderer — renders session-level patch events (hash + file list)."""

from __future__ import annotations

from typing import Any

from rendering.events.base import EventRenderer
from rendering.utils import relativize_path
import _colors as C


class PatchRenderer(EventRenderer):
    event_types = ("patch",)

    def render(self, event: dict[str, Any]) -> bool:
        part = event.get("part", {})
        hash_ = part.get("hash", "")
        raw_files = part.get("files")
        files: list[str] = raw_files if isinstance(raw_files, list) else []
        short_hash = hash_[:8] if hash_ else ""

        if not files and not short_hash:
            return False

        if self.rich:
            return self._render_rich(short_hash, files)
        else:
            return self._render_plain(short_hash, files)

    def _render_rich(self, hash_: str, files: list[str]) -> bool:
        from rich.console import Group
        from rich.panel import Panel
        from rich.text import Text

        settings = self.context.settings
        cache = self.context.cache

        sections: list[Any] = []
        shown = files[:settings.apply_patch_max_files]
        for fpath in shown:
            rel = relativize_path(fpath, self.context.root)
            sections.append(Text(f"  {rel}", style="dim"))

        remaining = len(files) - len(shown)
        if remaining > 0:
            sections.append(Text(f"  ... and {remaining} more file(s)", style="dim"))

        title = f"Session patch  hash={hash_}" if hash_ else "Session patch"
        nfile = len(files)
        if nfile:
            title += f"  {nfile} file{'s' if nfile != 1 else ''}"

        self.sink.write(Panel(
            Group(*sections) if sections else Text("  (no files)"),
            title=title,
            border_style="green" if files else "yellow",
            expand=True,
        ))

        for fpath in files:
            cache.reread(fpath)
        return True

    def _render_plain(self, hash_: str, files: list[str]) -> bool:
        settings = self.context.settings
        cache = self.context.cache

        nfile = len(files)
        hash_part = f"  hash={hash_}" if hash_ else ""
        file_part = f"  {nfile} file{'s' if nfile != 1 else ''}" if nfile else ""
        self.sink.write_text(C.header(f"patch{hash_part}{file_part}"))

        shown = files[:settings.apply_patch_max_files]
        for fpath in shown:
            rel = relativize_path(fpath, self.context.root)
            self.sink.write_text(f"  {rel}")

        remaining = len(files) - len(shown)
        if remaining > 0:
            self.sink.write_text(f"  ... and {remaining} more file(s)")

        for fpath in files:
            cache.reread(fpath)
        return True
