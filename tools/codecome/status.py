# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Shared run status values for phase harnesses."""

from __future__ import annotations

from enum import IntEnum


class RunStatus(IntEnum):
    """Process-compatible status codes used by phase orchestration."""

    OK = 0
    ERROR = 1
    INCOMPLETE = 2
    SERVER_UNREACHABLE = 3
    SESSION_STALLED = 4
    INTERRUPTED = 130


def normalize_status(value: int | RunStatus) -> RunStatus:
    """Return a known RunStatus, mapping unknown failures to ERROR."""
    if isinstance(value, RunStatus):
        return value
    try:
        return RunStatus(value)
    except ValueError:
        return RunStatus.ERROR
