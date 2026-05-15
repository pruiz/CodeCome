from __future__ import annotations

from conftest import load_tool_module


def test_has_meaningful_evidence_detects_template_only_readme(tmp_path):
    module = load_tool_module("gate_check", "tools/gate-check.py")
    module.ROOT = tmp_path

    evidence_dir = tmp_path / "itemdb" / "evidence" / "CC-0001"
    evidence_dir.mkdir(parents=True)
    readme = evidence_dir / "README.md"
    readme.write_text("Briefly summarize what this evidence proves or disproves.", encoding="utf-8")

    assert module.has_meaningful_evidence("CC-0001") is False


def test_has_meaningful_evidence_detects_non_readme_artifact(tmp_path):
    module = load_tool_module("gate_check_artifact", "tools/gate-check.py")
    module.ROOT = tmp_path

    evidence_dir = tmp_path / "itemdb" / "evidence" / "CC-0002"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "output.txt").write_text("proof", encoding="utf-8")

    assert module.has_meaningful_evidence("CC-0002") is True


def test_find_finding_exact_match_bare_cc_xxxx(tmp_path):
    module = load_tool_module("gate_check_exact", "tools/gate-check.py")
    module.ROOT = tmp_path

    pending = tmp_path / "itemdb" / "findings" / "PENDING"
    pending.mkdir(parents=True)
    (pending / "CC-0003.md").write_text("---\nid: CC-0003\n---\n", encoding="utf-8")

    result = module.find_finding("CC-0003")
    assert result is not None
    assert result.name == "CC-0003.md"


def test_find_finding_slug_match(tmp_path):
    module = load_tool_module("gate_check_slug", "tools/gate-check.py")
    module.ROOT = tmp_path

    pending = tmp_path / "itemdb" / "findings" / "PENDING"
    pending.mkdir(parents=True)
    (pending / "CC-0003-some-finding.md").write_text("---\nid: CC-0003\n---\n", encoding="utf-8")

    result = module.find_finding("CC-0003")
    assert result is not None
    assert result.name == "CC-0003-some-finding.md"


def test_find_finding_exact_wins_over_slug(tmp_path):
    module = load_tool_module("gate_check_priority", "tools/gate-check.py")
    module.ROOT = tmp_path

    pending = tmp_path / "itemdb" / "findings" / "PENDING"
    pending.mkdir(parents=True)
    (pending / "CC-0003.md").write_text("---\nid: CC-0003\n---\n", encoding="utf-8")
    (pending / "CC-0003-other-finding.md").write_text("---\nid: CC-0003\n---\n", encoding="utf-8")

    result = module.find_finding("CC-0003")
    assert result is not None
    assert result.name == "CC-0003.md"


def test_find_finding_returns_none_for_missing(tmp_path):
    module = load_tool_module("gate_check_missing", "tools/gate-check.py")
    module.ROOT = tmp_path

    result = module.find_finding("CC-9999")
    assert result is None


def test_gate_phase_4_accepts_bare_id(tmp_path, monkeypatch):
    module = load_tool_module("gate_check_phase4", "tools/gate-check.py")
    module.ROOT = tmp_path

    pending = tmp_path / "itemdb" / "findings" / "PENDING"
    pending.mkdir(parents=True)
    (pending / "CC-0003.md").write_text("---\nid: CC-0003\n---\n", encoding="utf-8")

    exit_code = module.gate_phase_4("CC-0003")
    assert exit_code == 0


def test_gate_phase_4_rejects_wrong_status(tmp_path, monkeypatch):
    module = load_tool_module("gate_check_phase4_wrong", "tools/gate-check.py")
    module.ROOT = tmp_path

    confirmed = tmp_path / "itemdb" / "findings" / "CONFIRMED"
    confirmed.mkdir(parents=True)
    (confirmed / "CC-0003.md").write_text("---\nid: CC-0003\n---\n", encoding="utf-8")

    exit_code = module.gate_phase_4("CC-0003")
    assert exit_code == 1
