from __future__ import annotations

import argparse
import sys

from conftest import load_tool_module
import findings.constants as const_ROOT
from findings.constants import FindingsContext
from findings import move as move_module
from findings import evidence as evidence_module
from findings import create as create_module


def test_move_finding_updates_status_and_moves_file(tmp_path, monkeypatch):
    ctx = FindingsContext(
        root=tmp_path,
        itemdb_root=tmp_path / "itemdb",
        findings_root=tmp_path / "itemdb" / "findings",
    )

    src = tmp_path / "itemdb" / "findings" / "PENDING" / "CC-0001-test.md"
    src.parent.mkdir(parents=True)
    src.write_text(
        "---\n"
        'status: "PENDING"\n'
        'confidence: "LOW"\n'
        'updated_at: "2026-01-01"\n'
        "validation:\n"
        '  status: "NOT_STARTED"\n'
        "---\n",
        encoding="utf-8",
    )

    out = move_module.move_finding(src, "CONFIRMED", ctx=ctx)
    assert out.exists()
    assert out.parent.name == "CONFIRMED"
    text = out.read_text(encoding="utf-8")
    assert 'status: "CONFIRMED"' in text
    assert 'confidence: "CONFIRMED"' in text
    assert '  status: "CONFIRMED"' in text


def test_create_evidence_requires_existing_finding(tmp_path, monkeypatch):
    ctx = FindingsContext(
        root=tmp_path,
        itemdb_root=tmp_path / "itemdb",
        findings_root=tmp_path / "itemdb" / "findings",
        evidence_root=tmp_path / "itemdb" / "evidence",
        evidence_template_path=tmp_path / "templates" / "evidence-readme.md",
    )

    template_path = tmp_path / "templates" / "evidence-readme.md"
    template_path.parent.mkdir(parents=True)
    template_path.write_text("# Evidence for CC-0000\nDate: YYYY-MM-DD\n", encoding="utf-8")

    try:
        evidence_module.create_evidence("CC-0001", ctx=ctx)
        raise AssertionError("Expected FileNotFoundError")
    except FileNotFoundError as exc:
        assert "Finding not found" in str(exc)


def test_move_finding_not_found_shows_friendly_error(tmp_path, capsys, monkeypatch):
    wrapper = load_tool_module("move_finding", "tools/move-finding.py")
    monkeypatch.setattr(sys, "argv", ["move-finding.py", "CC-9999", "PENDING"])

    def mock_find_finding(identifier, *, findings_root=None, root=None):
        raise FileNotFoundError(f"Finding not found: {identifier}")

    monkeypatch.setattr(move_module, "find_finding", mock_find_finding)

    result = wrapper.main()
    assert result == 1
    captured = capsys.readouterr()
    assert "Finding not found: CC-9999" in captured.out


def test_create_finding_invalid_id_shows_friendly_error(tmp_path, capsys, monkeypatch):
    wrapper = load_tool_module("create_finding", "tools/create-finding.py")
    template_path = tmp_path / "templates" / "finding.md"
    template_path.parent.mkdir(parents=True)
    template_path.write_text("---\nid: CC-0000\ntitle: Test\nstatus: PENDING\n---\n", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["create-finding.py", "Test Title", "--id", "INVALID"])

    result = wrapper.main()
    assert result == 1
    captured = capsys.readouterr()
    assert "Invalid finding id format" in captured.out


def test_create_evidence_invalid_id_shows_friendly_error(tmp_path, capsys, monkeypatch):
    wrapper = load_tool_module("create_evidence", "tools/create-evidence.py")
    template_path = tmp_path / "templates" / "evidence-readme.md"
    template_path.parent.mkdir(parents=True)
    template_path.write_text("# Evidence\n", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["create-evidence.py", "INVALID"])

    result = wrapper.main()
    assert result == 1
    captured = capsys.readouterr()
    assert "Invalid finding id" in captured.out
