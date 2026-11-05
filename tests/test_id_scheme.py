from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from findings.constants import FindingsContext  # noqa: E402
from findings.create import create_finding  # noqa: E402
from findings.ids import next_finding_id  # noqa: E402
from findings.scheme import (  # noqa: E402
    IdSchemeError,
    allocate_next_id,
    load_id_scheme,
    parse_id_scheme,
    save_id_scheme,
)


def _workspace(tmp_path: Path) -> FindingsContext:
    notes = tmp_path / "itemdb" / "notes"
    findings = tmp_path / "itemdb" / "findings"
    evidence = tmp_path / "itemdb" / "evidence"
    template_dir = tmp_path / "templates"
    notes.mkdir(parents=True)
    (findings / "PENDING").mkdir(parents=True)
    evidence.mkdir(parents=True)
    template_dir.mkdir(parents=True)
    (template_dir / "finding.md").write_text(
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
        "Briefly describe the suspected vulnerability.\n",
        encoding="utf-8",
    )
    return FindingsContext(
        root=tmp_path,
        findings_root=findings,
        evidence_root=evidence,
        notes_root=notes,
        template_path=template_dir / "finding.md",
        evidence_template_path=template_dir / "evidence-readme.md",
    )


def test_parse_specimen_sets_width_and_start():
    scheme = parse_id_scheme("CC-0142")
    assert scheme.prefix == "CC"
    assert scheme.width == 4
    assert scheme.start == 142
    assert scheme.format(142) == "CC-0142"


def test_parse_rejects_free_form_text():
    with pytest.raises(IdSchemeError):
        parse_id_scheme("start at one")


def test_default_numbering_still_starts_at_cc_0001(tmp_path):
    ctx = _workspace(tmp_path)
    assert next_finding_id(findings_root=ctx.findings_root, notes_root=ctx.notes_root) == "CC-0001"


def test_phase1_scheme_is_reused_by_the_next_finding(tmp_path):
    ctx = _workspace(tmp_path)
    save_id_scheme(parse_id_scheme("CC-0142"), ctx.notes_root)
    assert next_finding_id(findings_root=ctx.findings_root, notes_root=ctx.notes_root) == "CC-0142"

    pending = ctx.findings_root / "PENDING"
    (pending / "CC-0142-first.md").write_text("id: CC-0142\n", encoding="utf-8")
    assert next_finding_id(findings_root=ctx.findings_root, notes_root=ctx.notes_root) == "CC-0143"


def test_requested_start_does_not_reuse_a_taken_number(tmp_path):
    ctx = _workspace(tmp_path)
    pending = ctx.findings_root / "PENDING"
    (pending / "CC-0001-old.md").write_text("id: CC-0001\n", encoding="utf-8")
    (pending / "CC-0002-old.md").write_text("id: CC-0002\n", encoding="utf-8")
    save_id_scheme(parse_id_scheme("CC-0001"), ctx.notes_root)
    assert next_finding_id(findings_root=ctx.findings_root, notes_root=ctx.notes_root) == "CC-0003"


def test_other_prefix_does_not_collide_with_cc(tmp_path):
    ctx = _workspace(tmp_path)
    pending = ctx.findings_root / "PENDING"
    (pending / "CC-0001-old.md").write_text("id: CC-0001\n", encoding="utf-8")
    save_id_scheme(parse_id_scheme("INT-0007"), ctx.notes_root)
    assert next_finding_id(findings_root=ctx.findings_root, notes_root=ctx.notes_root) == "INT-0007"


def test_ledger_continues_across_audits(tmp_path):
    ledger = tmp_path / "finding-ids.json"
    first = parse_id_scheme("CC-0001")
    first = type(first)(first.prefix, first.width, first.start, ledger)
    assert allocate_next_id(first, []) == "CC-0001"
    second_notes = tmp_path / "other" / "notes"
    second_notes.mkdir(parents=True)
    save_id_scheme(first, second_notes)
    loaded = load_id_scheme(second_notes)
    assert loaded is not None
    assert allocate_next_id(loaded, []) == "CC-0002"


def test_create_finding_uses_saved_scheme(tmp_path):
    ctx = _workspace(tmp_path)
    save_id_scheme(parse_id_scheme("CC-0142"), ctx.notes_root)
    out = create_finding(
        Namespace(
            title="Missing auth check",
            id=None,
            slug=None,
            severity="HIGH",
            confidence="MEDIUM",
            category="Auth",
            language="python",
            target_area="api",
            force=False,
        ),
        ctx=ctx,
    )
    assert out.name.startswith("CC-0142-")
    assert 'id: "CC-0142"' in out.read_text(encoding="utf-8")
