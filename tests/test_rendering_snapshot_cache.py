from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from rendering.cache import SnapshotCache


class TestSnapshotCache:
    def test_set_and_get(self, tmp_path):
        cache = SnapshotCache()
        path = tmp_path / "test.txt"
        path.write_text("hello", encoding="utf-8")
        cache.set(str(path), "hello")
        assert cache.get(str(path)) == "hello"

    def test_get_returns_none_for_unknown(self):
        cache = SnapshotCache()
        assert cache.get("/no/such/path") is None

    def test_disabled_cache_returns_none(self):
        cache = SnapshotCache(enabled=False)
        cache.set("/x", "y")
        assert cache.get("/x") is None

    def test_invalidate_stale_removes_deleted(self, tmp_path):
        cache = SnapshotCache()
        path = tmp_path / "stale.txt"
        path.write_text("old", encoding="utf-8")
        cache.set(str(path), "old")
        path.unlink()
        cache.invalidate_stale()
        assert cache.get(str(path)) is None

    def test_invalidate_stale_removes_modified(self, tmp_path):
        cache = SnapshotCache()
        path = tmp_path / "mod.txt"
        path.write_text("v1", encoding="utf-8")
        cache.set(str(path), "v1")
        path.write_text("v2", encoding="utf-8")
        cache.invalidate_stale()
        assert cache.get(str(path)) is None

    def test_reread(self, tmp_path):
        cache = SnapshotCache()
        path = tmp_path / "reread.txt"
        path.write_text("before", encoding="utf-8")
        cache.set(str(path), "before")
        path.write_text("after", encoding="utf-8")
        cache.reread(str(path))
        assert cache.get(str(path)) == "after"

    def test_reread_missing_file(self, tmp_path):
        cache = SnapshotCache()
        path = tmp_path / "missing.txt"
        path.write_text("x", encoding="utf-8")
        cache.set(str(path), "x")
        path.unlink()
        cache.reread(str(path))
        assert cache.get(str(path)) is None

    def test_lru_eviction(self, tmp_path):
        cache = SnapshotCache(max_entries=2)
        files = []
        for i in range(4):
            p = tmp_path / f"f{i}.txt"
            p.write_text(str(i), encoding="utf-8")
            files.append(p)
            cache.set(str(p), str(i))
        assert cache.get(str(files[0])) is None
        assert cache.get(str(files[1])) is None
        assert cache.get(str(files[2])) == "2"
        assert cache.get(str(files[3])) == "3"

    def test_disabled_invalidate_is_noop(self):
        cache = SnapshotCache(enabled=False)
        cache.invalidate_stale()
        assert len(cache._entries) == 0

    def test_disabled_reread_is_noop(self):
        cache = SnapshotCache(enabled=False)
        cache.reread("/x")
        assert len(cache._entries) == 0
