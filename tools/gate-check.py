#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Check readiness gates for a CodeCome phase.

Usage:

    ./tools/gate-check.py 1           # Check Phase 1 readiness
    ./tools/gate-check.py 2           # Check Phase 2 readiness
    ./tools/gate-check.py 3           # Check Phase 3 readiness
    ./tools/gate-check.py 4 CC-0001   # Check Phase 4 readiness for a specific finding
    ./tools/gate-check.py 5 CC-0001   # Check Phase 5 readiness for a specific finding
    ./tools/gate-check.py 6           # Check Phase 6 readiness

Returns exit code 0 if ready, 1 if not.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

# Allow importing sibling modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _colors import ok, fail, warn, header, info, GREEN, RESET, BOLD, SYM_OK

ROOT = Path(__file__).resolve().parents[1]
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
EVIDENCE_TEMPLATE_MARKERS = [
    "Briefly summarize what this evidence proves or disproves.",
    "Describe the validation method used.",
    "command goes here",
    "Describe what happened.",
]

REQUIRED_NOTES = [
    "target-profile.md",
    "attack-surface.md",
]

REQUIRED_NOTES_1B = [
    "attack-surface.md",
    "execution-model.md",
    "trust-boundaries.md",
    "data-flow.md",
    "validation-model.md",
    "interesting-files.md",
    "file-risk-index.yml",
    "security-assumptions.md",
]

# ---------------------------------------------------------------------------
# Conditional rich support: gate functions accept an optional Console.
# ---------------------------------------------------------------------------
try:
    from rich.console import Console as _RichConsole
    HAVE_RICH = True
except ImportError:  # pragma: no cover
    _RichConsole = None  # type: ignore[assignment]
    HAVE_RICH = False


def _emit(console, level: str, text: str) -> None:
    """Emit a gate message through rich Console or plain print."""
    if console is not None and HAVE_RICH:
        from rich.text import Text
        style_map = {
            "header": "bold cyan",
            "ok": "green",
            "fail": "bold red",
            "warn": "yellow",
            "info": "dim",
        }
        style = style_map.get(level, "")
        console.print(Text(text, style=style))
    else:
        fn_map = {
            "header": header,
            "ok": ok,
            "fail": fail,
            "warn": warn,
            "info": info,
        }
        fn = fn_map.get(level, print)
        fn(text)


def _emit_separator(console, style: str = "green") -> None:
    """Emit a visual separator."""
    if console is not None and HAVE_RICH:
        from rich.rule import Rule
        console.print(Rule(style=style))
    else:
        print()

FINDING_STATUS_DIRS = [
    "PENDING",
    "CONFIRMED",
    "EXPLOITED",
    "REJECTED",
    "DUPLICATE",
]


def has_source_files() -> bool:
    """Return True if src/ contains at least one file (not just .gitkeep)."""
    src_dir = ROOT / "src"
    if not src_dir.exists():
        return False
    for child in src_dir.rglob("*"):
        if child.is_file() and child.name != ".gitkeep":
            return True
    return False


def has_notes(*names: str) -> list[str]:
    """Return list of missing note files."""
    notes_dir = ROOT / "itemdb" / "notes"
    missing = []
    for name in names:
        if not (notes_dir / name).exists():
            missing.append(name)
    return missing


def count_findings(status: str) -> int:
    """Count finding files in a status directory."""
    status_dir = ROOT / "itemdb" / "findings" / status
    if not status_dir.exists():
        return 0
    return len(list(status_dir.glob("CC-*.md")))


def count_all_findings() -> int:
    """Count finding files across all status directories."""
    return sum(count_findings(s) for s in FINDING_STATUS_DIRS)


def load_frontmatter(path: Path) -> dict[str, object]:
    """Load YAML frontmatter from a finding file."""
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: pip install -r requirements.txt")

    content = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)
    if not match:
        return {}

    data = yaml.safe_load(match.group(1))
    return data if isinstance(data, dict) else {}


