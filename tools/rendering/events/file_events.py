# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""File event renderers — file.edited and file.watcher.updated."""

from __future__ import annotations

import os
from typing import Any

from rendering.events.base import EventRenderer
from rendering.utils import relativize_path
import _colors as C


def _norm(path: str) -> str:
    return os.path.normpath(os.path.abspath(path)) if path else path


class FileEditedRenderer(EventRenderer):
    event_types = ("file.edited",)

    def render(self, event: dict[str, Any]) -> bool:
        file_path = str(event.get("properties", {}).get("file", ""))
        if not file_path:
            return False

        normed = _norm(file_path)

        if normed in self.context.inflight_write_files:
            return True

        rel = relativize_path(file_path, self.context.root)
        if self.rich:
            from rich.text import Text
            self.sink.write(Text(f"  edited  {rel}", style="dim"))
        else:
            self.sink.write_text(C.info(f"  edited  {rel}"))

        self.context.cache.reread(file_path)
        return True


class FileWatcherRenderer(EventRenderer):
    event_types = ("file.watcher.updated",)

    def render(self, event: dict[str, Any]) -> bool:
        file_path = str(event.get("properties", {}).get("file", ""))
        watcher_event = str(event.get("properties", {}).get("event", ""))

        if not self.context.settings.debug_unknown_events:
            return True

        if not file_path:
            return False

        rel = relativize_path(file_path, self.context.root)
        label = f"  watcher  {watcher_event}  {rel}"
        if self.rich:
            from rich.text import Text
            self.sink.write(Text(label, style="dim"))
        else:
            self.sink.write_text(C.info(label))
        return True
