#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


ROOT = Path.cwd()
NOTES = ROOT / "itemdb" / "notes"
RUNS = ROOT / "runs"


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


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value != "" else []


def metadata_list(metadata: dict[str, Any], *names: str) -> list[str]:
    for name in names:
        values = as_list(metadata.get(name))
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
            cwe=metadata_list(metadata, "cwe", "cwe_id"),
            owasp=metadata_list(metadata, "owasp", "owasp-top-ten"),
            category=str(metadata.get("category") or metadata.get("technology") or ""),
            lines=str(extra.get("lines") or ""),
        ))
    return findings


def finding_dict(finding: SemgrepFinding) -> dict[str, Any]:
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


def counts_by(items: list[SemgrepFinding], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(getattr(item, attr) or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def risk_score(findings: list[SemgrepFinding]) -> int:
    severity_scores = {"ERROR": 4, "WARNING": 3, "INFO": 2}
    base = max([severity_scores.get(item.severity, 2) for item in findings] or [1])
    if len(findings) >= 5:
        base += 1
    return min(base, 5)


def semgrep_signal(item: SemgrepFinding) -> dict[str, Any]:
    return {"id": item.id, "rule_id": item.rule_id, "severity": item.severity, "line": item.start_line, "message": item.message}


def dedupe_semgrep_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for signal in signals:
        key = (str(signal.get("rule_id") or ""), str(signal.get("line") or ""), str(signal.get("message") or ""))
        deduped.setdefault(key, dict(signal))
    return [deduped[key] for key in sorted(deduped.keys())]


def group_by_file(findings: list[SemgrepFinding]) -> dict[str, list[SemgrepFinding]]:
    grouped: dict[str, list[SemgrepFinding]] = {}
    for finding in findings:
        grouped.setdefault(finding.path, []).append(finding)
    return grouped


def replace_markdown_section(path: Path, default_title: str, section_title: str, body_lines: list[str]) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else f"# {default_title}\n"
    marker = f"\n# {section_title}\n"
    base = existing.split(marker, 1)[0].rstrip()
    path.write_text("\n".join([base, "", f"# {section_title}", "", *body_lines]).rstrip() + "\n", encoding="utf-8")


def merge_file_risk_index(by_file: dict[str, list[SemgrepFinding]]) -> None:
    path = NOTES / "file-risk-index.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": 1, "files": []}
    if not isinstance(data, dict):
        data = {"schema_version": 1, "files": []}
    files = data.get("files") if isinstance(data.get("files"), list) else []
    data["files"] = files
    by_path = {entry.get("path"): entry for entry in files if isinstance(entry, dict)}
    for file_path, items in sorted(by_file.items()):
        entry = by_path.get(file_path)
        if entry is None:
            entry = {"path": file_path, "score": risk_score(items), "reasons": []}
            files.append(entry)
        current = int(entry.get("score") or 1) if isinstance(entry.get("score"), int) else 1
        entry["score"] = max(current, risk_score(items))
        reasons = entry.get("reasons") if isinstance(entry.get("reasons"), list) else []
        reason = f"Semgrep reported {len(items)} result(s) in this file."
        if reason not in reasons:
            reasons.append(reason)
        entry["reasons"] = reasons
        external = entry.get("external_signals") if isinstance(entry.get("external_signals"), dict) else {}
        external["semgrep"] = dedupe_semgrep_signals([semgrep_signal(item) for item in items])
        entry["external_signals"] = external
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def semgrep_note_lines(by_file: dict[str, list[SemgrepFinding]], generated_at: str, purpose: str) -> list[str]:
    lines = [
        f"Date: {generated_at}",
        "",
        "Semgrep results are source-backed reconnaissance signals only. They are not confirmed vulnerabilities and are not CodeCome findings.",
        f"Use this section to {purpose}; Phase 2 must still perform source-to-sink and trust-boundary reasoning before creating findings.",
        "",
    ]
    for file_path, items in sorted(by_file.items(), key=lambda entry: (-risk_score(entry[1]), entry[0])):
        lines.extend([f"## `{file_path}`", "", f"- Signal count: {len(items)}", f"- Risk score hint: {risk_score(items)}"])
        for item in items[:5]:
            location = f":{item.start_line}" if item.start_line else ""
            lines.append(f"- `{item.rule_id}` at `{file_path}{location}`: {item.message}")
        lines.append("")
    if not by_file:
        lines.append("No Semgrep-backed leads were produced.")
    return lines


def write_semgrep_outputs(findings: list[SemgrepFinding], command: list[str], returncode: int | None, error: str) -> None:
    NOTES.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat(timespec="seconds")
    by_file = group_by_file(findings)
    (NOTES / "semgrep-results.yml").write_text(yaml.safe_dump({
        "schema_version": 1,
        "tool": "semgrep",
        "generated_at": generated_at,
        "status": "completed" if returncode == 0 else "failed" if returncode is not None else "skipped",
        "command": command,
        "returncode": returncode,
        "error": error,
        "summary": {"total_results": len(findings), "by_severity": counts_by(findings, "severity"), "by_file": counts_by(findings, "path")},
        "results": [finding_dict(item) for item in findings],
    }, sort_keys=False), encoding="utf-8")
    (NOTES / "semgrep-scan.md").write_text("\n".join(["# Semgrep Phase 1 Enrichment", "", f"Date: {generated_at}", "", f"- Total Semgrep results: {len(findings)}", "- Semgrep results are reconnaissance signals only, not findings.", ""]), encoding="utf-8")
    interesting = ["# Semgrep Interesting Files", "", f"Date: {generated_at}", "", "These files are Phase 2 leads, not findings.", ""]
    for file_path, items in sorted(by_file.items(), key=lambda entry: (-risk_score(entry[1]), entry[0])):
        interesting.extend([f"## `{file_path}`", "", f"- Risk score hint: {risk_score(items)}", f"- Semgrep results: {len(items)}", ""])
    (NOTES / "semgrep-interesting-files.md").write_text("\n".join(interesting), encoding="utf-8")
    (NOTES / "semgrep-file-risk-index.yml").write_text(yaml.safe_dump({"schema_version": 1, "generated_at": generated_at, "source": "semgrep", "files": [{"path": p, "score": risk_score(i), "reasons": [f"{len(i)} Semgrep result(s) in this file."], "external_signals": {"semgrep": [semgrep_signal(x) for x in i]}} for p, i in sorted(by_file.items())]}, sort_keys=False), encoding="utf-8")
    merge_file_risk_index(by_file)
    replace_markdown_section(NOTES / "attack-surface.md", "Attack Surface", "Semgrep Enrichment", semgrep_note_lines(by_file, generated_at, "prioritize attack surfaces for follow-up review"))
    replace_markdown_section(NOTES / "trust-boundaries.md", "Trust Boundaries", "Semgrep Enrichment", semgrep_note_lines(by_file, generated_at, "identify lower-trust input paths reaching sensitive code"))
    replace_markdown_section(NOTES / "threat-model.md", "Threat Model", "Semgrep Enrichment", semgrep_note_lines(by_file, generated_at, "calibrate Phase 2 abuse-path themes"))
    (RUNS / f"phase-1-semgrep-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.md").write_text("\n".join(["# Run Summary", "", f"Date: {generated_at}", "Phase: phase-1-semgrep", "Findings created: none", ""]), encoding="utf-8")


def run_semgrep(config: str = "auto") -> int:
    command = ["semgrep", "--json", "--config", config, "src"]
    raw_path = NOTES / "semgrep-raw.json"
    NOTES.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raw_path.write_text(json.dumps({"error": str(exc), "results": []}, indent=2), encoding="utf-8")
        write_semgrep_outputs([], command, None, str(exc))
        return 0
    raw_path.write_text(completed.stdout or json.dumps({"results": [], "stderr": completed.stderr}, indent=2), encoding="utf-8")
    try:
        payload = json.loads(completed.stdout) if completed.stdout.strip() else {"results": []}
    except json.JSONDecodeError:
        payload = {"results": []}
    write_semgrep_outputs(normalize_semgrep_results(payload), command, completed.returncode, completed.stderr.strip() if completed.returncode else "")
    return 0 if completed.returncode in (0, 1) else completed.returncode


def read_prompt_file() -> tuple[str, str] | None:
    prompt_file = os.environ.get("CODECOME_PHASE1_ENRICHMENT_PROMPT_FILE", "").strip()
    if not prompt_file:
        return None
    path = Path(prompt_file)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return None
    return f"env CODECOME_PHASE1_ENRICHMENT_PROMPT_FILE={prompt_file}", path.read_text(encoding="utf-8").strip()


def semgrep_file_leads() -> list[str]:
    path = NOTES / "semgrep-results.yml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    by_file = (data.get("summary") or {}).get("by_file") or {}
    return sorted(str(file) for file in by_file.keys()) if isinstance(by_file, dict) else []


def build_prompt(user_prompt: str, semgrep_files: list[str]) -> str:
    file_lines = "\n".join(f"- `{file}`" for file in semgrep_files[:20]) or "- No Semgrep file leads were available."
    return "\n".join([
        "# Phase 1 User Prompt Enrichment",
        "",
        "You are enriching existing CodeCome Phase 1 reconnaissance artifacts.",
        "",
        "Read existing Phase 1 notes under `itemdb/notes/` and Semgrep artifacts if present.",
        "",
        "## Semgrep File Leads",
        "",
        file_lines,
        "",
        "## User Prompt",
        "",
        user_prompt,
        "",
        "## Rules",
        "",
        "- Update or enrich Phase 1 notes only under `itemdb/notes/`.",
        "- Write `itemdb/notes/user-prompt-enrichment.md` with a human-readable summary.",
        "- Write `itemdb/notes/user-prompt-candidates.yml` with structured candidate leads using IDs like `UPE-0001`; these leads are not findings.",
        "- Do not create files under `itemdb/findings/`.",
        "- Do not run `make findings-create` or `make findings-move`.",
        "- Do not claim anything is confirmed.",
        "",
    ])


def run_prompt() -> int:
    loaded = read_prompt_file()
    RUNS.mkdir(parents=True, exist_ok=True)
    if not loaded:
        (RUNS / f"phase-1-prompt-enrichment-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.md").write_text("# Run Summary\n\nStatus: skipped\nReason: no enrichment prompt configured\n", encoding="utf-8")
        return 0
    source, prompt_text = loaded
    generated_at = datetime.now().isoformat(timespec="seconds")
    prompt = build_prompt(prompt_text, semgrep_file_leads())
    prompt_copy = RUNS / "phase-1-enrichment-prompt.md"
    prompt_copy.write_text(prompt, encoding="utf-8")
    body = [f"Date: {generated_at}", f"Prompt source: {source}", "Durable prompt copy: `runs/phase-1-enrichment-prompt.md`", "", "Prompt-derived context is not a finding. Phase 2 decides whether leads become `PENDING` findings."]
    replace_markdown_section(NOTES / "attack-surface.md", "Attack Surface", "User Prompt Enrichment", body)
    replace_markdown_section(NOTES / "trust-boundaries.md", "Trust Boundaries", "User Prompt Enrichment", body)
    replace_markdown_section(NOTES / "threat-model.md", "Threat Model", "User Prompt Enrichment", body)
    command = ["opencode", "run", "--agent", "recon", prompt]
    if os.environ.get("CODECOME_THINKING") == "1":
        command.insert(3, "--thinking")
    result = subprocess.run(command, cwd=str(ROOT), check=False)
    (RUNS / f"phase-1-prompt-enrichment-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.md").write_text("\n".join(["# Run Summary", "", f"Date: {generated_at}", "Phase: phase-1-prompt-enrichment", f"Status: {'completed' if result.returncode == 0 else 'failed'}", "Findings created: none", ""]), encoding="utf-8")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["semgrep", "prompt"])
    parser.add_argument("--config", default="auto")
    args = parser.parse_args()
    if args.command == "semgrep":
        return run_semgrep(args.config)
    return run_prompt()


if __name__ == "__main__":
    raise SystemExit(main())
