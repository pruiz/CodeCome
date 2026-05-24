# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
SnapshotCache — file content snapshot for diff computation.

Isolated state so renderers (read/write/edit/apply_patch) can show
diffs without relying on module-level globals.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from pathlib import Path


class SnapshotCache:
    """LRU cache of file content snapshots keyed by absolute path.

    Used by Write/Edit/ApplyPatch renderers to compute what changed.
    """

    def __init__(self, *, enabled: bool = True, max_entries: int = 200) -> None:
        self._enabled = enabled
        self._max = max_entries
        self._entries: OrderedDict[str, tuple[str, float]] = OrderedDict()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set(self, path: str, content: str) -> None:
        """Cache *content* for *path*, recording its current mtime."""
        if not self._enabled:
            return
        mtime = self._current_mtime(path)
        if mtime is None:
            return
        self._entries[path] = (content, mtime)
        self._entries.move_to_end(path)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def get(self, path: str) -> str | None:
        """Return cached content for *path*, or None."""
        if not self._enabled:
            return None
        entry = self._entries.get(path)
        if entry is None:
            return None
        return entry[0]

    def invalidate_stale(self) -> None:
        """Remove entries whose file has been deleted or modified."""
        if not self._enabled:
            return
        stale = []
        for p, (_, recorded_mtime) in self._entries.items():
            actual = self._current_mtime(p)
            if actual is None or actual != recorded_mtime:
                stale.append(p)
        for p in stale:
            del self._entries[p]

    def reread(self, path: str) -> None:
        """Invalidate and re-read *path* from disk."""
        if not self._enabled:
            return
        if path in self._entries:
            del self._entries[path]
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
            self.set(path, content)
        except OSError:
            pass

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _current_mtime(path: str) -> float | None:
        try:
            return os.stat(path).st_mtime
        except OSError:
            return None
