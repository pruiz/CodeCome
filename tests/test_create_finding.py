from __future__ import annotations

from argparse import Namespace

from findings.constants import FindingsContext
from findings import create as create_module


def _mk_workspace(tmp_path):
    (tmp_path / "templates").mkdir(parents=True)
    (tmp_path / "itemdb" / "findings" / "PENDING").mkdir(parents=True)
    (tmp_path / "itemdb" / "evidence").mkdir(parents=True)


def test_create_finding_writes_expected_file(tmp_path):
    _mk_workspace(tmp_path)

    template = (
        "---\n"
        'id: "CC-0000"\n'
        'title: "Short vulnerability title"\n'
        'status: "PENDING"\n'
        'severity: "MEDIUM"\n'
        'confidence: "LOW"\n'
        'category: "Unclassified"\n'
        'language: "unknown"\n'
        'target_area: "unknown"\n'
        "validation:\n"
        '  evidence_dir: "itemdb/evidence/CC-0000"\n'
        "exploitation:\n"
        '  artifacts_dir: "itemdb/evidence/CC-0000/exploits"\n'
        'created_at: "YYYY-MM-DD"\n'
        'updated_at: "YYYY-MM-DD"\n'
        "---\n\n"
        "Briefly describe the suspected vulnerability.\n"
    )
    (tmp_path / "templates" / "finding.md").write_text(template, encoding="utf-8")

    ctx = FindingsContext(
        root=tmp_path,
        findings_root=tmp_path / "itemdb" / "findings",
        evidence_root=tmp_path / "itemdb" / "evidence",
        notes_root=tmp_path / "itemdb" / "notes",
        template_path=tmp_path / "templates" / "finding.md",
        evidence_template_path=tmp_path / "templates" / "evidence-readme.md",
    )

    args = Namespace(
        title="Missing auth check",
        id=None,
        slug=None,
        severity="HIGH",
        confidence="MEDIUM",
        category="Auth",
        language="python",
        target_area="api",
        force=False,
    )

    out = create_module.create_finding(args, ctx=ctx)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert 'id: "CC-0001"' in content
    assert 'title: "Missing auth check"' in content
    assert 'severity: "HIGH"' in content
    assert 'confidence: "MEDIUM"' in content
    assert "Pending." in content
    assert (tmp_path / "itemdb" / "evidence" / "CC-0001").exists()


def test_create_finding_rejects_invalid_explicit_id(tmp_path):
    _mk_workspace(tmp_path)
    (tmp_path / "templates" / "finding.md").write_text('---\nid: "CC-0000"\n---\n', encoding="utf-8")

    ctx = FindingsContext(
        root=tmp_path,
        findings_root=tmp_path / "itemdb" / "findings",
        evidence_root=tmp_path / "itemdb" / "evidence",
        notes_root=tmp_path / "itemdb" / "notes",
        template_path=tmp_path / "templates" / "finding.md",
        evidence_template_path=tmp_path / "templates" / "evidence-readme.md",
    )

    args = Namespace(
        title="x",
        id="BAD-1",
        slug=None,
        severity="MEDIUM",
        confidence="LOW",
        category="Unclassified",
        language="unknown",
        target_area="unknown",
        force=False,
    )

    try:
        create_module.create_finding(args, ctx=ctx)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "Invalid finding id format" in str(exc)
