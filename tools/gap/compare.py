from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import re

import yaml

from findings.constants import FindingsContext
from findings.frontmatter import load_frontmatter


ACTIVE_STATUSES = {"PENDING", "CONFIRMED", "EXPLOITED"}
INACTIVE_STATUSES = {"REJECTED", "DUPLICATE"}


@dataclass
class GapCandidate:
    id: str
    title: str
    category: str = "Unclassified"
    cwe: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    sinks: list[str] = field(default_factory=list)
    trust_boundary: str = ""
    evidence: list[str] = field(default_factory=list)
    impact: str = ""
    validation_idea: str = ""
    matched_notes: list[str] = field(default_factory=list)
    sweep_files: list[str] = field(default_factory=list)
    safety: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FindingRecord:
    id: str
    status: str
    title: str
    path: str
    category: str = ""
    cwe: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    sinks: list[str] = field(default_factory=list)
    trust_boundary: str = ""
    content: str = ""


@dataclass
class ComparisonResult:
    candidate_id: str
    decision: str
    action: str
    match_confidence: str
    matched_findings: list[str] = field(default_factory=list)
    matched_notes: list[str] = field(default_factory=list)
    rationale: str = ""
    sweep_files: list[str] = field(default_factory=list)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value != "" else []


def _tokens(*values: Any) -> set[str]:
    text = " ".join(str(value or "") for value in values)
    return {token for token in re.split(r"[^a-zA-Z0-9_]+", text.lower()) if len(token) >= 4}


def load_candidates(path: Path) -> list[GapCandidate]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    candidates = data.get("candidates") or []
    result = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        result.append(GapCandidate(
            id=str(item.get("id", "")),
            title=str(item.get("title", "")),
            category=str(item.get("category", "Unclassified")),
            cwe=_as_list(item.get("cwe")),
            files=_as_list(item.get("files")),
            symbols=_as_list(item.get("symbols")),
            entry_points=_as_list(item.get("entry_points")),
            sources=_as_list(item.get("sources")),
            sinks=_as_list(item.get("sinks")),
            trust_boundary=str(item.get("trust_boundary", "")),
            evidence=_as_list(item.get("evidence")),
            impact=str(item.get("impact", "")),
            validation_idea=str(item.get("validation_idea", "")),
            matched_notes=_as_list(item.get("matched_notes")),
            sweep_files=_as_list(item.get("sweep_files")),
            safety=item.get("safety") if isinstance(item.get("safety"), dict) else {},
            raw=item,
        ))
    return result


def load_finding_records(ctx: FindingsContext) -> list[FindingRecord]:
    records = []
    for status in ctx.statuses:
        status_dir = ctx.findings_root / status
        if not status_dir.exists():
            continue
        for path in sorted(status_dir.glob("CC-*.md")):
            frontmatter = load_frontmatter(path)
            records.append(FindingRecord(
                id=str(frontmatter.get("id", path.stem.split("-", 2)[0])),
                status=status,
                title=str(frontmatter.get("title", path.stem)),
                path=str(path.relative_to(ctx.root)),
                category=str(frontmatter.get("category", "")),
                cwe=_as_list(frontmatter.get("cwe")),
                files=_as_list(frontmatter.get("files")),
                symbols=_as_list(frontmatter.get("symbols")),
                entry_points=_as_list(frontmatter.get("entry_points")),
                sources=_as_list(frontmatter.get("sources")),
                sinks=_as_list(frontmatter.get("sinks")),
                trust_boundary=str(frontmatter.get("trust_boundary", "")),
                content=path.read_text(encoding="utf-8"),
            ))
    return records


def notes_mentions_candidate(candidate: GapCandidate, notes_root: Path) -> list[str]:
    if candidate.matched_notes:
        return candidate.matched_notes
    if not notes_root.exists():
        return []
    needle_tokens = _tokens(candidate.title, candidate.category, " ".join(candidate.evidence))
    matches = []
    for path in sorted(notes_root.glob("*.md")):
        content = path.read_text(encoding="utf-8", errors="replace")
        if needle_tokens and len(needle_tokens & _tokens(content)) >= min(3, len(needle_tokens)):
            matches.append(str(path.relative_to(notes_root.parent.parent)))
    return matches


def finding_match_score(candidate: GapCandidate, finding: FindingRecord) -> int:
    score = 0
    if set(candidate.files) & set(finding.files):
        score += 4
    if set(candidate.symbols) & set(finding.symbols):
        score += 3
    if set(candidate.cwe) & set(finding.cwe):
        score += 2
    if candidate.category and candidate.category.lower() == finding.category.lower():
        score += 2
    if set(candidate.sources) & set(finding.sources):
        score += 1
    if set(candidate.sinks) & set(finding.sinks):
        score += 1
    if candidate.trust_boundary and candidate.trust_boundary.lower() == finding.trust_boundary.lower():
        score += 1

    candidate_tokens = _tokens(candidate.title, candidate.impact, candidate.validation_idea, " ".join(candidate.evidence))
    finding_tokens = _tokens(finding.title, finding.content)
    overlap = candidate_tokens & finding_tokens
    if len(overlap) >= 5:
        score += 2
    elif len(overlap) >= 3:
        score += 1
    return score


