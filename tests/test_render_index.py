from __future__ import annotations

from conftest import load_tool_module


def test_render_index_includes_status_counts_and_links():
    module = load_tool_module("render_index", "tools/render-index.py")
    rows = [
        {
            "id": "CC-0001",
            "status": "CONFIRMED",
            "severity": "HIGH",
            "confidence": "CONFIRMED",
            "title": "Issue",
            "target_area": "api",
            "finding_path": "itemdb/findings/CONFIRMED/CC-0001-issue.md",
            "evidence": "itemdb/evidence/CC-0001",
        }
    ]

    out = module.render_index(rows)
    assert "# CodeCome Finding Index" in out
    assert "| CONFIRMED | 1 |" in out
    assert "[finding](itemdb/findings/CONFIRMED/CC-0001-issue.md)" in out
    assert "[evidence](itemdb/evidence/CC-0001)" in out
