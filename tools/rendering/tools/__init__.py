# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Tool renderer classes — one per OpenCode tool family.
"""

from __future__ import annotations

from rendering.tools.base import FallbackToolRenderer, ToolRenderer
from rendering.tools.permissions import PermissionErrorRenderer
from rendering.tools.skill import SkillRenderer
from rendering.tools.task import TaskRenderer
from rendering.tools.todo import TodoRenderer

__all__ = [
    "FallbackToolRenderer",
    "PermissionErrorRenderer",
    "SkillRenderer",
    "TaskRenderer",
    "TodoRenderer",
    "ToolRenderer",
]
