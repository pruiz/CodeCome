from __future__ import annotations

from collections import OrderedDict

import pytest
from rich.console import Console

from conftest import ROOT, load_tool_module


def _load_config_module():
    return load_tool_module("codecome_config", "tools/codecome/config.py")


def _load_graceful_module():
    return load_tool_module("codecome_graceful", "tools/codecome/graceful.py")


FIXTURES = ROOT / "tests" / "fixtures" / "run_agent"


@pytest.mark.unit
@pytest.mark.compat_matrix
@pytest.mark.parametrize(
    ("fixture_name", "expected"),
    [
        ("openai_export.json", "openai/gpt-5.3"),
        ("anthropic_export.json", "anthropic/claude-opus-4-7"),
        ("google_export.json", "google/gemini-2.5-pro"),
        ("unknown_export.json", None),
    ],
)
def test_extract_model_from_export_matrix(fixture_name, expected):
    module = _load_config_module()
    payload = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    assert module._extract_model_from_export(payload) == expected


@pytest.mark.unit
def test_extract_flag_value_supports_both_flag_forms():
    module = _load_config_module()
    tokens = ["--model=openai/gpt-5", "--variant", "high"]
    assert module._extract_flag_value(tokens, ("--model", "-m")) == "openai/gpt-5"
    assert module._extract_flag_value(tokens, ("--variant",)) == "high"


@pytest.mark.unit
def test_strip_probe_unsafe_flags_removes_session_and_continue_flags():
    module = _load_config_module()
    command = [
        "opencode",
        "run",
        "--format",
        "json",
        "--session",
        "abc",
        "--continue",
        "--title=test",
        "--port",
        "9999",
        "--agent",
        "recon",
    ]
    out = module._strip_probe_unsafe_flags(command)
    assert "--session" not in out
    assert "--continue" not in out
    assert "--title=test" not in out
    assert "--port" not in out
    assert "--agent" in out


@pytest.mark.unit
def test_resolve_model_and_variant_precedence(monkeypatch):
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import codecome.config as _cfg
    monkeypatch.setenv("CODECOME_MODEL", "env/model")
    monkeypatch.setenv("CODECOME_MODEL_VARIANT", "max")
    monkeypatch.setattr(_cfg, "_read_codecome_yml_agent", lambda _agent: ("yaml/model", "yamlvar"))
    monkeypatch.setattr(_cfg, "_discover_opencode_default_model", lambda: "history/model")

    model, variant, model_source, variant_source = _cfg.resolve_model_and_variant(
        "auditor", ["--model", "args/model", "--variant=high"]
    )
    assert (model, variant) == ("args/model", "high")
    assert model_source == "OPENCODE_ARGS"
    assert variant_source == "OPENCODE_ARGS"


@pytest.mark.component
def test_stream_model_scan_finds_nested_provider_model_pair():
    module = _load_config_module()
    event = {
        "type": "tool_result",
        "part": {
            "tool": "bash",
            "state": {
                "meta": {
                    "providerID": "anthropic",
                    "modelID": "claude-sonnet-4"
                }
            },
        },
    }
    assert module._scan_event_for_model(event) == "anthropic/claude-sonnet-4"


@pytest.mark.unit
def test_thinking_default_is_disabled_for_anthropic_only():
    module = _load_config_module()
    assert module._thinking_default_for_provider("anthropic") is False
    assert module._thinking_default_for_provider("anthropic-foo") is False
    assert module._thinking_default_for_provider("openai") is True
    assert module._thinking_default_for_provider(None) is True


@pytest.mark.unit
def test_resolve_thinking_decision_precedence(monkeypatch):
    module = load_tool_module("run_agent_thinking_precedence", "tools/run-agent.py")

    on, source = module.resolve_thinking_decision("anthropic/claude-opus-4-7", ["--thinking"])
    assert (on, source) == (True, "user-args")

    monkeypatch.setenv("CODECOME_THINKING", "0")
    on, source = module.resolve_thinking_decision("openai/gpt-5", [])
    assert (on, source) == (False, "env")

    monkeypatch.setenv("CODECOME_THINKING", "1")
    on, source = module.resolve_thinking_decision("anthropic/claude-opus-4-7", [])
    assert (on, source) == (True, "env")


@pytest.mark.unit
def test_show_model_table_prints_resolution_sources(monkeypatch, capsys):
    """show_model_table should emit a table with all resolution sources."""
    import codecome.config as _cfg
    monkeypatch.setenv("OPENCODE_ARGS", "--model openai/gpt-5 --variant high")
    monkeypatch.setenv("CODECOME_MODEL", "env/model")
    monkeypatch.setenv("CODECOME_MODEL_VARIANT", "envvar")
    monkeypatch.setattr(_cfg, "_read_codecome_yml_agent", lambda _agent: ("yaml/model", "yamlvar"))
    monkeypatch.setattr(_cfg, "_discover_opencode_default_model", lambda: "history/model")

    rc = _cfg.show_model_table("auditor")
    assert rc == 0

    out = capsys.readouterr().out
    assert "Model resolution for agent auditor" in out
    assert "OPENCODE_ARGS" in out
    assert "env CODECOME_MODEL" in out
    assert "codecome.yml" in out
    assert "opencode session history" in out
    assert "effective" in out
    assert "openai/gpt-5" in out  # args win
    assert "high" in out
    assert "thinking=" in out


@pytest.mark.unit
def test_parse_grep_output_detects_line_mode_and_file_mode():
    module = load_tool_module("run_agent_grep_parse", "tools/run-agent.py")

    mode, entries = module._parse_grep_output("foo.py:10:needle\nbar.py:2:x")
    assert mode == "lines"
    assert entries[0]["path"] == "foo.py"
    assert entries[0]["line"] == 10

    mode, entries = module._parse_grep_output("foo.py\nbar.py")
    assert mode == "files"
    assert entries == [{"path": "foo.py"}, {"path": "bar.py"}]


@pytest.mark.unit
def test_grep_compile_pattern_falls_back_for_invalid_regex(monkeypatch):
    module = load_tool_module("run_agent_grep_compile", "tools/run-agent.py")
    monkeypatch.setattr(module, "_GREP_HIGHLIGHT", True)
    pat = module._grep_compile_pattern("(")
    assert pat is not None
    assert pat.pattern == "\\("


