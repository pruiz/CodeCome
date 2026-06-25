import re
from pathlib import Path
import yaml

def test_prompt_safeguards():
    """Ensure prompts enforce CLI usage and frontmatter validation."""
    prompts_dir = Path("prompts")

    # Phase 3, 4, 5 should enforce using make findings-move
    for phase in ["phase-3-review.md", "phase-4-validate.md", "phase-5-exploit.md"]:
        content = (prompts_dir / phase).read_text(encoding="utf-8")
        assert "make findings-move" in content, f"{phase} is missing make findings-move instruction"

    # All modification phases should run frontmatter check
    for phase in ["phase-2-audit.md", "phase-3-review.md", "phase-4-validate.md", "phase-5-exploit.md"]:
        content = (prompts_dir / phase).read_text(encoding="utf-8")
        assert "make frontmatter" in content, f"{phase} is missing make frontmatter instruction"


def test_no_stale_phase_1b_1c_references_in_prompts():
    """Ensure no prompt files reference the old Phase 1b/1c ordering.

    After the refactor:
      - Phase 1b = Sandbox Bootstrap
      - Phase 1c = Detailed Reconnaissance
    Old contradictory patterns must not appear outside the canonical prompt files.
    """
    prompts_dir = Path("prompts")

    # Stale patterns that indicate the old order (1b = recon, 1c = sandbox)
    stale_patterns = [
        (r"Phase 1b(?:.|\n){0,100}Detailed Reconnaissance", "Phase 1b should not describe Detailed Reconnaissance (now 1c)"),
        (r"Phase 1b(?:.|\n){0,100}reconnaissance", "Phase 1b should not be described as reconnaissance (now 1c)"),
        (r"Phase 1c(?:.|\n){0,100}Sandbox Bootstrap", "Phase 1c should not describe Sandbox Bootstrap (now 1b)"),
        (r"Phase 1c(?:.|\n){0,100}sandbox bootstrap", "Phase 1c should not describe sandbox bootstrap (now 1b)"),
        (r"\b1b\b(?:.|\n){0,100}\brecon\b", "phase-1b should not reference recon (now 1c)"),
    ]

    # The canonical files may reference the old names in their key/value style
    # but NOT in a way that mixes the phase number with the wrong task.
    exceptions: dict[str, list[str]] = {
        "phase-1b-sandbox.md": [],
        "phase-1c-recon.md": [r"Phase 1b(?:.|\n){0,100}reconnaissance", r"\b1b\b(?:.|\n){0,100}\brecon\b"],
        "README.md": [r"\b1b\b(?:.|\n){0,100}\brecon\b", r"Phase 1b(?:.|\n){0,100}reconnaissance"],
    }

    for prompt_file in sorted(prompts_dir.glob("*.md")):
        content = prompt_file.read_text(encoding="utf-8")
        for pattern, reason in stale_patterns:
            if prompt_file.name in exceptions and pattern in exceptions[prompt_file.name]:
                continue
            if re.search(pattern, content, re.IGNORECASE):
                raise AssertionError(
                    f"{prompt_file.name}: {reason}. Found pattern: {pattern!r}"
                )


def test_phase_1b_sandbox_prompt_is_self_consistent():
    content = Path("prompts/phase-1b-sandbox.md").read_text(encoding="utf-8")
    assert "Phase 1b" in content
    assert "Sandbox Bootstrap" in content
    assert "second sub-stage" in content.lower()  # sandbox is the second sub-phase


def test_phase_1c_recon_prompt_is_self_consistent():
    content = Path("prompts/phase-1c-recon.md").read_text(encoding="utf-8")
    assert "Phase 1c" in content
    assert "Detailed Reconnaissance" in content
    assert "third and final" in content  # recon is the third sub-phase


def test_gap_scan_prompt_is_candidate_only():
    content = Path("prompts/phase-2-gap-sast.md").read_text(encoding="utf-8")

    assert "itemdb/notes/sast-gap-candidates.yml" in content
    assert "itemdb/notes/sast-gap-scan.md" in content
    assert "CODECOME_GAP_MAX_CANDIDATES" in content
    assert "Do not create files under `itemdb/findings/`" in content
    assert "Do not run `make findings-create`" in content
    assert "Do not run `make findings-move`" in content
    assert "Do not mark anything as `CONFIRMED`" in content
    assert "Do not mark anything as `EXPLOITED`, `REJECTED`, or `DUPLICATE`" in content
    assert "Do not re-open `REJECTED` or `DUPLICATE` findings" in content
    assert "Preserve the normal CodeCome lifecycle" in content
    assert "Do not treat notes-only references as active findings" in content
    assert "stack traces" in content


def test_makefile_has_manual_gap_scan_target():
    content = Path("Makefile").read_text(encoding="utf-8")

    assert "gap-scan: env-check" in content
    assert "gap-compare: env-check" in content
    assert "--label \"Gap Scan\"" in content
    assert "--agent gap-scanner" in content
    assert "--prompt-file prompts/phase-2-gap-sast.md" in content
    assert "tools/gap-config.py" in content
    assert "tools/gap-compare.py" in content
    assert "gap-loop:" not in content
    assert "gap-sweep:" not in content


def test_gap_scanner_agent_is_candidate_only():
    content = Path(".opencode/agents/gap-scanner.md").read_text(encoding="utf-8")

    assert "You do not create vulnerability findings." in content
    assert "You do not validate findings." in content
    assert "You do not develop exploits." in content
    assert "Do not write under `itemdb/findings/`" in content
    assert "make findings-create" in content
    assert "make findings-move" in content
    assert "Do not claim any candidate is confirmed." in content


def test_gap_scan_templates_define_required_artifacts():
    expected = [
        "sast-gap-scan.md",
        "sast-gap-candidates.yml",
        "sast-gap-interesting-files.md",
        "sast-gap-file-risk-index.yml",
        "sast-gap-compare-summary.md",
        "sast-gap-sweep-summary.md",
    ]

    for name in expected:
        assert (Path("templates") / name).is_file(), f"missing template {name}"

    candidates = yaml.safe_load(Path("templates/sast-gap-candidates.yml").read_text(encoding="utf-8"))
    candidate = candidates["candidates"][0]
    for field in [
        "id",
        "title",
        "category",
        "cwe",
        "severity_hint",
        "confidence",
        "files",
        "symbols",
        "entry_points",
        "sources",
        "sinks",
        "trust_boundary",
        "evidence",
        "impact",
        "validation_idea",
        "matched_existing_findings",
        "matched_notes",
        "match_confidence",
        "decision",
        "action",
        "sweep_files",
        "sweep_rationale",
        "expected_vulnerability_class",
        "safety",
    ]:
        assert field in candidate

    assert candidate["id"] == "GAP-0001"
    assert candidate["decision"] == "missing_sweep"
