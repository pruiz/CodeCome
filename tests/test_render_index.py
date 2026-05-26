from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import pytest

from findings import render_index as render_index_module


def test_render_index_includes_per_finding_rows_with_all_columns():
    rows = [
        {
            "id": "CC-0001",
            "status": "PENDING",
            "severity": "HIGH",
            "confidence": "MEDIUM",
            "exploitation_status": "",
            "validation_status": "NOT_STARTED",
            "title": "Off-by-one stack write",
            "target_area": "parser",
            "finding_path": "itemdb/findings/PENDING/CC-0001-off-by-one.md",
            "evidence": "evidence/CC-0001",
        },
        {
            "id": "CC-0002",
            "status": "PENDING",
            "severity": "LOW",
            "confidence": "HIGH",
            "exploitation_status": "",
            "validation_status": "NOT_STARTED",
            "title": "Format string in echo",
            "target_area": "cli",
            "finding_path": "itemdb/findings/PENDING/CC-0002-format-string.md",
            "evidence": "evidence/CC-0002",
        },
        {
            "id": "CC-0003",
            "status": "CONFIRMED",
            "severity": "HIGH",
            "confidence": "CONFIRMED",
            "exploitation_status": "",
            "validation_status": "VALIDATED",
            "title": "Heap overflow",
            "target_area": "parser",
            "finding_path": "itemdb/findings/CONFIRMED/CC-0003-heap-overflow.md",
            "evidence": "evidence/CC-0003",
        },
    ]

    ctx = render_index_module.FindingsContext.default()
    out = render_index_module.render_index(rows, ctx=ctx)

    assert "| ID | Status | Severity | Confidence | Target area | Title | Finding | Evidence |" in out
    assert "CC-0001" in out
    assert "CC-0002" in out
    assert "CC-0003" in out

    assert "parser" in out

    assert "[evidence](evidence/CC-0001)" in out
    assert "[evidence](evidence/CC-0002)" in out
    assert "[evidence](evidence/CC-0003)" in out

    assert "[finding](findings/PENDING/CC-0001-off-by-one.md)" in out
    assert "[finding](findings/PENDING/CC-0002-format-string.md)" in out
    assert "[finding](findings/CONFIRMED/CC-0003-heap-overflow.md)" in out

    pending_row_1 = out.find("CC-0001")
    pending_row_2 = out.find("CC-0002")
    assert pending_row_1 != -1
    assert pending_row_2 != -1

    from findings.constants import FindingsContext

    ctx_empty = FindingsContext.default()
    empty_out = render_index_module.render_index([], ctx=ctx_empty)
    assert "| ID |" in empty_out