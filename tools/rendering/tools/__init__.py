# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Tool renderer classes — one per OpenCode tool family.
"""

from __future__ import annotations

from rendering.tools.apply_patch import ApplyPatchRenderer
from rendering.tools.base import FallbackToolRenderer, ToolRenderer
from rendering.tools.command import CommandRenderer
from rendering.tools.edit import EditRenderer
from rendering.tools.glob import GlobRenderer
from rendering.tools.grep import GrepRenderer
from rendering.tools.permissions import PermissionErrorRenderer
from rendering.tools.read import ReadRenderer
from rendering.tools.skill import SkillRenderer
from rendering.tools.task import TaskRenderer
from rendering.tools.todo import TodoRenderer
from rendering.tools.write import WriteRenderer

__all__ = [
    "ApplyPatchRenderer",
    "CommandRenderer",
    "EditRenderer",
    "FallbackToolRenderer",
    "GlobRenderer",
    "GrepRenderer",
    "PermissionErrorRenderer",
    "ReadRenderer",
    "SkillRenderer",
    "TaskRenderer",
    "TodoRenderer",
    "ToolRenderer",
    "WriteRenderer",
]
