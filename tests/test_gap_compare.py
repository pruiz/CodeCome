from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from findings.constants import FindingsContext
from gap.compare import compare_gap_candidates, load_candidates, load_finding_records


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


def write_candidates(root: Path, candidates: str):
    notes = root / "itemdb" / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    path = notes / "sast-gap-candidates.yml"
    path.write_text(candidates, encoding="utf-8")
    return path


def test_load_candidates_and_findings(tmp_path):
    ctx = make_ctx(tmp_path)
    write_finding(tmp_path, "PENDING", "CC-0001", title="Exception disclosure", category="Information Disclosure", files=["src/App.java"], cwe=["CWE-209"])
    candidate_path = write_candidates(tmp_path, """
candidates:
  - id: GAP-0001
    title: Exception disclosure
    category: Information Disclosure
    cwe: [CWE-209]
    files: [src/App.java]
    sweep_files: [src/App.java]
    safety: {source_backed: true}
""")

    assert load_candidates(candidate_path)[0].id == "GAP-0001"
    assert load_finding_records(ctx)[0].id == "CC-0001"


def test_gap_compare_marks_active_finding_as_covered(tmp_path):
    ctx = make_ctx(tmp_path)
    write_finding(tmp_path, "CONFIRMED", "CC-0002", title="Exception disclosure", category="Information Disclosure", files=["src/App.java"], cwe=["CWE-209"])
    write_candidates(tmp_path, """
candidates:
  - id: GAP-0001
    title: Exception disclosure leaks internals
    category: Information Disclosure
    cwe: [CWE-209]
    files: [src/App.java]
    evidence: ['return "Error: " + e.getMessage();']
    sweep_files: [src/App.java]
    safety: {source_backed: true}
""")

    results, summary = compare_gap_candidates(ctx)

    assert results[0].decision == "covered"
    assert results[0].matched_findings == ["CC-0002 (CONFIRMED)"]
    assert summary.exists()


def test_gap_compare_marks_notes_only_candidate_as_missing_sweep(tmp_path):
    ctx = make_ctx(tmp_path)
    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "attack-surface.md").write_text("Error handling leaks stack traces and exception messages to HTTP response body", encoding="utf-8")
    write_candidates(tmp_path, """
candidates:
  - id: GAP-0003
    title: Stack trace disclosure in HTTP responses
    category: Information Disclosure
    files: [src/EmployeeController.java]
    matched_notes: [itemdb/notes/attack-surface.md:66]
    sweep_files: [src/EmployeeController.java]
    safety: {source_backed: true}
""")

    results, summary = compare_gap_candidates(ctx)

    assert results[0].decision == "missing_sweep"
    assert results[0].sweep_files == ["src/EmployeeController.java"]
    assert "GAP-0003" in summary.read_text(encoding="utf-8")


def test_gap_compare_discovers_phase_1_note_only_stack_trace_gap(tmp_path):
    ctx = make_ctx(tmp_path)
    notes = tmp_path / "itemdb" / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "attack-surface.md").write_text(
        "# Attack Surface\n\n"
        "Error handling leaks stack traces and exception messages to HTTP response body. "
        "Employee import and report flows return exception class names to remote users.",
        encoding="utf-8",
    )
    (tmp_path / "itemdb" / "findings" / "PENDING").mkdir(parents=True, exist_ok=True)
    write_candidates(tmp_path, """
candidates:
  - id: GAP-0005
    title: Stack trace exception message disclosure in HTTP responses
    category: Information Disclosure
    cwe: [CWE-209]
    files: [src/EmployeeController.java]
    evidence:
      - 'return "Error: " + e.getClass().getName() + ": " + e.getMessage();'
    sweep_files: [src/EmployeeController.java]
    safety: {source_backed: true, not_generic_guess: true}
""")

    results, summary = compare_gap_candidates(ctx)

    assert results[0].candidate_id == "GAP-0005"
    assert results[0].decision == "missing_sweep"
    assert results[0].action == "sweep"
    assert results[0].matched_findings == []
    assert results[0].matched_notes == ["itemdb/notes/attack-surface.md"]
    summary_text = summary.read_text(encoding="utf-8")
    assert "GAP-0005" in summary_text
    assert "missing_sweep" in summary_text


def test_gap_compare_does_not_reopen_rejected_findings(tmp_path):
    ctx = make_ctx(tmp_path)
    write_finding(tmp_path, "REJECTED", "CC-0004", title="Exception disclosure", category="Information Disclosure", files=["src/App.java"], cwe=["CWE-209"])
    write_candidates(tmp_path, """
candidates:
  - id: GAP-0004
    title: Exception disclosure
    category: Information Disclosure
    cwe: [CWE-209]
    files: [src/App.java]
    sweep_files: [src/App.java]
    safety: {source_backed: true}
""")

    results, _ = compare_gap_candidates(ctx)

    assert results[0].decision == "needs_human"
    assert results[0].action == "review"
