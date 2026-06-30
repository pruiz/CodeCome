from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
import json
import subprocess

import yaml

from findings.constants import FindingsContext


@dataclass(frozen=True)
class SemgrepFinding:
    id: str
    rule_id: str
    path: str
    start_line: int | None
    end_line: int | None
    message: str
    severity: str
    confidence: str = ""
    cwe: list[str] = field(default_factory=list)
    owasp: list[str] = field(default_factory=list)
    category: str = ""
    lines: str = ""


@dataclass
class SemgrepEnrichmentRun:
    status: str
    command: list[str]
    returncode: int | None
    findings: list[SemgrepFinding] = field(default_factory=list)
    error: str = ""
    raw_output_path: Path | None = None
    results_path: Path | None = None
    scan_path: Path | None = None
    interesting_files_path: Path | None = None
    file_risk_index_path: Path | None = None
    summary_path: Path | None = None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value != "" else []


def _metadata_list(metadata: dict[str, Any], *names: str) -> list[str]:
    for name in names:
        values = _as_list(metadata.get(name))
        if values:
            return values
    return []


def normalize_semgrep_results(payload: dict[str, Any]) -> list[SemgrepFinding]:
    findings = []
    for index, item in enumerate(payload.get("results") or [], start=1):
        if not isinstance(item, dict):
            continue
        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        metadata = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
        start = item.get("start") if isinstance(item.get("start"), dict) else {}
        end = item.get("end") if isinstance(item.get("end"), dict) else {}
        findings.append(SemgrepFinding(
            id=f"SG-{index:04d}",
            rule_id=str(item.get("check_id") or "unknown"),
            path=str(item.get("path") or ""),
            start_line=start.get("line") if isinstance(start.get("line"), int) else None,
            end_line=end.get("line") if isinstance(end.get("line"), int) else None,
            message=str(extra.get("message") or ""),
            severity=str(extra.get("severity") or "INFO").upper(),
            confidence=str(metadata.get("confidence") or ""),
            cwe=_metadata_list(metadata, "cwe", "cwe_id"),
            owasp=_metadata_list(metadata, "owasp", "owasp-top-ten"),
            category=str(metadata.get("category") or metadata.get("technology") or ""),
            lines=str(extra.get("lines") or ""),
        ))
    return findings


def _finding_dict(finding: SemgrepFinding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "rule_id": finding.rule_id,
        "path": finding.path,
        "start_line": finding.start_line,
        "end_line": finding.end_line,
        "message": finding.message,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "cwe": finding.cwe,
        "owasp": finding.owasp,
        "category": finding.category,
        "lines": finding.lines,
    }


