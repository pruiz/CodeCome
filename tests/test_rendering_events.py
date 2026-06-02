from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from rendering.context import RenderContext
from rendering.registry import RendererRegistry
from rendering.sink import PlainSink, RichConsoleSink
from rendering.settings import RenderSettings
from rendering.cache import SnapshotCache
from rendering.tools.base import FallbackToolRenderer
from rendering.events import (
    StepStartRenderer,
    TextEventRenderer,
    ReasoningEventRenderer,
    ToolUseEventRenderer,
    StepFinishRenderer,
    ErrorEventRenderer,
    SessionStatusRenderer,
    ServerConnectedRenderer,
    ServerHeartbeatRenderer,
    SessionDiffRenderer,
    MessageUpdatedRenderer,
    SubagentStatusRenderer,
    UnknownEventRenderer,
    _reset_subagent_state,
)


def _ctx(sink_mode="plain", **settings_overrides):
    if sink_mode == "rich":
        from rich.console import Console
        sink = RichConsoleSink(Console(record=True))
    else:
        sink = PlainSink()
    settings = RenderSettings(**settings_overrides)
    return RenderContext(
        root=Path("/fake"),
        sink=sink,
        settings=settings,
        cache=SnapshotCache(),
    )


def _ctx_with_registry(sink_mode="plain", **settings_overrides):
    ctx = _ctx(sink_mode, **settings_overrides)
    ctx.registry = RendererRegistry(ctx)
    ctx.registry.register_tool(FallbackToolRenderer(ctx))
    return ctx


# ---------------------------------------------------------------------------
# StepStartRenderer
# ---------------------------------------------------------------------------

class TestStepStartRenderer:
    def test_renders_step_start_plain(self, capsys):
        ctx = _ctx("plain")
        ctx.phase = "1"
        ctx.label = "recon"
        r = StepStartRenderer(ctx)
        assert r.render({"part": {"type": "tool_use"}}) is True
        out = capsys.readouterr().out
        assert "[1] recon: tool_use" in out

    def test_renders_step_start_rich(self):
        ctx = _ctx("rich")
        ctx.phase = "2"
        ctx.label = "audit"
        r = StepStartRenderer(ctx)
        assert r.render({"part": {"type": "text"}}) is True

    def test_defaults_to_step_start_type(self, capsys):
        r = StepStartRenderer(_ctx("plain"))
        assert r.render({"part": {}}) is True
        out = capsys.readouterr().out
        assert "step-start" in out


# ---------------------------------------------------------------------------
# TextEventRenderer
# ---------------------------------------------------------------------------

class TestTextEventRenderer:
    def test_renders_text_plain(self, capsys):
        r = TextEventRenderer(_ctx("plain"))
        assert r.render({"part": {"text": "Hello world"}}) is True
        out = capsys.readouterr().out
        assert "Assistant" in out
        assert "Hello world" in out

    def test_renders_text_rich(self):
        r = TextEventRenderer(_ctx("rich"))
        assert r.render({"part": {"text": "Hello world"}}) is True

    def test_skips_empty_text(self, capsys):
        r = TextEventRenderer(_ctx("plain"))
        assert r.render({"part": {"text": ""}}) is True
        assert r.render({"part": {"text": "   \n\t  "}}) is True
        assert capsys.readouterr().out == ""

    def test_skips_missing_text(self, capsys):
        r = TextEventRenderer(_ctx("plain"))
        assert r.render({"part": {}}) is True
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# ReasoningEventRenderer
# ---------------------------------------------------------------------------

