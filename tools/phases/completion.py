# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Phase completion checks, required artifact checks, resume prompt builders.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

from findings.constants import (
    ROOT,
    FINDINGS_ROOT,
    EVIDENCE_ROOT,
    NOTES_ROOT,
    REPORTS_ROOT,
    SANDBOX_PLAN_PATH,
    evidence_dir_for,
    exploits_dir_for,
    finding_status_dir,
)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

_ITEMDB_NOTES_DIR = "itemdb/notes/"
_ITEMDB_FINDINGS_DIR = "itemdb/findings/"
_ITEMDB_REPORTS_DIR = "itemdb/reports/"

_PHASE1_REQUIRED_ARTIFACT_NAMES = [
    "target-profile.md",
    "attack-surface.md",
    "build-model.md",
    "execution-model.md",
    "trust-boundaries.md",
    "data-flow.md",
    "validation-model.md",
    "interesting-files.md",
    "file-risk-index.yml",
    "security-assumptions.md",
    "threat-model.md",
    "sandbox-plan.md",
]

# Subphase-specific artifact sets.  Phase 1b uses its own list (the canonical
# source of truth consumed by artifact_checks.py as well).  Phase 1a and 1c
# lists are defined here alongside the monolith set.
_PHASE_1A_ARTIFACT_NAMES = ("target-profile.md", "build-model.md", "codeql-plan.yml")

PHASE_1B_REQUIRED_NOTES: list[str] = [
    "attack-surface.md",
    "execution-model.md",
    "trust-boundaries.md",
    "data-flow.md",
    "threat-model.md",
    "validation-model.md",
    "interesting-files.md",
    "file-risk-index.yml",
    "security-assumptions.md",
]


def _phase1_required_artifacts() -> list[Path]:
    return [NOTES_ROOT / name for name in _PHASE1_REQUIRED_ARTIFACT_NAMES]


def _path_is_fresh(path: Path, run_start_time: float) -> bool:
    return path.exists() and path.stat().st_mtime >= run_start_time


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _run_summary_is_fresh(phase_id: str, run_start_time: float) -> bool:
    """Return whether any fresh run-summary file exists for *phase_id*.

    The glob is intentionally unhyphenated after ``summary`` to match the
    timestamped path convention ``runs/phase-<phase>-summary-YYYY-MM-DD-HHMMSS.md``
    and to accept older ad-hoc filenames.
    """
    import glob as _glob
    matches = _glob.glob(str(ROOT / "runs" / f"phase-{phase_id}-summary*.md"))
    return any(Path(p).stat().st_mtime >= run_start_time for p in matches)


def _append_run_summary_check(
    failures: list[str], phase_id: str, run_start_time: float
) -> None:
    """Append a missing-summary failure detail if no fresh summary exists."""
    if _run_summary_is_fresh(phase_id, run_start_time):
        return
    failures.append(
        f"Missing: runs/phase-{phase_id}-summary*.md — run summary "
        "was not created or updated during this run"
    )


def _iter_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def _find_finding_file(status_dir: Path, finding_id: str, run_start_time: float) -> Path | None:
    """Find a finding file matching the ID in the status directory.

    Finding filenames may include a descriptive slug after the ID
    (e.g. ``CC-0009-file-input-reaches-vprintf.md``).  Use a glob so
    both ``CC-0009.md`` and ``CC-0009-slug.md`` are discovered.

    If more than one candidate exists, at least one must have been
    modified after *run_start_time*, and the freshest is returned.
    """
    candidates = list(status_dir.glob(f"{finding_id}*.md"))
    files = [p for p in candidates if p.is_file() and p.name != ".gitkeep"]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    fresh = files[0]
    if len(files) == 1:
        return fresh if fresh.stat().st_mtime >= run_start_time else None
    return fresh if fresh.stat().st_mtime >= run_start_time else None