def find_finding(identifier: str) -> Path | None:
    """Locate a finding file by path or ID."""
    candidate = Path(identifier)
    if candidate.is_absolute() and candidate.exists():
        return candidate.resolve()

    root_relative = ROOT / identifier
    if root_relative.exists():
        return root_relative.resolve()

    findings_root = ROOT / "itemdb" / "findings"
    for status in FINDING_STATUS_DIRS:
        status_dir = findings_root / status
        if not status_dir.exists():
            continue
        # Exact match: CC-0003.md (no slug)
        exact = status_dir / f"{identifier}.md"
        if exact.exists():
            return exact.resolve()
        # Slug match: CC-0003-some-title.md
        matches = list(status_dir.glob(f"{identifier}-*.md"))
        if matches:
            return matches[0].resolve()
    return None


def has_meaningful_evidence(finding_id: str) -> bool:
    """Return True when the evidence directory contains more than scaffolding."""
    evidence_dir = ROOT / "itemdb" / "evidence" / finding_id
    if not evidence_dir.exists():
        return False

    files = [path for path in evidence_dir.rglob("*") if path.is_file()]
    if not files:
        return False

    non_readme_files = [path for path in files if path.name != "README.md"]
    if non_readme_files:
        return True

    readme_path = evidence_dir / "README.md"
    if not readme_path.exists():
        return False

    content = readme_path.read_text(encoding="utf-8")
    return not any(marker in content for marker in EVIDENCE_TEMPLATE_MARKERS)


def gate_phase_1() -> int:
    """Phase 1: src/ must contain target source code."""
    print(header("Phase 1: Target Reconnaissance"))
    print()

    if not has_source_files():
        print(fail("src/ is empty or does not exist."))
        print()
        print(info("Place target source code under src/ before running Phase 1."))
        print(info("See docs/target-setup.md for instructions."))
        return 1

    print(ok("src/ contains source files."))
    print()
    print(f"{GREEN}{SYM_OK}{RESET} Ready to run Phase 1.")
    return 0


def gate_phase_2() -> int:
    """Phase 2: reconnaissance notes must exist."""
    print(header("Phase 2: Vulnerability Hypothesis Generation"))
    print()

    missing = has_notes(*REQUIRED_NOTES)
    if missing:
        print(fail("Required reconnaissance notes are missing:"))
        for name in missing:
            print(f"    {name}")
        print()
        print(info("Run Phase 1 first: make phase-1"))
        return 1

    print(ok("Required reconnaissance notes exist."))
    print()
    print(f"{GREEN}{SYM_OK}{RESET} Ready to run Phase 2.")
    return 0


def gate_phase_3() -> int:
    """Phase 3: at least one PENDING finding must exist."""
    print(header("Phase 3: Counter-analysis"))
    print()

    nv_count = count_findings("PENDING")
    if nv_count == 0:
        print(fail("No findings in PENDING."))
        print()
        print(info("Run Phase 2 first: make phase-2"))
        return 1

    print(ok(f"{nv_count} finding(s) in PENDING."))
    print()
    print(f"{GREEN}{SYM_OK}{RESET} Ready to run Phase 3.")
    return 0


def gate_phase_4(identifier: str) -> int:
    """Phase 4: finding must exist and be in PENDING."""
    print(header(f"Phase 4: Validate {identifier}"))
    print()

    path = find_finding(identifier)
    if path is None:
        print(fail(f"Finding not found: {identifier}"))
        print()
        print(info("Check available findings: make status"))
        return 1

    if path.parent.name != "PENDING":
        print(warn(f"{path.stem} is in {path.parent.name}, not PENDING."))
        print()
        print(info("Only PENDING findings can be validated."))
        return 1

    print(ok(f"Found: {path.relative_to(ROOT)}"))
    print()
    print(f"{GREEN}{SYM_OK}{RESET} Ready to validate {path.stem}.")
    return 0


