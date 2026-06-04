# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Phase artifact validation (post-generation quality checks).

This module is the single source of truth for per-phase artifact validation.
It is consumed by:
- ``tools/codecome.py check-phase-artifacts`` (thin CLI wrapper),
- phase gates (via ``check_phase_1a`` / ``check_phase_1b`` etc.),
- ``make tests --allow-missing-generated-artifacts``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import _colors as C

from codecome.config import ROOT


# -- Heading sets ---------------------------------------------------------------

REQUIRED_THREAT_MODEL_HEADINGS = [
    "# Threat Model Summary",
    "# Scope",
    "# System model",
    "# Assets and security objectives",
    "# Attacker model",
    "# Trust boundary summary",
    "# Existing controls",
    "# Abuse-path themes for Phase 2",
    "# Risk calibration for review focus",
    "# Open questions for the user",
    "# Re-run prompt hints",
]

REQUIRED_SUMMARY_HEADINGS = [
    "# Open questions for the user",
    "# Re-run prompt hints",
]

VALID_PHASES = frozenset({"1a", "1b", "1c", "1", "2", "3", "4", "5", "6", "all"})


# -- Heading helpers ------------------------------------------------------------

# Equivalent strict H1 regex: starts with "# " and is NOT followed by whitespace
_STRICT_H1_RE = re.compile(r"^# [^\s]", re.MULTILINE)


def _h1_headings_from_text(content: str) -> set[str]:
    """Return set of strict H1 headings found in markdown text.

    Matches only ``# Heading`` — exactly one space after ``#``,
    and the character after the space must not be whitespace.
    Does **not** match ``#NoSpace``, ``#  DoubleSpace``, ``# `` (trailing space), or ``## H2``.
    """
    headings: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        # Must match "# [^\s]" — hash, exactly one space, then non-whitespace.
        # Also reject "## " (H2).
        if _STRICT_H1_RE.match(stripped) and not stripped.startswith("## "):
            headings.add(stripped)
    return headings


def _h1_headings(path: Path) -> set[str]:
    """Return set of strict H1 headings found in a file."""
    if not path.is_file():
        return set()
    return _h1_headings_from_text(path.read_text(encoding="utf-8"))


def _missing_headings(path: Path, required: list[str]) -> list[str]:
    """Return list of required headings missing from *path*."""
    present = _h1_headings(path)
    return [h for h in required if h not in present]


# -- Artifact helpers -----------------------------------------------------------


def _artifact_ok(
    path: Path,
    *,
    allow_missing_generated: bool = False,
    generated: bool = True,
) -> Optional[str]:
    """Return error message if *path* is missing, or None if OK.

    *generated* marks artifacts that only exist after a phase run.
    When *allow_missing_generated* is True and *generated* is True,
    missing files are tolerated.
    """
    if path.is_file():
        return None
    if allow_missing_generated and generated:
        return None
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        rel = path
    return f"Missing artifact: {rel}"


# -- Phase 1a ------------------------------------------------------------------


def check_phase_1a_artifacts(
    allow_missing_generated: bool = False,
    phase_1a_start_time: Optional[float] = None,
) -> list[str]:
    """Validate Phase 1a artifacts.

    Parameters
    ----------
    allow_missing_generated:
        If True, skip errors for missing phase-generated files.
    phase_1a_start_time:
        Optional Unix timestamp. When provided, negative checks use
        ``mtime >= phase_1a_start_time`` to detect Phase 1a leakage.
        When None, negative checks are skipped (caller did not provide a snapshot).
    """
    errors: list[str] = []
    notes = ROOT / "itemdb" / "notes"
    runs = ROOT / "runs"

    # -- Required files --
    for name in ("target-profile.md", "build-model.md", "codeql-plan.yml"):
        err = _artifact_ok(notes / name, allow_missing_generated=allow_missing_generated)
        if err:
            errors.append(err)

    # -- Run summary --
    summary_path = runs / "phase-1a-summary.md"
    err = _artifact_ok(summary_path, allow_missing_generated=allow_missing_generated)
    if err:
        errors.append(err)
    elif summary_path.is_file():
        missing = _missing_headings(summary_path, REQUIRED_SUMMARY_HEADINGS)
        if missing:
            rel = summary_path.relative_to(ROOT)
            errors.append(f"{rel} missing headings: {', '.join(missing)}")

    # -- Negative checks (leak detection) --
    _check_phase_1a_no_leak(notes, errors, phase_1a_start_time)

    return errors


def _check_phase_1a_no_leak(
    notes: Path,
    errors: list[str],
    cutoff: Optional[float],
) -> None:
    """Verify Phase 1a did not create files owned by Phase 1b/1c."""
    for name in ("threat-model.md", "sandbox-plan.md"):
        path = notes / name
        if not path.is_file():
            continue
        if cutoff is None:
            continue
        if path.stat().st_mtime >= cutoff:
            errors.append(
                f"Phase 1a should not create itemdb/notes/{name} "
                f"(modified after Phase 1a start)"
            )


# -- Phase 1b ------------------------------------------------------------------

from phases.completion import PHASE_1B_REQUIRED_NOTES  # noqa: E402


