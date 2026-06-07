from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def test_phase1_required_artifact_names_includes_threat_model() -> None:
    from phases.completion import _PHASE1_REQUIRED_ARTIFACT_NAMES

    assert "threat-model.md" in _PHASE1_REQUIRED_ARTIFACT_NAMES


def test_phase_checklist_lines_mentions_threat_model() -> None:
    from phases.completion import phase_checklist_lines

    lines = phase_checklist_lines("1", None)
    joined = "\n".join(lines)

    assert "threat-model.md" in joined
    assert "# Threat Model Summary" in joined


def test_build_artifact_repair_resume_prompt_includes_validation_output() -> None:
    from phases.completion import build_artifact_repair_resume_prompt

    output = "itemdb/notes/threat-model.md missing headings: # Attacker model"
    prompt = build_artifact_repair_resume_prompt("1b", None, output)

    assert output in prompt
    assert "threat-model.md" in prompt


def test_build_artifact_repair_resume_prompt_includes_checklist() -> None:
    from phases.completion import build_artifact_repair_resume_prompt

    prompt = build_artifact_repair_resume_prompt("1b", None, "some error")

    assert "threat-model.md" in prompt
    assert "completion checklist" in prompt.lower()


def test_build_artifact_repair_resume_prompt_avoids_unrelated_rewrites() -> None:
    from phases.completion import build_artifact_repair_resume_prompt

    prompt = build_artifact_repair_resume_prompt("1b", None, "some error")

    assert "unrelated" in prompt
    assert "do not modify target source code" in prompt


def test_build_artifact_repair_resume_prompt_supports_phase_1a() -> None:
    from phases.completion import build_artifact_repair_resume_prompt

    prompt = build_artifact_repair_resume_prompt(
        "1a",
        None,
        "itemdb/notes/codeql-plan.yml has empty languages; set recommended=false",
    )

    assert "Phase 1a artifacts" in prompt
    assert "codeql-plan.yml" in prompt
    assert "recommended=false" in prompt
