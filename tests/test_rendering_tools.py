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
from rendering.tools.read import ReadRenderer
from rendering.tools.write import WriteRenderer
from rendering.tools.edit import EditRenderer
from rendering.tools.apply_patch import ApplyPatchRenderer
from rendering.tools.glob import GlobRenderer
from rendering.tools.grep import GrepRenderer
from rendering.tools.command import CommandRenderer
from rendering.tools.command.interceptors.sandbox_bootstrap import SandboxBootstrapInterceptor
from rendering.tools.command.interceptors.rtk_read import RtkReadInterceptor
from rendering.tools.command.interceptors.rtk_grep import RtkGrepInterceptor
from rendering.tools.command.interceptors.shell_listing import ShellListingInterceptor


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


# ——————————————————————————————————————————————
# ReadRenderer
# ——————————————————————————————————————————————

class TestReadRenderer:
    def _framed(self, path, content, kind="file"):
        return f"<path>{path}</path>\n<type>{kind}</type>\n<content>\n{content}\n</content>"

    def test_renders_file_plain(self, capsys):
        r = ReadRenderer(_ctx("plain"))
        state = {
            "input": {"filePath": "/fake/src/main.py"},
            "output": self._framed("src/main.py", "print('hello')"),
            "status": "completed",
        }
        assert r.render("read", state) is True
        out = capsys.readouterr().out
        assert "main.py" in out
        assert "print" in out

    def test_renders_file_rich(self):
        r = ReadRenderer(_ctx("rich"))
        state = {
            "input": {"filePath": "/fake/src/main.py"},
            "output": self._framed("src/main.py", "print('hello')"),
            "status": "completed",
        }
        assert r.render("read", state) is True

    def test_renders_directory_plain(self, capsys):
        r = ReadRenderer(_ctx("plain"))
        state = {
            "input": {"filePath": "/fake/src"},
            "output": (
                "<path>src</path>\n"
                "<type>directory</type>\n"
                "<entries>\n"
                "main.py\n"
                "utils/\n"
                "(2 entries total)\n"
                "</entries>"
            ),
            "status": "completed",
        }
        assert r.render("read", state) is True
        out = capsys.readouterr().out
        assert "main.py" in out
        assert "utils/" in out

    def test_renders_error_output_plain(self, capsys):
        r = ReadRenderer(_ctx("plain"))
        state = {
            "input": {"filePath": "/fake/missing.txt"},
            "output": "Error: no such file or directory",
            "status": "error",
        }
        assert r.render("read", state) is True
        out = capsys.readouterr().out
        assert "missing.txt" in out

    def test_returns_false_for_missing_file_path(self):
        r = ReadRenderer(_ctx("plain"))
        assert r.render("read", {"input": {"filePath": ""}, "output": "x"}) is False

    def test_returns_false_for_non_dict_input(self):
        r = ReadRenderer(_ctx("plain"))
        assert r.render("read", {"input": "not a dict", "output": "x"}) is False

    def test_suppresses_internal_read(self, capsys):
        r = ReadRenderer(_ctx("plain"))
        state = {
            "input": {"filePath": "/fake/AGENTS.md"},
            "output": self._framed("AGENTS.md", "# Agents"),
            "status": "completed",
        }
        assert r.render("read", state) is True
        out = capsys.readouterr().out
        assert "workspace doc" in out


# ——————————————————————————————————————————————
# WriteRenderer
# ——————————————————————————————————————————————