def _counts_by(items: list[SemgrepFinding], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(getattr(item, attr) or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _risk_score(findings: list[SemgrepFinding]) -> int:
    severity_scores = {"ERROR": 4, "WARNING": 3, "INFO": 2}
    base = max([severity_scores.get(item.severity, 2) for item in findings] or [1])
    if len(findings) >= 5:
        base += 1
    return min(base, 5)


def _write_results(run: SemgrepEnrichmentRun, ctx: FindingsContext) -> None:
    ctx.notes_root.mkdir(parents=True, exist_ok=True)
    runs_dir = ctx.root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat(timespec="seconds")

    results_data = {
        "schema_version": 1,
        "tool": "semgrep",
        "generated_at": generated_at,
        "status": run.status,
        "command": run.command,
        "returncode": run.returncode,
        "error": run.error,
        "summary": {
            "total_results": len(run.findings),
            "by_severity": _counts_by(run.findings, "severity"),
            "by_file": _counts_by(run.findings, "path"),
        },
        "results": [_finding_dict(item) for item in run.findings],
    }

    run.results_path = ctx.notes_root / "semgrep-results.yml"
    run.results_path.write_text(yaml.safe_dump(results_data, sort_keys=False), encoding="utf-8")

    scan_lines = [
        "# Semgrep Phase 1 Enrichment",
        "",
        f"Date: {generated_at}",
        "Target path: `./src`",
        f"Status: `{run.status}`",
        "",
        "# Summary",
        "",
        f"- Total Semgrep results: {len(run.findings)}",
        f"- Return code: {run.returncode if run.returncode is not None else '-'}",
        f"- Command: `{' '.join(run.command)}`",
    ]
    if run.error:
        scan_lines.append(f"- Error: {run.error}")
    scan_lines.extend(["", "# Severity Counts", ""])
    for severity, count in _counts_by(run.findings, "severity").items():
        scan_lines.append(f"- {severity}: {count}")
    scan_lines.extend([
        "",
        "# Interpretation Rules",
        "",
        "Semgrep results are reconnaissance signals only. They are not CodeCome findings and do not confirm vulnerabilities.",
        "Phase 2 must perform source-to-sink reasoning, trust-boundary analysis, counter-analysis planning, and validation planning before creating findings.",
        "",
    ])
    run.scan_path = ctx.notes_root / "semgrep-scan.md"
    run.scan_path.write_text("\n".join(scan_lines), encoding="utf-8")

    by_file: dict[str, list[SemgrepFinding]] = {}
    for finding in run.findings:
        by_file.setdefault(finding.path, []).append(finding)

    interesting_lines = [
        "# Semgrep Interesting Files",
        "",
        f"Date: {generated_at}",
        "",
        "These files are Phase 2 leads, not findings.",
        "",
    ]
    for path, items in sorted(by_file.items(), key=lambda entry: (-_risk_score(entry[1]), entry[0])):
        interesting_lines.extend([
            f"## `{path}`",
            "",
            f"- Risk score hint: {_risk_score(items)}",
            f"- Semgrep results: {len(items)}",
        ])
        for item in items[:5]:
            location = f":{item.start_line}" if item.start_line else ""
            interesting_lines.append(f"- `{item.rule_id}` at `{path}{location}`: {item.message}")
        interesting_lines.append("")
    if not by_file:
        interesting_lines.append("No Semgrep file leads were produced.")
    run.interesting_files_path = ctx.notes_root / "semgrep-interesting-files.md"
    run.interesting_files_path.write_text("\n".join(interesting_lines), encoding="utf-8")

    risk_data = {
        "schema_version": 1,
        "generated_at": generated_at,
        "source": "semgrep",
        "files": [
            {
                "path": path,
                "score": _risk_score(items),
                "reasons": [f"{len(items)} Semgrep result(s) in this file."],
                "external_signals": {
                    "semgrep": [
                        {
                            "id": item.id,
                            "rule_id": item.rule_id,
                            "severity": item.severity,
                            "line": item.start_line,
                            "message": item.message,
                        }
                        for item in items
                    ]
                },
            }
            for path, items in sorted(by_file.items(), key=lambda entry: (-_risk_score(entry[1]), entry[0]))
        ],
    }
    run.file_risk_index_path = ctx.notes_root / "semgrep-file-risk-index.yml"
    run.file_risk_index_path.write_text(yaml.safe_dump(risk_data, sort_keys=False), encoding="utf-8")

    run.summary_path = runs_dir / f"phase-1-semgrep-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.md"
    summary_lines = [
        "# Run Summary",
        "",
        f"Date: {generated_at}",
        "Phase: phase-1-semgrep",
        "Goal: Optional Phase 1 Semgrep enrichment.",
        "",
        "# Files Created Or Modified",
        "",
        "- `itemdb/notes/semgrep-results.yml`",
        "- `itemdb/notes/semgrep-scan.md`",
        "- `itemdb/notes/semgrep-interesting-files.md`",
        "- `itemdb/notes/semgrep-file-risk-index.yml`",
        "",
        "# Findings Created",
        "",
        "None. This enrichment step does not create CodeCome findings by default.",
        "",
        "# Important Assumptions",
        "",
        "- Semgrep results are treated as reconnaissance signals only.",
        "- Phase 2 remains responsible for creating `PENDING` findings.",
        "",
        "# Next Recommended Step",
        "",
        "Run `make phase-2` so the auditor can use the enriched notes during hypothesis generation.",
        "",
    ]
    run.summary_path.write_text("\n".join(summary_lines), encoding="utf-8")


def run_semgrep_enrichment(
    *,
    ctx: FindingsContext | None = None,
    semgrep_config: str = "auto",
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> SemgrepEnrichmentRun:
    ctx = ctx or FindingsContext.default()
    command = ["semgrep", "--json", "--config", semgrep_config, "src"]
    raw_path = ctx.notes_root / "semgrep-raw.json"
    ctx.notes_root.mkdir(parents=True, exist_ok=True)

    try:
        completed = runner(command, cwd=str(ctx.root), capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        run = SemgrepEnrichmentRun(status="skipped", command=command, returncode=None, error=str(exc), raw_output_path=raw_path)
        raw_path.write_text(json.dumps({"error": run.error, "results": []}, indent=2), encoding="utf-8")
        _write_results(run, ctx)
        return run

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    raw_path.write_text(stdout if stdout.strip() else json.dumps({"results": [], "stderr": stderr}, indent=2), encoding="utf-8")
    try:
        payload = json.loads(stdout) if stdout.strip() else {"results": []}
    except json.JSONDecodeError:
        payload = {"results": []}
        status = "failed"
        error = "Semgrep did not return valid JSON."
    else:
        status = "completed" if completed.returncode == 0 else "failed"
        error = stderr.strip() if completed.returncode != 0 else ""

    run = SemgrepEnrichmentRun(
        status=status,
        command=command,
        returncode=completed.returncode,
        findings=normalize_semgrep_results(payload if isinstance(payload, dict) else {"results": []}),
        error=error,
        raw_output_path=raw_path,
    )
    _write_results(run, ctx)
    return run


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run optional Phase 1 Semgrep enrichment.")
    parser.add_argument("--config", default="auto", help="Semgrep config to use (default: auto).")
    args = parser.parse_args(argv)
    run = run_semgrep_enrichment(semgrep_config=args.config)
    print(f"Semgrep enrichment {run.status}: {len(run.findings)} result(s)")
    if run.summary_path:
        print(f"Summary: {run.summary_path.relative_to(FindingsContext.default().root)}")
    return 0
