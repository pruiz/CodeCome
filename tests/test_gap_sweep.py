from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from findings.constants import FindingsContext
from gap.config import GapLimits
from gap.sweep import previous_sweeps, run_gap_sweep, select_sweep_items, sweep_items_from_results
from gap.compare import ComparisonResult


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


def write_candidates(root: Path):
    notes = root / "itemdb" / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "sast-gap-candidates.yml").write_text("""
candidates:
  - id: GAP-0001
    title: Stack trace disclosure
    category: Information Disclosure
    matched_notes: [itemdb/notes/attack-surface.md:66]
    files: [src/A.java]
    sweep_files: [src/A.java, src/B.java]
    safety: {source_backed: true}
  - id: GAP-0002
    title: Covered issue
    category: Access Control
    files: [src/C.java]
    safety: {source_backed: true}
""", encoding="utf-8")


def write_finding(root: Path, status: str, finding_id: str, *, title: str, category: str, files: list[str], cwe: list[str] | None = None):
    directory = root / "itemdb" / "findings" / status
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{finding_id}-demo.md"
    path.write_text(
        "---\n"
        f"id: \"{finding_id}\"\n"
        f"title: \"{title}\"\n"
        f"status: \"{status}\"\n"
        f"category: \"{category}\"\n"
        f"cwe: {cwe or []}\n"
        f"files: {files}\n"
        "symbols: []\n"
        "sources: []\n"
        "sinks: []\n"
        "trust_boundary: \"remote user -> server response\"\n"
        "---\n"
        f"# Summary\n\n{title}\n",
        encoding="utf-8",
    )
    return path


def test_sweep_items_only_use_missing_sweep_results():
    results = [
        ComparisonResult(candidate_id="GAP-0001", decision="missing_sweep", action="sweep", match_confidence="NONE", sweep_files=["src/A.java"]),
        ComparisonResult(candidate_id="GAP-0002", decision="covered", action="none", match_confidence="HIGH", sweep_files=["src/B.java"]),
    ]

    assert sweep_items_from_results(results) == [type(sweep_items_from_results(results)[0])("GAP-0001", "src/A.java", "")]


def test_select_sweep_items_respects_limits(tmp_path):
    ctx = make_ctx(tmp_path)
    results = [ComparisonResult(candidate_id="GAP-0001", decision="missing_sweep", action="sweep", match_confidence="NONE", sweep_files=["src/A.java", "src/B.java"])]

    selected, skipped = select_sweep_items(results, ctx, GapLimits(max_sweep_files=1, max_sweeps_per_audit=5))

    assert [item.file for item in selected] == ["src/A.java"]
    assert skipped[0][0].file == "src/B.java"
    assert "limit" in skipped[0][1]


def test_previous_sweeps_prevents_duplicates(tmp_path):
    ctx = make_ctx(tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "sast-gap-sweep-2026-01-01-000000.md").write_text("| GAP-0001 | `src/A.java` | `make sweep FILE=src/A.java` | executed |\n")
    results = [ComparisonResult(candidate_id="GAP-0001", decision="missing_sweep", action="sweep", match_confidence="NONE", sweep_files=["src/A.java"])]

    selected, skipped = select_sweep_items(results, ctx, GapLimits(), force=False)

    assert previous_sweeps(ctx) == {("GAP-0001", "src/A.java")}
    assert selected == []
    assert skipped[0][1].startswith("already swept")


def test_run_gap_sweep_invokes_existing_make_sweep(tmp_path):
    ctx = make_ctx(tmp_path)
    write_candidates(tmp_path)
    calls = []

    def fake_runner(command, cwd, check):
        calls.append((command, cwd, check))
        class Result:
            returncode = 0
        return Result()

    run = run_gap_sweep(ctx=ctx, runner=fake_runner, limits=GapLimits(max_sweep_files=1, max_sweeps_per_audit=1))

    assert calls == [(["make", "sweep", "FILE=src/A.java"], str(tmp_path), False)]
    assert run.summary_path and run.summary_path.exists()
    assert "GAP-0001" in run.summary_path.read_text(encoding="utf-8")


def test_run_gap_sweep_can_select_one_candidate(tmp_path):
    ctx = make_ctx(tmp_path)
    write_candidates(tmp_path)

    run = run_gap_sweep(ctx=ctx, candidate_id="GAP-0001", dry_run=True, limits=GapLimits(max_sweep_files=5, max_sweeps_per_audit=5))

    assert [item.file for item in run.selected] == ["src/A.java", "src/B.java"]


def test_run_gap_sweep_does_not_resweep_covered_candidate(tmp_path):
    ctx = make_ctx(tmp_path)
    write_finding(
        tmp_path,
        "PENDING",
        "CC-0007",
        title="Stack trace disclosure",
        category="Information Disclosure",
        files=["src/A.java"],
    )
    write_candidates(tmp_path)
    calls = []

    def fake_runner(command, cwd, check):
        calls.append((command, cwd, check))
        class Result:
            returncode = 0
        return Result()

    run = run_gap_sweep(ctx=ctx, runner=fake_runner, limits=GapLimits(max_sweep_files=5, max_sweeps_per_audit=5))

    assert calls == []
    assert run.selected == []
    assert run.summary_path and run.summary_path.exists()
    assert "None." in run.summary_path.read_text(encoding="utf-8")