def _load_finding_frontmatter(path: Path) -> dict[str, Any] | None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(m.group(1))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _exploitation_status_looks_real(frontmatter: dict[str, Any] | None) -> bool:
    if not isinstance(frontmatter, dict):
        return False
    exploitation = frontmatter.get("exploitation")
    if not isinstance(exploitation, dict):
        return False
    status = str(exploitation.get("status", "")).strip().lower()
    return bool(status and status not in ("", "pending.", "todo.", "tbd."))


def check_phase_graceful_completion(phase: str, finding: str | None, run_start_time: float) -> tuple[bool, list[str]]:
    original_phase = str(phase)
    phase_key = original_phase
    phase_is_1c = phase_key == "1c"
    if phase_key in ("1a", "1b", "1c"):
        phase_key = "1"

    failures: list[str] = []

    try:
        if phase_key == "1":
            # -- Subphase-specific graceful-completion checks --
            # Phase 1a and 1b should not require artifacts owned by other subphases
            # (sandbox-plan.md from 1c, or sandbox/CODECOME-GENERATED.md).
            # Bare "1" (full Phase 1) and 1c keep the existing monolith check below.

            if original_phase == "1a":
                notes_dir = ROOT / "itemdb" / "notes"
                paths_1a = [notes_dir / n for n in _PHASE_1A_ARTIFACT_NAMES]
                fresh_1a = any(_path_is_fresh(p, run_start_time) for p in paths_1a)
                if not fresh_1a:
                    failures.append(
                        f"Missing: {_display_path(NOTES_ROOT)}/ — no phase-1a required notes "
                        f"({', '.join(_PHASE_1A_ARTIFACT_NAMES)}) "
                        "created or updated during this run"
                    )
                _append_run_summary_check(failures, original_phase, run_start_time)
                return (len(failures) == 0, failures)

            if original_phase == "1b":
                notes_dir = ROOT / "itemdb" / "notes"
                paths_1b = [notes_dir / n for n in PHASE_1B_REQUIRED_NOTES]
                fresh_1b = any(_path_is_fresh(p, run_start_time) for p in paths_1b)
                if not fresh_1b:
                    failures.append(
                        f"Missing: {_display_path(NOTES_ROOT)}/ — no phase-1b required notes "
                        f"({', '.join(PHASE_1B_REQUIRED_NOTES)}) "
                        "created or updated during this run"
                    )
                _append_run_summary_check(failures, original_phase, run_start_time)
                return (len(failures) == 0, failures)

            if original_phase == "1c":
                notes_dir = ROOT / "itemdb" / "notes"
                sandbox_generated = ROOT / "sandbox" / "CODECOME-GENERATED.md"
                fresh_1c = (
                    _path_is_fresh(notes_dir / "sandbox-plan.md", run_start_time)
                    or _path_is_fresh(sandbox_generated, run_start_time)
                )
                if not fresh_1c:
                    failures.append(
                        "Missing: itemdb/notes/sandbox-plan.md or sandbox/CODECOME-GENERATED.md "
                        "— neither sandbox state artifact was created or updated during this run"
                    )
                _append_run_summary_check(failures, original_phase, run_start_time)
                return (len(failures) == 0, failures)

            # Phase 1c and bare "1": require the full monolith set.
            required_artifacts = _phase1_required_artifacts()
            sandbox_generated = ROOT / "sandbox" / "CODECOME-GENERATED.md"
            sandbox_state_recorded = _path_is_fresh(sandbox_generated, run_start_time) or _path_is_fresh(
                SANDBOX_PLAN_PATH, run_start_time
            )
            import glob as _glob
            run_summaries = _glob.glob(str(ROOT / "runs" / f"phase-{original_phase}-summary*.md"))
            summary_fresh = any(Path(p).stat().st_mtime >= run_start_time for p in run_summaries)

            if all(path.exists() for path in required_artifacts):
                fresh_required = any(_path_is_fresh(path, run_start_time) for path in required_artifacts)
                if not fresh_required:
                    failures.append(
                        f"Missing: {_display_path(NOTES_ROOT)}/ — no phase-1 required notes "
                        f"({', '.join(_PHASE1_REQUIRED_ARTIFACT_NAMES)}) "
                        "created or updated during this run"
                    )
            else:
                failures.append(
                    f"Missing: {_display_path(NOTES_ROOT)}/ — required phase-1 notes "
                    f"({', '.join(_PHASE1_REQUIRED_ARTIFACT_NAMES)}) are not all present"
                )

            if not sandbox_state_recorded:
                failures.append(
                    "Missing: sandbox/CODECOME-GENERATED.md or itemdb/notes/sandbox-plan.md "
                    "— sandbox state was not recorded during this run"
                )
            if not summary_fresh:
                failures.append(
                    f"Missing: runs/phase-{original_phase}-summary*.md — run summary "
                    "was not created or updated during this run"
                )
            return (len(failures) == 0, failures)
        elif phase_key in ("2", "sweep"):
            import glob as _glob
            run_summaries = _glob.glob(str(ROOT / "runs" / "phase-2-summary*.md"))
            summary_fresh = any(Path(p).stat().st_mtime >= run_start_time for p in run_summaries)
            if not summary_fresh:
                failures.append(
                    "Missing: runs/phase-2-summary*.md — run summary was not "
                    "created or updated"
                )
            return (len(failures) == 0, failures)
        elif phase_key == "3":
            import glob as _glob
            run_summaries = _glob.glob(str(ROOT / "runs" / "phase-3-summary-*.md"))
            summary_fresh = any(Path(p).stat().st_mtime >= run_start_time for p in run_summaries)
            if not summary_fresh:
                failures.append(
                    "Missing: runs/phase-3-summary-*.md — run summary was not "
                    "created or updated"
                )
            return (len(failures) == 0, failures)
        elif phase_key == "4" and finding:
            evidence_dir = evidence_dir_for(finding)
            evidence_fresh = any(path.stat().st_mtime >= run_start_time for path in _iter_files(evidence_dir))
            finding_is_fresh = False
            for status in ("PENDING", "CONFIRMED", "REJECTED", "DUPLICATE", "EXPLOITED"):
                if _find_finding_file(finding_status_dir(status), finding, run_start_time):
                    finding_is_fresh = True
                    break
            if not evidence_fresh:
                failures.append(
                    f"Missing: {_display_path(EVIDENCE_ROOT)}/{finding}/ — no evidence files "
                    "created or updated during this run"
                )
            if not finding_is_fresh:
                failures.append(
                    f"Missing: {_display_path(FINDINGS_ROOT)}/*/{finding}*.md — finding file "
                    "not created or updated during this run"
                )
            _append_run_summary_check(failures, f"4-{finding}", run_start_time)
            return (len(failures) == 0, failures)
        elif phase_key == "5" and finding:
            exploits_dir = exploits_dir_for(finding)
            exploits_fresh = any(path.stat().st_mtime >= run_start_time for path in _iter_files(exploits_dir))

            _append_run_summary_check(failures, f"5-{finding}", run_start_time)
            finding_is_fresh = False
            status_found = None
            for status in ("PENDING", "CONFIRMED", "REJECTED", "DUPLICATE", "EXPLOITED"):
                if _find_finding_file(finding_status_dir(status), finding, run_start_time):
                    finding_is_fresh = True
                    status_found = status
                    break

            if not finding_is_fresh:
                failures.append(
                    f"Missing: {_display_path(FINDINGS_ROOT)}/*/{finding}*.md — finding file "
                    "not created or updated during this run"
                )
                return (len(failures) == 0, failures)

            if status_found == "EXPLOITED":
                exploited_file = _find_finding_file(finding_status_dir("EXPLOITED"), finding, run_start_time)
                if exploited_file:
                    fm = _load_finding_frontmatter(exploited_file)
                    if fm and fm.get("status") == "EXPLOITED" and _exploitation_status_looks_real(fm):
                        if not exploits_fresh:
                            failures.append(
                                f"Missing: {_display_path(EVIDENCE_ROOT)}/{finding}/exploits/ "
                                "— no exploit artifacts created or updated during this run"
                            )
                        return (len(failures) == 0, failures)
                failures.append(
                    f"Missing: exploitation frontmatter on {_display_path(FINDINGS_ROOT)}/EXPLOITED/{finding}*.md "
                    "— exploitation status block is missing or invalid"
                )
                return (len(failures) == 0, failures)

            if status_found == "CONFIRMED":
                confirmed_file = _find_finding_file(finding_status_dir("CONFIRMED"), finding, run_start_time)
                if confirmed_file:
                    fm = _load_finding_frontmatter(confirmed_file)
                    if fm and isinstance(fm.get("exploitation"), dict) and str(fm["exploitation"].get("status", "")).upper() == "NOT_FEASIBLE":
                        return (True, [])
                if not exploits_fresh:
                    failures.append(
                        f"Missing: {_display_path(EVIDENCE_ROOT)}/{finding}/exploits/ "
                        "— no exploit artifacts created or updated during this run"
                    )
                return (len(failures) == 0, failures)

            if status_found in ("REJECTED", "DUPLICATE"):
                return (True, [])

            failures.append(
                f"Missing: exploitation outcome for {_display_path(FINDINGS_ROOT)}/{finding}*.md "
                "— finding is in an unexpected status for Phase 5"
            )
            return (len(failures) == 0, failures)
        elif phase_key == "6":
            reports_dir = REPORTS_ROOT
            fresh_report = False
            if reports_dir.exists():
                fresh_report = any(
                    f.name.endswith(".md") and f.name != ".gitkeep"
                    and f.stat().st_mtime >= run_start_time
                    for f in reports_dir.iterdir()
                )
            if not fresh_report:
                failures.append(
                    f"Missing: {_display_path(REPORTS_ROOT)}/ — no report files created "
                    "or updated during this run"
                )
            _append_run_summary_check(failures, "6", run_start_time)
            return (len(failures) == 0, failures)
    except Exception:
        return (False, [f"Internal error during artifact check for phase '{original_phase}'"])
    # No phase_key branch matched (e.g., unknown phase like "7", or phase="4" with finding=None)
    return (False, [f"No completion gate defined for phase '{original_phase}'"])


