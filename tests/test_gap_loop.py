from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from findings.constants import FindingsContext
from gap.config import GapLimits
from gap.loop import GAP_LOOP_COMMANDS, run_gap_loop


def make_ctx(root: Path) -> FindingsContext:
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


def test_gap_loop_dry_run_records_bounded_steps(tmp_path):
    run = run_gap_loop(ctx=make_ctx(tmp_path), limits=GapLimits(max_scan_rounds=2), dry_run=True)

    assert len(run.steps) == len(GAP_LOOP_COMMANDS) * 2
    assert all(step.skipped for step in run.steps)
    assert run.summary_path and run.summary_path.exists()
    assert "Dry run: yes" in run.summary_path.read_text(encoding="utf-8")


def test_gap_loop_runs_sequence_once_by_default(tmp_path):
    calls = []

    def fake_runner(command, cwd, check):
        calls.append(command)
        class Result:
            returncode = 0
        return Result()

    run = run_gap_loop(ctx=make_ctx(tmp_path), limits=GapLimits(max_scan_rounds=1), runner=fake_runner)

    assert calls == [command for _, command in GAP_LOOP_COMMANDS]
    assert run.exit_code == 0


def test_gap_loop_stops_on_first_failure(tmp_path):
    calls = []

    def fake_runner(command, cwd, check):
        calls.append(command)
        class Result:
            returncode = 1 if command == ["make", "gap-sweep"] else 0
        return Result()

    run = run_gap_loop(ctx=make_ctx(tmp_path), limits=GapLimits(max_scan_rounds=2), runner=fake_runner)

    assert calls == [["make", "gap-scan"], ["make", "gap-compare"], ["make", "gap-sweep"]]
    assert run.exit_code == 1
