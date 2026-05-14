from __future__ import annotations

import pytest
from rich.console import Console

from conftest import ROOT, load_tool_module


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
    module = load_tool_module("run_agent_matrix", "tools/run-agent.py")
    payload = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    assert module._extract_model_from_export(payload) == expected


@pytest.mark.unit
def test_extract_flag_value_supports_both_flag_forms():
    module = load_tool_module("run_agent_flags", "tools/run-agent.py")
    tokens = ["--model=openai/gpt-5", "--variant", "high"]
    assert module._extract_flag_value(tokens, ("--model", "-m")) == "openai/gpt-5"
    assert module._extract_flag_value(tokens, ("--variant",)) == "high"


@pytest.mark.unit
def test_strip_probe_unsafe_flags_removes_session_and_continue_flags():
    module = load_tool_module("run_agent_strip", "tools/run-agent.py")
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
    module = load_tool_module("run_agent_resolve", "tools/run-agent.py")
    monkeypatch.setenv("CODECOME_MODEL", "env/model")
    monkeypatch.setenv("CODECOME_MODEL_VARIANT", "max")
    monkeypatch.setattr(module, "_read_codecome_yml_agent", lambda _agent: ("yaml/model", "yamlvar"))
    monkeypatch.setattr(module, "_discover_opencode_default_model", lambda: "history/model")

    model, variant, model_source, variant_source = module.resolve_model_and_variant(
        "auditor", ["--model", "args/model", "--variant=high"]
    )
    assert (model, variant) == ("args/model", "high")
    assert model_source == "OPENCODE_ARGS"
    assert variant_source == "OPENCODE_ARGS"


@pytest.mark.component
def test_build_child_command_appends_enforced_env_model(monkeypatch):
    module = load_tool_module("run_agent_child", "tools/run-agent.py")
    monkeypatch.setenv("OPENCODE_ARGS", "")
    monkeypatch.setenv("CODECOME_MODEL", "env/model")
    monkeypatch.setenv("CODECOME_MODEL_VARIANT", "high")

    class Args:
        agent = "recon"

    cmd, model, variant, model_source, variant_source, thinking_on, thinking_source = module.build_child_command(Args())
    assert cmd[:5] == ["opencode", "run", "--format", "json", "--agent"]
    assert "--model" in cmd and "env/model" in cmd
    assert "--variant" in cmd and "high" in cmd
    assert "--thinking" in cmd
    assert thinking_on is True
    assert thinking_source == "provider-default"
    assert model_source == "env CODECOME_MODEL"
    assert variant_source == "env CODECOME_MODEL_VARIANT"


@pytest.mark.component
def test_stream_model_scan_finds_nested_provider_model_pair():
    module = load_tool_module("run_agent_scan", "tools/run-agent.py")
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
    module = load_tool_module("run_agent_thinking_default", "tools/run-agent.py")
    assert module._thinking_default_for_provider("anthropic") is False
    assert module._thinking_default_for_provider("anthropic-foo") is False
    assert module._thinking_default_for_provider("openai") is True
    assert module._thinking_default_for_provider(None) is True


