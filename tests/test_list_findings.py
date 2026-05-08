from __future__ import annotations

from conftest import load_tool_module


def test_filter_eligible_for_exploit_only_returns_supported_statuses():
    module = load_tool_module("list_findings", "tools/list-findings.py")
    rows = [
        {"id": "CC-0001", "status": "CONFIRMED", "exploitation_status": ""},
        {"id": "CC-0002", "status": "CONFIRMED", "exploitation_status": "IN_PROGRESS"},
        {"id": "CC-0003", "status": "CONFIRMED", "exploitation_status": "DEMONSTRATED"},
        {"id": "CC-0004", "status": "PENDING", "exploitation_status": ""},
    ]

    out = module.filter_eligible_for_exploit(rows)
    ids = [row["id"] for row in out]
    assert ids == ["CC-0001", "CC-0002"]
