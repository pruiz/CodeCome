# Copyright (C) 2025-2026 Pablo Ruiz Garcia <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL language capability metadata."""

from __future__ import annotations


BUILD_MODES_BY_LANGUAGE: dict[str, set[str]] = {
    "python": {"none"},
    "javascript-typescript": {"none"},
    "ruby": {"none"},
    "c-cpp": {"manual", "autobuild"},
    "go": {"manual", "autobuild"},
    "csharp": {"none", "manual", "autobuild"},
    "java-kotlin": {"none", "manual", "autobuild"},
    "swift": {"manual", "autobuild"},
}


def supported_build_modes(language_id: str) -> set[str]:
    """Return supported CodeQL build modes for *language_id*."""
    return set(BUILD_MODES_BY_LANGUAGE.get(language_id, set()))


def is_supported_language(language_id: str) -> bool:
    """Return whether *language_id* is known to this CodeQL integration."""
    return language_id in BUILD_MODES_BY_LANGUAGE