class TestWriteRenderer:
    def test_renders_new_file_plain(self, capsys):
        r = WriteRenderer(_ctx("plain"))
        state = {
            "input": {"filePath": "/fake/new.txt", "content": "hello world\n"},
            "output": "Wrote file new.txt",
            "status": "completed",
        }
        assert r.render("write", state) is True
        out = capsys.readouterr().out
        assert "new.txt" in out
        assert "new file" in out.lower()
        assert "hello world" in out

    def test_renders_new_file_rich(self):
        r = WriteRenderer(_ctx("rich"))
        state = {
            "input": {"filePath": "/fake/new.txt", "content": "hello world\n"},
            "output": "Wrote file new.txt",
            "status": "completed",
        }
        assert r.render("write", state) is True

    def test_renders_diff_plain(self, capsys, tmp_path):
        existing = tmp_path / "existing.txt"
        existing.write_text("old line\n")
        ctx = _ctx("plain")
        ctx.cache.set(str(existing), "old line\n")
        r = WriteRenderer(ctx)
        state = {
            "input": {"filePath": str(existing), "content": "new line\n"},
            "output": "Wrote file existing.txt",
            "status": "completed",
        }
        assert r.render("write", state) is True
        out = capsys.readouterr().out
        assert "diff:" in out
        assert "-" in out
        assert "+" in out

    def test_renders_error_plain(self, capsys):
        r = WriteRenderer(_ctx("plain"))
        state = {
            "input": {"filePath": "/fake/bad.txt", "content": "x"},
            "output": "Permission denied",
            "status": "error",
        }
        assert r.render("write", state) is True
        out = capsys.readouterr().out
        assert "Permission denied" in out

    def test_returns_false_for_missing_file_path(self):
        r = WriteRenderer(_ctx("plain"))
        assert r.render("write", {"input": {"filePath": ""}, "output": "x"}) is False

    def test_returns_false_for_non_dict_input(self):
        r = WriteRenderer(_ctx("plain"))
        assert r.render("write", {"input": "not a dict"}) is False

    def test_renders_new_file_rich_fallback_on_small_highlight_limit(self):
        from rich.console import Console
        from rendering.context import RenderContext
        from rendering.sink import RichConsoleSink
        from rendering.settings import RenderSettings
        from rendering.cache import SnapshotCache

        sink = RichConsoleSink(Console(record=True))
        ctx = RenderContext(
            root=Path("/fake"),
            sink=sink,
            settings=RenderSettings(write_highlight_limit=10),
            cache=SnapshotCache(),
        )
        r = WriteRenderer(ctx)
        content = "hello world\n" * 10
        state = {
            "input": {"filePath": "/fake/new.txt", "content": content},
            "output": "Wrote file new.txt",
            "status": "completed",
        }
        assert r.render("write", state) is True
        markup = sink.console.export_text()
        assert "new.txt" in markup
        assert "hello world" in markup

    def test_renders_new_file_rich_syntax_on_large_highlight_limit(self):
        from rich.console import Console
        from rendering.context import RenderContext
        from rendering.sink import RichConsoleSink
        from rendering.settings import RenderSettings
        from rendering.cache import SnapshotCache

        sink = RichConsoleSink(Console(record=True))
        ctx = RenderContext(
            root=Path("/fake"),
            sink=sink,
            settings=RenderSettings(write_highlight_limit=1_000_000),
            cache=SnapshotCache(),
        )
        r = WriteRenderer(ctx)
        content = "hello world\n" * 10
        state = {
            "input": {"filePath": "/fake/new.txt", "content": content},
            "output": "Wrote file new.txt",
            "status": "completed",
        }
        assert r.render("write", state) is True
        markup = sink.console.export_text()
        assert "new.txt" in markup
        assert "hello world" in markup


# ——————————————————————————————————————————————
# EditRenderer
# ——————————————————————————————————————————————