def gate_phase_5(identifier: str) -> int:
    """Phase 5: finding must be CONFIRMED with evidence."""
    print(header(f"Phase 5: Exploit Development for {identifier}"))
    print()

    path = find_finding(identifier)
    if path is None:
        print(fail(f"Finding not found: {identifier}"))
        print()
        print(info("Check available findings: make status"))
        return 1

    if path.parent.name != "CONFIRMED":
        print(warn(f"{path.stem} is in {path.parent.name}, not CONFIRMED."))
        print()
        print(info("Only CONFIRMED findings can have exploits developed."))
        return 1

    frontmatter = load_frontmatter(path)
    validation = frontmatter.get("validation")
    validation_status = validation.get("status") if isinstance(validation, dict) else None
    if validation_status != "CONFIRMED":
        print(warn(f"{path.stem} has validation.status={validation_status!r}, not 'CONFIRMED'."))
        print()
        print(info("Only findings with confirmed validation evidence can enter Phase 5."))
        return 1

    finding_id = str(frontmatter.get("id", "-".join(path.stem.split("-", 2)[:2])))

    evidence_dir = ROOT / "itemdb" / "evidence" / finding_id
    if not has_meaningful_evidence(finding_id):
        print(warn(f"No meaningful validation evidence found under itemdb/evidence/{finding_id}/."))
        print()
        print(info("Run Phase 4 first and record actual evidence before Phase 5."))
        return 1

    print(ok(f"Found: {path.relative_to(ROOT)}"))
    print(ok(f"Evidence exists: itemdb/evidence/{finding_id}/"))
    print()
    print(f"{GREEN}{SYM_OK}{RESET} Ready to develop exploit for {finding_id}.")
    return 0


def gate_phase_6() -> int:
    """Phase 6: at least one finding must exist."""
    print(header("Phase 6: Reporting"))
    print()

    total = count_all_findings()
    if total == 0:
        print(fail("No findings exist in any status directory."))
        print()
        print(info("Run Phases 1-5 first to produce findings."))
        return 1

    print(ok(f"{total} finding(s) across all status directories."))
    print()
    print(f"{GREEN}{SYM_OK}{RESET} Ready to run Phase 6.")
    return 0


# ---------------------------------------------------------------------------
# Phase 1 subphase gates (1a / 1b / 1c)
# ---------------------------------------------------------------------------

def _notes_exist(*names: str) -> list[str]:
    """Return names of note files that are missing from itemdb/notes/."""
    notes_dir = ROOT / "itemdb" / "notes"
    return [n for n in names if not (notes_dir / n).exists()]


def _count_findings_since(snapshot: dict[str, int] | None = None) -> dict[str, int]:
    """Return {status_dir: count} of CC-*.md files.  If *snapshot* is given,
    return the delta (current - snapshot) instead of absolute counts."""
    findings_root = ROOT / "itemdb" / "findings"
    current: dict[str, int] = {}
    for s in FINDING_STATUS_DIRS:
        sd = findings_root / s
        current[s] = len(list(sd.glob("CC-*.md"))) if sd.exists() else 0
    if snapshot is None:
        return current
    return {s: max(0, current[s] - snapshot.get(s, 0)) for s in FINDING_STATUS_DIRS}


