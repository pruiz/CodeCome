from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def _read_prompt(name: str) -> str:
    path = ROOT / "prompts" / name
    assert path.is_file(), f"{path} does not exist"
    return path.read_text(encoding="utf-8")


def _read_opencode(path_from_root: str) -> str:
    path = ROOT / path_from_root
    assert path.is_file(), f"{path} does not exist"
    return path.read_text(encoding="utf-8")


def test_phase_1c_recon_prompt_exists() -> None:
    path = ROOT / "prompts" / "phase-1c-recon.md"
    assert path.is_file(), f"{path} does not exist"


def test_phase_1c_recon_has_detailed_reconnaissance_title() -> None:
    content = _read_prompt("phase-1c-recon.md")
    assert "Detailed Reconnaissance" in content
    assert "CodeQL-assisted Reconnaissance" not in content


def test_phase_1c_recon_mentions_codeql_as_optional() -> None:
    content = _read_prompt("phase-1c-recon.md")
    assert "optional enrichment" in content


def test_phase_1c_recon_requires_threat_model() -> None:
    content = _read_prompt("phase-1c-recon.md")
    assert "threat-model.md" in content


def test_phase_1c_recon_references_threat_model_references() -> None:
    content = _read_prompt("phase-1c-recon.md")
    assert "threat-model-checklist.md" in content
    assert "security-controls-and-assets.md" in content


def test_phase_1c_recon_mentions_attacker_capabilities() -> None:
    content = _read_prompt("phase-1c-recon.md")
    assert "attacker capabilities" in content.lower()
    assert "non-capabilities" in content


def test_phase_1c_recon_mentions_open_questions_and_rerun() -> None:
    content = _read_prompt("phase-1c-recon.md")
    assert "Open questions for the user" in content or "open questions" in content.lower()


def test_phase_1c_recon_mentions_abuse_path_themes() -> None:
    content = _read_prompt("phase-1c-recon.md")
    assert "abuse-path" in content.lower() or "Abuse-path" in content


def test_phase_1a_does_not_produce_threat_model() -> None:
    content = _read_prompt("phase-1a-profile.md")
    assert "does not produce" in content


def test_phase_1c_reads_threat_model() -> None:
    content = _read_prompt("phase-1c-recon.md")
    assert "threat-model.md" in content


def test_phase_2_audit_explicitly_references_threat_model() -> None:
    content = _read_prompt("phase-2-audit.md")
    assert "itemdb/notes/threat-model.md" in content


def test_phase_2_says_abuse_path_themes_are_leads() -> None:
    content = _read_prompt("phase-2-audit.md")
    assert "abuse-path" in content.lower()


def test_phase_3_explicitly_references_threat_model() -> None:
    content = _read_prompt("phase-3-review.md")
    assert "itemdb/notes/threat-model.md" in content


def test_phase_3_uses_attacker_capabilities_in_review() -> None:
    content = _read_prompt("phase-3-review.md")
    assert "attacker capabilities" in content.lower()


def test_phase_1_codecome_uses_renamed_prompt_file() -> None:
    content = (ROOT / "tools" / "codecome" / "phase_1.py").read_text(encoding="utf-8")
    assert "phase-1c-recon.md" in content
    assert "phase-1b-codeql-recon.md" not in content


def test_phase_1_recon_md_removed() -> None:
    path = ROOT / "prompts" / "phase-1-recon.md"
    assert not path.exists(), f"{path} should have been removed"


def test_phase_1b_codeql_recon_md_removed() -> None:
    path = ROOT / "prompts" / "phase-1b-codeql-recon.md"
    assert not path.exists(), f"{path} should have been renamed"



# ---------------------------------------------------------------------------
# Phase 4 validator agent and skill — threat-model.md integration
# ---------------------------------------------------------------------------

def test_validator_agent_references_threat_model() -> None:
    content = _read_opencode(".opencode/agents/validator.md")
    assert "itemdb/notes/threat-model.md" in content


def test_validator_agent_uses_conditional_language() -> None:
    content = _read_opencode(".opencode/agents/validator.md")
    content_lower = content.lower()
    assert (
        "when available" in content_lower
        or "when present" in content_lower
        or "if present" in content_lower
    )


def test_exploit_validation_skill_references_threat_model() -> None:
    content = _read_opencode(".opencode/skills/exploit-validation/SKILL.md")
    assert "itemdb/notes/threat-model.md" in content


def test_exploit_validation_skill_mentions_attacker_capabilities() -> None:
    content = _read_opencode(".opencode/skills/exploit-validation/SKILL.md")
    assert "non-capabilities" in content.lower()


# ---------------------------------------------------------------------------
# Phase 4 — threat-model.md integration
# ---------------------------------------------------------------------------

def test_phase_4_explicitly_references_threat_model_when_present() -> None:
    content = _read_prompt("phase-4-validate.md")
    assert "itemdb/notes/threat-model.md" in content


def test_phase_4_uses_conditional_when_available_language() -> None:
    content = _read_prompt("phase-4-validate.md")
    content_lower = content.lower()
    assert (
        "when this file is available" in content_lower
        or "when available" in content_lower
        or "when present" in content_lower
        or "if present" in content_lower
    )


def test_phase_4_mentions_attacker_capabilities_and_non_capabilities() -> None:
    content = _read_prompt("phase-4-validate.md")
    assert "attacker capabilit" in content.lower()
    assert "non-capabilities" in content.lower()


def test_phase_4_mentions_trust_boundaries_in_validation_context() -> None:
    content = _read_prompt("phase-4-validate.md")
    assert "trust boundar" in content.lower()


def test_phase_4_mentions_existing_controls() -> None:
    content = _read_prompt("phase-4-validate.md")
    assert "existing controls" in content.lower()
