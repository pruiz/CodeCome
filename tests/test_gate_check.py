from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from phases import gates as gates_module


def test_has_meaningful_evidence_detects_template_only_readme(tmp_path):
    original_root = gates_module.ROOT
    gates_module.ROOT = tmp_path

    evidence_dir = tmp_path / "itemdb" / "evidence" / "CC-0001"
    evidence_dir.mkdir(parents=True)
    readme = evidence_dir / "README.md"
    readme.write_text("Briefly summarize what this evidence proves or disproves.", encoding="utf-8")

    try:
        assert gates_module.has_meaningful_evidence("CC-0001") is False
    finally:
        gates_module.ROOT = original_root


def test_has_meaningful_evidence_detects_non_readme_artifact(tmp_path):
    original_root = gates_module.ROOT
    gates_module.ROOT = tmp_path

    evidence_dir = tmp_path / "itemdb" / "evidence" / "CC-0002"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "output.txt").write_text("proof", encoding="utf-8")

    try:
        assert gates_module.has_meaningful_evidence("CC-0002") is True
    finally:
        gates_module.ROOT = original_root


def test_find_finding_exact_match_bare_cc_xxxx(tmp_path):
    original_root = gates_module.ROOT
    gates_module.ROOT = tmp_path

    pending = tmp_path / "itemdb" / "findings" / "PENDING"
    pending.mkdir(parents=True)
    (pending / "CC-0003.md").write_text("---\nid: CC-0003\n---\n", encoding="utf-8")

    try:
        result = gates_module.find_finding("CC-0003")
        assert result is not None
        assert result.name == "CC-0003.md"
    finally:
        gates_module.ROOT = original_root


def test_find_finding_slug_match(tmp_path):
    original_root = gates_module.ROOT
    gates_module.ROOT = tmp_path

    pending = tmp_path / "itemdb" / "findings" / "PENDING"
    pending.mkdir(parents=True)
    (pending / "CC-0003-some-finding.md").write_text("---\nid: CC-0003\n---\n", encoding="utf-8")

    try:
        result = gates_module.find_finding("CC-0003")
        assert result is not None
        assert result.name == "CC-0003-some-finding.md"
    finally:
        gates_module.ROOT = original_root


def test_find_finding_exact_wins_over_slug(tmp_path):
    original_root = gates_module.ROOT
    gates_module.ROOT = tmp_path

    pending = tmp_path / "itemdb" / "findings" / "PENDING"
    pending.mkdir(parents=True)
    (pending / "CC-0003.md").write_text("---\nid: CC-0003\n---\n", encoding="utf-8")
    (pending / "CC-0003-other-finding.md").write_text("---\nid: CC-0003\n---\n", encoding="utf-8")

    try:
        result = gates_module.find_finding("CC-0003")
        assert result is not None
        assert result.name == "CC-0003.md"
    finally:
        gates_module.ROOT = original_root


def test_find_finding_returns_none_for_missing(tmp_path):
    original_root = gates_module.ROOT
    gates_module.ROOT = tmp_path

    try:
        result = gates_module.find_finding("CC-9999")
        assert result is None
    finally:
        gates_module.ROOT = original_root


def test_gate_phase_4_accepts_bare_id(tmp_path, monkeypatch):
    original_root = gates_module.ROOT
    gates_module.ROOT = tmp_path

    pending = tmp_path / "itemdb" / "findings" / "PENDING"
    pending.mkdir(parents=True)
    (pending / "CC-0003.md").write_text("---\nid: CC-0003\n---\n", encoding="utf-8")

    try:
        exit_code = gates_module.gate_phase_4("CC-0003")
        assert exit_code == 0
    finally:
        gates_module.ROOT = original_root


def test_gate_phase_4_rejects_wrong_status(tmp_path, monkeypatch):
    original_root = gates_module.ROOT
    gates_module.ROOT = tmp_path

    confirmed = tmp_path / "itemdb" / "findings" / "CONFIRMED"
    confirmed.mkdir(parents=True)
    (confirmed / "CC-0003.md").write_text("---\nid: CC-0003\n---\n", encoding="utf-8")

    try:
        exit_code = gates_module.gate_phase_4("CC-0003")
        assert exit_code == 1
    finally:
        gates_module.ROOT = original_root