def compare_candidate(candidate: GapCandidate, findings: list[FindingRecord], notes_root: Path) -> ComparisonResult:
    scored = sorted(
        [(finding_match_score(candidate, finding), finding) for finding in findings],
        key=lambda item: item[0],
        reverse=True,
    )
    strong_matches = [(score, finding) for score, finding in scored if score >= 4]
    if strong_matches:
        active = [finding for score, finding in strong_matches if finding.status in ACTIVE_STATUSES]
        inactive = [finding for score, finding in strong_matches if finding.status in INACTIVE_STATUSES]
        matched = [f"{finding.id} ({finding.status})" for score, finding in strong_matches[:5]]
        if active:
            return ComparisonResult(
                candidate_id=candidate.id,
                decision="covered",
                action="none",
                match_confidence="HIGH",
                matched_findings=matched,
                matched_notes=notes_mentions_candidate(candidate, notes_root),
                rationale="Candidate is semantically covered by an active finding.",
                sweep_files=[],
            )
        if inactive:
            return ComparisonResult(
                candidate_id=candidate.id,
                decision="needs_human",
                action="review",
                match_confidence="MEDIUM",
                matched_findings=matched,
                matched_notes=notes_mentions_candidate(candidate, notes_root),
                rationale="Candidate overlaps rejected or duplicate findings and should not be re-opened automatically.",
                sweep_files=[],
            )

    matched_notes = notes_mentions_candidate(candidate, notes_root)
    if matched_notes and candidate.sweep_files:
        return ComparisonResult(
            candidate_id=candidate.id,
            decision="missing_sweep",
            action="sweep",
            match_confidence="NONE",
            matched_notes=matched_notes,
            rationale="Candidate appears in notes but no equivalent finding was found.",
            sweep_files=candidate.sweep_files,
        )
    if candidate.safety.get("source_backed") and candidate.sweep_files:
        return ComparisonResult(
            candidate_id=candidate.id,
            decision="missing_sweep",
            action="sweep",
            match_confidence="NONE",
            matched_notes=matched_notes,
            rationale="Candidate is source-backed and has sweep files, but no equivalent finding was found.",
            sweep_files=candidate.sweep_files,
        )
    return ComparisonResult(
        candidate_id=candidate.id,
        decision="defer_low_signal",
        action="none",
        match_confidence="NONE",
        matched_notes=matched_notes,
        rationale="Candidate lacks enough evidence or sweep planning for automatic action.",
    )


def compare_gap_candidates(ctx: FindingsContext | None = None) -> tuple[list[ComparisonResult], Path]:
    ctx = ctx or FindingsContext.default()
    candidates = load_candidates(ctx.notes_root / "sast-gap-candidates.yml")
    findings = load_finding_records(ctx)
    results = [compare_candidate(candidate, findings, ctx.notes_root) for candidate in candidates]
    summary_path = write_compare_summary(results, ctx)
    return results, summary_path


def write_compare_summary(results: list[ComparisonResult], ctx: FindingsContext) -> Path:
    ctx.root.joinpath("runs").mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = ctx.root / "runs" / f"sast-gap-compare-{timestamp}.md"
    counts: dict[str, int] = {}
    for result in results:
        counts[result.decision] = counts.get(result.decision, 0) + 1

    lines = [
        "# SAST Gap Compare Summary",
        "",
        f"Date: {datetime.now().isoformat(timespec='seconds')}",
        "Candidate file: `itemdb/notes/sast-gap-candidates.yml`",
        "Findings root: `itemdb/findings/`",
        "",
        "# Decision Summary",
        "",
        "| Decision | Count |",
        "|---|---:|",
    ]
    for decision in ["covered", "missing_sweep", "missing_candidate", "duplicate", "rejected_conflict", "needs_human", "defer_low_signal"]:
        lines.append(f"| {decision} | {counts.get(decision, 0)} |")
    lines.extend([
        "",
        "# Candidate Decisions",
        "",
        "| Candidate | Decision | Matched findings | Matched notes | Rationale | Sweep files |",
        "|---|---|---|---|---|---|",
    ])
    for result in results:
        lines.append(
            "| "
            + " | ".join([
                result.candidate_id,
                result.decision,
                ", ".join(result.matched_findings) or "-",
                ", ".join(result.matched_notes) or "-",
                result.rationale.replace("|", "\\|"),
                ", ".join(f"`{item}`" for item in result.sweep_files) or "-",
            ])
            + " |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