@pytest.mark.unit
def test_render_reasoning_plain_skips_empty_and_whitespace(monkeypatch, capsys):
    module = load_tool_module("run_agent_reasoning_skip", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_RENDER_REASONING", True)

    # Empty body
    module.render_reasoning(None, {"part": {"text": ""}})
    # Whitespace-only body
    module.render_reasoning(None, {"part": {"text": "   \n\t  "}})
    # Missing text key
    module.render_reasoning(None, {"part": {}})
    # Missing part dict
    module.render_reasoning(None, {})

    out = capsys.readouterr().out
    assert out == ""


# --- subagent summary helper -------------------------------------------------

@pytest.mark.unit
def test_format_subagent_summary_formats_all_fields():
    module = load_tool_module("run_agent_subagent_summary", "tools/run-agent.py")
    assert module._format_subagent_summary({"additions": 3, "deletions": 1, "files": 2}) == "+3 -1  2 file(s)"
    assert module._format_subagent_summary({"additions": 0, "files": 1}) == "+0 -0  1 file(s)"
    assert module._format_subagent_summary({"files": 5}) == "5 file(s)"
    assert module._format_subagent_summary({}) == ""
    assert module._format_subagent_summary(None) == ""


# --- task renderer -----------------------------------------------------------

@pytest.mark.unit
def test_render_task_plain_shows_description_truncated_prompt_and_output(monkeypatch, capsys):
    module = load_tool_module("run_agent_task_plain", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_TASK_PROMPT_PREVIEW_LINES", 2)

    state = {
        "input": {
            "description": "Analyze batch 2",
            "subagent_type": "explore",
            "prompt": "line one\nline two\nline three\nline four",
        },
        "output": "Done analyzing.",
        "status": "completed",
    }
    assert module.render_task_plain(state) is True
    out = capsys.readouterr().out
    assert "task Analyze batch 2 [explore] [completed]" in out
    assert "line one" in out
    assert "line two" in out
    assert "... 2 more lines" in out
    assert "Done analyzing." in out


@pytest.mark.unit
def test_render_task_plain_handles_missing_fields(monkeypatch, capsys):
    module = load_tool_module("run_agent_task_plain_minimal", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    state = {"input": {}, "status": "in_progress"}
    assert module.render_task_plain(state) is True
    out = capsys.readouterr().out
    assert "task  [in_progress]" in out


@pytest.mark.unit
def test_render_task_rich_shows_panel(monkeypatch):
    module = load_tool_module("run_agent_task_rich", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", True)
    monkeypatch.setattr(module, "_TASK_PROMPT_PREVIEW_LINES", 3)

    from rich.console import Console

    console = Console(record=True, force_terminal=True, width=60, highlight=False)
    state = {
        "input": {
            "description": "Counter-analysis",
            "subagentType": "reviewer",
            "prompt": "a\nb\nc\nd",
        },
        "status": "in_progress",
    }
    assert module.render_task_rich(console, state) is True
    out = console.export_text()
    assert "Task [in_progress]" in out
    assert "Counter-analysis" in out
    assert "[reviewer]" in out
    assert "... 1 more lines" in out


# --- subagent status renderer ------------------------------------------------

@pytest.mark.unit
def test_render_subagent_status_plain_created_and_finished(monkeypatch, capsys):
    module = load_tool_module("run_agent_subagent_plain_lifecycle", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_RENDER_SUBAGENT_UPDATES", True)

    module.render_subagent_status(None, {
        "type": "subagent.status",
        "properties": {"statusType": "created", "sessionID": "s1", "title": "Batch A"},
    })
    out = capsys.readouterr().out
    assert "[subagent] started: Batch A" in out

    module.render_subagent_status(None, {
        "type": "subagent.status",
        "properties": {"statusType": "finished", "sessionID": "s1", "title": "Batch A"},
    })
    out = capsys.readouterr().out
    assert "[subagent] finished: Batch A" in out


@pytest.mark.unit
def test_render_subagent_status_plain_heartbeat_shows_elapsed(monkeypatch, capsys):
    module = load_tool_module("run_agent_subagent_plain_heartbeat", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_RENDER_SUBAGENT_UPDATES", True)

    module.render_subagent_status(None, {
        "type": "subagent.status",
        "properties": {
            "statusType": "heartbeat",
            "sessionID": "s1",
            "title": "Slow job",
            "elapsedMs": 45000,
        },
    })
    out = capsys.readouterr().out
    assert "Subagent · Slow job still running (45s)" in out


@pytest.mark.unit
def test_render_subagent_status_plain_update_dedupes_unchanged_summary(monkeypatch, capsys):
    module = load_tool_module("run_agent_subagent_plain_dedup", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_RENDER_SUBAGENT_UPDATES", True)
    monkeypatch.setattr(module, "_SUBAGENT_UPDATE_THROTTLE_S", 5)

    event = {
        "type": "subagent.status",
        "properties": {
            "statusType": "updated",
            "sessionID": "s2",
            "title": "Job",
            "summary": {"additions": 1, "deletions": 0, "files": 1},
        },
    }

    # First update renders.
    module.render_subagent_status(None, event)
    out = capsys.readouterr().out
    assert "Subagent · Job" in out
    assert "+1 -0" in out

    # Identical update immediately after is suppressed.
    module.render_subagent_status(None, event)
    out = capsys.readouterr().out
    assert out == ""


@pytest.mark.unit
def test_render_subagent_status_plain_update_renders_when_summary_changes(monkeypatch, capsys):
    module = load_tool_module("run_agent_subagent_plain_change", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_RENDER_SUBAGENT_UPDATES", True)
    monkeypatch.setattr(module, "_SUBAGENT_UPDATE_THROTTLE_S", 5)

    module.render_subagent_status(None, {
        "type": "subagent.status",
        "properties": {
            "statusType": "updated",
            "sessionID": "s3",
            "title": "Job",
            "summary": {"additions": 1, "files": 1},
        },
    })
    out = capsys.readouterr().out
    assert "+1 -0" in out

    # Change summary -> renders again even inside throttle window.
    module.render_subagent_status(None, {
        "type": "subagent.status",
        "properties": {
            "statusType": "updated",
            "sessionID": "s3",
            "title": "Job",
            "summary": {"additions": 2, "files": 1},
        },
    })
    out = capsys.readouterr().out
    assert "+2 -0" in out


@pytest.mark.unit
def test_render_subagent_status_rich_created_renders_panel(monkeypatch):
    module = load_tool_module("run_agent_subagent_rich_created", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", True)
    monkeypatch.setattr(module, "_RENDER_SUBAGENT_UPDATES", True)

    from rich.console import Console

    console = Console(record=True, force_terminal=True, width=60, highlight=False)
    module.render_subagent_status(console, {
        "type": "subagent.status",
        "properties": {"statusType": "created", "sessionID": "s1", "title": "Batch A"},
    })
    out = console.export_text()
    assert "Subagent started" in out
    assert "Batch A" in out


@pytest.mark.unit
def test_render_event_dispatches_subagent_status(monkeypatch):
    """render_event dispatches subagent.status through SubagentStatusRenderer."""
    import rendering.events as _evts
    module = load_tool_module("run_agent_dispatch_subagent", "tools/run-agent.py")
    calls = []

    class _FakeRenderer:
        def __init__(self, ctx):
            pass
        def render(self, event):
            calls.append("subagent.status")
            return True

    monkeypatch.setattr(_evts, "SubagentStatusRenderer", _FakeRenderer)
    module.render_event(None, "2", "x", {"type": "subagent.status", "properties": {}})
    assert calls == ["subagent.status"]


@pytest.mark.unit
def test_dispatch_tool_renderer_routes_task_to_task_renderer(monkeypatch):
    """_dispatch_tool_renderer delegates 'task' to rendering.tools.task.TaskRenderer."""
    import rendering.tools.task as _task_mod
    module = load_tool_module("run_agent_dispatch_task", "tools/run-agent.py")

    task_calls = []

    class _FakeRenderer:
        def render(self, tool_name, state):
            task_calls.append(tool_name)
            return True

    monkeypatch.setattr(_task_mod, "TaskRenderer", lambda ctx: _FakeRenderer())

    # With rich
    monkeypatch.setattr(module, "HAVE_RICH", True)
    assert module._dispatch_tool_renderer(None, "task", {}) is True
    assert task_calls == ["task"]

    task_calls.clear()
    monkeypatch.setattr(module, "HAVE_RICH", False)
    assert module._dispatch_tool_renderer(None, "task", {}) is True
    assert task_calls == ["task"]


# --- reasoning / error rendering edge cases --------------------------------


@pytest.mark.unit
def test_render_reasoning_plain_skips_empty_and_whitespace(monkeypatch, capsys):
    module = load_tool_module("run_agent_reasoning_skip", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_RENDER_REASONING", True)

    # Empty body
    module.render_reasoning(None, {"part": {"text": ""}})
    # Whitespace-only body
    module.render_reasoning(None, {"part": {"text": "   \n\t  "}})
    # Missing text key
    module.render_reasoning(None, {"part": {}})
    # Missing part dict
    module.render_reasoning(None, {})

    out = capsys.readouterr().out
    assert out == ""


@pytest.mark.unit
def test_render_reasoning_rich_wraps_markdown_inside_panel(monkeypatch):
    module = load_tool_module("run_agent_reasoning_rich_wrap", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", True)
    monkeypatch.setattr(module, "_RENDER_REASONING", True)
    monkeypatch.setattr(module, "_REASONING_MAX_CHARS", 10000)

    console = Console(record=True, force_terminal=True, width=60, highlight=False)
    text = (
        "**Summarizing file updates**\n\n"
        "I need to mention the sandbox and validate the modifications. "
        "Updating the item database for attack surfaces might need a more "
        "realistic runtime setup so later phases can rely on it."
    )

    module.render_reasoning(console, {"part": {"text": text}})

    out = console.export_text()
    assert "Thinking" in out
    assert "Summarizing file updates" in out
    assert "realistic runtime setup" in out
    assert "later phases can rely on it" in out


@pytest.mark.unit
def test_render_reasoning_rich_wraps_plain_text_inside_panel(monkeypatch):
    module = load_tool_module("run_agent_reasoning_rich_plain_wrap", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", True)
    monkeypatch.setattr(module, "_RENDER_REASONING", True)
    monkeypatch.setattr(module, "_REASONING_MAX_CHARS", 10000)

    console = Console(record=True, force_terminal=True, width=60, highlight=False)
    text = (
        "I need to mention the sandbox and validate the modifications. "
        "Updating the item database for attack surfaces might need a more "
        "realistic runtime setup so later phases can rely on it."
    )

    module.render_reasoning(console, {"part": {"text": text}})

    out = console.export_text()
    assert "Thinking" in out
    assert "Updating the item database" in out
    assert "realistic runtime setup" in out
    assert "later phases can rely on it" in out


@pytest.mark.unit
def test_render_error_plain_mode_handles_missing_error_field(monkeypatch, capsys):
    module = load_tool_module("run_agent_error_missing", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    module.render_error(None, {})
    out = capsys.readouterr().out
    # Title line plus a (no error message) body line.
    assert "Error" in out
    assert "(no error message)" in out


@pytest.mark.unit
def test_render_error_plain_mode_handles_dict_with_only_message(monkeypatch, capsys):
    module = load_tool_module("run_agent_error_only_msg", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    module.render_error(None, {"error": {"message": "rate limited"}})
    out = capsys.readouterr().out
    assert "rate limited" in out


# --- grep highlight helpers ------------------------------------------------

@pytest.mark.unit
def test_grep_format_line_plain_with_color_emits_ansi(monkeypatch):
    module = load_tool_module("run_agent_grep_plain_ansi", "tools/run-agent.py")
    monkeypatch.setattr(module, "_GREP_HIGHLIGHT", True)
    pat = module._grep_compile_pattern("error")
    out = module._grep_format_line_plain(42, "an error here and error again", pat, color=True)
    # Bold yellow + reset around each match.
    assert out.count("\x1b[1;33m") == 2
    assert out.count("\x1b[0m") == 2
    assert "    42: " in out


@pytest.mark.unit
def test_grep_format_line_plain_without_color_uses_markers(monkeypatch):
    module = load_tool_module("run_agent_grep_plain_markers", "tools/run-agent.py")
    monkeypatch.setattr(module, "_GREP_HIGHLIGHT", True)
    pat = module._grep_compile_pattern("error")
    out = module._grep_format_line_plain(7, "an error", pat, color=False)
    assert ">>>error<<<" in out
    assert "    7: " in out


@pytest.mark.unit
def test_grep_format_line_plain_no_pattern_returns_unstyled(monkeypatch):
    module = load_tool_module("run_agent_grep_plain_nopat", "tools/run-agent.py")
    out = module._grep_format_line_plain(99, "plain text", None, color=True)
    assert out == "       99: plain text"


@pytest.mark.unit
def test_grep_format_line_plain_disabled_returns_unstyled(monkeypatch):
    """CODECOME_GREP_HIGHLIGHT=0 must skip even ANSI emission."""
    module = load_tool_module("run_agent_grep_plain_disabled", "tools/run-agent.py")
    monkeypatch.setattr(module, "_GREP_HIGHLIGHT", False)
    pat = module._grep_compile_pattern("error")  # returns None when disabled
    out = module._grep_format_line_plain(1, "an error", pat, color=True)
    assert "\x1b[1;33m" not in out
    assert ">>>" not in out
    assert "an error" in out


@pytest.mark.unit
def test_grep_compile_pattern_returns_none_when_highlight_disabled(monkeypatch):
    module = load_tool_module("run_agent_grep_compile_off", "tools/run-agent.py")
    monkeypatch.setattr(module, "_GREP_HIGHLIGHT", False)
    assert module._grep_compile_pattern("foo") is None


@pytest.mark.unit
def test_grep_compile_pattern_returns_none_for_empty_pattern(monkeypatch):
    module = load_tool_module("run_agent_grep_compile_empty", "tools/run-agent.py")
    monkeypatch.setattr(module, "_GREP_HIGHLIGHT", True)
    assert module._grep_compile_pattern("") is None


# --- grep parser additional cases ------------------------------------------

@pytest.mark.unit
def test_parse_grep_output_empty_returns_empty_files_mode():
    module = load_tool_module("run_agent_grep_empty", "tools/run-agent.py")
    mode, entries = module._parse_grep_output("")
    assert mode == "files"
    assert entries == []


@pytest.mark.unit
def test_parse_grep_output_70_percent_threshold_for_lines_mode():
    module = load_tool_module("run_agent_grep_threshold", "tools/run-agent.py")

    # 7 of 10 lines are line-level => exactly 70% => "lines" mode.
    output = "\n".join(
        [f"foo.py:{i}:match" for i in range(7)] + ["plain1", "plain2", "plain3"]
    )
    mode, entries = module._parse_grep_output(output)
    assert mode == "lines"
    # The non-matching lines become path-only entries with line=0.
    assert any(e["line"] == 0 for e in entries)

    # 6 of 10 -> below threshold -> "files" mode.
    output_low = "\n".join(
        [f"foo.py:{i}:match" for i in range(6)] + ["a", "b", "c", "d"]
    )
    mode, _ = module._parse_grep_output(output_low)
    assert mode == "files"


@pytest.mark.unit
def test_cache_invalidate_stale_removes_missing_and_modified(monkeypatch, tmp_path):
    """_cache_invalidate_stale should remove entries for deleted files
    and for files whose mtime changed since caching."""
    module = load_tool_module("run_agent_cache_stale", "tools/run-agent.py")
    monkeypatch.setattr(module, "_WRITE_CACHE_ENABLED", True)

    # _SNAPSHOT_CACHE is an module-level OrderedDict; monkeypatch it per-test.
    fake_cache = OrderedDict()
    monkeypatch.setattr(module, "_SNAPSHOT_CACHE", fake_cache)

    existing = tmp_path / "existing.txt"
    existing.write_text("old", encoding="utf-8")
    deleted = tmp_path / "deleted.txt"
    deleted.write_text("gone", encoding="utf-8")

    module._cache_set(str(existing), "old")
    module._cache_set(str(deleted), "gone")

    assert str(existing) in fake_cache
    assert str(deleted) in fake_cache

    # Simulate file deletion
    deleted.unlink()
    # Simulate modification of existing file
    existing.write_text("new", encoding="utf-8")

    module._cache_invalidate_stale()

    # Deleted and modified entries are both removed
    assert str(deleted) not in fake_cache
    assert str(existing) not in fake_cache


@pytest.mark.unit
def test_read_renderer_caches_stripped_lines_instead_of_numbered(monkeypatch):
    module = load_tool_module("run_agent_read_cache_strip", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_INTERNAL_READ_SUPPRESS", False)

    cache_writes = []

    def fake_cache_set(path, content):
        cache_writes.append((path, content))

    monkeypatch.setattr(module, "_cache_set", fake_cache_set)

    output = "<path>/tmp/x.txt</path>\n<type>file</type>\n<content>\n1: alpha\n2: beta\n\n(End of file - total 2 lines)\n</content>"
    state = {
        "input": {"filePath": "/tmp/x.txt", "offset": 1, "limit": 20},
        "output": output,
        "status": "completed",
    }

    assert module.render_read_plain(state) is True
    assert cache_writes
    assert cache_writes[-1][1] == "alpha\nbeta"


@pytest.mark.unit
def test_write_diff_uses_clean_cached_content_without_line_numbers(monkeypatch, capsys):
    module = load_tool_module("run_agent_write_diff_clean", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    monkeypatch.setattr(module, "_cache_get", lambda _path: "alpha\nbeta\n")
    monkeypatch.setattr(module, "_cache_set", lambda _path, _content: None)

    state = {
        "input": {"filePath": "/tmp/x.txt", "content": "alpha\ngamma\n"},
        "output": "Wrote file successfully.",
        "status": "completed",
    }

    assert module.render_write_plain(state) is True
    out = capsys.readouterr().out
    assert "-1: alpha" not in out
    assert "-2: beta" not in out
    assert "+1: alpha" not in out
    assert "+2: gamma" not in out


# --- sandbox-bootstrap renderer detection ----------------------------------

SANDBOX_FIXTURES = ROOT / "tests" / "fixtures" / "sandbox_bootstrap"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("command", "expected"),
    [
        # Direct script invocations.
        (".venv/bin/python3 tools/sandbox-bootstrap.py --format json status", "status"),
        ("python3 tools/sandbox-bootstrap.py status --format=json", "status"),
        ("python tools/sandbox-bootstrap.py --format json validate --keep-going", "validate"),
        ("python tools/sandbox-bootstrap.py --format=json detect", "detect"),
        ("./tools/sandbox-bootstrap.py --format json list", "list"),
        # make-target wrappers with json forced via BOOTSTRAP_ARGS.
        ("make sandbox-status BOOTSTRAP_ARGS='--format json'", "status"),
        ("make sandbox-validate BOOTSTRAP_ARGS=--format=json", "validate"),
        ("make sandbox-bootstrap ID=python BOOTSTRAP_ARGS='--format json'", "apply"),
        ("BOOTSTRAP_ARGS='--format json --keep-going' make sandbox-validate", "validate"),
        ("BOOTSTRAP_ARGS=--format=json make sandbox-status", "status"),
        # Negatives.
        ("python tools/sandbox-bootstrap.py status", None),  # no --format json
        ("make sandbox-status", None),                       # text mode
        ("python tools/list-findings.py --format json", None),  # different script
        ("", None),
        ("ls -la", None),
    ],
)
def test_is_sandbox_bootstrap_json_call(command, expected):
    module = load_tool_module("run_agent_sandbox_detect", "tools/run-agent.py")
    assert module._is_sandbox_bootstrap_json_call(command) == expected


@pytest.mark.unit
def test_lexer_map_includes_erlang_extensions():
    module = load_tool_module("run_agent_erlang_lexer", "tools/run-agent.py")

    assert module._LEXER_MAP[".erl"] == "erlang"
    assert module._LEXER_MAP[".hrl"] == "erlang"


@pytest.mark.unit
def test_sandbox_payload_matches_filters_unrelated_json():
    module = load_tool_module("run_agent_sandbox_match", "tools/run-agent.py")

    # Status-shape payload matches.
    assert module._sandbox_payload_matches("status", {"sandbox_state": "missing", "capabilities": {}}) is True
    # Unrelated dict does not match status.
    assert module._sandbox_payload_matches("status", {"foo": "bar"}) is False
    # list expects a list.
    assert module._sandbox_payload_matches("list", []) is True
    assert module._sandbox_payload_matches("list", {"id": "x"}) is False
    # validate expects overall_outcome or tiers.
    assert module._sandbox_payload_matches("validate", {"overall_outcome": "passed"}) is True
    assert module._sandbox_payload_matches("validate", {"tiers": []}) is True
    assert module._sandbox_payload_matches("validate", {"unrelated": True}) is False


@pytest.mark.unit
def test_sandbox_glyphs_uses_emoji_on_utf8_else_ascii(monkeypatch):
    module = load_tool_module("run_agent_sandbox_glyphs", "tools/run-agent.py")

    class FakeConsole:
        encoding = "utf-8"

    glyphs = module._sandbox_glyphs(FakeConsole())
    assert glyphs["ok"] == "✅"
    assert glyphs["fail"] == "❌"

    class AsciiConsole:
        encoding = "ascii"

    glyphs = module._sandbox_glyphs(AsciiConsole())
    assert glyphs["ok"] == "[OK]"
    assert glyphs["fail"] == "[FAIL]"


@pytest.mark.component
def test_render_sandbox_status_plain_renders_pass_gate(monkeypatch, capsys):
    """End-to-end through _maybe_render_sandbox_bootstrap with a real status payload."""
    module = load_tool_module("run_agent_sandbox_status_plain", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    payload = (SANDBOX_FIXTURES / "status_pass.json").read_text(encoding="utf-8")
    state = {
        "input": {
            "command": ".venv/bin/python3 tools/sandbox-bootstrap.py --format json status",
            "description": "Show sandbox status",
        },
        "output": payload,
        "status": "completed",
    }
    handled = module._maybe_render_sandbox_bootstrap(None, state)
    assert handled is True
    out = capsys.readouterr().out
    assert "Sandbox" in out
    assert "status" in out
    # Required capabilities should each appear with an OK marker.
    for cap in ("setup", "start", "check", "build", "test", "stop"):
        assert cap in out


@pytest.mark.component
def test_render_sandbox_validate_plain_failed_shows_stderr_tail(monkeypatch, capsys):
    module = load_tool_module("run_agent_sandbox_validate_plain", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    # Force a small cap so we can confirm truncation works.
    monkeypatch.setattr(module, "_SANDBOX_VALIDATE_STDERR_LINES", 2)

    payload = (SANDBOX_FIXTURES / "validate_failed.json").read_text(encoding="utf-8")
    state = {
        "input": {
            "command": "tools/sandbox-bootstrap.py --format json validate",
            "description": "validate",
        },
        "output": payload,
        "status": "completed",
    }
    handled = module._maybe_render_sandbox_bootstrap(None, state)
    assert handled is True
    out = capsys.readouterr().out
    assert "failed" in out
    # Failed tier's stderr_tail should appear (capped to 2 lines).
    assert "port 5432 already in use" in out
    assert "please free the port" in out
    # "Error: container failed to start" is the earliest of 3 lines and
    # must be elided by the cap.
    assert "Error: container failed to start" not in out
    assert "earlier lines truncated" in out
    # missing helpers warning is present.
    assert "clean" in out and "reset" in out


@pytest.mark.component
def test_render_sandbox_apply_plain_dry_run_lists_unfilled_markers(monkeypatch, capsys):
    module = load_tool_module("run_agent_sandbox_apply_plain", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    payload = (SANDBOX_FIXTURES / "apply_dry_run.json").read_text(encoding="utf-8")
    state = {
        "input": {
            "command": "tools/sandbox-bootstrap.py --format json apply python --dry-run --var PYTHON_VERSION=3.11",
            "description": "apply",
        },
        "output": payload,
        "status": "completed",
    }
    handled = module._maybe_render_sandbox_bootstrap(None, state)
    assert handled is True
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "EXTRA_PIP" in out
    assert "Dockerfile" in out


@pytest.mark.component
def test_render_sandbox_list_plain_uses_real_fixture(monkeypatch, capsys):
    module = load_tool_module("run_agent_sandbox_list_plain", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    payload = (SANDBOX_FIXTURES / "list.json").read_text(encoding="utf-8")
    state = {
        "input": {
            "command": "tools/sandbox-bootstrap.py --format json list",
            "description": "list",
        },
        "output": payload,
        "status": "completed",
    }
    handled = module._maybe_render_sandbox_bootstrap(None, state)
    assert handled is True
    out = capsys.readouterr().out
    # Spot-check at least one known example id.
    import json as _json
    examples = _json.loads(payload)
    assert len(examples) > 0
    first_id = examples[0]["id"]
    assert first_id in out
    assert "example(s) available" in out


@pytest.mark.unit
def test_maybe_render_sandbox_bootstrap_skips_non_sandbox_bash(monkeypatch):
    module = load_tool_module("run_agent_sandbox_skip", "tools/run-agent.py")
    state = {
        "input": {"command": "ls -la", "description": "list files"},
        "output": "total 0",
        "status": "completed",
    }
    assert module._maybe_render_sandbox_bootstrap(None, state) is False


@pytest.mark.unit
def test_maybe_render_sandbox_bootstrap_strips_leading_text(monkeypatch, capsys):
    module = load_tool_module("run_agent_sandbox_leading_text", "tools/run-agent.py")
    # Simulate a make command that echoes the invocation line before the JSON payload
    state = {
        "input": {"command": "tools/sandbox-bootstrap.py --format json status"},
        "output": 'python tools/sandbox-bootstrap.py status --format json\n{"sandbox_state": "missing", "phase2_gate_pass": false, "capabilities": {}}',
        "status": "completed",
    }
    
    # Force _SANDBOX_RENDER = True
    monkeypatch.setattr(module, "_SANDBOX_RENDER", True)
    
    assert module._maybe_render_sandbox_bootstrap(None, state) is True
    
    captured = capsys.readouterr()
    assert "Sandbox · status" in captured.out


@pytest.mark.unit
def test_maybe_render_sandbox_bootstrap_handles_env_prefixed_make(monkeypatch, capsys):
    module = load_tool_module("run_agent_sandbox_env_prefixed_make", "tools/run-agent.py")
    state = {
        "input": {
            "command": "BOOTSTRAP_ARGS='--format json --keep-going' make sandbox-validate",
            "description": "Run validation with longer timeout",
        },
        "output": '{"overall_outcome": "passed", "tiers": []}',
        "status": "completed",
    }

    monkeypatch.setattr(module, "_SANDBOX_RENDER", True)

    assert module._maybe_render_sandbox_bootstrap(None, state) is True
    captured = capsys.readouterr()
    assert "Sandbox · validate" in captured.out


@pytest.mark.unit
def test_maybe_render_sandbox_bootstrap_falls_through_on_invalid_json(monkeypatch):
    module = load_tool_module("run_agent_sandbox_bad_json", "tools/run-agent.py")
    state = {
        "input": {"command": "tools/sandbox-bootstrap.py --format json status"},
        "output": "Loading config...\n{partial",
        "status": "completed",
    }
    assert module._maybe_render_sandbox_bootstrap(None, state) is False


@pytest.mark.unit
def test_maybe_render_sandbox_bootstrap_falls_through_on_schema_mismatch(monkeypatch):
    module = load_tool_module("run_agent_sandbox_schema_miss", "tools/run-agent.py")
    state = {
        "input": {"command": "tools/sandbox-bootstrap.py --format json status"},
        "output": '{"unrelated": true, "foo": [1, 2, 3]}',
        "status": "completed",
    }
    # Looks like JSON, parses as JSON, but does not have any of
    # sandbox_state / phase2_gate_pass / capabilities -> fall through.
    assert module._maybe_render_sandbox_bootstrap(None, state) is False


@pytest.mark.unit
def test_maybe_render_sandbox_bootstrap_disabled_via_env(monkeypatch):
    module = load_tool_module("run_agent_sandbox_disabled", "tools/run-agent.py")
    monkeypatch.setattr(module, "_SANDBOX_RENDER", False)
    state = {
        "input": {"command": "tools/sandbox-bootstrap.py --format json status"},
        "output": '{"sandbox_state": "missing", "phase2_gate_pass": false, "capabilities": {}}',
        "status": "completed",
    }
    assert module._maybe_render_sandbox_bootstrap(None, state) is False


# --- bash-shim detection ----------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    ("command", "expected_family", "expected_attrs"),
    [
        # rtk read family
        ("rtk read README.md", "read", {"files": ["README.md"], "rtk_filtered": False}),
        ("rtk read README.md AGENTS.md", "read",
         {"files": ["README.md", "AGENTS.md"], "rtk_filtered": False}),
        ("rtk read --level minimal README.md", "read",
         {"files": ["README.md"], "rtk_filtered": True}),
        ("rtk read --tail-lines 5 README.md", "read",
         {"files": ["README.md"], "rtk_filtered": True}),
        ("rtk read -n -m 50 README.md", "read",
         {"files": ["README.md"], "rtk_filtered": True}),
        # cat / head / tail
        ("cat README.md", "read", {"files": ["README.md"]}),
        ("cat README.md AGENTS.md", "read", {"files": ["README.md", "AGENTS.md"]}),
        ("head -n 10 README.md", "read", {"files": ["README.md"], "head_limit": 10}),
        ("head -n10 README.md", "read", {"files": ["README.md"], "head_limit": 10}),
        ("tail -n 5 README.md", "read", {"files": ["README.md"], "tail_limit": 5}),
        # grep / rg / rtk grep
        ("rg foo tools/run-agent.py", "grep", {"pattern": "foo", "path": "tools/run-agent.py"}),
        ("rg --vimgrep render_grep tools/run-agent.py", "grep",
         {"pattern": "render_grep", "path": "tools/run-agent.py"}),
        ("rtk grep render_grep tools/run-agent.py", "grep",
         {"pattern": "render_grep", "path": "tools/run-agent.py"}),
        ("rtk grep -i needle .", "grep", {"pattern": "needle", "path": "."}),
        ("grep -r foo bar/", "grep", {"pattern": "foo", "path": "bar/"}),
        # ls
        ("ls", "ls", {"path": ".", "long_format": False}),
        ("ls -la tools", "ls", {"path": "tools", "long_format": True}),
        ("rtk ls -la", "ls", {"path": ".", "long_format": True}),
        # find / tree
        ("find tools", "find", {"path": "tools"}),
        ("find tools -name '*.py'", "find", {"path": "tools"}),
        ("tree", "find", {"path": "."}),
        # leading env / sudo wrappers should be stripped
        ("LANG=C ls tools", "ls", {"path": "tools"}),
        ("sudo cat /etc/hosts", "read", {"files": ["/etc/hosts"]}),
        ("time rg foo bar/", "grep", {"pattern": "foo", "path": "bar/"}),
    ],
)
def test_is_bash_shim_call_recognises_supported_commands(command, expected_family, expected_attrs):
    module = load_tool_module("run_agent_shim_detect", "tools/run-agent.py")
    shim = module._is_bash_shim_call(command)
    assert shim is not None, f"expected shim match for {command!r}"
    assert shim.family == expected_family
    for k, v in expected_attrs.items():
        assert getattr(shim, k) == v, (
            f"attribute {k}: expected {v!r}, got {getattr(shim, k)!r} for {command!r}"
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "command",
    [
        "",
        "echo hello",
        "make phase-1",
        "git status",
        "rtk diff a b",
        "rtk smart README.md",
        # Pipelines / redirections / substitutions disqualify shim handling.
        "cat README.md | head",
        "rg foo > out.txt",
        "ls && pwd",
        "ls; pwd",
        "echo $(pwd)",
        "cat `which python`",
        # No file argument.
        "rtk read",
        "cat",
        "rg",
        # rtk subcommand we don't route.
        "rtk json '{}'",
        "rtk wc README.md",
    ],
)
def test_is_bash_shim_call_rejects_unsupported(command):
    module = load_tool_module("run_agent_shim_reject", "tools/run-agent.py")
    assert module._is_bash_shim_call(command) is None


@pytest.mark.unit
def test_normalize_rtk_grep_output_converts_grouped_to_flat():
    module = load_tool_module("run_agent_shim_norm_rtk", "tools/run-agent.py")
    raw = (
        "4 matches in 3F:\n"
        "\n"
        "[file] tools/run-agent.py (2):\n"
        "  2811: return render_grep_rich(console, state)\n"
        "  2813: return render_grep_plain(state)\n"
        "\n"
        "[file] tools/x.py (1):\n"
        "    42: hit\n"
    )
    out = module._normalize_rtk_grep_output(raw)
    lines = [l for l in out.split("\n") if l.strip()]
    assert lines == [
        "tools/run-agent.py:2811:return render_grep_rich(console, state)",
        "tools/run-agent.py:2813:return render_grep_plain(state)",
        "tools/x.py:42:hit",
    ]


@pytest.mark.unit
def test_normalize_rtk_grep_output_passes_through_when_no_markers():
    module = load_tool_module("run_agent_shim_norm_passthrough", "tools/run-agent.py")
    raw = "tools/foo.py:10:hit\nanother line\n"
    assert module._normalize_rtk_grep_output(raw) == raw


@pytest.mark.unit
def test_strip_ls_long_format_to_filenames_strips_columns_and_total():
    module = load_tool_module("run_agent_shim_ls_strip", "tools/run-agent.py")
    raw = (
        "total 616\n"
        "drwxr-xr-x@ 14 pruiz  staff     448 May  8 03:02 __pycache__\n"
        "-rw-r--r--@  1 pruiz  staff    3893 May  8 00:37 _colors.py\n"
        "-rwxr-xr-x@  1 pruiz  staff    6347 May  8 00:37 check-frontmatter.py\n"
    )
    out = module._strip_ls_long_format_to_filenames(raw)
    assert out.split("\n") == ["__pycache__", "_colors.py", "check-frontmatter.py"]


@pytest.mark.component
def test_render_shim_read_routes_to_read_renderer(monkeypatch, capsys):
    module = load_tool_module("run_agent_shim_read_e2e", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_INTERNAL_READ_SUPPRESS", False)

    raw_content = "alpha\nbeta\ngamma\n"
    state = {
        "input": {"command": "rtk read tests/fixtures/run_agent/openai_export.json", "description": "rtk read"},
        "output": raw_content,
        "status": "completed",
    }
    handled = module._maybe_render_bash_shim(None, state)
    assert handled is True
    out = capsys.readouterr().out
    # The Read renderer header includes the file path.
    assert "openai_export.json" in out
    # Body content is rendered.
    assert "alpha" in out
    assert "beta" in out


@pytest.mark.component
def test_render_shim_grep_routes_through_normalizer(monkeypatch, capsys):
    module = load_tool_module("run_agent_shim_grep_e2e", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    rtk_output = (
        "2 matches in 1F:\n"
        "\n"
        "[file] tools/run-agent.py (2):\n"
        "  100: foo bar\n"
        "  200: foo baz\n"
    )
    state = {
        "input": {"command": "rtk grep foo tools/run-agent.py", "description": "rtk grep"},
        "output": rtk_output,
        "status": "completed",
    }
    handled = module._maybe_render_bash_shim(None, state)
    assert handled is True
    out = capsys.readouterr().out
    assert "tools/run-agent.py" in out
    # Both line numbers should appear since grep renderer detected lines mode.
    assert "100" in out and "200" in out
    # The header pattern should be visible.
    assert "foo" in out


@pytest.mark.component
def test_render_shim_ls_long_format_strips_columns(monkeypatch, capsys):
    module = load_tool_module("run_agent_shim_ls_e2e", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    long_ls = (
        "total 4\n"
        "-rw-r--r--  1 u  g  10 May  8 README.md\n"
        "drwxr-xr-x  2 u  g   1 May  8 docs\n"
    )
    state = {
        "input": {"command": "ls -la", "description": "ls"},
        "output": long_ls,
        "status": "completed",
    }
    handled = module._maybe_render_bash_shim(None, state)
    assert handled is True
    out = capsys.readouterr().out
    assert "README.md" in out
    assert "docs" in out
    # Long-format columns must be gone.
    assert "rw-r--r--" not in out
    assert "May  8" not in out


@pytest.mark.component
def test_render_shim_ls_long_format_can_be_disabled(monkeypatch, capsys):
    module = load_tool_module("run_agent_shim_ls_no_strip", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_BASH_SHIM_LS_STRIP_LONG_FORMAT", False)

    long_ls = "total 4\n-rw-r--r--  1 u  g  10 May  8 README.md\n"
    state = {
        "input": {"command": "ls -la", "description": "ls"},
        "output": long_ls,
        "status": "completed",
    }
    handled = module._maybe_render_bash_shim(None, state)
    assert handled is True
    out = capsys.readouterr().out
    # When disabled, the renderer keeps the long-format raw line.
    assert "rw-r--r--" in out


@pytest.mark.unit
def test_maybe_render_bash_shim_disabled_via_env(monkeypatch):
    module = load_tool_module("run_agent_shim_disabled", "tools/run-agent.py")
    monkeypatch.setattr(module, "_BASH_SHIM_RENDER", False)
    state = {
        "input": {"command": "rtk read README.md"},
        "output": "anything",
        "status": "completed",
    }
    assert module._maybe_render_bash_shim(None, state) is False


@pytest.mark.unit
def test_maybe_render_bash_shim_skips_unrecognized_commands():
    module = load_tool_module("run_agent_shim_skip", "tools/run-agent.py")
    state = {
        "input": {"command": "make phase-1", "description": ""},
        "output": "Phase 1 done",
        "status": "completed",
    }
    assert module._maybe_render_bash_shim(None, state) is False


@pytest.mark.component
def test_render_shim_read_filtered_triggers_cache_reread(monkeypatch):
    """When rtk read uses a filtering flag, the renderer must call
    _cache_reread for each requested file so the cache holds raw disk
    content instead of the filtered output."""
    module = load_tool_module("run_agent_shim_filter_cache", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_INTERNAL_READ_SUPPRESS", False)

    cache_calls: list[str] = []
    monkeypatch.setattr(module, "_cache_reread", lambda p: cache_calls.append(p))

    state = {
        "input": {"command": "rtk read --level aggressive tools/run-agent.py", "description": "rtk read"},
        "output": "filtered content",
        "status": "completed",
    }
    handled = module._maybe_render_bash_shim(None, state)
    assert handled is True
    assert any("tools/run-agent.py" in c for c in cache_calls)


@pytest.mark.component
def test_render_shim_read_multi_file_triggers_cache_reread(monkeypatch):
    """rtk read of multiple files concatenates output without delimiters,
    so we cannot per-file split. The renderer must fall back to direct
    filesystem reads to refresh the cache."""
    module = load_tool_module("run_agent_shim_multi_cache", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_INTERNAL_READ_SUPPRESS", False)

    cache_calls: list[str] = []
    monkeypatch.setattr(module, "_cache_reread", lambda p: cache_calls.append(p))

    state = {
        "input": {"command": "rtk read README.md AGENTS.md", "description": "rtk read"},
        "output": "combined content",
        "status": "completed",
    }
    handled = module._maybe_render_bash_shim(None, state)
    assert handled is True
    assert sum("README.md" in c for c in cache_calls) == 1
    assert sum("AGENTS.md" in c for c in cache_calls) == 1


# ---------------------------------------------------------------------------
# Glob output parsing — summary line filtering
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_parse_glob_output_filters_summary_lines():
    module = load_tool_module("run_agent_glob_summary_1", "tools/run-agent.py")
    output = "0 for '*.md'\n"
    files, summaries = module._parse_glob_output(output)
    assert files == []
    assert summaries == ["0 for '*.md'"]


@pytest.mark.unit
def test_parse_glob_output_keeps_real_paths():
    module = load_tool_module("run_agent_glob_summary_2", "tools/run-agent.py")
    output = "src/foo.py\nsrc/bar.py\n"
    files, summaries = module._parse_glob_output(output)
    assert files == ["src/foo.py", "src/bar.py"]
    assert summaries == []


@pytest.mark.unit
def test_parse_glob_output_mixed():
    module = load_tool_module("run_agent_glob_summary_3", "tools/run-agent.py")
    output = "src/foo.py\nsrc/bar.py\n3 match(es)\n"
    files, summaries = module._parse_glob_output(output)
    assert files == ["src/foo.py", "src/bar.py"]
    assert len(summaries) == 1


@pytest.mark.unit
def test_parse_glob_output_no_matches_found():
    module = load_tool_module("run_agent_glob_summary_4", "tools/run-agent.py")
    output = "No matches found\n"
    files, summaries = module._parse_glob_output(output)
    assert files == []
    assert summaries == ["No matches found"]


@pytest.mark.component
def test_render_glob_plain_zero_matches_with_summary(capsys):
    module = load_tool_module("run_agent_glob_summary_5", "tools/run-agent.py")
    state = {
        "input": {"pattern": "**/*.md", "path": "itemdb/findings"},
        "output": "0 for '*.md'\n",
        "status": "completed",
    }
    result = module.render_glob_plain(state)
    assert result is True
    out = capsys.readouterr().out
    assert "0 for" in out
    # Footer should say 0, not 1.
    assert "0 match(es)" in out


# ---------------------------------------------------------------------------
# find -name extraction
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_parse_find_tree_extracts_name_filter():
    module = load_tool_module("run_agent_find_name_1", "tools/run-agent.py")
    shim = module._parse_find_tree("find", ["itemdb/findings", "-name", "*.md"], "find itemdb/findings -name '*.md'")
    assert shim is not None
    assert shim.pattern == "*.md"
    assert shim.path == "itemdb/findings"


@pytest.mark.unit
def test_parse_find_tree_extracts_iname_filter():
    module = load_tool_module("run_agent_find_name_2", "tools/run-agent.py")
    shim = module._parse_find_tree("find", [".", "-iname", "*.PY"], "find . -iname '*.PY'")
    assert shim is not None
    assert shim.pattern == "*.PY"
    assert shim.path == "."


@pytest.mark.unit
def test_parse_find_tree_no_name_falls_back_to_verb():
    module = load_tool_module("run_agent_find_name_3", "tools/run-agent.py")
    shim = module._parse_find_tree("find", ["src/"], "find src/")
    assert shim is not None
    assert shim.pattern == "find"
    assert shim.path == "src/"


@pytest.mark.unit
def test_parse_find_tree_extracts_path_after_type_flag():
    module = load_tool_module("run_agent_find_name_4", "tools/run-agent.py")
    shim = module._parse_find_tree("find", ["itemdb", "-type", "f", "-name", "*.md"], "find itemdb -type f -name '*.md'")
    assert shim is not None
    assert shim.pattern == "*.md"
    assert shim.path == "itemdb"


@pytest.mark.unit
def test_parse_find_tree_tree_verb_no_name():
    module = load_tool_module("run_agent_find_name_5", "tools/run-agent.py")
    shim = module._parse_find_tree("tree", ["src/"], "tree src/")
    assert shim is not None
    assert shim.pattern == "tree"
    assert shim.path == "src/"


# ---------------------------------------------------------------------------
# load_prompt extra-prompt tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def prompt_env(tmp_path, monkeypatch):
    """Set up an isolated environment for load_prompt tests."""
    config_module = _load_config_module()

    # Create a minimal prompt file.
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("# Phase prompt\n\nBase content.", encoding="utf-8")

    # Point ROOT at tmp_path so codecome.yml is found there.
    monkeypatch.setattr(config_module, "ROOT", tmp_path)

    # Clear env vars by default.
    monkeypatch.delenv("PROMPT_EXTRA", raising=False)
    monkeypatch.delenv("PROMPT_EXTRA_FILE", raising=False)

    return config_module, prompt_file, tmp_path


@pytest.mark.unit
def test_load_prompt_no_extras(prompt_env):
    module, prompt_file, _ = prompt_env
    result = module.load_prompt(prompt_file, None)
    assert result == "# Phase prompt\n\nBase content."
    assert "Additional instructions" not in result


@pytest.mark.unit
def test_load_prompt_inline_extra(prompt_env, monkeypatch):
    module, prompt_file, _ = prompt_env
    monkeypatch.setenv("PROMPT_EXTRA", "Use ASAN builds.")
    result = module.load_prompt(prompt_file, None, phase="1")
    assert "## Additional instructions" in result
    assert "Use ASAN builds." in result


@pytest.mark.unit
def test_load_prompt_extra_file(prompt_env, monkeypatch):
    module, prompt_file, tmp_path = prompt_env
    extra_file = tmp_path / "extra.md"
    extra_file.write_text("Extra from file.", encoding="utf-8")
    monkeypatch.setenv("PROMPT_EXTRA_FILE", str(extra_file))
    result = module.load_prompt(prompt_file, None, phase="1")
    assert "## Additional instructions" in result
    assert "Extra from file." in result


@pytest.mark.unit
def test_load_prompt_yaml_extra(prompt_env):
    module, prompt_file, tmp_path = prompt_env
    yml = tmp_path / "codecome.yml"
    yml.write_text(
        "audit:\n  extra_prompts:\n    reconnaissance: |\n      Focus on memory safety.\n",
        encoding="utf-8",
    )
    result = module.load_prompt(prompt_file, None, phase="1")
    assert "## Additional instructions" in result
    assert "Focus on memory safety." in result
    assert "From codecome.yml" in result


@pytest.mark.unit
def test_load_prompt_all_three_sources(prompt_env, monkeypatch):
    module, prompt_file, tmp_path = prompt_env

    # YAML source
    yml = tmp_path / "codecome.yml"
    yml.write_text(
        "audit:\n  extra_prompts:\n    reconnaissance: |\n      YAML extra.\n",
        encoding="utf-8",
    )

    # File source
    extra_file = tmp_path / "extra.md"
    extra_file.write_text("File extra.", encoding="utf-8")
    monkeypatch.setenv("PROMPT_EXTRA_FILE", str(extra_file))

    # Inline source
    monkeypatch.setenv("PROMPT_EXTRA", "Inline extra.")

    result = module.load_prompt(prompt_file, None, phase="1")
    assert "## Additional instructions" in result
    assert "YAML extra." in result
    assert "File extra." in result
    assert "Inline extra." in result

    # Verify ordering: yaml before file before inline.
    yaml_pos = result.index("YAML extra.")
    file_pos = result.index("File extra.")
    inline_pos = result.index("Inline extra.")
    assert yaml_pos < file_pos < inline_pos


@pytest.mark.unit
def test_load_prompt_no_phase_skips_yaml(prompt_env, monkeypatch):
    module, prompt_file, tmp_path = prompt_env
    yml = tmp_path / "codecome.yml"
    yml.write_text(
        "audit:\n  extra_prompts:\n    reconnaissance: |\n      Should not appear.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROMPT_EXTRA", "Inline only.")
    result = module.load_prompt(prompt_file, None)  # no phase
    assert "Should not appear." not in result
    assert "Inline only." in result


@pytest.mark.unit
def test_load_prompt_empty_extras_no_heading(prompt_env, monkeypatch):
    module, prompt_file, _ = prompt_env
    monkeypatch.setenv("PROMPT_EXTRA", "   ")  # whitespace only
    monkeypatch.setenv("PROMPT_EXTRA_FILE", "")
    result = module.load_prompt(prompt_file, None, phase="1")
    assert "Additional instructions" not in result


@pytest.mark.unit
def test_load_prompt_finding_substitution_still_works(prompt_env):
    module, _, tmp_path = prompt_env
    prompt_file = tmp_path / "prompt-with-finding.md"
    prompt_file.write_text("Validate FINDING_PATH_OR_ID now.", encoding="utf-8")
    result = module.load_prompt(prompt_file, "CC-0001", phase="4")
    assert "CC-0001" in result
    assert "FINDING_PATH_OR_ID" not in result


@pytest.mark.unit
def test_load_prompt_relative_extra_file(prompt_env, monkeypatch):
    module, prompt_file, tmp_path = prompt_env
    extra_file = tmp_path / "notes" / "extra.md"
    extra_file.parent.mkdir()
    extra_file.write_text("Relative file content.", encoding="utf-8")
    monkeypatch.setenv("PROMPT_EXTRA_FILE", "notes/extra.md")
    result = module.load_prompt(prompt_file, None, phase="1")
    assert "Relative file content." in result


@pytest.mark.component
def test_auto_correction_resume_loops_back_via_popen(monkeypatch, tmp_path):
    """Frontmatter errors trigger a resume of the same session; on the second
    attempt the check passes and main exits 0.  The session ID must come from
    the event stream, not from a DB fallback."""
    module = load_tool_module("run_agent_autocorrect_serve", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "check_opencode_version", lambda: None)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    import sys
    monkeypatch.setattr(sys.modules["codecome.cli_render"], "ROOT", tmp_path)

    sys.path.insert(0, str(ROOT / "tools"))
    if "codecome" in sys.modules and not hasattr(sys.modules["codecome"], "__path__"):
        del sys.modules["codecome"]
    import codecome.runner as _runner

    # Reset the attempt counter so transcript numbering is deterministic.
    if hasattr(_runner._run_single_attempt, "_attempt_counter"):
        delattr(_runner._run_single_attempt, "_attempt_counter")

    calls: list[tuple] = []

    def fake_run_single_attempt(args, console, prompt, model, variant, thinking_on, base_url, auth_token, workspace_dir, **kwargs):
        existing_session_id = kwargs.get("existing_session_id")
        calls.append((existing_session_id, prompt))
        # Both attempts succeed with the same session.
        return (
            0,
            "ses_test_abc",
            module.RunResult(
                any_step_finish_seen=True,
                step_finish_count=1,
                last_finish_reason="stop",
                last_finish_tokens={},
                last_permission_error=None,
            ),
            tmp_path / f"transcript-{len(calls)}.jsonl",
        )

    monkeypatch.setattr(_runner, "_run_single_attempt", fake_run_single_attempt)

    frontmatter_call_count = [0]

    class FakeResult:
        def __init__(self, rc, out="", err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def fake_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return FakeResult(0, out="opencode 1.15.0\n")
        if any("check-frontmatter" in str(c) for c in cmd):
            frontmatter_call_count[0] += 1
            if frontmatter_call_count[0] == 1:
                return FakeResult(1, err="bad frontmatter")
            return FakeResult(0)
        return FakeResult(0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    prompt_file = tmp_path / "phase.md"
    prompt_file.write_text("run recon", encoding="utf-8")
    monkeypatch.setattr(module.sys, "argv", [
        "run-agent.py", "--phase", "1", "--label", "test",
        "--agent", "recon", "--prompt-file", str(prompt_file),
    ])

    rc = module.main()
    assert rc == 0
    assert len(calls) == 2, f"expected 2 attempts, got {len(calls)}"
    # First attempt is a fresh session; second reuses the same session ID.
    assert calls[0][0] is None
    assert calls[1][0] == "ses_test_abc"
    # The second prompt should be the frontmatter repair prompt.
    assert "Repair only the reported YAML/frontmatter issues" in calls[1][1]


@pytest.mark.component
def test_frontmatter_failure_without_session_id_exits_nonzero(monkeypatch, tmp_path):
    """Frontmatter validation failures must not be reported as success when
    the wrapper cannot determine a resumable session ID."""
    module = load_tool_module("run_agent_frontmatter_no_session_serve", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "check_opencode_version", lambda: None)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    import sys
    monkeypatch.setattr(sys.modules["codecome.cli_render"], "ROOT", tmp_path)

    sys.path.insert(0, str(ROOT / "tools"))
    if "codecome" in sys.modules and not hasattr(sys.modules["codecome"], "__path__"):
        del sys.modules["codecome"]
    import codecome.runner as _runner

    if hasattr(_runner._run_single_attempt, "_attempt_counter"):
        delattr(_runner._run_single_attempt, "_attempt_counter")

    def fake_run_single_attempt(args, console, prompt, model, variant, thinking_on, base_url, auth_token, workspace_dir, **kwargs):
        return (
            0,
            "",  # empty session ID
            module.RunResult(
                any_step_finish_seen=True,
                step_finish_count=1,
                last_finish_reason="stop",
            ),
            tmp_path / "transcript.jsonl",
        )

    monkeypatch.setattr(_runner, "_run_single_attempt", fake_run_single_attempt)

    class FakeResult:
        def __init__(self, rc, out="", err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def fake_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return FakeResult(0, out="opencode 1.15.0\n")
        if any("check-frontmatter" in str(c) for c in cmd):
            return FakeResult(1, err="bad frontmatter")
        return FakeResult(0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    prompt_file = tmp_path / "phase.md"
    prompt_file.write_text("run recon", encoding="utf-8")
    monkeypatch.setattr(module.sys, "argv", [
        "run-agent.py", "--phase", "1", "--label", "test",
        "--agent", "recon", "--prompt-file", str(prompt_file),
    ])

    rc = module.main()
    assert rc == 2


@pytest.mark.component
def test_iteration_limit_triggers_auto_resume(monkeypatch, tmp_path):
    """When the stream ends with a mid-turn finish reason (tool-calls) and
    graceful forgiveness does not apply, run-agent resumes once then exits."""
    module = load_tool_module("run_agent_iter_resume_serve", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "check_opencode_version", lambda: None)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    import sys
    monkeypatch.setattr(sys.modules["codecome.cli_render"], "ROOT", tmp_path)
    monkeypatch.setenv("CODECOME_MAX_ITERATION_RETRIES", "1")

    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    if "codecome" in sys.modules and not hasattr(sys.modules["codecome"], "__path__"):
        del sys.modules["codecome"]
    import codecome.runner as _runner

    if hasattr(_runner._run_single_attempt, "_attempt_counter"):
        delattr(_runner._run_single_attempt, "_attempt_counter")

    calls: list[tuple] = []

    def fake_run_single_attempt(args, console, prompt, model, variant, thinking_on, base_url, auth_token, workspace_dir, **kwargs):
        existing_session_id = kwargs.get("existing_session_id")
        calls.append((existing_session_id, prompt))
        return (
            0,
            "ses_iter_xyz",
            module.RunResult(
                any_step_finish_seen=True,
                step_finish_count=1,
                last_finish_reason="tool-calls",
            ),
            tmp_path / f"transcript-{len(calls)}.jsonl",
        )

    monkeypatch.setattr(_runner, "_run_single_attempt", fake_run_single_attempt)
    monkeypatch.setattr(module, "check_phase_graceful_completion", lambda *a, **kw: False)

    class FakeResult:
        def __init__(self, rc, out="", err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def fake_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return FakeResult(0, out="opencode 1.15.0\n")
        if any("check-frontmatter" in str(c) for c in cmd):
            return FakeResult(0)
        return FakeResult(0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    prompt_file = tmp_path / "phase.md"
    prompt_file.write_text("run recon for FINDING_PATH_OR_ID", encoding="utf-8")
    monkeypatch.setattr(module.sys, "argv", [
        "run-agent.py", "--phase", "4", "--label", "test",
        "--agent", "recon", "--prompt-file", str(prompt_file),
        "--finding", "CC-9999",
    ])

    rc = module.main()

    # After 1 retry (2 total attempts) the retry budget is exhausted → exit 2
    assert len(calls) == 2, f"expected 2 attempts, got {len(calls)}"
    assert rc == 2

    # Verify the retry reused the same session and included the resume prompt.
    assert calls[1][0] == "ses_iter_xyz"
    assert "Your previous response was cut off by the model/provider" in calls[1][1]


# ---------------------------------------------------------------------------
# check_phase_graceful_completion – mtime-aware artifact detection
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_check_phase_graceful_completion_mtime(monkeypatch, tmp_path):
    """Graceful completion is only True when the artifact was written during
    the current run (st_mtime >= run_start_time)."""
    import os

    module = _load_graceful_module()
    monkeypatch.setattr(module, "ROOT", tmp_path)

    start = 1_000_000.0
    old   = start - 1.0
    fresh = start + 1.0

    # ---- Phase 1 ----
    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    phase1_files = {
        name: notes / name for name in module._PHASE1_REQUIRED_ARTIFACT_NAMES
    }
    sandbox_generated = tmp_path / "sandbox" / "CODECOME-GENERATED.md"
    sandbox_generated.parent.mkdir(parents=True)

    # missing files
    assert module.check_phase_graceful_completion("1", None, start) is False

    for path in phase1_files.values():
        path.write_text("x")
        os.utime(path, (old, old))
    assert module.check_phase_graceful_completion("1", None, start) is False

    sandbox_generated.write_text("x")
    os.utime(sandbox_generated, (old, old))
    os.utime(phase1_files["target-profile.md"], (fresh, fresh))
    assert module.check_phase_graceful_completion("1", None, start) is False

    os.utime(sandbox_generated, (fresh, fresh))
    assert module.check_phase_graceful_completion("1", None, start) is True

    # ---- Phase 2 ----
    pending = tmp_path / "itemdb" / "findings" / "PENDING"
    pending.mkdir(parents=True)
    f2 = pending / "CC-0001.md"; f2.write_text("x")
    os.utime(f2, (old, old))
    assert module.check_phase_graceful_completion("2", None, start) is False
    os.utime(f2, (fresh, fresh))
    assert module.check_phase_graceful_completion("2", None, start) is True

    # ---- Phase 3: touches any finding in any status dir ----
    confirmed = tmp_path / "itemdb" / "findings" / "CONFIRMED"
    confirmed.mkdir(parents=True)
    f3 = confirmed / "CC-0002.md"; f3.write_text("x")
    os.utime(f3, (old, old))
    # Phase 2 file is still fresh but phase 3 should check all dirs
    assert module.check_phase_graceful_completion("3", None, start) is True
    # Make the phase 2 file old too
    os.utime(f2, (old, old))
    assert module.check_phase_graceful_completion("3", None, start) is False
    os.utime(f3, (fresh, fresh))
    assert module.check_phase_graceful_completion("3", None, start) is True

    # ---- Phase 5: NOT_FEASIBLE fallback (CONFIRMED finding with frontmatter) ----
    conf5 = confirmed / "CC-0005.md"
    conf5.write_text(
        "---\n"
        "status: CONFIRMED\n"
        "exploitation:\n"
        "  status: NOT_FEASIBLE\n"
        "---\n"
    )
    os.utime(conf5, (old, old))
    assert module.check_phase_graceful_completion("5", "CC-0005", start) is False
    os.utime(conf5, (fresh, fresh))
    assert module.check_phase_graceful_completion("5", "CC-0005", start) is True

    # ---- Phase 5: EXPLOITED path requires frontmatter + exploit artifacts ----
    # Age the NOT_FEASIBLE fallback so it no longer matches.
    os.utime(conf5, (old, old))
    exploited_dir = tmp_path / "itemdb" / "findings" / "EXPLOITED"
    exploited_dir.mkdir(parents=True)
    exp5 = exploited_dir / "CC-0005.md"
    exp5.write_text(
        "---\n"
        "status: EXPLOITED\n"
        "exploitation:\n"
        "  status: COMPLETED\n"
        "---\n"
    )
    os.utime(exp5, (old, old))
    # Still False: no fresh exploit artifacts
    assert module.check_phase_graceful_completion("5", "CC-0005", start) is False

    exploits = tmp_path / "itemdb" / "evidence" / "CC-0005" / "exploits"
    exploits.mkdir(parents=True)
    xf = exploits / "exploit.py"
    xf.write_text("x")
    os.utime(xf, (fresh, fresh))
    os.utime(exp5, (fresh, fresh))
    assert module.check_phase_graceful_completion("5", "CC-0005", start) is True

    # ---- Phase 6 ----
    reports = tmp_path / "itemdb" / "reports"
    reports.mkdir(parents=True)
    rpt = reports / "report.md"; rpt.write_text("x")
    os.utime(rpt, (old, old))
    assert module.check_phase_graceful_completion("6", None, start) is False
    os.utime(rpt, (fresh, fresh))
    assert module.check_phase_graceful_completion("6", None, start) is True


@pytest.mark.unit
def test_stream_session_id_and_step_finish_count(monkeypatch, tmp_path):
    """Verify that the main loop captures sessionID and step_finish count
    from the RunResult returned by _run_single_attempt."""
    module = load_tool_module("run_agent_stream_tracking_serve", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "check_opencode_version", lambda: None)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    import sys
    monkeypatch.setattr(sys.modules["codecome.cli_render"], "ROOT", tmp_path)

    sys.path.insert(0, str(ROOT / "tools"))
    if "codecome" in sys.modules and not hasattr(sys.modules["codecome"], "__path__"):
        del sys.modules["codecome"]
    import codecome.runner as _runner

    if hasattr(_runner._run_single_attempt, "_attempt_counter"):
        delattr(_runner._run_single_attempt, "_attempt_counter")

    def fake_run_single_attempt(args, console, prompt, model, variant, thinking_on, base_url, auth_token, workspace_dir, **kwargs):
        return (
            0,
            "ses_stream_test_001",
            module.RunResult(
                any_step_finish_seen=True,
                step_finish_count=3,
                last_finish_reason="stop",
                last_finish_tokens={"input": 10, "output": 20},
            ),
            tmp_path / "transcript.jsonl",
        )

    monkeypatch.setattr(_runner, "_run_single_attempt", fake_run_single_attempt)

    class FakeResult:
        def __init__(self, rc, out="", err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def fake_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return FakeResult(0, out="opencode 1.15.0\n")
        if any("check-frontmatter" in str(c) for c in cmd):
            return FakeResult(0)
        return FakeResult(0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    prompt_file = tmp_path / "phase.md"
    prompt_file.write_text("run recon", encoding="utf-8")
    monkeypatch.setattr(module.sys, "argv", [
        "run-agent.py", "--phase", "1", "--label", "test",
        "--agent", "recon", "--prompt-file", str(prompt_file),
    ])

    rc = module.main()
    assert rc == 0

    # The session terminated with 'stop', no frontmatter errors → single attempt
    # (We cannot introspect the loop variables directly, but the clean exit
    # with rc=0 proves the RunResult signals were consumed correctly.)


@pytest.mark.unit
def test_render_event_fallback_to_unknown_renderer(monkeypatch):
    """render_event falls back to UnknownEventRenderer for unregistered event types
    without raising NameError."""
    module = load_tool_module("run_agent_unknown_fallback", "tools/run-agent.py")
    ctx = module._get_rendering_ctx(None)
    renderers = getattr(ctx, "_renderers", {})

    # Ensure the "unknown" key is absent so the fallback path is triggered.
    renderers.pop("unknown", None)
    renderers.pop("some.unregistered.event", None)

    # Should not raise NameError.
    module.render_event(
        None, "2", "x",
        {"type": "some.unregistered.event", "properties": {"foo": "bar"}}
    )


@pytest.mark.component
def test_first_attempt_failure_prints_finish_warning(monkeypatch, tmp_path):
    """When _run_single_attempt returns non-zero on the very first iteration,
    main() should not raise UnboundLocalError for finish_warning."""
    module = load_tool_module("run_agent_first_fail", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "check_opencode_version", lambda: None)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    import sys
    monkeypatch.setattr(sys.modules["codecome.cli_render"], "ROOT", tmp_path)

    sys.path.insert(0, str(ROOT / "tools"))
    if "codecome" in sys.modules and not hasattr(sys.modules["codecome"], "__path__"):
        del sys.modules["codecome"]
    import codecome.runner as _runner

    if hasattr(_runner._run_single_attempt, "_attempt_counter"):
        delattr(_runner._run_single_attempt, "_attempt_counter")

    def fake_run_single_attempt(args, console, prompt, model, variant, thinking_on, base_url, auth_token, workspace_dir, **kwargs):
        return (
            1,  # non-zero return code on first attempt
            "",
            module.RunResult(
                any_step_finish_seen=False,
                step_finish_count=0,
                last_finish_reason=None,
                last_finish_tokens={},
                last_permission_error=None,
            ),
            tmp_path / "transcript.jsonl",
        )

    monkeypatch.setattr(_runner, "_run_single_attempt", fake_run_single_attempt)

    class FakeResult:
        def __init__(self, rc, out="", err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def fake_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return FakeResult(0, out="opencode 1.15.0\n")
        return FakeResult(0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    prompt_file = tmp_path / "phase.md"
    prompt_file.write_text("run recon", encoding="utf-8")
    monkeypatch.setattr(module.sys, "argv", [
        "run-agent.py", "--phase", "1", "--label", "test",
        "--agent", "recon", "--prompt-file", str(prompt_file),
    ])

    rc = module.main()
    assert rc == 1