def phase_checklist_lines(phase: str, finding: str | None) -> list[str]:
    phase_key = str(phase)
    if phase_key in ("1a", "1b", "1c"):
        phase_key = "1"
    if phase_key == "1":
        return [
            f"Ensure all required Phase 1 notes exist under {_ITEMDB_NOTES_DIR}.",
            f"Ensure {_display_path(NOTES_ROOT)}/threat-model.md has all required H1 headings: # Threat Model Summary, # Scope, # System model, # Assets and security objectives, # Attacker model, # Trust boundary summary, # Existing controls, # Abuse-path themes for Phase 2, # Risk calibration for review focus, # Open questions for the user, # Re-run prompt hints.",
            f"Ensure {_display_path(NOTES_ROOT)}/file-risk-index.yml is present and consistent with interesting-files.md.",
            f"Ensure {_display_path(NOTES_ROOT)}/sandbox-plan.md documents the Phase 1b outcome.",
            "If sandbox bootstrap succeeded, ensure sandbox/CODECOME-GENERATED.md exists; otherwise document the halt clearly in sandbox-plan.md.",
        ]
    if str(phase) in ("2", "sweep"):
        return [
            f"Create or update precise findings under {_display_path(FINDINGS_ROOT)}/PENDING/.",
            "Each finding must identify affected code, trust-boundary/source-to-sink reasoning, attackability, impact, validation plan, and counter-analysis placeholder.",
            "If no new vulnerabilities are found, document this in the run summary rather than creating placeholder findings.",
            f"Write a run summary to runs/phase-2-summary-YYYY-MM-DD-HHMMSS.md using templates/run-summary.md.",
            "Do not stop until the run summary is durable on disk.",
        ]
    if str(phase) == "3":
        return [
            f"Review all candidate findings under {_display_path(FINDINGS_ROOT)}/PENDING/.",
            "Move clearly invalid findings to REJECTED and duplicates to DUPLICATE.",
            "Leave surviving findings reviewable, deduplicated, and updated with counter-analysis.",
            f"Write a run summary to runs/phase-3-summary-YYYY-MM-DD-HHMMSS.md using templates/run-summary.md.",
            "Do not stop until the run summary is durable on disk.",
        ]
    if str(phase) == "4":
        finding_ref = finding or "<finding-id>"
        return [
            f"Ensure validation evidence exists under {_display_path(EVIDENCE_ROOT)}/{finding_ref}/, including README.md.",
            "Update the finding with validation results and move it to the correct status directory if needed.",
            "Do not stop until the evidence and finding status are consistent.",
        ]
    if str(phase) == "5":
        finding_ref = finding or "<finding-id>"
        return [
            f"If exploitation succeeds, ensure {_display_path(EVIDENCE_ROOT)}/{finding_ref}/exploits/ contains the exploit artifacts and exploits/README.md.",
            "If exploitation is not feasible, keep the finding in CONFIRMED and update its exploitation.status to NOT_FEASIBLE with a clear explanation.",
            "Do not stop until the exploit artifacts or the NOT_FEASIBLE documentation are durable and consistent.",
        ]
    if str(phase) == "6":
        return [
            f"Ensure the report output under {_display_path(REPORTS_ROOT)}/ is written and reviewable.",
            "Include the required summary sections and evidence references for exploited and confirmed findings.",
            "Do not stop until the report artifacts are durable on disk.",
        ]
    return ["Finish the remaining required work for the current phase before ending."]