def check_phase_1a(console=None) -> int:
    """Gate 1a: Phase 1a outputs must exist; codeql-plan.yml must be valid."""
    _emit(console, "header", "Gate 1a: Target Profile")
    _emit_separator(console, "cyan")

    notes_dir = ROOT / "itemdb" / "notes"

    required = ["target-profile.md", "build-model.md", "codeql-plan.yml"]
    missing = [n for n in required if not (notes_dir / n).exists()]
    if missing:
        _emit(console, "fail", "Required Phase 1a outputs are missing:")
        for m in missing:
            _emit(console, "info", f"    itemdb/notes/{m}")
        _emit(console, "info", "Run Phase 1a first.")
        return 1

    _emit(console, "ok", "itemdb/notes/target-profile.md exists")
    _emit(console, "ok", "itemdb/notes/build-model.md exists")
    _emit(console, "ok", "itemdb/notes/codeql-plan.yml exists")

    # Validate codeql-plan.yml
    plan_path = notes_dir / "codeql-plan.yml"
    if yaml is None:
        _emit(console, "warn", "Cannot validate codeql-plan.yml: PyYAML not available")
    else:
        try:
            plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        except Exception as exc:
            _emit(console, "fail", f"codeql-plan.yml is not valid YAML: {exc}")
            return 1

        if not isinstance(plan, dict):
            _emit(console, "fail", "codeql-plan.yml is not a mapping")
            return 1

        if plan.get("recommended") is True:
            languages = plan.get("languages", [])
            if not isinstance(languages, list) or len(languages) == 0:
                _emit(console, "fail", "codeql-plan.yml: recommended=true but no language entries")
                return 1

            valid_build_modes = {"none", "manual", "autobuild"}
            valid_confidences = {"HIGH", "MEDIUM", "LOW"}
            for i, lang in enumerate(languages):
                if not isinstance(lang, dict):
                    _emit(console, "fail", f"codeql-plan.yml: language entry {i} is not a mapping")
                    return 1
                if "id" not in lang:
                    _emit(console, "fail", f"codeql-plan.yml: language entry {i} missing 'id'")
                    return 1
                if lang.get("confidence") not in valid_confidences:
                    _emit(console, "warn",
                          f"codeql-plan.yml: language '{lang.get('id', '?')}' "
                          f"has unexpected confidence '{lang.get('confidence')}'")
                if lang.get("build_mode") not in valid_build_modes:
                    _emit(console, "warn",
                          f"codeql-plan.yml: language '{lang.get('id', '?')}' "
                          f"has unexpected build_mode '{lang.get('build_mode')}'")
                if "packs" not in lang:
                    _emit(console, "fail", f"codeql-plan.yml: language '{lang['id']}' missing 'packs'")
                    return 1
                if not isinstance(lang["packs"], list) or len(lang["packs"]) == 0:
                    _emit(console, "fail", f"codeql-plan.yml: language '{lang['id']}' has empty packs list")
                    return 1

            _emit(console, "ok", f"codeql-plan.yml: {len(languages)} language(s) configured")

    _emit_separator(console, "green")
    _emit(console, "ok", "Ready to run Phase 1b (CodeQL-assisted Reconnaissance).")
    return 0


def check_phase_1b(console=None, findings_snapshot: dict[str, int] | None = None) -> int:
    """Gate 1b: all recon notes must exist; file-risk-index.yml must be valid."""
    _emit(console, "header", "Gate 1b: CodeQL-assisted Reconnaissance")
    _emit_separator(console, "cyan")

    missing = _notes_exist(*REQUIRED_NOTES_1B)
    if missing:
        _emit(console, "fail", "Required Phase 1b reconnaissance notes are missing:")
        for m in missing:
            _emit(console, "info", f"    itemdb/notes/{m}")
        _emit(console, "info", "Run Phase 1b first.")
        return 1

    for name in REQUIRED_NOTES_1B:
        _emit(console, "ok", f"itemdb/notes/{name} exists")

    # Validate file-risk-index.yml
    risk_path = ROOT / "itemdb" / "notes" / "file-risk-index.yml"
    if yaml is not None:
        try:
            data = yaml.safe_load(risk_path.read_text(encoding="utf-8"))
        except Exception as exc:
            _emit(console, "fail", f"file-risk-index.yml is not valid YAML: {exc}")
            return 1

        if isinstance(data, dict):
            if "schema_version" not in data:
                _emit(console, "warn", "file-risk-index.yml: missing 'schema_version'")
            files = data.get("files")
            if files is None:
                _emit(console, "fail", "file-risk-index.yml: missing 'files' key")
                return 1
            if not isinstance(files, list):
                _emit(console, "fail", "file-risk-index.yml: 'files' is not a list")
                return 1

            for entry in files:
                if not isinstance(entry, dict):
                    continue
                path_val = entry.get("path", "")
                if "../" in str(path_val) or str(path_val).startswith("/"):
                    _emit(console, "warn",
                          f"file-risk-index.yml: path '{path_val}' is not workspace-relative")
                score = entry.get("score")
                if score is not None:
                    try:
                        s = int(score)
                        if s < 1 or s > 5:
                            _emit(console, "warn",
                                  f"file-risk-index.yml: score {score} for '{path_val}' is not in 1..5")
                    except (TypeError, ValueError):
                        _emit(console, "warn",
                              f"file-risk-index.yml: non-integer score '{score}' for '{path_val}'")

            _emit(console, "ok", f"file-risk-index.yml: {len(files)} file(s) indexed")

    # Check no findings were created during 1b
    if findings_snapshot is not None:
        delta = _count_findings_since(findings_snapshot)
        new_findings = sum(delta.values())
        if new_findings > 0:
            _emit(console, "warn",
                  f"{new_findings} new finding(s) were created during Phase 1b. "
                  "Findings should not be created during reconnaissance.")
            for status, count in delta.items():
                if count > 0:
                    _emit(console, "info", f"    {status}: +{count}")

    _emit_separator(console, "green")
    _emit(console, "ok", "Ready to run Phase 1c (Sandbox Bootstrap).")
    return 0


