from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
import subprocess

from findings.constants import FindingsContext
from gap.config import GapLimits, load_gap_limits


GAP_LOOP_COMMANDS = [
    ("gap-scan", ["make", "gap-scan"]),
    ("gap-compare", ["make", "gap-compare"]),
    ("gap-sweep", ["make", "gap-sweep"]),
    ("phase-3", ["make", "phase-3"]),
    ("validate-all", ["make", "validate-all"]),
    ("exploit-all", ["make", "exploit-all"]),
]


@dataclass
class GapLoopStep:
    round_number: int
    name: str
    command: list[str]
    exit_code: int | None = None
    skipped: bool = False


@dataclass
class GapLoopRun:
    dry_run: bool
    max_rounds: int
    steps: list[GapLoopStep] = field(default_factory=list)
    summary_path: Path | None = None

    @property
    def exit_code(self) -> int:
        for step in self.steps:
            if step.exit_code not in (None, 0):
                return int(step.exit_code)
        return 0


def run_gap_loop(
    *,
    ctx: FindingsContext | None = None,
    limits: GapLimits | None = None,
    dry_run: bool = False,
    runner: Callable = subprocess.run,
) -> GapLoopRun:
    ctx = ctx or FindingsContext.default()
    limits = limits or load_gap_limits()
    run = GapLoopRun(dry_run=dry_run, max_rounds=limits.max_scan_rounds)

    should_stop = False
    for round_number in range(1, limits.max_scan_rounds + 1):
        for name, command in GAP_LOOP_COMMANDS:
            step = GapLoopStep(round_number=round_number, name=name, command=list(command))
            run.steps.append(step)
            if dry_run:
                step.skipped = True
                continue
            result = runner(command, cwd=str(ctx.root), check=False)
            step.exit_code = int(getattr(result, "returncode", 1))
            if step.exit_code != 0:
                should_stop = True
                break
        if should_stop:
            break

    run.summary_path = write_loop_summary(run, ctx)
    return run


def write_loop_summary(run: GapLoopRun, ctx: FindingsContext) -> Path:
    runs_dir = ctx.root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = runs_dir / f"sast-gap-loop-{timestamp}.md"

    lines = [
        "# SAST Gap Loop Summary",
        "",
        f"Date: {datetime.now().isoformat(timespec='seconds')}",
        f"Dry run: {'yes' if run.dry_run else 'no'}",
        f"Configured max rounds: {run.max_rounds}",
        f"Exit code: {run.exit_code}",
        "",
        "# Steps",
        "",
        "| Round | Step | Command | Exit code |",
        "|---:|---|---|---:|",
    ]
    for step in run.steps:
        command_text = " ".join(step.command)
        exit_text = "skipped" if step.skipped else ("-" if step.exit_code is None else str(step.exit_code))
        lines.append(f"| {step.round_number} | {step.name} | `{command_text}` | {exit_text} |")

    lines.extend([
        "",
        "# Notes",
        "",
        "This loop is manual-only. It does not run automatically before reporting unless explicitly invoked.",
        "Normal CodeCome finding lifecycle is preserved: gap sweeps may create PENDING findings, then Phase 3/4/5 process them.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
