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
    content_lower = content.lower()
    assert "attacker" in content_lower
    assert "non-capabilities" in content_lower


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


# ---------------------------------------------------------------------------
# Phase 5 exploiter agent — threat-model.md integration
# ---------------------------------------------------------------------------

def test_exploiter_agent_references_threat_model() -> None:
    content = _read_opencode(".opencode/agents/exploiter.md")
    assert "itemdb/notes/threat-model.md" in content


def test_exploiter_agent_uses_conditional_language() -> None:
    content = _read_opencode(".opencode/agents/exploiter.md")
    content_lower = content.lower()
    assert (
        "when available" in content_lower
        or "when present" in content_lower
        or "if present" in content_lower
    )


def test_exploiter_agent_mentions_non_capabilities() -> None:
    content = _read_opencode(".opencode/agents/exploiter.md")
    assert "non-capabilities" in content


# ---------------------------------------------------------------------------
# Phase 5 exploit-development skill — threat-model.md integration
# ---------------------------------------------------------------------------

def test_exploit_development_skill_references_threat_model() -> None:
    content = _read_opencode(".opencode/skills/exploit-development/SKILL.md")
    assert "itemdb/notes/threat-model.md" in content


def test_exploit_development_skill_mentions_non_capabilities() -> None:
    content = _read_opencode(".opencode/skills/exploit-development/SKILL.md")
    assert "non-capabilities" in content


# ---------------------------------------------------------------------------
# Phase 5 prompt — threat-model.md integration
# ---------------------------------------------------------------------------

def test_phase_5_explicitly_references_threat_model_when_present() -> None:
    content = _read_prompt("phase-5-exploit.md")
    assert "itemdb/notes/threat-model.md" in content


def test_phase_5_uses_conditional_when_present_language() -> None:
    content = _read_prompt("phase-5-exploit.md")
    content_lower = content.lower()
    assert (
        "when available" in content_lower
        or "when present" in content_lower
        or "if present" in content_lower
    )


def test_phase_5_mentions_attacker_capabilities_and_non_capabilities() -> None:
    content = _read_prompt("phase-5-exploit.md")
    assert "attacker capabilit" in content.lower()
    assert "non-capabilities" in content


def test_phase_5_mentions_trust_boundaries() -> None:
    content = _read_prompt("phase-5-exploit.md")
    assert "trust boundar" in content.lower()


def test_phase_5_mentions_existing_controls() -> None:
    content = _read_prompt("phase-5-exploit.md")
    assert "existing controls" in content.lower()


def test_phase_5_mentions_open_assumptions() -> None:
    content = _read_prompt("phase-5-exploit.md")
    assert "open assumptions" in content.lower()


def test_phase_5_checklist_references_non_capabilities() -> None:
    content = _read_prompt("phase-5-exploit.md")
    assert "non-capabilities" in content
    assert "threat-model.md" in content


def test_phase_5_final_response_mentions_threat_model_assumptions() -> None:
    content = _read_prompt("phase-5-exploit.md")
    assert "threat-model assumptions" in content.lower()


# ---------------------------------------------------------------------------
# Exploit README template — threat-model assumptions section
# ---------------------------------------------------------------------------

def test_exploit_readme_template_has_threat_model_assumptions_section() -> None:
    content = _read_opencode("templates/exploit-readme.md")
    assert "# Threat Model Assumptions" in content


def test_exploit_readme_template_mentions_non_capabilities() -> None:
    content = _read_opencode("templates/exploit-readme.md")
    assert "non-capabilities" in content.lower()


def test_exploit_readme_template_mentions_open_assumptions() -> None:
    content = _read_opencode("templates/exploit-readme.md")
    assert "open assumptions" in content.lower()


# ---------------------------------------------------------------------------
# Phase 6 reporter agent — threat-model.md integration
# ---------------------------------------------------------------------------

def test_reporter_agent_references_threat_model() -> None:
    content = _read_opencode(".opencode/agents/reporter.md")
    assert "itemdb/notes/threat-model.md" in content


def test_reporter_agent_uses_conditional_language() -> None:
    content = _read_opencode(".opencode/agents/reporter.md")
    content_lower = content.lower()
    assert (
        "when available" in content_lower
        or "when present" in content_lower
        or "if present" in content_lower
    )


def test_reporter_agent_mentions_attacker_model() -> None:
    content = _read_opencode(".opencode/agents/reporter.md")
    assert "attacker model" in content.lower() or "attacker-model" in content.lower()


def test_reporter_agent_mentions_threat_model_in_limitations() -> None:
    content = _read_opencode(".opencode/agents/reporter.md")
    assert "threat model" in content.lower() or "threat-model" in content.lower()
    assert "open assumptions" in content.lower()


# ---------------------------------------------------------------------------
# Phase 6 report-writing skill — threat-model.md integration
# ---------------------------------------------------------------------------

def test_report_writing_skill_references_threat_model() -> None:
    content = _read_opencode(".opencode/skills/report-writing/SKILL.md")
    assert "itemdb/notes/threat-model.md" in content


def test_report_writing_skill_mentions_attacker() -> None:
    content = _read_opencode(".opencode/skills/report-writing/SKILL.md")
    assert "attacker" in content.lower()


# ---------------------------------------------------------------------------
# Phase 6 prompt — threat-model.md integration
# ---------------------------------------------------------------------------

def test_phase_6_explicitly_references_threat_model_when_present() -> None:
    content = _read_prompt("phase-6-report.md")
    assert "itemdb/notes/threat-model.md" in content


def test_phase_6_uses_conditional_language() -> None:
    content = _read_prompt("phase-6-report.md")
    content_lower = content.lower()
    assert (
        "when available" in content_lower
        or "when present" in content_lower
        or "if present" in content_lower
    )


def test_phase_6_mentions_trust_boundaries() -> None:
    content = _read_prompt("phase-6-report.md")
    assert "trust boundar" in content.lower() or "trust-boundary" in content.lower()


def test_phase_6_mentions_attacker_model_in_methodology() -> None:
    content = _read_prompt("phase-6-report.md")
    assert "attacker model" in content.lower() or "attacker-model" in content.lower()


def test_phase_6_guards_against_speculative_severity() -> None:
    content = _read_prompt("phase-6-report.md")
    content_lower = content.lower()
    assert "inflate" in content_lower or "abuse-path" in content_lower


# ---------------------------------------------------------------------------
# Report template — threat-model context
# ---------------------------------------------------------------------------

def test_report_template_mentions_threat_model() -> None:
    content = _read_opencode("templates/report.md")
    assert "threat model" in content.lower() or "threat-model" in content.lower()


def test_report_template_mentions_trust_boundaries_in_scope() -> None:
    content = _read_opencode("templates/report.md")
    assert "trust boundar" in content.lower()


def test_report_template_mentions_attacker_model_in_methodology() -> None:
    content = _read_opencode("templates/report.md")
    assert "attacker model" in content.lower()
