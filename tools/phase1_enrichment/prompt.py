from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
import os
import subprocess

from findings.constants import FindingsContext


PROMPT_COPY_REL = Path("runs/phase-1-enrichment-prompt.md")


@dataclass(frozen=True)
class EnrichmentPrompt:
    source: str
    text: str


@dataclass
class PromptEnrichmentRun:
    status: str
    prompt_copy_path: Path | None = None
    summary_path: Path | None = None
    command: list[str] | None = None
    returncode: int | None = None
    error: str = ""


def preview_analysis_prompt_path(ctx: FindingsContext) -> Path:
    return ctx.root / "web_app" / "backend" / "data" / "preview-analysis.md"


def _read_prompt_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def load_enrichment_prompt(ctx: FindingsContext, explicit_prompt_file: str | None = None) -> EnrichmentPrompt | None:
    candidates: list[tuple[str, Path]] = []
    if explicit_prompt_file:
        explicit = Path(explicit_prompt_file)
        if not explicit.is_absolute():
            explicit = ctx.root / explicit
        candidates.append((str(explicit), explicit))

    env_file = os.environ.get("CODECOME_PHASE1_ENRICHMENT_PROMPT_FILE", "").strip()
    if env_file:
        env_path = Path(env_file)
        if not env_path.is_absolute():
            env_path = ctx.root / env_path
        candidates.append((f"env CODECOME_PHASE1_ENRICHMENT_PROMPT_FILE={env_file}", env_path))

    preview_path = preview_analysis_prompt_path(ctx)
    candidates.append(("Preview Analysis prompt", preview_path))

    for source, path in candidates:
        text = _read_prompt_file(path)
        if text:
            return EnrichmentPrompt(source=source, text=text)
    return None


def build_phase1_enrichment_prompt(prompt: EnrichmentPrompt, semgrep_files: Iterable[str] = ()) -> str:
    files = [file for file in semgrep_files if file]
    file_lines = "\n".join(f"- `{file}`" for file in files[:20]) or "- No Semgrep file leads were available."
    return "\n".join([
        "# Phase 1 User Prompt Enrichment",
        "",
        "You are enriching existing CodeCome Phase 1 reconnaissance artifacts.",
        "",
        "## Required Reading",
        "",
        "Read these workspace files before making changes:",
        "",
        "- `AGENTS.md`",
        "- `codecome.yml`",
        "- `itemdb/notes/target-profile.md`",
        "- `itemdb/notes/build-model.md`",
        "- `itemdb/notes/attack-surface.md`",
        "- `itemdb/notes/trust-boundaries.md`",
        "- `itemdb/notes/threat-model.md`",
        "- `itemdb/notes/interesting-files.md`",
        "- `itemdb/notes/file-risk-index.yml`",
        "- `itemdb/notes/semgrep-results.yml` if it exists",
        "- `itemdb/notes/semgrep-interesting-files.md` if it exists",
        "",
        "## Semgrep File Leads",
        "",
        file_lines,
        "",
        "## User Prompt",
        "",
        prompt.text,
        "",
        "## Rules",
        "",
        "- Update or enrich Phase 1 notes only under `itemdb/notes/`.",
        "- Do not create files under `itemdb/findings/`.",
        "- Do not run `make findings-create` or `make findings-move`.",
        "- Do not claim any Semgrep or prompt-derived signal is a confirmed vulnerability.",
        "- Distinguish user-prompt hypotheses, Semgrep signals, and source-backed observations.",
        "- Preserve the normal CodeCome lifecycle: Phase 2 creates `PENDING` findings if warranted.",
        "- Record assumptions and uncertainty explicitly.",
        "",
        "## Required Output Behavior",
        "",
        "Add clearly marked `User Prompt Enrichment` sections to relevant Phase 1 notes when useful.",
        "Write a run summary under `runs/phase-1-prompt-enrichment-YYYY-MM-DD-HHMMSS.md` if this prompt is executed by an agent.",
        "",
    ])


def _replace_markdown_section(path: Path, default_title: str, section_title: str, body_lines: list[str]) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else f"# {default_title}\n"
    marker = f"\n# {section_title}\n"
    base = existing.split(marker, 1)[0].rstrip()
    content = "\n".join([base, "", f"# {section_title}", "", *body_lines]).rstrip() + "\n"
    path.write_text(content, encoding="utf-8")


def write_enrichment_prompt_artifacts(
    ctx: FindingsContext,
    prompt: EnrichmentPrompt,
    *,
    generated_at: str,
    semgrep_files: Iterable[str] = (),
) -> Path:
    runs_dir = ctx.root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    ctx.notes_root.mkdir(parents=True, exist_ok=True)
    prompt_path = ctx.root / PROMPT_COPY_REL
    prompt_path.write_text(build_phase1_enrichment_prompt(prompt, semgrep_files), encoding="utf-8")

    body = [
        f"Date: {generated_at}",
        f"Prompt source: {prompt.source}",
        f"Durable prompt copy: `{PROMPT_COPY_REL.as_posix()}`",
        "",
        "This section records a user-defined enrichment prompt for later recon-agent execution.",
        "The prompt is constrained to update Phase 1 notes only and must not create findings.",
        "",
        "Phase 2 remains responsible for turning enriched reconnaissance into CodeCome-quality `PENDING` findings.",
    ]
    for note_name, title in [
        ("attack-surface.md", "Attack Surface"),
        ("trust-boundaries.md", "Trust Boundaries"),
        ("threat-model.md", "Threat Model"),
    ]:
        _replace_markdown_section(ctx.notes_root / note_name, title, "User Prompt Enrichment", body)
    return prompt_path


