from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
import subprocess

from findings.constants import FindingsContext
from gap.compare import ComparisonResult, compare_gap_candidates, load_finding_records
from gap.config import GapLimits, load_gap_limits


@dataclass(frozen=True)
class GapSweepItem:
    candidate_id: str
    file: str
    reason: str = ""


@dataclass
class GapSweepRun:
    selected: list[GapSweepItem] = field(default_factory=list)
    skipped: list[tuple[GapSweepItem, str]] = field(default_factory=list)
    created_findings: list[str] = field(default_factory=list)
    summary_path: Path | None = None


def previous_sweeps(ctx: FindingsContext) -> set[tuple[str, str]]:
    seen = set()
    runs_dir = ctx.root / "runs"
    if not runs_dir.exists():
        return seen
    for path in runs_dir.glob("sast-gap-sweep-*.md"):
        content = path.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            if not line.startswith("| GAP-"):
                continue
            parts = [part.strip().strip("`") for part in line.strip("|").split("|")]
            if len(parts) >= 2:
                seen.add((parts[0], parts[1]))
    return seen


def sweep_items_from_results(results: list[ComparisonResult], candidate_id: str | None = None) -> list[GapSweepItem]:
    items = []
    for result in results:
        if result.decision != "missing_sweep":
            continue
        if candidate_id and result.candidate_id != candidate_id:
            continue
        for file in result.sweep_files:
            items.append(GapSweepItem(candidate_id=result.candidate_id, file=file, reason=result.rationale))
    return list(dict.fromkeys(items))


def select_sweep_items(
    results: list[ComparisonResult],
    ctx: FindingsContext,
    limits: GapLimits,
    *,
    candidate_id: str | None = None,
    force: bool = False,
) -> tuple[list[GapSweepItem], list[tuple[GapSweepItem, str]]]:
    selected = []
    skipped = []
    seen_prior = previous_sweeps(ctx) if not force else set()
    seen_current = set()

    for item in sweep_items_from_results(results, candidate_id):
        key = (item.candidate_id, item.file)
        if key in seen_prior:
            skipped.append((item, "already swept in a previous gap-sweep summary"))
            continue
        if key in seen_current:
            skipped.append((item, "duplicate in current candidate set"))
            continue
        if len(selected) >= limits.max_sweep_files or len(selected) >= limits.max_sweeps_per_audit:
            skipped.append((item, "gap-sweep limit reached"))
            continue
        selected.append(item)
        seen_current.add(key)
    return selected, skipped


def _finding_ids(records) -> set[str]:
    return {str(record.id) for record in records}


def run_gap_sweep(
    *,
    ctx: FindingsContext | None = None,
    candidate_id: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    runner: Callable = subprocess.run,
    limits: GapLimits | None = None,
) -> GapSweepRun:
    ctx = ctx or FindingsContext.default()
    limits = limits or load_gap_limits()
    results, _ = compare_gap_candidates(ctx)
    selected, skipped = select_sweep_items(results, ctx, limits, candidate_id=candidate_id, force=force)
    before_ids = _finding_ids(load_finding_records(ctx))
    run = GapSweepRun(selected=selected, skipped=skipped)

    for item in selected:
        if dry_run:
            continue
        completed = runner(["make", "sweep", f"FILE={item.file}"], cwd=str(ctx.root), check=False)
        if getattr(completed, "returncode", 0) != 0:
            skipped.append((item, f"sweep command exited {getattr(completed, 'returncode', 'unknown')}"))

    after_ids = _finding_ids(load_finding_records(ctx))
    run.created_findings = sorted(after_ids - before_ids)
    run.summary_path = write_sweep_summary(run, ctx, dry_run=dry_run, limits=limits)
    return run


def write_sweep_summary(run: GapSweepRun, ctx: FindingsContext, *, dry_run: bool, limits: GapLimits) -> Path:
    runs_dir = ctx.root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = runs_dir / f"sast-gap-sweep-{timestamp}.md"
    lines = [
        "# SAST Gap Sweep Summary",
        "",
        f"Date: {datetime.now().isoformat(timespec='seconds')}",
        "Candidate source: `itemdb/notes/sast-gap-candidates.yml`",
        f"Dry run: {'yes' if dry_run else 'no'}",
        "",
        "# Sweep Bounds",
        "",
        f"- Maximum sweep files: {limits.max_sweep_files}",
        f"- Maximum sweeps per audit: {limits.max_sweeps_per_audit}",
        "",
        "# Files Swept",
        "",
        "| Candidate | File | Command | Result |",
        "|---|---|---|---|",
    ]
    if run.selected:
        for item in run.selected:
            result = "dry-run" if dry_run else "executed"
            lines.append(f"| {item.candidate_id} | `{item.file}` | `make sweep FILE={item.file}` | {result} |")
    else:
        lines.append("| - | - | - | None. |")
    lines.extend(["", "# Findings Created", "", "| Finding ID |", "|---|"])
    if run.created_findings:
        for finding_id in run.created_findings:
            lines.append(f"| {finding_id} |")
    else:
        lines.append("| None. |")
    lines.extend(["", "# Candidates Deferred", "", "| Candidate | File | Reason |", "|---|---|---|"])
    if run.skipped:
        for item, reason in run.skipped:
            lines.append(f"| {item.candidate_id} | `{item.file}` | {reason} |")
    else:
        lines.append("| - | - | None. |")
    lines.extend(["", "# Notes", "", "Normal Phase 3/4/5 must handle counter-analysis, validation, and exploitation for any new findings.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