class TestEditRenderer:
    def test_renders_edit_plain(self, capsys):
        r = EditRenderer(_ctx("plain"))
        state = {
            "input": {
                "filePath": "/fake/file.py",
                "oldString": "old line\n",
                "newString": "new line\n",
            },
            "output": "1 occurrence replaced successfully",
            "status": "completed",
        }
        assert r.render("edit", state) is True
        out = capsys.readouterr().out
        assert "file.py" in out
        assert "diff:" in out
        assert "-" in out
        assert "+" in out

    def test_renders_edit_rich(self):
        r = EditRenderer(_ctx("rich"))
        state = {
            "input": {
                "filePath": "/fake/file.py",
                "oldString": "old line\n",
                "newString": "new line\n",
            },
            "output": "1 occurrence replaced successfully",
            "status": "completed",
        }
        assert r.render("edit", state) is True

    def test_renders_replace_all_plain(self, capsys):
        r = EditRenderer(_ctx("plain"))
        state = {
            "input": {
                "filePath": "/fake/file.py",
                "oldString": "old\n",
                "newString": "new\n",
                "replaceAll": True,
            },
            "output": "3 occurrences replaced successfully",
            "status": "completed",
        }
        assert r.render("edit", state) is True
        out = capsys.readouterr().out
        assert "replace all" in out

    def test_renders_error_plain(self, capsys):
        r = EditRenderer(_ctx("plain"))
        state = {
            "input": {
                "filePath": "/fake/file.py",
                "oldString": "old\n",
                "newString": "new\n",
            },
            "output": "Error: oldString not found",
            "status": "error",
        }
        assert r.render("edit", state) is True
        out = capsys.readouterr().out
        assert "Error" in out

    def test_returns_false_for_missing_params(self):
        r = EditRenderer(_ctx("plain"))
        assert r.render("edit", {"input": {"filePath": "/fake/f.py"}, "output": "x"}) is False
        assert r.render("edit", {"input": {"filePath": "", "oldString": "a", "newString": "b"}}) is False

    def test_returns_false_for_non_dict_input(self):
        r = EditRenderer(_ctx("plain"))
        assert r.render("edit", {"input": "not a dict"}) is False


# ——————————————————————————————————————————————
# ApplyPatchRenderer
# ——————————————————————————————————————————————

