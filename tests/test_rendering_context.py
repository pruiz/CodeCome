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