def _resume_opener_for_reason(reason: str) -> str:
    """Return a context-specific opener for the resume prompt.

    The ``reason`` is whatever the harness recorded for why the run was
    treated as incomplete:

    - ``"infrastructure_error"`` — harness fatal-retry path.
    - A finish reason from ``rendering.events._FINISH_MID_TURN`` (e.g.
      ``"length"``, ``"tool_use"``) — the model/provider cut off mid-turn.
    - A finish reason from ``rendering.events._FINISH_FAILURE`` — the
      model/provider reported a failure finish reason.
    - ``"graceful_forgiveness"`` — synthesized by the harness when the
      mid-turn cutoff happened but partial artifacts were written.
    - A finish reason from ``rendering.events._FINISH_TERMINAL_OK`` (e.g.
      ``"stop"``) or any other value — the model reported completion but
      the gate still failed, so required artifacts are missing.
    """
    from rendering.events import (
        _FINISH_FAILURE,
        _FINISH_MID_TURN,
        _FINISH_TERMINAL_OK,
    )

    if reason == "infrastructure_error":
        return "Your previous attempt failed with an infrastructure error and was retried."
    if reason in _FINISH_MID_TURN:
        return (
            f"Your previous run was cut off mid-turn (finish reason '{reason}') "
            "before completing all required artifacts."
        )
    if reason in _FINISH_FAILURE:
        return (
            f"Your previous run stopped with a failure finish reason '{reason}' "
            "before completing all required artifacts."
        )
    if reason == "graceful_forgiveness":
        return (
            "Your previous run was treated as incomplete by CodeCome even though "
            "some expected artifacts were written."
        )
    if reason in _FINISH_TERMINAL_OK:
        return (
            f"Your previous run reported a terminal finish reason '{reason}', but "
            "CodeCome's completion gate did not find the required durable artifacts."
        )
    return "Your previous run was treated as incomplete by CodeCome."