class TestReasoningEventRenderer:
    def test_renders_reasoning_plain(self, capsys):
        r = ReasoningEventRenderer(_ctx("plain", render_reasoning=True))
        assert r.render({"part": {"text": "I think therefore I am"}}) is True
        out = capsys.readouterr().out
        assert "Thinking" in out
        assert "I think therefore I am" in out

    def test_renders_reasoning_rich(self):
        r = ReasoningEventRenderer(_ctx("rich", render_reasoning=True))
        assert r.render({"part": {"text": "Deep thought"}}) is True

    def test_disabled_by_settings(self):
        r = ReasoningEventRenderer(_ctx("plain", render_reasoning=False))
        assert r.render({"part": {"text": "Hidden"}}) is True

    def test_skips_empty_text(self, capsys):
        r = ReasoningEventRenderer(_ctx("plain", render_reasoning=True))
        assert r.render({"part": {"text": ""}}) is True
        assert capsys.readouterr().out == ""

    def test_renders_hidden_reasoning_after_first_event(self, capsys, monkeypatch):
        monkeypatch.setattr("rendering.events.reasoning.time.monotonic", lambda: 100.0)
        r = ReasoningEventRenderer(_ctx("plain", render_reasoning=True, hidden_reasoning_throttle_s=2))
        event = {"part": {"text": "", "metadata": {"openai": {"reasoningEncryptedContent": "enc"}}}}

        assert r.render(event) is True

        out = capsys.readouterr().out
        assert "Assistant reasoning [0.0s so far]" in out

    def test_throttles_hidden_reasoning_updates(self, capsys, monkeypatch):
        times = iter([100.0, 101.0])
        monkeypatch.setattr("rendering.events.reasoning.time.monotonic", lambda: next(times))
        r = ReasoningEventRenderer(_ctx("plain", render_reasoning=True, hidden_reasoning_throttle_s=2))
        event = {"part": {"text": "", "metadata": {"openai": {"reasoningEncryptedContent": "enc"}}}}

        assert r.render(event) is True
        assert r.render(event) is True

        out = capsys.readouterr().out
        assert out.count("Assistant reasoning") == 1

    def test_hidden_reasoning_suppresses_server_heartbeat(self, capsys, monkeypatch):
        monkeypatch.setattr("rendering.events.reasoning.time.monotonic", lambda: 100.0)
        ctx = _ctx("plain", render_reasoning=True, hidden_reasoning_throttle_s=2)
        reasoning = ReasoningEventRenderer(ctx)
        heartbeat = ServerHeartbeatRenderer(ctx)
        event = {"part": {"text": "", "metadata": {"openai": {"reasoningEncryptedContent": "enc"}}}}

        assert reasoning.render(event) is True
        assert heartbeat.render({}) is True

        out = capsys.readouterr().out
        assert "Assistant reasoning" in out
        assert "server heartbeat" not in out

    def test_visible_text_clears_hidden_reasoning_state(self, capsys, monkeypatch):
        monkeypatch.setattr("rendering.events.reasoning.time.monotonic", lambda: 100.0)
        ctx = _ctx("plain", render_reasoning=True, hidden_reasoning_throttle_s=2)
        reasoning = ReasoningEventRenderer(ctx)
        text_renderer = TextEventRenderer(ctx)

        assert reasoning.render({"part": {"text": "", "metadata": {"openai": {"reasoningEncryptedContent": "enc"}}}}) is True
        assert ctx.hidden_reasoning_active is True

        assert text_renderer.render({"part": {"text": "done"}}) is True
        assert ctx.hidden_reasoning_active is False

    def test_truncates_long_text(self, capsys):
        r = ReasoningEventRenderer(_ctx("plain", render_reasoning=True, reasoning_max_chars=10))
        assert r.render({"part": {"text": "123456789012345"}}) is True
        out = capsys.readouterr().out
        assert "1234567890" in out
        assert "truncated" in out


# ---------------------------------------------------------------------------
# ToolUseEventRenderer
# ---------------------------------------------------------------------------

class TestToolUseEventRenderer:
    def test_delegates_to_fallback_tool_renderer(self, capsys):
        r = ToolUseEventRenderer(_ctx_with_registry("plain"))
        assert r.render({"part": {"tool": "unknown_tool", "state": {"status": "completed"}}}) is True
        out = capsys.readouterr().out
        assert "unknown_tool" in out

    def test_handles_missing_state(self):
        r = ToolUseEventRenderer(_ctx_with_registry("plain"))
        # FallbackToolRenderer should handle empty state
        assert r.render({"part": {"tool": "bash"}}) is True


# ---------------------------------------------------------------------------
# StepFinishRenderer
# ---------------------------------------------------------------------------

class TestStepFinishRenderer:
    def test_renders_finish_plain(self, capsys):
        r = StepFinishRenderer(_ctx("plain"))
        assert r.render({"part": {"reason": "stop"}}) is True
        out = capsys.readouterr().out
        assert "step finished: stop" in out

    def test_renders_finish_with_tokens(self, capsys):
        r = StepFinishRenderer(_ctx("plain"))
        assert r.render({"part": {"reason": "end_turn", "tokens": {"input": 100, "output": 50}}}) is True
        out = capsys.readouterr().out
        assert "input=100" in out
        assert "output=50" in out

    def test_failure_reason_styled(self, capsys):
        r = StepFinishRenderer(_ctx("plain"))
        assert r.render({"part": {"reason": "error"}}) is True
        out = capsys.readouterr().out
        assert "error" in out

    def test_renders_finish_rich(self):
        r = StepFinishRenderer(_ctx("rich"))
        assert r.render({"part": {"reason": "stop"}}) is True


