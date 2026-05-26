from __future__ import annotations

import pytest

from findings import render_index as render_index_module


@pytest.mark.xfail(reason="P16: render_index uses dynamic __import__('render_index') to get wrapper globals — must be removed first")
def test_render_index_includes_status_counts_and_links():
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

    out = render_index_module.render_index(rows)
    assert "# CodeCome Finding Index" in out
    assert "| CONFIRMED | 1 |" in out
    assert "[finding](itemdb/findings/CONFIRMED/CC-0001-issue.md)" in out
    assert "[evidence](itemdb/evidence/CC-0001)" in out
