from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from findings.constants import FindingsContext
from phase1_enrichment.prompt import build_phase1_enrichment_prompt, load_enrichment_prompt, write_enrichment_prompt_artifacts
from phase1_enrichment.semgrep import run_semgrep_enrichment


def temp_ctx(root: Path) -> FindingsContext:
    return FindingsContext(
        root=root,
        itemdb_root=root / "itemdb",
        findings_root=root / "itemdb" / "findings",
        evidence_root=root / "itemdb" / "evidence",
        notes_root=root / "itemdb" / "notes",
        reports_root=root / "itemdb" / "reports",
        template_path=root / "templates" / "finding.md",
        evidence_template_path=root / "templates" / "evidence-readme.md",
    )


def test_load_enrichment_prompt_reuses_preview_analysis_prompt(tmp_path):
    ctx = temp_ctx(tmp_path)
    preview_path = tmp_path / "web_app" / "backend" / "data" / "preview-analysis.md"
    preview_path.parent.mkdir(parents=True)
    preview_path.write_text("Focus on auth boundary drift.", encoding="utf-8")

    prompt = load_enrichment_prompt(ctx)

    assert prompt is not None
    assert prompt.source == "Preview Analysis prompt"
    assert prompt.text == "Focus on auth boundary drift."


def test_build_phase1_enrichment_prompt_contains_safety_rules():
    prompt = build_phase1_enrichment_prompt(
        load_enrichment_prompt(temp_ctx(Path("/nonexistent"))) or type("Prompt", (), {"text": "Check imports.", "source": "test"})(),
        ["src/app.php"],
    )

    assert "itemdb/notes/semgrep-results.yml" in prompt
    assert "src/app.php" in prompt
    assert "Do not create files under `itemdb/findings/`" in prompt
    assert "Do not claim any Semgrep or prompt-derived signal is a confirmed vulnerability" in prompt
    assert "Preserve the normal CodeCome lifecycle" in prompt


def test_write_enrichment_prompt_artifacts_records_note_sections(tmp_path):
    ctx = temp_ctx(tmp_path)
    ctx.notes_root.mkdir(parents=True)
    for name, title in [("attack-surface.md", "Attack Surface"), ("trust-boundaries.md", "Trust Boundaries"), ("threat-model.md", "Threat Model")]:
        (ctx.notes_root / name).write_text(f"# {title}\n\nExisting content.\n", encoding="utf-8")
    prompt = type("Prompt", (), {"text": "Check imports.", "source": "test prompt"})()

    path = write_enrichment_prompt_artifacts(ctx, prompt, generated_at="2026-06-30T12:00:00", semgrep_files=["src/app.php"])

    assert path == tmp_path / "runs" / "phase-1-enrichment-prompt.md"
    assert "Check imports." in path.read_text(encoding="utf-8")
    for name in ["attack-surface.md", "trust-boundaries.md", "threat-model.md"]:
        content = (ctx.notes_root / name).read_text(encoding="utf-8")
        assert "Existing content." in content
        assert "# User Prompt Enrichment" in content
        assert "must not create findings" in content


def test_semgrep_enrichment_writes_prompt_copy_from_explicit_file(tmp_path):
    ctx = temp_ctx(tmp_path)
    (tmp_path / "src").mkdir()
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Prioritize tenant isolation.", encoding="utf-8")

    def fake_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, '{"results": []}', "")

    run = run_semgrep_enrichment(ctx=ctx, runner=fake_runner, enrichment_prompt_file=str(prompt_file))

    assert run.status == "completed"
    assert run.prompt_copy_path == tmp_path / "runs" / "phase-1-enrichment-prompt.md"
    assert "Prioritize tenant isolation." in run.prompt_copy_path.read_text(encoding="utf-8")