# ---------------------------------------------------------------------------
# ErrorEventRenderer
# ---------------------------------------------------------------------------

class TestErrorEventRenderer:
    def test_renders_dict_error_with_name_and_message(self, capsys):
        r = ErrorEventRenderer(_ctx("plain"))
        assert r.render({"error": {"name": "RateLimit", "data": {"message": "too many requests"}}}) is True
        out = capsys.readouterr().out
        assert "RateLimit" in out
        assert "too many requests" in out

    def test_renders_dict_error_with_top_level_message(self, capsys):
        r = ErrorEventRenderer(_ctx("plain"))
        assert r.render({"error": {"message": "something broke"}}) is True
        out = capsys.readouterr().out
        assert "something broke" in out

    def test_renders_string_error(self, capsys):
        r = ErrorEventRenderer(_ctx("plain"))
        assert r.render({"error": "plain string error"}) is True
        out = capsys.readouterr().out
        assert "plain string error" in out

    def test_renders_missing_error(self, capsys):
        r = ErrorEventRenderer(_ctx("plain"))
        assert r.render({}) is True
        out = capsys.readouterr().out
        assert "(no error message)" in out

    def test_renders_error_rich(self):
        r = ErrorEventRenderer(_ctx("rich"))
        assert r.render({"error": "test"}) is True


# ---------------------------------------------------------------------------
# SessionStatusRenderer
# ---------------------------------------------------------------------------

class TestSessionStatusRenderer:
    def test_renders_retry_status(self, capsys):
        r = SessionStatusRenderer(_ctx("plain"))
        assert r.render({"properties": {"status": {"type": "retry", "attempt": 3, "message": "Timeout"}}}) is True
        out = capsys.readouterr().out
        assert "retry attempt 3" in out
        assert "Timeout" in out

    def test_renders_busy_status(self, capsys):
        r = SessionStatusRenderer(_ctx("plain"))
        assert r.render({"properties": {"status": {"type": "busy"}}}) is True
        out = capsys.readouterr().out
        assert "busy" in out

    def test_renders_idle_status(self, capsys):
        r = SessionStatusRenderer(_ctx("plain"))
        assert r.render({"properties": {"status": {"type": "idle"}}}) is True
        out = capsys.readouterr().out
        assert "idle" in out

    def test_renders_legacy_session_idle_event(self, capsys):
        r = SessionStatusRenderer(_ctx("plain"))
        assert r.render({"type": "session.idle"}) is True
        out = capsys.readouterr().out
        assert "session status: idle" in out

    def test_renders_status_rich(self):
        r = SessionStatusRenderer(_ctx("rich"))
        assert r.render({"properties": {"status": {"type": "busy"}}}) is True

    def test_throttles_repeated_busy_status(self, capsys, monkeypatch):
        times = iter([100.0, 101.0])
        monkeypatch.setattr("rendering.events.session_status.time.monotonic", lambda: next(times))
        r = SessionStatusRenderer(_ctx("plain", session_busy_throttle_s=5))

        assert r.render({"properties": {"status": {"type": "busy"}}}) is True
        assert r.render({"properties": {"status": {"type": "busy"}}}) is True

        out = capsys.readouterr().out
        assert out.count("session status: busy") == 1

    def test_renders_busy_after_throttle_window(self, capsys, monkeypatch):
        times = iter([100.0, 106.0])
        monkeypatch.setattr("rendering.events.session_status.time.monotonic", lambda: next(times))
        r = SessionStatusRenderer(_ctx("plain", session_busy_throttle_s=5))

        assert r.render({"properties": {"status": {"type": "busy"}}}) is True
        assert r.render({"properties": {"status": {"type": "busy"}}}) is True

        out = capsys.readouterr().out
        assert out.count("session status: busy") == 2

    def test_busy_throttle_zero_disables_suppression(self, capsys, monkeypatch):
        times = iter([100.0, 101.0])
        monkeypatch.setattr("rendering.events.session_status.time.monotonic", lambda: next(times))
        r = SessionStatusRenderer(_ctx("plain", session_busy_throttle_s=0))

        assert r.render({"properties": {"status": {"type": "busy"}}}) is True
        assert r.render({"properties": {"status": {"type": "busy"}}}) is True

        out = capsys.readouterr().out
        assert out.count("session status: busy") == 2

    def test_idle_resets_busy_throttle(self, capsys, monkeypatch):
        times = iter([100.0, 101.0])
        monkeypatch.setattr("rendering.events.session_status.time.monotonic", lambda: next(times))
        r = SessionStatusRenderer(_ctx("plain", session_busy_throttle_s=5))

        assert r.render({"properties": {"status": {"type": "busy"}}}) is True
        assert r.render({"properties": {"status": {"type": "idle"}}}) is True
        assert r.render({"properties": {"status": {"type": "busy"}}}) is True

        out = capsys.readouterr().out
        assert out.count("session status: busy") == 2
        assert "session status: idle" in out