def semgrep_file_leads(ctx: FindingsContext) -> list[str]:
    path = ctx.notes_root / "semgrep-results.yml"
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    summary = data.get("summary") if isinstance(data, dict) else {}
    by_file = summary.get("by_file") if isinstance(summary, dict) else {}
    if isinstance(by_file, dict):
        return sorted(str(file) for file in by_file.keys() if file)
    return []


def write_prompt_enrichment_summary(run: PromptEnrichmentRun, ctx: FindingsContext, generated_at: str) -> Path:
    runs_dir = ctx.root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"phase-1-prompt-enrichment-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.md"
    lines = [
        "# Run Summary",
        "",
        f"Date: {generated_at}",
        "Phase: phase-1-prompt-enrichment",
        "Goal: Optional Phase 1 user-prompt enrichment.",
        f"Status: {run.status}",
        f"Return code: {run.returncode if run.returncode is not None else '-'}",
        "",
        "# Prompt",
        "",
        f"Durable prompt copy: `{PROMPT_COPY_REL.as_posix()}`" if run.prompt_copy_path else "Durable prompt copy: not created",
        f"Command: `{' '.join(run.command or [])}`" if run.command else "Command: not executed",
        "",
        "# Files Created Or Modified",
        "",
        "- `runs/phase-1-enrichment-prompt.md`" if run.prompt_copy_path else "- None.",
        "- `itemdb/notes/attack-surface.md`" if run.prompt_copy_path else "",
        "- `itemdb/notes/trust-boundaries.md`" if run.prompt_copy_path else "",
        "- `itemdb/notes/threat-model.md`" if run.prompt_copy_path else "",
        "",
        "# Findings Created",
        "",
        "None. This enrichment step must not create CodeCome findings.",
        "",
        "# Important Assumptions",
        "",
        "- User-prompt output is reconnaissance context only.",
        "- Phase 2 remains responsible for creating `PENDING` findings.",
        "",
    ]
    if run.error:
        lines.extend(["# Error", "", run.error, ""])
    path.write_text("\n".join(line for line in lines if line != "") + "\n", encoding="utf-8")
    return path


def run_prompt_enrichment(
    *,
    ctx: FindingsContext | None = None,
    enrichment_prompt_file: str | None = None,
    execute: bool = True,
    runner=subprocess.run,
) -> PromptEnrichmentRun:
    ctx = ctx or FindingsContext.default()
    generated_at = datetime.now().isoformat(timespec="seconds")
    prompt = load_enrichment_prompt(ctx, enrichment_prompt_file)
    if prompt is None:
        run = PromptEnrichmentRun(status="skipped", error="No enrichment prompt was configured.")
        run.summary_path = write_prompt_enrichment_summary(run, ctx, generated_at)
        return run

    prompt_copy = write_enrichment_prompt_artifacts(
        ctx,
        prompt,
        generated_at=generated_at,
        semgrep_files=semgrep_file_leads(ctx),
    )
    prompt_text = prompt_copy.read_text(encoding="utf-8")
    command = ["opencode", "run", "--agent", "recon"]
    if os.environ.get("CODECOME_THINKING") == "1":
        command.append("--thinking")
    command.append(prompt_text)
    run = PromptEnrichmentRun(status="prepared", prompt_copy_path=prompt_copy, command=command)
    if execute:
        try:
            completed = runner(command, cwd=str(ctx.root), check=False)
        except FileNotFoundError as exc:
            run.status = "failed"
            run.error = str(exc)
        else:
            run.returncode = getattr(completed, "returncode", None)
            run.status = "completed" if run.returncode == 0 else "failed"
    run.summary_path = write_prompt_enrichment_summary(run, ctx, generated_at)
    return run


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run optional Phase 1 user-prompt enrichment with the recon agent.")
    parser.add_argument("--enrichment-prompt-file", help="Optional user prompt file. Defaults to Preview Analysis prompt when present.")
    parser.add_argument("--prepare-only", action="store_true", help="Materialize prompt artifacts without executing opencode.")
    args = parser.parse_args(argv)
    run = run_prompt_enrichment(enrichment_prompt_file=args.enrichment_prompt_file, execute=not args.prepare_only)
    print(f"Prompt enrichment {run.status}")
    if run.prompt_copy_path:
        print(f"Prompt: {run.prompt_copy_path.relative_to(FindingsContext.default().root)}")
    if run.summary_path:
        print(f"Summary: {run.summary_path.relative_to(FindingsContext.default().root)}")
    return 0 if run.status in {"completed", "prepared", "skipped"} else 1
