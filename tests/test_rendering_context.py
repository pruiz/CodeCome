from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from rendering.context import RenderContext
from rendering.sink import PlainSink
from rendering.settings import RenderSettings
from rendering.cache import SnapshotCache


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
