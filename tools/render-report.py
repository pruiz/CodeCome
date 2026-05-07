#!/usr/bin/env python3
"""
Render a basic CodeCome Markdown report from findings and notes.

Example:

    ./tools/render-report.py
    ./tools/render-report.py --output itemdb/reports/technical-report.md
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

ROOT = Path(__file__).resolve().parents[1]
FINDINGS_ROOT = ROOT / "itemdb" / "findings"
NOTES_ROOT = ROOT / "itemdb" / "notes"
DEFAULT_OUTPUT = ROOT / "itemdb" / "reports" / "report.md"

STATUSES = [
    "EXPLOITED",
    "CONFIRMED",
    "PENDING",
    "REJECTED",
    "DUPLICATE",
]

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SECTION_RE = re.compile(r"^# (?P<title>.+?)\n(?P<body>.*?)(?=^# |\Z)", re.MULTILINE | re.DOTALL)


def load_frontmatter(path: Path) -> Dict[str, object]:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: pip install -r requirements.txt")

    content = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)

    if not match:
        return {}

    data = yaml.safe_load(match.group(1))
    return data if isinstance(data, dict) else {}


def iter_finding_files(status: str) -> Iterable[Path]:
    status_dir = FINDINGS_ROOT / status
    if not status_dir.exists():
        return []

    return sorted(status_dir.glob("CC-*.md"))


def load_findings() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    for status_dir_name in STATUSES:
        for path in iter_finding_files(status_dir_name):
            frontmatter = load_frontmatter(path)

            validation = frontmatter.get("validation")
            exploitation = frontmatter.get("exploitation")
            evidence_dir = ""
            validation_status = ""
            exploitation_status = ""
            exploitation_impact = ""
            exploitation_type = ""

            if isinstance(validation, dict):
                evidence_dir = str(validation.get("evidence_dir", ""))
                validation_status = str(validation.get("status", ""))

            if isinstance(exploitation, dict):
                exploitation_status = str(exploitation.get("status", ""))
                exploitation_impact = str(exploitation.get("impact_demonstrated", ""))
                exploitation_type = str(exploitation.get("exploit_type", ""))

            sections = extract_sections(path)
            files = frontmatter.get("files")
            affected_files = ", ".join(str(item) for item in files) if isinstance(files, list) else ""

            rows.append(
                {
                    "id": str(frontmatter.get("id", "-".join(path.stem.split("-", 2)[:2]))),
                    "status": str(frontmatter.get("status", path.parent.name)),
                    "severity": str(frontmatter.get("severity", "")),
                    "confidence": str(frontmatter.get("confidence", "")),
                    "category": str(frontmatter.get("category", "")),
                    "language": str(frontmatter.get("language", "")),
                    "target_area": str(frontmatter.get("target_area", "")),
                    "title": str(frontmatter.get("title", path.stem)),
                    "validation_status": validation_status,
                    "exploitation_status": exploitation_status,
                    "exploitation_impact": exploitation_impact,
                    "exploitation_type": exploitation_type,
                    "affected_files": affected_files,
                    "finding_path": str(path.relative_to(ROOT)),
                    "evidence": evidence_dir,
                    "summary": sections.get("Summary", "Pending."),
                    "impact": sections.get("Impact", "Pending."),
                    "validation_result": sections.get("Validation result", "Pending."),
                    "remediation": sections.get("Remediation idea", "Pending."),
                    "exploitation_result": sections.get("Exploitation Result", "Pending."),
                    "demonstrated_impact": sections.get("Demonstrated Impact", "Pending."),
                }
            )

    rows.sort(key=lambda row: (STATUSES.index(row["status"]) if row["status"] in STATUSES else 99, row["id"]))
    return rows


def read_note_excerpt(name: str, max_chars: int = 1200) -> str:
    path = NOTES_ROOT / name

    if not path.exists():
        return "_Not available yet._"

    text = path.read_text(encoding="utf-8").strip()

    if not text:
        return "_Empty._"

    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n\n_Excerpt truncated._"

    return text


def extract_sections(path: Path) -> Dict[str, str]:
    content = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)
    body = content[match.end() :] if match else content
    sections: Dict[str, str] = {}

    for section_match in SECTION_RE.finditer(body):
        title = section_match.group("title").strip()
        section_body = section_match.group("body").strip()
        sections[title] = section_body or "Pending."

    return sections


def table_for(rows: List[Dict[str, str]]) -> List[str]:
    lines = [
        "| ID | Status | Severity | Confidence | Target area | Title | Evidence |",
        "|---|---|---|---|---|---|---|",
    ]

    if not rows:
        lines.append("| - | - | - | - | - | None. | - |")
        return lines

    for row in rows:
        evidence = f"`{row['evidence']}`" if row["evidence"] else "-"
        lines.append(
            f"| {row['id']} "
            f"| {row['status']} "
            f"| {row['severity']} "
            f"| {row['confidence']} "
            f"| {row['target_area']} "
            f"| [{row['title']}]({row['finding_path']}) "
            f"| {evidence} |"
        )

    return lines


def render_detail_block(title: str, rows: List[Dict[str, str]], exploited: bool = False) -> List[str]:
    lines: List[str] = [title, ""]

    if not rows:
        lines.append("None.")
        lines.append("")
        return lines

    for row in rows:
        lines.append(f"## {row['id']} - {row['title']}")
        lines.append("")
        lines.append(f"- Status: {row['status']}")
        lines.append(f"- Severity: {row['severity']}")
        if exploited:
            lines.append(f"- Impact demonstrated: {row['exploitation_impact'] or 'Pending.'}")
            lines.append(f"- Exploit type: {row['exploitation_type'] or 'Pending.'}")
        else:
            lines.append(f"- Confidence: {row['confidence']}")
            lines.append(f"- Validation method: {row['validation_status'] or 'Pending.'}")
        lines.append(f"- Target area: {row['target_area'] or 'unknown'}")
        lines.append(f"- Affected files: {row['affected_files'] or 'Pending.'}")
        lines.append(f"- Evidence: `{row['evidence']}`" if row['evidence'] else "- Evidence: Pending.")
        if exploited:
            exploit_artifacts = f"{row['evidence']}/exploits" if row['evidence'] else ""
            lines.append(f"- Exploitation artifacts: `{exploit_artifacts}`" if exploit_artifacts else "- Exploitation artifacts: Pending.")
        lines.append("")
        lines.append("### Summary")
        lines.append("")
        lines.append(row["summary"])
        lines.append("")
        if exploited:
            lines.append("### Demonstrated Impact")
            lines.append("")
            lines.append(row["demonstrated_impact"])
            lines.append("")
            lines.append("### Exploitation Result")
            lines.append("")
            lines.append(row["exploitation_result"])
        else:
            lines.append("### Impact")
            lines.append("")
            lines.append(row["impact"])
            lines.append("")
            lines.append("### Validation result")
            lines.append("")
            lines.append(row["validation_result"])
        lines.append("")
        lines.append("### Remediation idea")
        lines.append("")
        lines.append(row["remediation"])
        lines.append("")

    return lines


def render_report(rows: List[Dict[str, str]]) -> str:
    exploited = [row for row in rows if row["status"] == "EXPLOITED"]
    confirmed = [row for row in rows if row["status"] == "CONFIRMED"]
    pending = [row for row in rows if row["status"] == "PENDING"]
    rejected = [row for row in rows if row["status"] == "REJECTED"]
    duplicate = [row for row in rows if row["status"] == "DUPLICATE"]

    lines: List[str] = []

    lines.append("# CodeCome Report")
    lines.append("")
    lines.append(f"Generated: {date.today().isoformat()}")
    lines.append("")

    lines.append("# Executive summary")
    lines.append("")
    lines.append(
        f"This report summarizes the current CodeCome workspace state. "
        f"It includes {len(exploited)} exploited finding(s), "
        f"{len(confirmed)} confirmed finding(s), "
        f"{len(pending)} finding(s) needing validation, "
        f"{len(rejected)} rejected finding(s), and "
        f"{len(duplicate)} duplicate finding(s)."
    )
    lines.append("")

    all_proven = exploited + confirmed
    if all_proven:
        severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        highest = min(all_proven, key=lambda r: severity_rank.get(r["severity"], 99))["severity"]
        lines.append(f"Highest proven severity currently listed: **{highest}**.")
    else:
        lines.append("No findings are currently confirmed or exploited.")
    lines.append("")

    lines.append("# Target overview")
    lines.append("")
    lines.append("The following target overview is based on reconnaissance notes, if available.")
    lines.append("")
    lines.append("## Target profile")
    lines.append("")
    lines.append(read_note_excerpt("target-profile.md"))
    lines.append("")
    lines.append("## Attack surface")
    lines.append("")
    lines.append(read_note_excerpt("attack-surface.md"))
    lines.append("")

    lines.append("# Methodology")
    lines.append("")
    lines.append("CodeCome uses a phased workflow:")
    lines.append("")
    lines.append("1. Target reconnaissance.")
    lines.append("2. Vulnerability hypothesis generation.")
    lines.append("3. Counter-analysis and deduplication.")
    lines.append("4. Sandboxed validation.")
    lines.append("5. Exploit development and impact demonstration.")
    lines.append("6. Markdown reporting.")
    lines.append("")
    lines.append("This report is generated from files under `itemdb/`.")
    lines.append("")

    lines.append("# Scope")
    lines.append("")
    lines.append("Default source scope: `src/`.")
    lines.append("")
    lines.append("Refer to `codecome.yml` and `itemdb/notes/` for exact scope and assumptions.")
    lines.append("")

    lines.append("# Findings summary")
    lines.append("")
    lines.extend(table_for(rows))
    lines.append("")

    lines.extend(render_detail_block("# Exploited findings", exploited, exploited=True))
    lines.extend(render_detail_block("# Confirmed findings", confirmed))

    lines.append("# Findings needing validation")
    lines.append("")
    lines.extend(table_for(pending))
    lines.append("")

    lines.append("# Rejected findings")
    lines.append("")
    lines.extend(table_for(rejected))
    lines.append("")

    lines.append("# Duplicate findings")
    lines.append("")
    lines.extend(table_for(duplicate))
    lines.append("")

    lines.append("# Evidence summary")
    lines.append("")
    if exploited or confirmed:
        for row in exploited + confirmed:
            evidence = row["evidence"] or "No evidence directory listed."
            status_label = f" ({row['status']})" if row["status"] == "EXPLOITED" else ""
            lines.append(f"- `{row['id']}`{status_label}: `{evidence}`")
    else:
        lines.append("No confirmed evidence is currently available.")
    lines.append("")

    lines.append("# Limitations")
    lines.append("")
    lines.append("- This report is generated from local Markdown artifacts.")
    lines.append("- Findings may have been generated by AI and should receive human review.")
    lines.append("- Unvalidated findings are hypotheses, not confirmed vulnerabilities.")
    lines.append("- Runtime validation depends on the local sandbox being representative.")
    lines.append("- Production systems are not tested by default.")
    lines.append("")

    lines.append("# Recommended next steps")
    lines.append("")
    if pending:
        lines.append("- Validate remaining findings under `itemdb/findings/PENDING/`.")
    else:
        lines.append("- Run reconnaissance and hypothesis generation to create findings.")
    lines.append("- Review generated findings manually.")
    lines.append("- Improve target-specific sandbox support as needed.")
    lines.append("- Regenerate `itemdb/index.md` and this report after changes.")
    lines.append("")

    lines.append("# Appendix")
    lines.append("")
    lines.append("- Finding index: `itemdb/index.md`")
    lines.append("- Workspace config: `codecome.yml`")
    lines.append("- Agent instructions: `AGENTS.md`")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a CodeCome Markdown report.")

    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT.relative_to(ROOT)),
        help="Output report path.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = load_findings()
    output_path.write_text(render_report(rows), encoding="utf-8")

    print(C.ok(f"Rendered {output_path.relative_to(ROOT)}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
