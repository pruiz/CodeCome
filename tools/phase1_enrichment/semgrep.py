from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
import json
import subprocess

import yaml

from findings.constants import FindingsContext
from phase1_enrichment.prompt import load_enrichment_prompt, write_enrichment_prompt_artifacts


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
    prompt_copy_path: Path | None = None


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


def _semgrep_signal(item: SemgrepFinding) -> dict[str, Any]:
    return {
        "id": item.id,
        "rule_id": item.rule_id,
        "severity": item.severity,
        "line": item.start_line,
        "message": item.message,
    }


def _group_by_file(findings: list[SemgrepFinding]) -> dict[str, list[SemgrepFinding]]:
    by_file: dict[str, list[SemgrepFinding]] = {}
    for finding in findings:
        by_file.setdefault(finding.path, []).append(finding)
    return by_file


def _merge_file_risk_index(ctx: FindingsContext, by_file: dict[str, list[SemgrepFinding]]) -> None:
    path = ctx.notes_root / "file-risk-index.yml"
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            data = {}
    else:
        data = {"schema_version": 1, "files": []}

    files = data.get("files")
    if not isinstance(files, list):
        files = []
        data["files"] = files

    by_path = {entry.get("path"): entry for entry in files if isinstance(entry, dict)}
    for file_path, items in sorted(by_file.items()):
        entry = by_path.get(file_path)
        if entry is None:
            entry = {"path": file_path, "score": _risk_score(items), "reasons": []}
            files.append(entry)
            by_path[file_path] = entry

        try:
            current_score = int(entry.get("score") or 1)
        except (TypeError, ValueError):
            current_score = 1
        entry["score"] = max(current_score, _risk_score(items))

        reasons = entry.get("reasons")
        if not isinstance(reasons, list):
            reasons = []
            entry["reasons"] = reasons
        reason = f"Semgrep reported {len(items)} result(s) in this file."
        if reason not in reasons:
            reasons.append(reason)

        external = entry.get("external_signals")
        if not isinstance(external, dict):
            external = {}
            entry["external_signals"] = external
        external["semgrep"] = [_semgrep_signal(item) for item in items]

    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _merge_interesting_files(ctx: FindingsContext, by_file: dict[str, list[SemgrepFinding]], generated_at: str) -> None:
    path = ctx.notes_root / "interesting-files.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Interesting Files\n"
    marker = "\n# Semgrep Enrichment\n"
    base = existing.split(marker, 1)[0].rstrip()
    lines = [base, "", "# Semgrep Enrichment", "", f"Date: {generated_at}", "", "These are reconnaissance signals only, not findings.", ""]
    if by_file:
        for file_path, items in sorted(by_file.items(), key=lambda entry: (-_risk_score(entry[1]), entry[0])):
            lines.extend([
                f"## `{file_path}`",
                "",
                f"- Risk score hint: {_risk_score(items)}",
                f"- Semgrep results: {len(items)}",
            ])
            for item in items[:5]:
                location = f":{item.start_line}" if item.start_line else ""
                lines.append(f"- `{item.rule_id}` at `{file_path}{location}`: {item.message}")
            lines.append("")
    else:
        lines.append("No Semgrep file leads were produced.")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _replace_markdown_section(path: Path, default_title: str, section_title: str, body_lines: list[str]) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else f"# {default_title}\n"
    marker = f"\n# {section_title}\n"
    base = existing.split(marker, 1)[0].rstrip()
    content = "\n".join([base, "", f"# {section_title}", "", *body_lines]).rstrip() + "\n"
    path.write_text(content, encoding="utf-8")


