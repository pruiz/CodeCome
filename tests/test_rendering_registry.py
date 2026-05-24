from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from rendering.context import RenderContext
from rendering.events import EventRenderer
from rendering.registry import RendererRegistry
from rendering.tools.base import ToolRenderer
from rendering.sink import PlainSink


@pytest.fixture
def registry():
    ctx = RenderContext(
        root=Path("/fake"),
        sink=PlainSink(),
        settings=MagicMock(),
        cache=MagicMock(),
    )
    return RendererRegistry(ctx)


class TestRegistryEventDispatch:
    def test_dispatches_to_matching_event_renderer(self, registry):
        events_seen = []

        class MyRenderer(EventRenderer):
            event_types = ("foo",)
            def render(self, event):
                events_seen.append(event["type"])
                return True

        registry.register_event(MyRenderer(registry.context))
        registry.dispatch_event({"type": "foo"})
        assert events_seen == ["foo"]

    def test_dispatches_to_first_matching_event_renderer(self, registry):
        order = []

        class First(EventRenderer):
            event_types = ("bar",)
            def render(self, event):
                order.append("first")
                return True

        class Second(EventRenderer):
            event_types = ("bar",)
            def render(self, event):
                order.append("second")
                return True

        registry.register_event(First(registry.context))
        registry.register_event(Second(registry.context))
        registry.dispatch_event({"type": "bar"})
        assert order == ["first"]

    def test_fallback_handles_unknown_event(self, registry, capsys):
        registry.dispatch_event({"type": "unknown.weird"})
        out = capsys.readouterr().out
        assert "unknown event type" in out.lower()

    def test_fallback_on_non_handling_renderer(self, registry, capsys):
        class NonHandler(EventRenderer):
            event_types = ("baz",)
            def render(self, event):
                return False

        registry.register_event(NonHandler(registry.context))
        registry.dispatch_event({"type": "baz"})
        # Should fall through to UnknownEventRenderer
        out = capsys.readouterr().out
        assert "unknown event type" in out.lower()


class TestRegistryToolDispatch:
    def test_dispatches_to_matching_tool_renderer(self, registry):
        seen = []

        class MyTool(ToolRenderer):
            tool_names = ("read",)
            def render(self, tool_name, state):
                seen.append(tool_name)
                return True

        registry.register_tool(MyTool(registry.context))
        registry.dispatch_tool("read", {"status": "completed"})
        assert seen == ["read"]

    def test_tool_name_normalisation(self, registry):
        seen = []

        class MyTool(ToolRenderer):
            tool_names = ("read",)
            def render(self, tool_name, state):
                seen.append(tool_name)
                return True

        registry.register_tool(MyTool(registry.context))
        registry.dispatch_tool("  Read  ", {"status": "completed"})
        assert seen == ["  Read  "]

    def test_fallback_tool_renderer(self, registry, capsys):
        registry.dispatch_tool("unknown_tool", {"status": "completed", "input": {"x": 1}})
        out = capsys.readouterr().out
        assert "unknown_tool" in out

    def test_fallback_on_non_handling_tool_renderer(self, registry, capsys):
        class NonHandler(ToolRenderer):
            tool_names = ("grep",)
            def render(self, tool_name, state):
                return False

        registry.register_tool(NonHandler(registry.context))
        registry.dispatch_tool("grep", {"status": "completed"})
        # Should fall through to FallbackToolRenderer
        out = capsys.readouterr().out
        assert "grep" in out.lower()