def build_phase_resume_prompt(
    phase: str,
    finding: str | None,
    reason: str,
    step_finish_count: int,
    failure_details: list[str] | None = None,
) -> str:
    checklist = "\n".join(f"- {line}" for line in phase_checklist_lines(phase, finding))

    lines = [
        _resume_opener_for_reason(reason),
        "",
        f"Observed finish reason: {reason}.",
        f"Completed loops before cutoff: {step_finish_count}.",
    ]

    if failure_details:
        lines.append("")
        lines.append("Missing required artifacts:")
        for detail in failure_details:
            lines.append(f"- {detail}")
        lines.append("")
        lines.append(
            "Fix only these missing items. Do not redo completed work."
        )
    else:
        lines.append("")
        lines.append(
            "Treat your prior work as partial. First, briefly reassess "
            "what remains unfinished for this phase. Then complete only "
            "the remaining required work. Do not restart from scratch "
            "unless necessary."
        )

    lines.append("")
    lines.append(f"Phase {phase} completion checklist:")
    lines.append(checklist)
    lines.append("")
    lines.append(
        "Before ending, verify that the required durable artifacts for "
        "this phase exist, are updated, and are internally consistent."
    )

    return "\n".join(lines)


def build_frontmatter_resume_prompt(phase: str, finding: str | None, validation_output: str) -> str:
    checklist = "\n".join(f"- {line}" for line in phase_checklist_lines(phase, finding))
    return (
        "Your previous run produced files that failed local validation.\n\n"
        "Validation errors:\n"
        f"{validation_output}\n\n"
        "Repair only the reported YAML/frontmatter issues with minimal changes. Do not redo unrelated analysis.\n\n"
        f"Phase {phase} completion checklist:\n"
        f"{checklist}\n\n"
        "After fixing the validation errors, ensure the affected files remain in the correct status/location and are internally consistent."
    )