# ---------------------------------------------------------------------------
# ServerConnectedRenderer
# ---------------------------------------------------------------------------

class TestServerConnectedRenderer:
    def test_renders_connected_plain(self, capsys):
        r = ServerConnectedRenderer(_ctx("plain"))
        assert r.render({}) is True
        out = capsys.readouterr().out
        assert "connected" in out

    def test_renders_connected_rich(self):
        r = ServerConnectedRenderer(_ctx("rich"))
        assert r.render({}) is True


# ---------------------------------------------------------------------------
# ServerHeartbeatRenderer
# ---------------------------------------------------------------------------

class TestServerHeartbeatRenderer:
    def test_renders_heartbeat_plain(self, capsys):
        r = ServerHeartbeatRenderer(_ctx("plain"))
        assert r.render({}) is True
        out = capsys.readouterr().out
        assert "heartbeat" in out

    def test_renders_heartbeat_rich(self):
        r = ServerHeartbeatRenderer(_ctx("rich"))
        assert r.render({}) is True


# ---------------------------------------------------------------------------
# SessionDiffRenderer
# ---------------------------------------------------------------------------

class TestSessionDiffRenderer:
    def test_renders_diff_count_plain(self, capsys):
        r = SessionDiffRenderer(_ctx("plain"))
        assert r.render({"properties": {"diff": ["a.py", "b.py"]}}) is True
        out = capsys.readouterr().out
        assert "2 files" in out

    def test_renders_single_file_diff(self, capsys):
        r = SessionDiffRenderer(_ctx("plain"))
        assert r.render({"properties": {"diff": ["a.py"]}}) is True
        out = capsys.readouterr().out
        assert "1 file" in out
        assert "2 files" not in out

    def test_returns_false_for_empty_diff(self):
        r = SessionDiffRenderer(_ctx("plain"))
        assert r.render({"properties": {"diff": []}}) is False

    def test_returns_false_for_missing_diff(self):
        r = SessionDiffRenderer(_ctx("plain"))
        assert r.render({"properties": {}}) is False

    def test_renders_diff_rich(self):
        r = SessionDiffRenderer(_ctx("rich"))
        assert r.render({"properties": {"diff": ["a.py"]}}) is True


# ---------------------------------------------------------------------------
# MessageUpdatedRenderer
# ---------------------------------------------------------------------------

