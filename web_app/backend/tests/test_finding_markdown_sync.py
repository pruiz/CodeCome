from types import SimpleNamespace

from app.api.findings import sync_finding_markdown_status


def test_sync_finding_markdown_moves_file_and_updates_frontmatter(tmp_path):
    root = tmp_path / "itemdb" / "findings"
    pending = root / "PENDING"
    confirmed = root / "CONFIRMED"
    pending.mkdir(parents=True)
    confirmed.mkdir(parents=True)
    source = pending / "CC-0001-demo.md"
    source.write_text(
        "---\n"
        "id: CC-0001\n"
        "status: PENDING\n"
        "severity: HIGH\n"
        "confidence: MEDIUM\n"
        "category: Test\n"
        "---\n"
        "# Summary\n"
    )
    audit = SimpleNamespace(workspace_path=str(tmp_path))
    finding = SimpleNamespace(id="CC-0001", status="CONFIRMED", severity="CRITICAL", confidence="CONFIRMED", category="RCE")

    sync_finding_markdown_status(audit, finding)

    target = confirmed / "CC-0001-demo.md"
    assert not source.exists()
    assert target.exists()
    content = target.read_text()
    assert "status: CONFIRMED" in content
    assert "severity: CRITICAL" in content
    assert "confidence: CONFIRMED" in content
    assert "category: RCE" in content
    assert "# Summary" in content