def build_artifact_repair_resume_prompt(
    phase: str, finding: str | None, validation_output: str
) -> str:
    """Build a resume prompt for phase artifact validation failures."""
    checklist = "\n".join(f"- {line}" for line in phase_checklist_lines(phase, finding))
    return (
        f"Your previous run produced Phase {phase} artifacts that failed local validation.\n\n"
        "Validation errors:\n"
        f"{validation_output}\n\n"
        f"Repair only the reported missing or malformed Phase {phase} artifacts with minimal changes. "
        "Do not rewrite unrelated reconnaissance notes and do not modify target source code. "
        "If threat-model.md is missing required headings, add only the missing H1 headings and "
        "leave the existing content intact.\n\n"
        f"Phase {phase} completion checklist:\n"
        f"{checklist}\n\n"
        "Before ending, verify that the repaired artifacts pass local validation."
    )


def build_resume_command(initial_command: list[str], session_id: str, prompt: str) -> list[str]:
    """Preserve connection/runtime flags needed to reach the original session."""
    resume = ["opencode", "run"]
    pending_passthrough_value = False
    passthrough_value_flags = {"--attach", "--port", "-p"}
    passthrough_standalone_flags = {"--thinking"}
    drop_value_flags = {"--agent", "--model", "-m", "--variant", "--session", "-s", "--format"}
    drop_standalone_flags = {"--continue", "-c", "--fork"}

    for token in initial_command[2:]:
        if pending_passthrough_value:
            resume.append(token)
            pending_passthrough_value = False
            continue

        name, has_equals, _ = token.partition("=")
        if name in drop_standalone_flags:
            continue
        if name in drop_value_flags:
            if not has_equals:
                pending_passthrough_value = False
            continue
        if name in passthrough_standalone_flags:
            resume.append(token)
            continue
        if name in passthrough_value_flags:
            resume.append(token)
            if not has_equals:
                pending_passthrough_value = True
            continue

    resume.extend(["--session", session_id, "--format", "json", prompt])
    return resume