def _semgrep_note_lines(by_file: dict[str, list[SemgrepFinding]], generated_at: str, purpose: str) -> list[str]:
    lines = [
        f"Date: {generated_at}",
        "",
        "Semgrep results are source-backed reconnaissance signals only. They are not confirmed vulnerabilities and are not CodeCome findings.",
        f"Use this section to {purpose}; Phase 2 must still perform source-to-sink and trust-boundary reasoning before creating findings.",
        "",
    ]
    if not by_file:
        lines.append("No Semgrep-backed leads were produced.")
        return lines

    for file_path, items in sorted(by_file.items(), key=lambda entry: (-_risk_score(entry[1]), entry[0])):
        lines.extend([
            f"## `{file_path}`",
            "",
            f"- Signal count: {len(items)}",
            f"- Risk score hint: {_risk_score(items)}",
        ])
        cwes = sorted({cwe for item in items for cwe in item.cwe})
        if cwes:
            lines.append(f"- CWE hints: {', '.join(cwes)}")
        for item in items[:5]:
            location = f":{item.start_line}" if item.start_line else ""
            lines.append(f"- `{item.rule_id}` at `{file_path}{location}`: {item.message}")
        lines.append("")
    return lines


def _merge_recon_notes(ctx: FindingsContext, by_file: dict[str, list[SemgrepFinding]], generated_at: str) -> None:
    _replace_markdown_section(
        ctx.notes_root / "attack-surface.md",
        "Attack Surface",
        "Semgrep Enrichment",
        _semgrep_note_lines(by_file, generated_at, "prioritize attack surfaces for follow-up review"),
    )
    _replace_markdown_section(
        ctx.notes_root / "trust-boundaries.md",
        "Trust Boundaries",
        "Semgrep Enrichment",
        _semgrep_note_lines(by_file, generated_at, "identify potential lower-trust input paths reaching sensitive code"),
    )
    _replace_markdown_section(
        ctx.notes_root / "threat-model.md",
        "Threat Model",
        "Semgrep Enrichment",
        _semgrep_note_lines(by_file, generated_at, "calibrate Phase 2 abuse-path themes from static-analysis signals"),
    )


def _write_results(run: SemgrepEnrichmentRun, ctx: FindingsContext, *, enrichment_prompt_file: str | None = None) -> None:
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

    by_file = _group_by_file(run.findings)

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
                            **_semgrep_signal(item),
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

    _merge_file_risk_index(ctx, by_file)
    _merge_interesting_files(ctx, by_file, generated_at)
    _merge_recon_notes(ctx, by_file, generated_at)

    enrichment_prompt = load_enrichment_prompt(ctx, enrichment_prompt_file)
    if enrichment_prompt:
        run.prompt_copy_path = write_enrichment_prompt_artifacts(
            ctx,
            enrichment_prompt,
            generated_at=generated_at,
            semgrep_files=by_file.keys(),
        )

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
        "- `itemdb/notes/file-risk-index.yml`",
        "- `itemdb/notes/interesting-files.md`",
        "- `itemdb/notes/attack-surface.md`",
        "- `itemdb/notes/trust-boundaries.md`",
        "- `itemdb/notes/threat-model.md`",
        *(["- `runs/phase-1-enrichment-prompt.md`"] if run.prompt_copy_path else []),
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
    enrichment_prompt_file: str | None = None,
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
        _write_results(run, ctx, enrichment_prompt_file=enrichment_prompt_file)
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
    _write_results(run, ctx, enrichment_prompt_file=enrichment_prompt_file)
    return run


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run optional Phase 1 Semgrep enrichment.")
    parser.add_argument("--config", default="auto", help="Semgrep config to use (default: auto).")
    parser.add_argument("--enrichment-prompt-file", help="Optional user prompt file for Phase 1 note enrichment.")
    args = parser.parse_args(argv)
    run = run_semgrep_enrichment(semgrep_config=args.config, enrichment_prompt_file=args.enrichment_prompt_file)
    print(f"Semgrep enrichment {run.status}: {len(run.findings)} result(s)")
    if run.summary_path:
        print(f"Summary: {run.summary_path.relative_to(FindingsContext.default().root)}")
    return 0