@pytest.mark.unit
def test_resolve_thinking_decision_precedence(monkeypatch):
    module = load_tool_module("run_agent_thinking_precedence", "tools/run-agent.py")

    on, source = module._resolve_thinking_decision("anthropic/claude-opus-4-7", ["--thinking"])
    assert (on, source) == (True, "user-args")

    monkeypatch.setenv("CODECOME_THINKING", "0")
    on, source = module._resolve_thinking_decision("openai/gpt-5", [])
    assert (on, source) == (False, "env")

    monkeypatch.setenv("CODECOME_THINKING", "1")
    on, source = module._resolve_thinking_decision("anthropic/claude-opus-4-7", [])
    assert (on, source) == (True, "env")


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
def test_render_reasoning_plain_mode_honors_toggle_and_truncates(monkeypatch, capsys):
    module = load_tool_module("run_agent_reasoning_plain", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setattr(module, "_RENDER_REASONING", True)
    monkeypatch.setattr(module, "_REASONING_MAX_CHARS", 5)

    module.render_reasoning(None, {"part": {"text": "abcdefgh"}})
    out = capsys.readouterr().out
    assert "Thinking" in out
    assert "abcde" in out
    assert "chars truncated" in out

    monkeypatch.setattr(module, "_RENDER_REASONING", False)
    module.render_reasoning(None, {"part": {"text": "should not print"}})
    out = capsys.readouterr().out
    assert out == ""


@pytest.mark.unit
def test_render_error_plain_mode_extracts_message_shapes(monkeypatch, capsys):
    module = load_tool_module("run_agent_error_plain", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    module.render_error(None, {"error": {"name": "ToolError", "data": {"message": "boom"}}})
    out = capsys.readouterr().out
    assert "Error" in out
    assert "ToolError: boom" in out

    module.render_error(None, {"error": "simple error"})
    out = capsys.readouterr().out
    assert "simple error" in out


@pytest.mark.unit
def test_render_event_dispatches_reasoning_and_error(monkeypatch):
    module = load_tool_module("run_agent_dispatch", "tools/run-agent.py")
    calls = []

    def _fake_reasoning(_console, _event):
        calls.append("reasoning")

    def _fake_error(_console, _event):
        calls.append("error")
        
    def _fake_session_status(_console, _event):
        calls.append("session.status")

    monkeypatch.setattr(module, "render_reasoning", _fake_reasoning)
    monkeypatch.setattr(module, "render_error", _fake_error)
    monkeypatch.setattr(module, "render_session_status", _fake_session_status)

    module.render_event(None, "2", "x", {"type": "reasoning", "part": {"text": "x"}})
    module.render_event(None, "2", "x", {"type": "error", "error": "x"})
    module.render_event(None, "2", "x", {"type": "session.status", "properties": {"status": {"type": "retry", "attempt": 1}}})

    assert calls == ["reasoning", "error", "session.status"]


@pytest.mark.unit
def test_render_session_status_plain_mode(monkeypatch, capsys):
    module = load_tool_module("run_agent_session_status_plain", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    
    event = {
        "type": "session.status",
        "properties": {
            "sessionID": "ses_123",
            "status": {
                "type": "retry",
                "attempt": 2,
                "message": "Rate limit exceeded"
            }
        }
    }
    
    module.render_session_status(None, event)
    out = capsys.readouterr().out
    assert "Waiting for LLM provider response" in out
    assert "retry attempt 2" in out
    assert "Rate limit exceeded" in out


@pytest.mark.unit
def test_finish_reason_sets_are_disjoint_and_expected():
    module = load_tool_module("run_agent_finish_sets", "tools/run-agent.py")

    terminal = module._FINISH_TERMINAL_OK
    mid_turn = module._FINISH_MID_TURN
    failure = module._FINISH_FAILURE

    assert "stop" in terminal
    assert "end_turn" in terminal
    assert "tool-calls" in mid_turn
    assert "error" in failure

    assert terminal.isdisjoint(mid_turn)
    assert terminal.isdisjoint(failure)
    assert mid_turn.isdisjoint(failure)


@pytest.mark.unit
def test_render_step_finish_plain_mode_marks_failure_reason_red(monkeypatch, capsys):
    module = load_tool_module("run_agent_step_finish_failure", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    fail_calls = []

    def fake_fail(msg):
        fail_calls.append(msg)
        return msg

    monkeypatch.setattr(module.C, "fail", fake_fail)

    module.render_step_finish(None, {"part": {"reason": "content-filter", "tokens": {}}})
    out = capsys.readouterr().out

    assert any("step finished: content-filter" in m for m in fail_calls)
    assert "step finished: content-filter" in out


@pytest.mark.unit
def test_render_step_finish_plain_mode_non_failure_is_plain(monkeypatch, capsys):
    module = load_tool_module("run_agent_step_finish_ok", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    fail_calls = []

    def fake_fail(msg):
        fail_calls.append(msg)
        return msg

    monkeypatch.setattr(module.C, "fail", fake_fail)

    module.render_step_finish(None, {"part": {"reason": "stop", "tokens": {"input": 10}}})
    out = capsys.readouterr().out

    assert fail_calls == []
    assert "step finished: stop" in out


@pytest.mark.unit
def test_finish_reason_classification_logic_matches_contract():
    module = load_tool_module("run_agent_finish_contract", "tools/run-agent.py")

    def classify(reason: str | None, any_seen: bool) -> str:
        if not any_seen:
            return "no-step-finish"
        if reason is None:
            return "missing"
        if reason in module._FINISH_FAILURE:
            return "failure"
        if reason in module._FINISH_MID_TURN:
            return "mid-turn"
        if reason in module._FINISH_TERMINAL_OK:
            return "ok"
        return "unknown"

    assert classify("stop", True) == "ok"
    assert classify("tool_use", True) == "mid-turn"
    assert classify("length", True) == "failure"
    assert classify("something-new", True) == "unknown"
    assert classify(None, True) == "missing"
    assert classify(None, False) == "no-step-finish"


@pytest.mark.unit
def test_extract_tool_permission_error_for_read_path():
    module = load_tool_module("run_agent_permission_error_read", "tools/run-agent.py")
    event = {
        "type": "tool_use",
        "part": {
            "tool": "read",
            "state": {
                "status": "error",
                "input": {"filePath": "/tmp/workspace/sandbox/.env"},
                "error": "The user rejected permission to use this specific tool call.",
            },
        },
    }
    msg = module._extract_tool_permission_error(event)
    assert msg == "tool permission rejected: read /tmp/workspace/sandbox/.env"


@pytest.mark.unit
def test_extract_tool_permission_error_for_bash_command():
    module = load_tool_module("run_agent_permission_error_bash", "tools/run-agent.py")
    event = {
        "type": "tool_use",
        "part": {
            "tool": "bash",
            "state": {
                "status": "error",
                "input": {"command": "rm -rf /"},
                "error": "permission denied",
            },
        },
    }
    msg = module._extract_tool_permission_error(event)
    assert msg == "tool permission rejected: bash `rm -rf /`"


@pytest.mark.unit
def test_extract_tool_permission_error_ignores_non_permission_errors():
    module = load_tool_module("run_agent_permission_error_ignore", "tools/run-agent.py")
    event = {
        "type": "tool_use",
        "part": {
            "tool": "read",
            "state": {
                "status": "error",
                "input": {"filePath": "/tmp/x"},
                "error": "File not found",
            },
        },
    }
    assert module._extract_tool_permission_error(event) is None


@pytest.mark.unit
def test_extract_apply_patch_payload_prefers_patchtext_key():
    module = load_tool_module("run_agent_patchtext_key", "tools/run-agent.py")
    state = {
        "input": {
            "input": "*** Begin Patch\n*** Update File: a.txt\n+wrong\n*** End Patch",
            "patchText": "*** Begin Patch\n*** Update File: b.txt\n+right\n*** End Patch",
        },
        "output": "Applied patch",
        "status": "completed",
    }

    raw_text, patches, output_str = module._extract_apply_patch_payload(state)
    assert "b.txt" in raw_text
    assert len(patches) == 1
    assert patches[0].path == "b.txt"
    assert patches[0].added == 1
    assert output_str == "Applied patch"


@pytest.mark.unit
def test_parse_apply_patch_envelope_handles_multiple_directives():
    module = load_tool_module("run_agent_patch_multi", "tools/run-agent.py")
    patch = """*** Begin Patch
*** Update File: foo.txt
@@
-old
+new
*** Add File: bar.txt
+hello
*** Delete File: gone.txt
*** End Patch
"""

    parsed = module._parse_apply_patch_envelope(patch)
    assert len(parsed) == 3

    assert parsed[0].op == "update"
    assert parsed[0].path == "foo.txt"
    assert parsed[0].added == 1
    assert parsed[0].removed == 1

    assert parsed[1].op == "add"
    assert parsed[1].path == "bar.txt"
    assert parsed[1].added == 1
    assert parsed[1].removed == 0

    assert parsed[2].op == "delete"
    assert parsed[2].path == "gone.txt"


@pytest.mark.unit
def test_extract_apply_patch_payload_parses_json_patches_variant():
    module = load_tool_module("run_agent_patch_json_variant", "tools/run-agent.py")
    state = {
        "input": {
            "patches": [
                {"path": "x.py", "patchText": "@@\n-old\n+new"},
                {"file": "y.py", "diff": "@@\n-a\n+b"},
            ]
        },
        "output": "done",
    }

    raw_text, patches, output_str = module._extract_apply_patch_payload(state)
    assert raw_text == ""
    assert output_str == "done"
    assert len(patches) == 2
    assert patches[0].path == "x.py"
    assert patches[0].added == 1 and patches[0].removed == 1
    assert patches[1].path == "y.py"


@pytest.mark.unit
def test_extract_apply_patch_payload_falls_back_to_unknown_unified_diff():
    module = load_tool_module("run_agent_patch_unified", "tools/run-agent.py")
    diff = "--- a/a.txt\n+++ b/a.txt\n@@\n-old\n+new\n"
    state = {"input": diff, "output": "ok"}

    raw_text, patches, output_str = module._extract_apply_patch_payload(state)
    assert raw_text == diff
    assert output_str == "ok"
    assert len(patches) == 1
    assert patches[0].op == "unknown"
    assert patches[0].path == "(patch)"
    assert patches[0].added == 1 and patches[0].removed == 1


# --- _first_string and _PATCH_TEXT_KEYS -------------------------------------

@pytest.mark.unit
def test_first_string_skips_non_string_and_empty_values():
    module = load_tool_module("run_agent_first_string", "tools/run-agent.py")
    keys = ("a", "b", "c", "d")

    # None, empty string, dict, and number are all rejected; the first
    # non-empty string wins.
    d = {"a": None, "b": "", "c": {"nested": "no"}, "d": "yes"}
    assert module._first_string(d, keys) == "yes"

    # Number-typed value should not be coerced via str().
    d = {"a": 42, "b": "fallback"}
    assert module._first_string(d, keys) == "fallback"

    # No string under any key.
    assert module._first_string({"a": None, "b": 0}, keys) == ""


@pytest.mark.unit
def test_patch_text_keys_have_correct_precedence_order():
    module = load_tool_module("run_agent_patch_keys", "tools/run-agent.py")

    # patchText must beat patch_text must beat patch must beat input must
    # beat content. Order matters: github-copilot/gpt-5.4 emits patchText
    # and that is what triggered the original bug fix.
    expected_first = ("patchText", "patch_text", "patch", "input", "content")
    assert module._PATCH_TEXT_KEYS[: len(expected_first)] == expected_first


@pytest.mark.unit
def test_extract_apply_patch_payload_ignores_non_string_patch_values():
    module = load_tool_module("run_agent_patch_ignores_nonstring", "tools/run-agent.py")

    # If patchText is a dict (something an SDK might pass through by
    # mistake), we must NOT stringify it via str(...). Earlier code did
    # `str(inp.get("patch", ...))` which silently produced "{'foo': 1}",
    # corrupting the parser. Now those keys are skipped and the next
    # valid string key wins.
    state = {
        "input": {
            "patchText": {"oops": "wrong shape"},
            "patch": "*** Begin Patch\n*** Update File: real.txt\n+ok\n*** End Patch",
        },
        "output": "done",
    }
    raw_text, patches, _ = module._extract_apply_patch_payload(state)
    assert "real.txt" in raw_text
    assert len(patches) == 1
    assert patches[0].path == "real.txt"


@pytest.mark.unit
def test_extract_apply_patch_payload_handles_none_value_without_str_coercion():
    module = load_tool_module("run_agent_patch_none", "tools/run-agent.py")

    # If patchText is explicitly None, we must not produce raw_text="None"
    # which would then fail to parse and fall through to the generic JSON
    # panel. This is the "str(None)" regression class from the original
    # bug.
    state = {"input": {"patchText": None}, "output": "ok"}
    raw_text, patches, _ = module._extract_apply_patch_payload(state)
    assert raw_text == ""
    assert patches == []


# --- apply_patch envelope: regex bug regression ----------------------------

@pytest.mark.unit
def test_parse_apply_patch_envelope_does_not_swallow_next_directive_after_begin():
    """Regex must split on each *** directive even when no horizontal
    whitespace separates them. The bug fix changed `\\s*` to `[ \\t]*` so
    that newlines remain directive separators. Reproduces the exact
    pattern emitted by github-copilot/gpt-5.4.
    """
    module = load_tool_module("run_agent_envelope_regex", "tools/run-agent.py")

    patch = (
        "*** Begin Patch\n"
        "*** Delete File: /abs/path/sandbox-plan.md\n"
        "*** Add File: /abs/path/sandbox-plan.md\n"
        "+# New Content\n"
        "+more\n"
        "*** End Patch\n"
    )

    parsed = module._parse_apply_patch_envelope(patch)
    # Must produce exactly two file entries: a delete and an add.
    assert len(parsed) == 2
    assert parsed[0].op == "delete"
    assert parsed[0].path == "/abs/path/sandbox-plan.md"
    assert parsed[1].op == "add"
    assert parsed[1].path == "/abs/path/sandbox-plan.md"
    assert parsed[1].added == 2


@pytest.mark.unit
def test_parse_apply_patch_envelope_tolerates_extra_horizontal_whitespace():
    module = load_tool_module("run_agent_envelope_ws", "tools/run-agent.py")
    # Multiple spaces and tabs around directive name and colon.
    patch = "*** Begin Patch\n***   Update File:\tfoo.txt\n+x\n*** End Patch\n"
    parsed = module._parse_apply_patch_envelope(patch)
    assert len(parsed) == 1
    assert parsed[0].op == "update"
    assert parsed[0].path == "foo.txt"


# --- thinking decision edge cases ------------------------------------------

@pytest.mark.unit
def test_resolve_thinking_decision_treats_empty_env_as_off(monkeypatch):
    module = load_tool_module("run_agent_thinking_empty_env", "tools/run-agent.py")
    monkeypatch.setenv("CODECOME_THINKING", "")
    on, source = module._resolve_thinking_decision("openai/gpt-5", [])
    # Empty string is in the off-list along with "0"/"false"/"no".
    assert (on, source) == (False, "env")


@pytest.mark.unit
def test_resolve_thinking_decision_unknown_provider_defaults_on(monkeypatch):
    module = load_tool_module("run_agent_thinking_unknown", "tools/run-agent.py")
    monkeypatch.delenv("CODECOME_THINKING", raising=False)
    on, source = module._resolve_thinking_decision("unknown-provider/some-model", [])
    assert (on, source) == (True, "provider-default")


@pytest.mark.unit
def test_resolve_thinking_decision_user_args_beats_env_off(monkeypatch):
    """OPENCODE_ARGS --thinking must win even when CODECOME_THINKING=0."""
    module = load_tool_module("run_agent_thinking_userargs_wins", "tools/run-agent.py")
    monkeypatch.setenv("CODECOME_THINKING", "0")
    on, source = module._resolve_thinking_decision("anthropic/claude-opus-4-7", ["--thinking"])
    assert (on, source) == (True, "user-args")


@pytest.mark.unit
def test_resolve_thinking_decision_no_provider_prefix_defaults_on(monkeypatch):
    module = load_tool_module("run_agent_thinking_no_prefix", "tools/run-agent.py")
    monkeypatch.delenv("CODECOME_THINKING", raising=False)
    # No slash in the model name -> no provider id derivable.
    on, source = module._resolve_thinking_decision("just-a-model", [])
    assert (on, source) == (True, "provider-default")


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


# --- build_child_command thinking interactions -----------------------------

@pytest.mark.component
def test_build_child_command_user_args_thinking_is_not_duplicated(monkeypatch):
    module = load_tool_module("run_agent_child_user_thinking", "tools/run-agent.py")
    monkeypatch.setenv("OPENCODE_ARGS", "--thinking")
    monkeypatch.setenv("CODECOME_MODEL", "anthropic/claude-opus-4-7")
    monkeypatch.delenv("CODECOME_MODEL_VARIANT", raising=False)
    monkeypatch.delenv("CODECOME_THINKING", raising=False)

    class Args:
        agent = "recon"

    cmd, _, _, _, _, thinking_on, thinking_source = module.build_child_command(Args())
    # Exactly one --thinking even though anthropic default is off.
    assert cmd.count("--thinking") == 1
    assert thinking_on is True
    assert thinking_source == "user-args"


@pytest.mark.component
def test_build_child_command_anthropic_default_omits_thinking(monkeypatch):
    module = load_tool_module("run_agent_child_anthropic_no_thinking", "tools/run-agent.py")
    monkeypatch.setenv("OPENCODE_ARGS", "")
    monkeypatch.setenv("CODECOME_MODEL", "anthropic/claude-opus-4-7")
    monkeypatch.delenv("CODECOME_MODEL_VARIANT", raising=False)
    monkeypatch.delenv("CODECOME_THINKING", raising=False)

    class Args:
        agent = "recon"

    cmd, _, _, _, _, thinking_on, thinking_source = module.build_child_command(Args())
    assert "--thinking" not in cmd
    assert thinking_on is False
    assert thinking_source == "provider-default"


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
    module = load_tool_module("run_agent_prompt", "tools/run-agent.py")

    # Create a minimal prompt file.
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("# Phase prompt\n\nBase content.", encoding="utf-8")

    # Point ROOT at tmp_path so codecome.yml is found there.
    monkeypatch.setattr(module, "ROOT", tmp_path)

    # Clear env vars by default.
    monkeypatch.delenv("PROMPT_EXTRA", raising=False)
    monkeypatch.delenv("PROMPT_EXTRA_FILE", raising=False)

    return module, prompt_file, tmp_path


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
    """Frontmatter errors trigger a second Popen loop; on the second run the
    check passes and main exits 0.  The session ID must come from the event
    stream, not from subprocess.run (the DB fallback)."""
    import io, json

    module = load_tool_module("run_agent_autocorrect", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setenv("OPENCODE_ARGS", "--attach http://127.0.0.1:7777 --port 4317")

    # Build a minimal JSON event stream that conveys a clean stop
    def _make_stream(session_id: str) -> io.StringIO:
        events = [
            {"sessionID": session_id, "type": "step_finish",
             "part": {"reason": "stop", "tokens": {}}},
        ]
        return io.StringIO("".join(json.dumps(e) + "\n" for e in events))

    popen_calls: list[list] = []

    class FakePopen:
        def __init__(self, cmd, *args, **kwargs):
            popen_calls.append(list(cmd))
            self.returncode = 0
            self.pid = 9999
            self.stdin = io.StringIO()
            self.stdout = _make_stream("ses_test_abc")
        def poll(self):
            return 0
        def wait(self):
            return None

    monkeypatch.setattr(module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(module.os, "killpg", lambda *a: None)

    # subprocess.run: frontmatter fails on first check, passes on second
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

    # The while loop should have called Popen twice: initial run + frontmatter resume
    assert len(popen_calls) == 2, f"expected 2 Popen calls, got {len(popen_calls)}"
    resume_cmd = popen_calls[1]
    assert "--attach" in resume_cmd
    assert "http://127.0.0.1:7777" in resume_cmd
    assert "--port" in resume_cmd
    assert "4317" in resume_cmd
    assert "--session" in resume_cmd
    assert "ses_test_abc" in resume_cmd
    assert "--format" in resume_cmd
    assert "json" in resume_cmd
    assert "Repair only the reported YAML/frontmatter issues with minimal changes." in resume_cmd[-1]
    assert "Phase 1 completion checklist:" in resume_cmd[-1]
    assert "Ensure itemdb/notes/sandbox-plan.md documents the Phase 1b outcome." in resume_cmd[-1]


@pytest.mark.component
def test_frontmatter_failure_without_session_id_exits_nonzero(monkeypatch, tmp_path):
    """Frontmatter validation failures must not be reported as success when
    the wrapper cannot determine a resumable session ID."""
    import io, json

    module = load_tool_module("run_agent_frontmatter_no_session", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    events = [
        {"type": "step_finish", "part": {"reason": "stop", "tokens": {}}},
    ]

    popen_calls: list[list] = []

    class FakePopen:
        def __init__(self, cmd, *args, **kwargs):
            popen_calls.append(list(cmd))
            self.returncode = 0
            self.pid = 9999
            self.stdin = io.StringIO()
            self.stdout = io.StringIO("".join(json.dumps(e) + "\n" for e in events))
        def poll(self):
            return 0
        def wait(self):
            return None

    monkeypatch.setattr(module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(module.os, "killpg", lambda *a: None)

    class FakeResult:
        def __init__(self, rc, out="", err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def fake_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return FakeResult(0, out="opencode 1.15.0\n")
        if any("check-frontmatter" in str(c) for c in cmd):
            return FakeResult(1, err="bad frontmatter")
        if "db" in cmd:
            return FakeResult(0, out="")
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
    assert len(popen_calls) == 1


@pytest.mark.component
def test_iteration_limit_triggers_auto_resume(monkeypatch, tmp_path):
    """When the stream ends with a mid-turn finish reason (tool-calls) and
    graceful forgiveness does not apply, run-agent resumes once then exits."""
    import io, json

    module = load_tool_module("run_agent_iter_resume", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)
    monkeypatch.setenv("CODECOME_MAX_ITERATION_RETRIES", "1")

    def _make_stream(session_id: str, reason: str) -> io.StringIO:
        events = [
            {"sessionID": session_id, "type": "step_finish",
             "part": {"reason": reason, "tokens": {}}},
        ]
        return io.StringIO("".join(json.dumps(e) + "\n" for e in events))

    popen_calls: list[list] = []

    class FakePopen:
        def __init__(self, cmd, *args, **kwargs):
            popen_calls.append(list(cmd))
            self.returncode = 0
            self.pid = 9999
            self.stdin = io.StringIO()
            # Always return tool-calls (iteration limit hit) so we test the
            # retry path; after the retry the retry counter is exhausted and
            # we exit with code 2.
            self.stdout = _make_stream("ses_iter_xyz", "tool-calls")
        def poll(self):
            return 0
        def wait(self):
            return None

    monkeypatch.setattr(module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(module.os, "killpg", lambda *a: None)

    class FakeResult:
        def __init__(self, rc, out="", err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def fake_run(cmd, *args, **kwargs):
        if "--version" in cmd:
            return FakeResult(0, out="opencode 1.15.0\n")
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

    # After 1 retry (2 total Popen calls) the retry budget is exhausted → exit 2
    assert len(popen_calls) == 2, f"expected 2 Popen calls, got {len(popen_calls)}"
    assert rc == 2

    resume_cmd = popen_calls[1]
    assert "--session" in resume_cmd
    assert "ses_iter_xyz" in resume_cmd
    assert "Your previous response was cut off by the model/provider" in resume_cmd[-1]
    assert "Observed finish reason: tool-calls." in resume_cmd[-1]
    assert "Phase 4 completion checklist:" in resume_cmd[-1]
    assert "Ensure validation evidence exists under itemdb/evidence/CC-9999/, including README.md." in resume_cmd[-1]


# ---------------------------------------------------------------------------
# check_phase_graceful_completion – mtime-aware artifact detection
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_check_phase_graceful_completion_mtime(monkeypatch, tmp_path):
    """Graceful completion is only True when the artifact was written during
    the current run (st_mtime >= run_start_time)."""
    import os

    module = load_tool_module("run_agent_graceful_mtime", "tools/run-agent.py")
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

    # ---- Phase 5 fallback: not-feasible updates the CONFIRMED finding ----
    conf5 = confirmed / "CC-0005.md"; conf5.write_text("x")
    os.utime(conf5, (old, old))
    assert module.check_phase_graceful_completion("5", "CC-0005", start) is False
    os.utime(conf5, (fresh, fresh))
    assert module.check_phase_graceful_completion("5", "CC-0005", start) is True

    # ---- Phase 5 exploit artifacts ----
    exploits = tmp_path / "itemdb" / "evidence" / "CC-0005" / "exploits"
    exploits.mkdir(parents=True)
    xf = exploits / "exploit.py"; xf.write_text("x")
    os.utime(xf, (fresh, fresh))
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
    """Verify that the main loop captures sessionID from the first event and
    counts step_finish events accurately."""
    import io, json

    module = load_tool_module("run_agent_stream_tracking", "tools/run-agent.py")
    monkeypatch.setattr(module, "HAVE_RICH", False)

    SESSION = "ses_stream_test_001"

    events = [
        {"sessionID": SESSION, "type": "step_start",  "part": {}},
        {"sessionID": SESSION, "type": "step_finish", "part": {"reason": "tool-calls", "tokens": {}}},
        {"sessionID": SESSION, "type": "step_start",  "part": {}},
        {"sessionID": SESSION, "type": "step_finish", "part": {"reason": "tool-calls", "tokens": {}}},
        {"sessionID": SESSION, "type": "step_start",  "part": {}},
        {"sessionID": SESSION, "type": "step_finish", "part": {"reason": "stop", "tokens": {}}},
    ]
    stream = io.StringIO("".join(json.dumps(e) + "\n" for e in events))

    popen_calls: list[list] = []

    class FakePopen:
        def __init__(self, cmd, *args, **kwargs):
            popen_calls.append(list(cmd))
            self.returncode = 0
            self.pid = 1234
            self.stdin = io.StringIO()
            self.stdout = stream
        def poll(self): return 0
        def wait(self): return None

    monkeypatch.setattr(module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(module.os, "killpg", lambda *a: None)

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

    # The session terminated with 'stop', no frontmatter errors → single Popen call
    assert len(popen_calls) == 1