def check_phase_1b_artifacts(
    allow_missing_generated: bool = False,
) -> list[str]:
    """Validate Phase 1b artifacts, including ``threat-model.md`` headings."""
    errors: list[str] = []
    notes = ROOT / "itemdb" / "notes"
    runs = ROOT / "runs"

    # -- Required recon notes --
    for name in PHASE_1B_REQUIRED_NOTES:
        path = notes / name
        err = _artifact_ok(path, allow_missing_generated=allow_missing_generated)
        if err:
            errors.append(err)
            continue
        if name == "threat-model.md" and path.is_file():
            missing = _missing_headings(path, REQUIRED_THREAT_MODEL_HEADINGS)
            if missing:
                errors.append(
                    f"itemdb/notes/threat-model.md missing headings: {', '.join(missing)}"
                )

    # -- Run summary --
    summary_path = runs / "phase-1b-summary.md"
    err = _artifact_ok(summary_path, allow_missing_generated=allow_missing_generated)
    if err:
        errors.append(err)
    elif summary_path.is_file():
        missing = _missing_headings(summary_path, REQUIRED_SUMMARY_HEADINGS)
        if missing:
            rel = summary_path.relative_to(ROOT)
            errors.append(f"{rel} missing headings: {', '.join(missing)}")

    # -- file-risk-index.yml --
    risk_path = notes / "file-risk-index.yml"
    if risk_path.is_file():
        risk_errors = _validate_risk_index()
        errors.extend(risk_errors)

    return errors


def has_valid_threat_model() -> bool:
    """Return True if ``threat-model.md`` exists with all required headings."""
    return check_phase_1b_threat_model_issues() == []


def check_phase_1b_threat_model_issues() -> list[str]:
    """Validate only the threat-model heading requirements.

    Returns a list of error messages (empty means success).
    Designed for gate and auto-repair consumers that only care about
    threat-model correctness, not the full 1b artifact set.
    """
    errors: list[str] = []
    path = ROOT / "itemdb" / "notes" / "threat-model.md"
    if not path.is_file():
        return ["itemdb/notes/threat-model.md does not exist"]
    missing = _missing_headings(path, REQUIRED_THREAT_MODEL_HEADINGS)
    if missing:
        errors.append(
            f"itemdb/notes/threat-model.md missing headings: {', '.join(missing)}"
        )
    return errors


# -- Phase 1c ------------------------------------------------------------------


def check_phase_1c_artifacts(
    allow_missing_generated: bool = False,
) -> list[str]:
    """Validate Phase 1c artifacts."""
    errors: list[str] = []
    notes = ROOT / "itemdb" / "notes"
    runs = ROOT / "runs"

    err = _artifact_ok(
        notes / "sandbox-plan.md", allow_missing_generated=allow_missing_generated
    )
    if err:
        errors.append(err)

    summary_path = runs / "phase-1c-summary.md"
    err = _artifact_ok(summary_path, allow_missing_generated=allow_missing_generated)
    if err:
        errors.append(err)
    elif summary_path.is_file():
        missing = _missing_headings(summary_path, REQUIRED_SUMMARY_HEADINGS)
        if missing:
            rel = summary_path.relative_to(ROOT)
            errors.append(f"{rel} missing headings: {', '.join(missing)}")

    return errors


# -- File risk index (shared) --------------------------------------------------


def _validate_risk_index() -> list[str]:
    """Reuse the existing ``validate_file_risk_index()`` from findings.checks."""
    from findings.checks import validate_file_risk_index  # noqa: PLC0415

    return validate_file_risk_index()


# -- Dispatch ------------------------------------------------------------------


def check_phase_artifacts(
    phase: str,
    allow_missing_generated: bool = False,
    phase_1a_start_time: Optional[float] = None,
) -> int:
    """Validate artifacts for one or more phases.  Returns 0 on success, 1 on errors.

    ``phase="1"`` runs 1a, 1b, 1c in sequence.
    ``phase="all"`` runs every implemented phase check in sequence.
    """
    if phase not in VALID_PHASES:
        print(
            C.fail(
                f"Invalid phase: {phase}. "
                f"Valid values: {', '.join(sorted(VALID_PHASES))}"
            )
        )
        return 1

    phases_to_check: list[str]

    if phase == "all":
        phases_to_check = ["1a", "1b", "1c"]
    elif phase == "1":
        phases_to_check = ["1a", "1b", "1c"]
    elif phase in ("2", "3", "4", "5", "6"):
        print(C.info(f"Phase {phase} artifact checks not yet implemented; nothing to do."))
        return 0
    else:
        phases_to_check = [phase]

    all_errors: list[str] = []
    for p in phases_to_check:
        func = _CHECKERS[p]
        errors = func(
            allow_missing_generated=allow_missing_generated,
            phase_1a_start_time=phase_1a_start_time,
        )
        if errors:
            print(C.fail(f"Phase {p} artifact errors ({len(errors)}):"))
            for err in errors:
                print(f"  {C.SYM_BULLET} {err}")
            all_errors.extend(errors)

    if all_errors:
        print()
        print(C.fail(f"Found {len(all_errors)} artifact error(s)."))
        return 1

    label = "all implemented phases" if phase in ("1", "all") else f"phase {phase}"
    print(C.ok(f"Artifact checks passed ({label})."))
    return 0


def _check_phase_1a_with_ct(
    allow_missing_generated: bool = False,
    phase_1a_start_time: float | None = None,
) -> list[str]:
    return check_phase_1a_artifacts(
        allow_missing_generated=allow_missing_generated,
        phase_1a_start_time=phase_1a_start_time,
    )


def _check_phase_1b_with_ct(
    allow_missing_generated: bool = False,
    phase_1a_start_time: float | None = None,
) -> list[str]:
    return check_phase_1b_artifacts(allow_missing_generated=allow_missing_generated)


def _check_phase_1c_with_ct(
    allow_missing_generated: bool = False,
    phase_1a_start_time: float | None = None,
) -> list[str]:
    return check_phase_1c_artifacts(allow_missing_generated=allow_missing_generated)


_CHECKERS = {
    "1a": _check_phase_1a_with_ct,
    "1b": _check_phase_1b_with_ct,
    "1c": _check_phase_1c_with_ct,
}
