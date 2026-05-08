from __future__ import annotations

from conftest import load_tool_module


def test_move_finding_updates_status_and_moves_file(tmp_path):
    module = load_tool_module("move_finding", "tools/move-finding.py")
    module.ROOT = tmp_path
    module.FINDINGS_ROOT = tmp_path / "itemdb" / "findings"

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

    out = module.move_finding(src, "CONFIRMED")
    assert out.exists()
    assert out.parent.name == "CONFIRMED"
    text = out.read_text(encoding="utf-8")
    assert 'status: "CONFIRMED"' in text
    assert 'confidence: "CONFIRMED"' in text
    assert '  status: "CONFIRMED"' in text


def test_create_evidence_requires_existing_finding(tmp_path):
    module = load_tool_module("create_evidence", "tools/create-evidence.py")
    module.ROOT = tmp_path
    module.FINDINGS_ROOT = tmp_path / "itemdb" / "findings"
    module.EVIDENCE_ROOT = tmp_path / "itemdb" / "evidence"
    module.TEMPLATE_PATH = tmp_path / "templates" / "evidence-readme.md"

    module.TEMPLATE_PATH.parent.mkdir(parents=True)
    module.TEMPLATE_PATH.write_text("# Evidence for CC-0000\nDate: YYYY-MM-DD\n", encoding="utf-8")

    try:
        module.create_evidence("CC-0001", force=False)
        raise AssertionError("Expected FileNotFoundError")
    except FileNotFoundError as exc:
        assert "Finding not found" in str(exc)
