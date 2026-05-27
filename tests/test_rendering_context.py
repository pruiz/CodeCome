from __future__ import annotations

import sys
from pathlib import Path

import pytest
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from rendering.context import RenderContext
from rendering.sink import PlainSink
from rendering.settings import RenderSettings
from rendering.cache import SnapshotCache
from rendering import dispatch as rendering_dispatch


class TestRenderContext:
    def test_construction(self):
        ctx = RenderContext(
            root=Path("/fake"),
            sink=PlainSink(),
            settings=RenderSettings(),
            cache=SnapshotCache(),
        )
        assert ctx.root == Path("/fake")
        assert isinstance(ctx.sink, PlainSink)
        assert isinstance(ctx.settings, RenderSettings)
        assert isinstance(ctx.cache, SnapshotCache)

    def test_cache_is_shared(self):
        cache = SnapshotCache()
        ctx = RenderContext(
            root=Path("/x"),
            sink=PlainSink(),
            settings=RenderSettings(),
            cache=cache,
        )
        assert ctx.cache is cache

    def test_cli_overrides_reach_render_settings(self):
        """dataclasses.replace() applies CLI tunable overrides correctly."""
        import dataclasses
        settings = RenderSettings.from_env()
        assert settings.read_display_lines == 10
        assert settings.write_content_lines == 25
        assert settings.write_diff_limit == 50
        assert settings.edit_diff_lines == 25

        settings = dataclasses.replace(settings,
            read_display_lines=42,
            write_content_lines=7,
            write_diff_limit=99,
            edit_diff_lines=3,
        )
        assert settings.read_display_lines == 42
        assert settings.write_content_lines == 7
        assert settings.write_diff_limit == 99
        assert settings.edit_diff_lines == 3

    def test_reconfigure_rendering_rebinds_sink_without_clearing_cache(self):
        from rich.console import Console

        rendering_dispatch.reset_rendering_context_cache()
        first_console = Console(record=True)
        ctx = rendering_dispatch.configure_rendering(first_console, render_reasoning=True)
        cache = ctx.cache
        registry = ctx.registry

        proxy_console = MagicMock()
        updated = rendering_dispatch.reconfigure_rendering(
            proxy_console,
            render_reasoning=False,
        )

        assert updated is ctx
        assert updated.cache is cache
        assert updated.registry is registry
        assert updated.settings.render_reasoning is False

        event = {"type": "session.status", "properties": {"status": {"type": "busy"}}}
        rendering_dispatch.render_event(proxy_console, "Chat", "Interactive Chat", event)

        proxy_console.print.assert_called_once()
        assert "session status: busy" not in first_console.export_text()
        rendering_dispatch.reset_rendering_context_cache()
