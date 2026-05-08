from __future__ import annotations

from conftest import load_tool_module


def test_collect_finding_ids_deduplicates_and_sorts(tmp_path):
    module = load_tool_module("codecome", "tools/codecome.py")
    files = [
        tmp_path / "CC-0010-a.md",
        tmp_path / "CC-0002-b.md",
        tmp_path / "CC-0010-c.md",
    ]
    for f in files:
        f.write_text("x", encoding="utf-8")

    ids = module.collect_finding_ids(files)
    assert ids == [2, 10]
