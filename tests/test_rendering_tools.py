from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from rendering.context import RenderContext
from rendering.sink import PlainSink, RichConsoleSink
from rendering.settings import RenderSettings
from rendering.cache import SnapshotCache
from rendering.tools.todo import TodoRenderer
from rendering.tools.task import TaskRenderer
from rendering.tools.skill import SkillRenderer
from rendering.tools.permissions import PermissionErrorRenderer


def _ctx(sink_mode="plain"):
    if sink_mode == "rich":
        from rich.console import Console
        sink = RichConsoleSink(Console(record=True))
    else:
        sink = PlainSink()
    return RenderContext(
        root=Path("/fake"),
        sink=sink,
        settings=RenderSettings(),
        cache=SnapshotCache(),
    )


# ——————————————————————————————————————————————
# TodoRenderer
# ——————————————————————————————————————————————

class TestTodoRenderer:
    def test_renders_empty_todos(self, capsys):
        r = TodoRenderer(_ctx("plain"))
        state = {"input": {"todos": []}}
        assert r.render("todowrite", state) is True
        out = capsys.readouterr().out
        assert "todos" in out.lower()
        assert "No todos" in out

    def test_renders_todos_plain(self, capsys):
        r = TodoRenderer(_ctx("plain"))
        state = {
            "input": {
                "todos": [
                    {"content": "Fix bug", "status": "completed", "priority": "high"},
                    {"content": "Write test", "status": "in_progress", "priority": "medium"},
                    {"content": "Deploy", "status": "pending", "priority": "low"},
                ]
            }
        }
        assert r.render("todowrite", state) is True
        out = capsys.readouterr().out
        assert "3 tasks" in out
        assert "Fix bug" in out
        assert "Write test" in out
        assert "Deploy" in out

    def test_renders_todos_rich(self):
        r = TodoRenderer(_ctx("rich"))
        state = {
            "input": {
                "todos": [
                    {"content": "Fix bug", "status": "completed", "priority": "high"},
                ]
            }
        }
        assert r.render("todowrite", state) is True

    def test_returns_false_when_state_not_recognized(self):
        r = TodoRenderer(_ctx("plain"))
        assert r.render("todowrite", {"input": {}}) is False

    def test_extracts_todos_from_output_list(self, capsys):
        r = TodoRenderer(_ctx("plain"))
        state = {
            "output": [
                {"content": "From output", "status": "pending", "priority": "low"},
            ]
        }
        assert r.render("todowrite", state) is True
        out = capsys.readouterr().out
        assert "From output" in out


# ——————————————————————————————————————————————
# TaskRenderer
# ——————————————————————————————————————————————

class TestTaskRenderer:
    def test_renders_task_plain(self, capsys):
        r = TaskRenderer(_ctx("plain"))
        state = {
            "input": {
                "description": "Look for bugs",
                "subagent_type": "auditor",
                "prompt": "Find security issues",
            },
            "status": "completed",
        }
        assert r.render("task", state) is True
        out = capsys.readouterr().out
        assert "Look for bugs" in out
        assert "auditor" in out
        assert "completed" in out

    def test_renders_task_rich(self):
        r = TaskRenderer(_ctx("rich"))
        state = {
            "input": {
                "description": "Look for bugs",
                "prompt": "line1\nline2\nline3",
            },
            "status": "completed",
        }
        assert r.render("task", state) is True

    def test_task_prompt_preview_truncates(self, capsys):
        r = TaskRenderer(_ctx("plain"))
        settings = RenderSettings(task_prompt_preview_lines=2)
        r.context.settings = settings
        state = {
            "input": {
                "description": "Audit",
                "prompt": "line1\nline2\nline3\nline4",
            },
            "status": "in_progress",
        }
        assert r.render("task", state) is True
        out = capsys.readouterr().out
        assert "line1" in out
        assert "line2" in out
        assert "more lines" in out

    def test_returns_false_for_non_dict_input(self):
        r = TaskRenderer(_ctx("plain"))
        assert r.render("task", {"input": "not a dict"}) is False

    def test_renders_output_when_present(self, capsys):
        r = TaskRenderer(_ctx("plain"))
        state = {
            "input": {"description": "X", "prompt": "Y"},
            "output": "Task result",
            "status": "completed",
        }
        assert r.render("task", state) is True
        out = capsys.readouterr().out
        assert "Task result" in out

    def test_output_truncated_over_200_chars(self, capsys):
        r = TaskRenderer(_ctx("plain"))
        long = "x" * 300
        state = {
            "input": {"description": "X", "prompt": "Y"},
            "output": long,
            "status": "completed",
        }
        assert r.render("task", state) is True
        out = capsys.readouterr().out
        assert "..." in out
        assert long not in out


# ——————————————————————————————————————————————
# SkillRenderer
# ——————————————————————————————————————————————

class TestSkillRenderer:
    def test_renders_known_skill_plain(self, capsys):
        r = SkillRenderer(_ctx("plain"))
        state = {"input": {"name": "web-security"}}
        assert r.render("skill", state) is True
        out = capsys.readouterr().out
        assert "web-security" in out

    def test_renders_unknown_skill_plain(self, capsys):
        r = SkillRenderer(_ctx("plain"))
        state = {"input": {"name": ""}}
        assert r.render("skill", state) is True
        out = capsys.readouterr().out
        assert "unknown" in out.lower()

    def test_renders_skill_rich(self):
        r = SkillRenderer(_ctx("rich"))
        state = {"input": {"name": "web-security"}}
        assert r.render("skill", state) is True

    def test_returns_false_for_non_dict_input(self):
        r = SkillRenderer(_ctx("plain"))
        assert r.render("skill", {"input": "nope"}) is False


# ——————————————————————————————————————————————
# PermissionErrorRenderer
# ——————————————————————————————————————————————

class TestPermissionErrorRenderer:
    def test_renders_permission_error_plain(self, capsys):
        r = PermissionErrorRenderer(_ctx("plain"))
        r.render_message("tool permission rejected: write")
        out = capsys.readouterr().out
        assert "Permission Denied" in out
        assert "write" in out

    def test_renders_permission_error_rich(self):
        r = PermissionErrorRenderer(_ctx("rich"))
        r.render_message("tool permission rejected: bash")
        # Should not raise