def check_phase_1c(console=None) -> int:
    """Gate 1c: sandbox-plan.md must exist; sandbox must have provenance."""
    _emit(console, "header", "Gate 1c: Sandbox Bootstrap")
    _emit_separator(console, "cyan")

    plan_path = ROOT / "itemdb" / "notes" / "sandbox-plan.md"
    if not plan_path.exists():
        _emit(console, "fail", "itemdb/notes/sandbox-plan.md does not exist")
        _emit(console, "info", "Run Phase 1c first.")
        return 1

    _emit(console, "ok", "itemdb/notes/sandbox-plan.md exists")

    # Check sandbox provenance
    provenance = ROOT / "sandbox" / "CODECOME-GENERATED.md"
    has_provenance = provenance.exists()

    generated_dir = ROOT / "sandbox"
    has_sandbox = generated_dir.exists() and any(
        f.name != ".gitkeep"
        for f in generated_dir.iterdir()
    )

    if has_provenance:
        _emit(console, "ok", "sandbox/CODECOME-GENERATED.md exists")
    elif has_sandbox:
        _emit(console, "warn",
              "sandbox/ exists without CODECOME-GENERATED.md — may be user-managed")
    else:
        _emit(console, "warn", "sandbox/ is empty or does not exist")

    _emit_separator(console, "green")
    _emit(console, "ok", "Phase 1 complete. Ready to run Phase 2.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check readiness gates for a CodeCome phase.",
    )
    parser.add_argument(
        "phase",
        help="Phase number (1-6) or subphase (1a, 1b, 1c).",
    )
    parser.add_argument("finding_id", nargs="?", help="Finding ID or path (required for Phase 4 and 5).")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    phase_str = str(args.phase)

    if phase_str == "1a":
        return check_phase_1a()
    elif phase_str == "1b":
        return check_phase_1b()
    elif phase_str == "1c":
        return check_phase_1c()

    try:
        phase_int = int(phase_str)
    except ValueError:
        print(fail(f"Invalid phase: {phase_str}"))
        print()
        print(info("Valid values: 1, 2, 3, 4, 5, 6, 1a, 1b, 1c"))
        return 1

    if phase_int == 1:
        return gate_phase_1()
    elif phase_int == 2:
        return gate_phase_2()
    elif phase_int == 3:
        return gate_phase_3()
    elif phase_int == 4:
        if not args.finding_id:
            print(fail("Phase 4 requires a finding ID."))
            print()
            print(info("Usage: ./tools/gate-check.py 4 CC-0001"))
            print(info("   or: ./tools/gate-check.py 4 itemdb/findings/PENDING/CC-0001-test.md"))
            return 1
        return gate_phase_4(args.finding_id)
    elif phase_int == 5:
        if not args.finding_id:
            print(fail("Phase 5 requires a finding ID."))
            print()
            print(info("Usage: ./tools/gate-check.py 5 CC-0001"))
            print(info("   or: ./tools/gate-check.py 5 itemdb/findings/CONFIRMED/CC-0001-test.md"))
            return 1
        return gate_phase_5(args.finding_id)
    elif phase_int == 6:
        return gate_phase_6()

    print(fail(f"Invalid phase: {phase_str}"))
    print()
    print(info("Valid values: 1, 2, 3, 4, 5, 6, 1a, 1b, 1c"))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