class TestMessageUpdatedRenderer:
    def test_renders_user_message(self, capsys):
        r = MessageUpdatedRenderer(_ctx("plain"))
        assert r.render({"info": {"role": "user", "summary": "test"}}) is True
        out = capsys.readouterr().out
        assert "User" in out

    def test_renders_assistant_with_tokens(self, capsys):
        r = MessageUpdatedRenderer(_ctx("plain"))
        assert r.render({"info": {"role": "assistant", "tokens": {"input": 10, "output": 20}}}) is True
        out = capsys.readouterr().out
        assert "Assistant" in out
        assert "10" in out
        assert "20" in out

    def test_renders_assistant_with_model(self, capsys):
        r = MessageUpdatedRenderer(_ctx("plain"))
        assert r.render({"info": {"role": "assistant", "modelID": "gpt-5", "providerID": "openai", "tokens": {"input": 1}}}) is True
        out = capsys.readouterr().out
        assert "openai/gpt-5" in out

    def test_model_fallback_to_nested_dict(self, capsys):
        r = MessageUpdatedRenderer(_ctx("plain"))
        assert r.render({"info": {"role": "assistant", "model": {"modelID": "claude-4", "providerID": "anthropic"}, "tokens": {"input": 1}}}) is True
        out = capsys.readouterr().out
        assert "anthropic/claude-4" in out

    def test_renders_custom_agent_role(self, capsys):
        r = MessageUpdatedRenderer(_ctx("plain"))
        assert r.render({"info": {"role": "", "agent": "auditor", "tokens": {"input": 1}}}) is True
        out = capsys.readouterr().out
        assert "auditor" in out

    def test_returns_true_and_renders_role_when_no_tokens_or_summary(self, capsys):
        r = MessageUpdatedRenderer(_ctx("plain"))
        assert r.render({"info": {"role": "assistant"}}) is True
        out = capsys.readouterr().out
        assert "Assistant" in out

    def test_renders_with_cost(self, capsys):
        r = MessageUpdatedRenderer(_ctx("plain"))
        assert r.render({"info": {"role": "assistant", "tokens": {"input": 10}, "cost": 0.005}}) is True
        out = capsys.readouterr().out
        assert "$0.0050" in out

    def test_renders_message_updated_rich(self):
        r = MessageUpdatedRenderer(_ctx("rich"))
        assert r.render({"info": {"role": "user", "summary": "test"}}) is True

    def test_reads_from_properties_fallback(self, capsys):
        r = MessageUpdatedRenderer(_ctx("plain"))
        assert r.render({"properties": {"info": {"role": "user", "summary": "test"}}}) is True
        out = capsys.readouterr().out
        assert "User" in out

    def test_throttles_token_then_tokenless_assistant_header(self, capsys, monkeypatch):
        times = iter([100.0, 101.0])
        monkeypatch.setattr("rendering.events.message.time.monotonic", lambda: next(times))
        r = MessageUpdatedRenderer(_ctx("plain", assistant_header_throttle_s=3))

        assert r.render({"info": {"role": "assistant", "tokens": {"input": 10, "output": 2}}}) is True
        assert r.render({"info": {"role": "assistant", "modelID": "gpt-5"}}) is True

        out = capsys.readouterr().out
        assert out.count("Assistant") == 1
        assert "10" in out

    def test_throttles_tokenless_then_token_assistant_header(self, capsys, monkeypatch):
        times = iter([100.0, 101.0])
        monkeypatch.setattr("rendering.events.message.time.monotonic", lambda: next(times))
        r = MessageUpdatedRenderer(_ctx("plain", assistant_header_throttle_s=3))

        assert r.render({"info": {"role": "assistant", "modelID": "gpt-5"}}) is True
        assert r.render({"info": {"role": "assistant", "tokens": {"input": 10, "output": 2}}}) is True

        out = capsys.readouterr().out
        assert out.count("Assistant") == 1
        assert "gpt-5" in out
        assert "10" not in out

    def test_renders_assistant_after_throttle_window(self, capsys, monkeypatch):
        times = iter([100.0, 104.0])
        monkeypatch.setattr("rendering.events.message.time.monotonic", lambda: next(times))
        r = MessageUpdatedRenderer(_ctx("plain", assistant_header_throttle_s=3))

        assert r.render({"info": {"role": "assistant", "modelID": "gpt-5"}}) is True
        assert r.render({"info": {"role": "assistant", "tokens": {"input": 10, "output": 2}}}) is True

        out = capsys.readouterr().out
        assert out.count("Assistant") == 2

    def test_assistant_header_throttle_zero_disables_suppression(self, capsys, monkeypatch):
        times = iter([100.0, 101.0])
        monkeypatch.setattr("rendering.events.message.time.monotonic", lambda: next(times))
        r = MessageUpdatedRenderer(_ctx("plain", assistant_header_throttle_s=0))

        assert r.render({"info": {"role": "assistant", "modelID": "gpt-5"}}) is True
        assert r.render({"info": {"role": "assistant", "tokens": {"input": 10, "output": 2}}}) is True

        out = capsys.readouterr().out
        assert out.count("Assistant") == 2

    def test_user_message_resets_assistant_header_throttle(self, capsys, monkeypatch):
        times = iter([100.0, 101.0])
        monkeypatch.setattr("rendering.events.message.time.monotonic", lambda: next(times))
        r = MessageUpdatedRenderer(_ctx("plain", assistant_header_throttle_s=3))

        assert r.render({"info": {"role": "assistant", "modelID": "gpt-5"}}) is True
        assert r.render({"info": {"role": "user", "summary": "test"}}) is True
        assert r.render({"info": {"role": "assistant", "tokens": {"input": 10, "output": 2}}}) is True

        out = capsys.readouterr().out
        assert out.count("Assistant") == 2
        assert "User" in out


