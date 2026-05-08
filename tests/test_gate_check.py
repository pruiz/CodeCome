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
