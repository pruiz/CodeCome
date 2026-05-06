#!/usr/bin/env python3
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
import sys
from pathlib import Path

# Allow importing sibling modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _colors import ok, fail, warn, header, info, GREEN, RESET, BOLD, SYM_OK

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_NOTES = [
    "target-profile.md",
    "attack-surface.md",
]

FINDING_STATUS_DIRS = [
    "NEEDS_VALIDATION",
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


def find_finding(finding_id: str) -> Path | None:
    """Locate a finding file by ID."""
    findings_root = ROOT / "itemdb" / "findings"
    for status in FINDING_STATUS_DIRS:
        status_dir = findings_root / status
        if not status_dir.exists():
            continue
        matches = list(status_dir.glob(f"{finding_id}-*.md"))
        if matches:
            return matches[0]
    return None


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
    """Phase 3: at least one NEEDS_VALIDATION finding must exist."""
    print(header("Phase 3: Counter-analysis"))
    print()

    nv_count = count_findings("NEEDS_VALIDATION")
    if nv_count == 0:
        print(fail("No findings in NEEDS_VALIDATION."))
        print()
        print(info("Run Phase 2 first: make phase-2"))
        return 1

    print(ok(f"{nv_count} finding(s) in NEEDS_VALIDATION."))
    print()
    print(f"{GREEN}{SYM_OK}{RESET} Ready to run Phase 3.")
    return 0


def gate_phase_4(finding_id: str) -> int:
    """Phase 4: finding must exist and be in NEEDS_VALIDATION."""
    print(header(f"Phase 4: Validate {finding_id}"))
    print()

    path = find_finding(finding_id)
    if path is None:
        print(fail(f"Finding not found: {finding_id}"))
        print()
        print(info("Check available findings: make status"))
        return 1

    if path.parent.name != "NEEDS_VALIDATION":
        print(warn(f"{finding_id} is in {path.parent.name}, not NEEDS_VALIDATION."))
        print()
        print(info("Only NEEDS_VALIDATION findings can be validated."))
        return 1

    print(ok(f"Found: {path.relative_to(ROOT)}"))
    print()
    print(f"{GREEN}{SYM_OK}{RESET} Ready to validate {finding_id}.")
    return 0


def gate_phase_5(finding_id: str) -> int:
    """Phase 5: finding must be CONFIRMED with evidence."""
    print(header(f"Phase 5: Exploit Development for {finding_id}"))
    print()

    path = find_finding(finding_id)
    if path is None:
        print(fail(f"Finding not found: {finding_id}"))
        print()
        print(info("Check available findings: make status"))
        return 1

    if path.parent.name != "CONFIRMED":
        print(warn(f"{finding_id} is in {path.parent.name}, not CONFIRMED."))
        print()
        print(info("Only CONFIRMED findings can have exploits developed."))
        return 1

    evidence_dir = ROOT / "itemdb" / "evidence" / finding_id
    if not evidence_dir.exists() or not any(evidence_dir.iterdir()):
        print(warn(f"No validation evidence found under itemdb/evidence/{finding_id}/."))
        print()
        print(info("Run Phase 4 first to validate the finding: make phase-4 FINDING=" + finding_id))
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check readiness gates for a CodeCome phase.",
    )
    parser.add_argument("phase", type=int, choices=[1, 2, 3, 4, 5, 6], help="Phase number.")
    parser.add_argument("finding_id", nargs="?", help="Finding ID (required for Phase 4 and 5).")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.phase == 1:
        return gate_phase_1()
    elif args.phase == 2:
        return gate_phase_2()
    elif args.phase == 3:
        return gate_phase_3()
    elif args.phase == 4:
        if not args.finding_id:
            print(fail("Phase 4 requires a finding ID."))
            print()
            print(info("Usage: ./tools/gate-check.py 4 CC-0001"))
            return 1
        return gate_phase_4(args.finding_id)
    elif args.phase == 5:
        if not args.finding_id:
            print(fail("Phase 5 requires a finding ID."))
            print()
            print(info("Usage: ./tools/gate-check.py 5 CC-0001"))
            return 1
        return gate_phase_5(args.finding_id)
    elif args.phase == 6:
        return gate_phase_6()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