class TestApplyPatchRenderer:
    def test_renders_envelope_patch_plain(self, capsys):
        r = ApplyPatchRenderer(_ctx("plain"))
        patch_text = (
            "*** Begin Patch\n"
            "*** Update File: file.py\n"
            "-old line\n"
            "+new line\n"
            "*** End Patch\n"
        )
        state = {
            "input": {"patchText": patch_text},
            "output": "Applied patch successfully",
            "status": "completed",
        }
        assert r.render("apply_patch", state) is True
        out = capsys.readouterr().out
        assert "apply_patch" in out
        assert "file.py" in out

    def test_renders_envelope_patch_rich(self):
        r = ApplyPatchRenderer(_ctx("rich"))
        patch_text = (
            "*** Begin Patch\n"
            "*** Update File: file.py\n"
            "-old line\n"
            "+new line\n"
            "*** End Patch\n"
        )
        state = {
            "input": {"patchText": patch_text},
            "output": "Applied patch successfully",
            "status": "completed",
        }
        assert r.render("apply_patch", state) is True

    def test_renders_raw_diff_plain(self, capsys):
        r = ApplyPatchRenderer(_ctx("plain"))
        patch_text = (
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        state = {
            "input": {"patchText": patch_text},
            "output": "Applied patch successfully",
            "status": "completed",
        }
        assert r.render("apply_patch", state) is True
        out = capsys.readouterr().out
        assert "apply_patch" in out

    def test_renders_json_patches_plain(self, capsys):
        r = ApplyPatchRenderer(_ctx("plain"))
        state = {
            "input": {
                "patches": [
                    {"path": "file.py", "diff": "-old\n+new\n"},
                ]
            },
            "output": "Applied patch successfully",
            "status": "completed",
        }
        assert r.render("apply_patch", state) is True
        out = capsys.readouterr().out
        assert "file.py" in out

    def test_renders_error_plain(self, capsys):
        r = ApplyPatchRenderer(_ctx("plain"))
        state = {
            "input": {"patchText": "-old\n+new\n"},
            "output": "Error: patch failed",
            "status": "error",
        }
        assert r.render("apply_patch", state) is True
        out = capsys.readouterr().out
        assert "Error" in out

    def test_returns_false_for_empty_input(self):
        r = ApplyPatchRenderer(_ctx("plain"))
        assert r.render("apply_patch", {"input": {}, "output": ""}) is False


# ——————————————————————————————————————————————
# GlobRenderer
# ——————————————————————————————————————————————

class TestGlobRenderer:
    def test_renders_matches_plain(self, capsys):
        r = GlobRenderer(_ctx("plain"))
        state = {
            "input": {"pattern": "*.py", "path": "/fake/src"},
            "output": "src/main.py\nsrc/utils.py\n2 matches for *.py",
            "status": "completed",
        }
        assert r.render("glob", state) is True
        out = capsys.readouterr().out
        assert "*.py" in out
        assert "main.py" in out
        assert "utils.py" in out
        assert "2 match" in out

    def test_renders_matches_rich(self):
        r = GlobRenderer(_ctx("rich"))
        state = {
            "input": {"pattern": "*.py", "path": "/fake/src"},
            "output": "src/main.py\nsrc/utils.py\n2 matches for *.py",
            "status": "completed",
        }
        assert r.render("glob", state) is True

    def test_renders_no_matches_plain(self, capsys):
        r = GlobRenderer(_ctx("plain"))
        state = {
            "input": {"pattern": "*.xyz", "path": "/fake/src"},
            "output": "No matches found",
            "status": "completed",
        }
        assert r.render("glob", state) is True
        out = capsys.readouterr().out
        assert "*.xyz" in out
        assert "no matches" in out.lower()

    def test_returns_false_for_non_dict_input(self):
        r = GlobRenderer(_ctx("plain"))
        assert r.render("glob", {"input": "not a dict", "output": "x"}) is False

    def test_returns_false_for_non_str_output(self):
        r = GlobRenderer(_ctx("plain"))
        assert r.render("glob", {"input": {"pattern": "*.py"}, "output": 123}) is False


# ——————————————————————————————————————————————
# GrepRenderer
# ——————————————————————————————————————————————

class TestGrepRenderer:
    def test_renders_file_matches_plain(self, capsys):
        r = GrepRenderer(_ctx("plain"))
        state = {
            "input": {"pattern": "def ", "path": "/fake/src"},
            "output": "src/main.py:1:def main():\nsrc/utils.py:5:def helper():",
            "status": "completed",
        }
        assert r.render("grep", state) is True
        out = capsys.readouterr().out
        assert "def " in out
        assert "main.py" in out
        assert "utils.py" in out

    def test_renders_file_matches_rich(self):
        r = GrepRenderer(_ctx("rich"))
        state = {
            "input": {"pattern": "def ", "path": "/fake/src"},
            "output": "src/main.py:1:def main():\nsrc/utils.py:5:def helper():",
            "status": "completed",
        }
        assert r.render("grep", state) is True

    def test_renders_line_matches_plain(self, capsys):
        r = GrepRenderer(_ctx("plain"))
        state = {
            "input": {"pattern": "foo", "path": "/fake/src"},
            "output": "src/main.py:10:    foo = 1\nsrc/main.py:20:    bar(foo)",
            "status": "completed",
        }
        assert r.render("grep", state) is True
        out = capsys.readouterr().out
        assert "main.py" in out
        assert "foo" in out

    def test_renders_no_matches_plain(self, capsys):
        r = GrepRenderer(_ctx("plain"))
        state = {
            "input": {"pattern": "xyz123", "path": "/fake/src"},
            "output": "",
            "status": "completed",
        }
        assert r.render("grep", state) is True
        out = capsys.readouterr().out
        assert "xyz123" in out
        assert "no matches" in out.lower()

    def test_renders_error_plain(self, capsys):
        r = GrepRenderer(_ctx("plain"))
        state = {
            "input": {"pattern": "foo", "path": "/fake/src"},
            "output": "Error: invalid regex",
            "status": "error",
        }
        assert r.render("grep", state) is True
        out = capsys.readouterr().out
        assert "Error" in out

    def test_returns_false_for_non_dict_input(self):
        r = GrepRenderer(_ctx("plain"))
        assert r.render("grep", {"input": "not a dict", "output": "x"}) is False

    def test_returns_false_for_non_str_non_dict_output(self):
        r = GrepRenderer(_ctx("plain"))
        assert r.render("grep", {"input": {"pattern": "foo"}, "output": 123}) is False


# ——————————————————————————————————————————————
# CommandRenderer
# ——————————————————————————————————————————————

class TestCommandRenderer:
    def test_renders_generic_bash_plain(self, capsys):
        r = CommandRenderer(_ctx("plain"))
        state = {
            "input": {"command": "echo hello", "description": "Say hello"},
            "output": "hello",
            "status": "completed",
        }
        assert r.render("bash", state) is True
        out = capsys.readouterr().out
        assert "echo hello" in out
        assert "hello" in out

    def test_renders_generic_bash_rich(self):
        r = CommandRenderer(_ctx("rich"))
        state = {
            "input": {"command": "echo hello", "description": "Say hello"},
            "output": "hello",
            "status": "completed",
        }
        assert r.render("bash", state) is True

    def test_renders_no_output_plain(self, capsys):
        r = CommandRenderer(_ctx("plain"))
        state = {
            "input": {"command": "true"},
            "output": "",
            "status": "completed",
        }
        assert r.render("bash", state) is True
        out = capsys.readouterr().out
        assert "true" in out
        assert "no output" in out.lower()

    def test_renders_error_output_plain(self, capsys):
        r = CommandRenderer(_ctx("plain"))
        state = {
            "input": {"command": "false"},
            "output": "command not found",
            "status": "error",
        }
        assert r.render("bash", state) is True
        out = capsys.readouterr().out
        assert "false" in out

    def test_returns_false_for_empty_command(self):
        r = CommandRenderer(_ctx("plain"))
        assert r.render("bash", {"input": {"command": ""}, "output": "x"}) is False

    def test_returns_false_for_non_dict_input(self):
        r = CommandRenderer(_ctx("plain"))
        assert r.render("bash", {"input": "not a dict"}) is False


# ——————————————————————————————————————————————
# Interceptors
# ——————————————————————————————————————————————

class TestSandboxBootstrapInterceptor:
    def test_try_render_detects_list_command(self, capsys):
        interceptor = SandboxBootstrapInterceptor()
        renderer = CommandRenderer(_ctx("plain"))
        state = {
            "input": {"command": "python tools/sandbox-bootstrap.py --format json list"},
            "output": '[{"id": "py", "display_name": "Python"}]',
            "status": "completed",
        }
        assert interceptor.try_render(state["input"]["command"], state, renderer) is True
        out = capsys.readouterr().out
        assert "Sandbox" in out
        assert "Python" in out

    def test_try_render_skips_non_sandbox_command(self):
        interceptor = SandboxBootstrapInterceptor()
        renderer = CommandRenderer(_ctx("plain"))
        state = {
            "input": {"command": "echo hello"},
            "output": "hello",
            "status": "completed",
        }
        assert interceptor.try_render(state["input"]["command"], state, renderer) is False

    def test_try_render_skips_when_disabled(self):
        ctx = _ctx("plain")
        ctx.settings.sandbox_render = False
        interceptor = SandboxBootstrapInterceptor()
        renderer = CommandRenderer(ctx)
        state = {
            "input": {"command": "python tools/sandbox-bootstrap.py --format json list"},
            "output": "[]",
            "status": "completed",
        }
        assert interceptor.try_render(state["input"]["command"], state, renderer) is False


class TestRtkReadInterceptor:
    def test_try_render_routes_cat_command(self, capsys):
        interceptor = RtkReadInterceptor()
        renderer = CommandRenderer(_ctx("plain"))
        command = "cat /fake/file.txt"
        state = {
            "input": {"command": command},
            "output": "hello world",
            "status": "completed",
        }
        assert interceptor.try_render(command, state, renderer) is True
        out = capsys.readouterr().out
        assert "file.txt" in out
        assert "hello world" in out

    def test_try_render_skips_non_read_command(self):
        interceptor = RtkReadInterceptor()
        renderer = CommandRenderer(_ctx("plain"))
        state = {
            "input": {"command": "echo hello"},
            "output": "hello",
            "status": "completed",
        }
        assert interceptor.try_render(state["input"]["command"], state, renderer) is False

    def test_try_render_skips_when_disabled(self):
        ctx = _ctx("plain")
        ctx.settings.bash_shim_render = False
        interceptor = RtkReadInterceptor()
        renderer = CommandRenderer(ctx)
        state = {
            "input": {"command": "cat /fake/file.txt"},
            "output": "hello",
            "status": "completed",
        }
        assert interceptor.try_render(state["input"]["command"], state, renderer) is False


class TestRtkGrepInterceptor:
    def test_try_render_routes_grep_command(self, capsys):
        interceptor = RtkGrepInterceptor()
        renderer = CommandRenderer(_ctx("plain"))
        state = {
            "input": {"command": "grep foo /fake/src"},
            "output": "src/main.py:1:foo = 1",
            "status": "completed",
        }
        assert interceptor.try_render(state["input"]["command"], state, renderer) is True
        out = capsys.readouterr().out
        assert "foo" in out
        assert "main.py" in out

    def test_try_render_skips_non_grep_command(self):
        interceptor = RtkGrepInterceptor()
        renderer = CommandRenderer(_ctx("plain"))
        state = {
            "input": {"command": "echo hello"},
            "output": "hello",
            "status": "completed",
        }
        assert interceptor.try_render(state["input"]["command"], state, renderer) is False

    def test_try_render_skips_when_disabled(self):
        ctx = _ctx("plain")
        ctx.settings.bash_shim_render = False
        interceptor = RtkGrepInterceptor()
        renderer = CommandRenderer(ctx)
        state = {
            "input": {"command": "grep foo /fake/src"},
            "output": "hello",
            "status": "completed",
        }
        assert interceptor.try_render(state["input"]["command"], state, renderer) is False


class TestShellListingInterceptor:
    def test_try_render_routes_ls_command(self, capsys):
        interceptor = ShellListingInterceptor()
        renderer = CommandRenderer(_ctx("plain"))
        state = {
            "input": {"command": "ls /fake/src"},
            "output": "main.py\nutils.py",
            "status": "completed",
        }
        assert interceptor.try_render(state["input"]["command"], state, renderer) is True
        out = capsys.readouterr().out
        assert "main.py" in out
        assert "utils.py" in out

    def test_try_render_routes_find_command(self, capsys):
        interceptor = ShellListingInterceptor()
        renderer = CommandRenderer(_ctx("plain"))
        state = {
            "input": {"command": "find /fake/src -name '*.py'"},
            "output": "src/main.py\nsrc/utils.py",
            "status": "completed",
        }
        assert interceptor.try_render(state["input"]["command"], state, renderer) is True
        out = capsys.readouterr().out
        assert "main.py" in out

    def test_try_render_skips_non_listing_command(self):
        interceptor = ShellListingInterceptor()
        renderer = CommandRenderer(_ctx("plain"))
        state = {
            "input": {"command": "echo hello"},
            "output": "hello",
            "status": "completed",
        }
        assert interceptor.try_render(state["input"]["command"], state, renderer) is False

    def test_try_render_skips_when_disabled(self):
        ctx = _ctx("plain")
        ctx.settings.bash_shim_render = False
        interceptor = ShellListingInterceptor()
        renderer = CommandRenderer(ctx)
        state = {
            "input": {"command": "ls /fake/src"},
            "output": "hello",
            "status": "completed",
        }
        assert interceptor.try_render(state["input"]["command"], state, renderer) is False
