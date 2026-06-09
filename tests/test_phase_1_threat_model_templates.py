from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))


def _headings(text: str) -> set[str]:
    """Extract H1 headings from markdown text (portable)."""
    headings: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            headings.add(stripped)
    return headings


REQUIRED_THREAT_MODEL_HEADINGS = [
    "# Threat Model Summary",
    "# Scope",
    "# System model",
    "# Assets and security objectives",
    "# Attacker model",
    "# Trust boundary summary",
    "# Existing controls",
    "# Abuse-path themes for Phase 2",
    "# Risk calibration for review focus",
    "# Open questions for the user",
    "# Re-run prompt hints",
]


def test_threat_model_template_exists() -> None:
    path = ROOT / "templates" / "threat-model.md"
    assert path.is_file(), f"{path} does not exist"


def test_threat_model_template_has_all_required_headings() -> None:
    path = ROOT / "templates" / "threat-model.md"
    content = path.read_text(encoding="utf-8")
    present = _headings(content)
    for h in REQUIRED_THREAT_MODEL_HEADINGS:
        assert h in present, f"missing heading: {h}"


def test_threat_model_template_uses_structured_subsection_markers() -> None:
    path = ROOT / "templates" / "threat-model.md"
    content = path.read_text(encoding="utf-8")

    assert "## Boundary: <source> -> <destination>" in content
    assert "## Theme: <short name>" in content
    assert "## Question: <short question>" in content


def test_run_summary_has_open_questions_section() -> None:
    path = ROOT / "templates" / "run-summary.md"
    content = path.read_text(encoding="utf-8")

    assert "# Open questions for the user" in content
    assert "## Question:" in content
    assert "# Re-run prompt hints" in content


def test_run_summary_uses_subsection_not_table_for_questions() -> None:
    path = ROOT / "templates" / "run-summary.md"
    content = path.read_text(encoding="utf-8")

    assert "## Question:" in content
    assert "| Question | Why it matters | Affects | Suggested answer format |" not in content


def test_target_recon_mentions_threat_model_and_controls() -> None:
    path = ROOT / "templates" / "target-recon.md"
    content = path.read_text(encoding="utf-8")

    assert "threat-model.md" in content
    assert "attacker" in content.lower()
    assert "existing controls" in content.lower()


def test_threat_model_heading_validation_rejects_malformed(tmp_path: Path) -> None:
    """verify strict H1 matching: '# Heading' ok, '#Heading' not ok."""
    from phases.artifact_checks import _h1_headings_from_text

    valid = "# Threat Model Summary\n# Scope\n## Subsection\n"
    headings = _h1_headings_from_text(valid)
    assert "# Threat Model Summary" in headings
    assert "# Scope" in headings
    assert "## Subsection" not in headings

    malformed = "#Scope\n#  DoubleSpace\n"
    headings = _h1_headings_from_text(malformed)
    assert "#Scope" not in headings
    assert "#  DoubleSpace" not in headings


def test_threat_model_template_validates_cleanly(tmp_path: Path) -> None:
    """The template itself should pass heading validation as if it were a real file."""
    from phases.artifact_checks import check_phase_1b_artifacts

    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True)
    (tmp_path / "runs").mkdir()

    # Copy the template in as threat-model.md
    template = (ROOT / "templates" / "threat-model.md").read_text(encoding="utf-8")
    (notes / "threat-model.md").write_text(template, encoding="utf-8")

    with patch("phases.artifact_checks.ROOT", tmp_path):
        errors = check_phase_1b_artifacts(allow_missing_generated=True)

    # Template has all required headings, so no heading errors for threat-model.md
    heading_errors = [e for e in errors if "threat-model.md" in e and "headings" in e]
    assert heading_errors == [], f"unexpected heading errors: {heading_errors}"