# ---------------------------------------------------------------------------
# SubagentStatusRenderer
# ---------------------------------------------------------------------------

class TestSubagentStatusRenderer:
    def setup_method(self):
        _reset_subagent_state()

    def teardown_method(self):
        _reset_subagent_state()

    def test_renders_created_plain(self, capsys):
        r = SubagentStatusRenderer(_ctx("plain", render_subagent_updates=True))
        assert r.render({"properties": {"statusType": "created", "sessionID": "s1", "title": "Job A"}}) is True
        out = capsys.readouterr().out
        assert "started" in out
        assert "Job A" in out

    def test_renders_finished_plain(self, capsys):
        r = SubagentStatusRenderer(_ctx("plain", render_subagent_updates=True))
        assert r.render({"properties": {"statusType": "finished", "sessionID": "s1", "title": "Job A"}}) is True
        out = capsys.readouterr().out
        assert "finished" in out

    def test_renders_heartbeat_plain(self, capsys):
        r = SubagentStatusRenderer(_ctx("plain", render_subagent_updates=True))
        assert r.render({"properties": {"statusType": "heartbeat", "sessionID": "s1", "title": "Job A", "elapsedMs": 45000}}) is True
        out = capsys.readouterr().out
        assert "45s" in out

    def test_renders_updated_with_summary(self, capsys):
        r = SubagentStatusRenderer(_ctx("plain", render_subagent_updates=True))
        assert r.render({"properties": {"statusType": "updated", "sessionID": "s1", "title": "Job A", "summary": {"additions": 3, "files": 2}}}) is True
        out = capsys.readouterr().out
        assert "+3" in out
        assert "2 file(s)" in out

    def test_dedupes_identical_updates(self, capsys):
        r = SubagentStatusRenderer(_ctx("plain", render_subagent_updates=True, subagent_update_throttle_s=5))
        event = {"properties": {"statusType": "updated", "sessionID": "s1", "title": "Job A", "summary": {"additions": 1}}}
        assert r.render(event) is True
        assert r.render(event) is False  # Deduped

    def test_renders_when_summary_changes(self, capsys):
        r = SubagentStatusRenderer(_ctx("plain", render_subagent_updates=True, subagent_update_throttle_s=5))
        assert r.render({"properties": {"statusType": "updated", "sessionID": "s1", "title": "Job A", "summary": {"additions": 1}}}) is True
        assert r.render({"properties": {"statusType": "updated", "sessionID": "s1", "title": "Job A", "summary": {"additions": 2}}}) is True

    def test_disabled_by_settings(self):
        r = SubagentStatusRenderer(_ctx("plain", render_subagent_updates=False))
        assert r.render({"properties": {"statusType": "created", "sessionID": "s1", "title": "Job"}}) is False

    def test_renders_subagent_rich(self):
        r = SubagentStatusRenderer(_ctx("rich", render_subagent_updates=True))
        assert r.render({"properties": {"statusType": "created", "sessionID": "s1", "title": "Job"}}) is True


# ---------------------------------------------------------------------------
# UnknownEventRenderer
# ---------------------------------------------------------------------------

class TestUnknownEventRenderer:
    def test_renders_unknown_event_type(self, capsys):
        r = UnknownEventRenderer(_ctx("plain"))
        assert r.render({"type": "weird.event"}) is True
        out = capsys.readouterr().out
        assert "unknown event type: weird.event" in out

    def test_renders_unknown_part_type(self, capsys):
        r = UnknownEventRenderer(_ctx("plain"))
        assert r.render({"type": "message.part.updated", "part": {"type": "custom"}}) is True
        out = capsys.readouterr().out
        assert "unknown part type: custom" in out

    def test_includes_debug_json_when_enabled(self, capsys):
        r = UnknownEventRenderer(_ctx("plain", debug_unknown_events=True))
        assert r.render({"type": "x", "extra": 1}) is True
        out = capsys.readouterr().out
        assert '"extra": 1' in out

    def test_omits_debug_json_when_disabled(self, capsys):
        r = UnknownEventRenderer(_ctx("plain", debug_unknown_events=False))
        assert r.render({"type": "x", "extra": 1}) is True
        out = capsys.readouterr().out
        assert '"extra"' not in out

    def test_renders_unknown_rich(self):
        r = UnknownEventRenderer(_ctx("rich"))
        assert r.render({"type": "x"}) is True
