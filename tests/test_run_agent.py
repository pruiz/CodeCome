from __future__ import annotations

import pytest

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

    monkeypatch.setattr(module, "render_reasoning", _fake_reasoning)
    monkeypatch.setattr(module, "render_error", _fake_error)

    module.render_event(None, "2", "x", {"type": "reasoning", "part": {"text": "x"}})
    module.render_event(None, "2", "x", {"type": "error", "error": "x"})

    assert calls == ["reasoning", "error"]


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
