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


def _phase1_required_artifacts() -> list[Path]:
    return [NOTES_ROOT / name for name in _PHASE1_REQUIRED_ARTIFACT_NAMES]


def _path_is_fresh(path: Path, run_start_time: float) -> bool:
    return path.exists() and path.stat().st_mtime >= run_start_time


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


def check_phase_graceful_completion(phase: str, finding: str | None, run_start_time: float) -> bool:
    original_phase = str(phase)
    phase_key = original_phase
    phase_is_1c = phase_key == "1c"
    if phase_key in ("1a", "1b", "1c"):
        phase_key = "1"

    try:
        if phase_key == "1":
            required_artifacts = _phase1_required_artifacts()
            if all(path.exists() for path in required_artifacts):
                sandbox_generated = ROOT / "sandbox" / "CODECOME-GENERATED.md"
                sandbox_state_recorded = _path_is_fresh(sandbox_generated, run_start_time) or _path_is_fresh(
                    SANDBOX_PLAN_PATH, run_start_time
                )
                import glob as _glob
                run_summaries = _glob.glob(str(ROOT / "runs" / f"phase-{original_phase}-summary*.md"))
                summary_fresh = any(Path(p).stat().st_mtime >= run_start_time for p in run_summaries)
                if phase_is_1c:
                    return sandbox_state_recorded and summary_fresh
                fresh_required = any(_path_is_fresh(path, run_start_time) for path in required_artifacts)
                return fresh_required and sandbox_state_recorded and summary_fresh
            return False
        elif phase_key in ("2", "sweep"):
            pending_dir = finding_status_dir("PENDING")
            pending_fresh = False
            if pending_dir.exists():
                pending_fresh = any(f.name.endswith(".md") and f.name != ".gitkeep" and f.stat().st_mtime >= run_start_time for f in pending_dir.iterdir())
            import glob as _glob
            run_summaries = _glob.glob(str(ROOT / "runs" / "phase-2-summary*.md"))
            summary_fresh = any(Path(p).stat().st_mtime >= run_start_time for p in run_summaries)
            return pending_fresh and summary_fresh
        elif phase_key == "3":
            import glob as _glob
            run_summaries = _glob.glob(str(ROOT / "runs" / "phase-3-summary-*.md"))
            return any(Path(p).stat().st_mtime >= run_start_time for p in run_summaries)
        elif phase_key == "4" and finding:
            evidence_dir = evidence_dir_for(finding)
            evidence_fresh = any(path.stat().st_mtime >= run_start_time for path in _iter_files(evidence_dir))
            finding_is_fresh = False
            for status in ("PENDING", "CONFIRMED", "REJECTED", "DUPLICATE", "EXPLOITED"):
                if _find_finding_file(finding_status_dir(status), finding, run_start_time):
                    finding_is_fresh = True
                    break
            return evidence_fresh and finding_is_fresh
        elif phase_key == "5" and finding:
            exploits_dir = exploits_dir_for(finding)
            exploits_fresh = any(path.stat().st_mtime >= run_start_time for path in _iter_files(exploits_dir))
            
            finding_is_fresh = False
            status_found = None
            for status in ("PENDING", "CONFIRMED", "REJECTED", "DUPLICATE", "EXPLOITED"):
                if _find_finding_file(finding_status_dir(status), finding, run_start_time):
                    finding_is_fresh = True
                    status_found = status
                    break
                    
            if not finding_is_fresh:
                return False
                
            if status_found == "EXPLOITED":
                exploited_file = _find_finding_file(finding_status_dir("EXPLOITED"), finding, run_start_time)
                if exploited_file:
                    fm = _load_finding_frontmatter(exploited_file)
                    if fm and fm.get("status") == "EXPLOITED" and _exploitation_status_looks_real(fm):
                        return exploits_fresh
                return False

            if status_found == "CONFIRMED":
                confirmed_file = _find_finding_file(finding_status_dir("CONFIRMED"), finding, run_start_time)
                if confirmed_file:
                    fm = _load_finding_frontmatter(confirmed_file)
                    if fm and isinstance(fm.get("exploitation"), dict) and str(fm["exploitation"].get("status", "")).upper() == "NOT_FEASIBLE":
                        return True
                return exploits_fresh
                
            if status_found in ("REJECTED", "DUPLICATE"):
                return True
                
            return False
        elif phase_key == "6":
            reports_dir = REPORTS_ROOT
            if reports_dir.exists():
                return any(f.name.endswith(".md") and f.name != ".gitkeep" and f.stat().st_mtime >= run_start_time for f in reports_dir.iterdir())
            return False
    except Exception:
        pass
    return False


def phase_checklist_lines(phase: str, finding: str | None) -> list[str]:
    if str(phase) == "1":
        return [
            f"Ensure all required Phase 1 notes exist under {_ITEMDB_NOTES_DIR}.",
            f"Ensure {NOTES_ROOT.relative_to(ROOT)}/threat-model.md has all required H1 headings: # Threat Model Summary, # Scope, # System model, # Assets and security objectives, # Attacker model, # Trust boundary summary, # Existing controls, # Abuse-path themes for Phase 2, # Risk calibration for review focus, # Open questions for the user, # Re-run prompt hints.",
            f"Ensure {NOTES_ROOT.relative_to(ROOT)}/file-risk-index.yml is present and consistent with interesting-files.md.",
            f"Ensure {NOTES_ROOT.relative_to(ROOT)}/sandbox-plan.md documents the Phase 1b outcome.",
            "If sandbox bootstrap succeeded, ensure sandbox/CODECOME-GENERATED.md exists; otherwise document the halt clearly in sandbox-plan.md.",
        ]
    if str(phase) in ("2", "sweep"):
        return [
            f"Create or update precise findings under {FINDINGS_ROOT.relative_to(ROOT)}/PENDING/.",
            "Each finding must identify affected code, trust-boundary/source-to-sink reasoning, attackability, impact, validation plan, and counter-analysis placeholder.",
            "Do not stop until the new or updated findings are durable on disk.",
        ]
    if str(phase) == "3":
        return [
            f"Review all candidate findings under {FINDINGS_ROOT.relative_to(ROOT)}/PENDING/.",
            "Move clearly invalid findings to REJECTED and duplicates to DUPLICATE.",
            "Leave surviving findings reviewable, deduplicated, and updated with counter-analysis.",
        ]
    if str(phase) == "4":
        finding_ref = finding or "<finding-id>"
        return [
            f"Ensure validation evidence exists under {EVIDENCE_ROOT.relative_to(ROOT)}/{finding_ref}/, including README.md.",
            "Update the finding with validation results and move it to the correct status directory if needed.",
            "Do not stop until the evidence and finding status are consistent.",
        ]
    if str(phase) == "5":
        finding_ref = finding or "<finding-id>"
        return [
            f"If exploitation succeeds, ensure {EVIDENCE_ROOT.relative_to(ROOT)}/{finding_ref}/exploits/ contains the exploit artifacts and exploits/README.md.",
            "If exploitation is not feasible, keep the finding in CONFIRMED and update its exploitation.status to NOT_FEASIBLE with a clear explanation.",
            "Do not stop until the exploit artifacts or the NOT_FEASIBLE documentation are durable and consistent.",
        ]
    if str(phase) == "6":
        return [
            f"Ensure the report output under {REPORTS_ROOT.relative_to(ROOT)}/ is written and reviewable.",
            "Include the required summary sections and evidence references for exploited and confirmed findings.",
            "Do not stop until the report artifacts are durable on disk.",
        ]
    return ["Finish the remaining required work for the current phase before ending."]


def build_phase_resume_prompt(
    phase: str,
    finding: str | None,
    reason: str,
    step_finish_count: int,
) -> str:
    checklist = "\n".join(f"- {line}" for line in phase_checklist_lines(phase, finding))
    return (
        "Your previous response was cut off by the model/provider before you produced a final completion signal.\n\n"
        f"Observed finish reason: {reason}.\n"
        f"Completed loops before cutoff: {step_finish_count}.\n\n"
        "Treat your prior work as partial. First, briefly reassess what remains unfinished for this phase. "
        "Then complete only the remaining required work. Do not restart from scratch unless necessary.\n\n"
        f"Phase {phase} completion checklist:\n"
        f"{checklist}\n\n"
        "Before ending, verify that the required durable artifacts for this phase exist, are updated, and are internally consistent."
    )


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


def build_codeql_plan_resume_prompt(validation_output: str) -> str:
    return (
        "Your previous run created or edited `itemdb/notes/codeql-plan.yml`, but the file failed local "
        "CodeQL plan validation.\n\n"
        "Validation errors:\n"
        f"{validation_output}\n\n"
        "Repair only `itemdb/notes/codeql-plan.yml` with the smallest change needed. Do not redo unrelated "
        "reconnaissance or modify target source code. Preserve the existing analysis units, pack selections, "
        "manual build commands, and notes unless a reported validation error requires changing them.\n\n"
        "Before ending, verify that the repaired plan passes local validation by running `rtk python3 tools/codecome.py check-codeql-plan`."
    )


def build_artifact_repair_resume_prompt(
    phase: str, finding: str | None, validation_output: str
) -> str:
    """Build a resume prompt for Phase 1b artifact validation failures."""
    checklist = "\n".join(f"- {line}" for line in phase_checklist_lines(phase, finding))
    return (
        "Your previous run produced Phase 1b artifacts that failed local validation.\n\n"
        "Validation errors:\n"
        f"{validation_output}\n\n"
        "Repair only the reported missing or malformed Phase 1b artifacts with minimal changes. "
        "Do not rewrite unrelated reconnaissance notes and do not modify target source code. "
        "If threat-model.md is missing required headings, add only the missing H1 headings and "
        "leave the existing content intact.\n\n"
        f"Phase {phase} completion checklist:\n"
        f"{checklist}\n\n"
        "Before ending, verify that the repaired artifacts pass local validation."
    )


def build_codeql_build_failure_resume_prompt(validation_output: str) -> str:
    return (
        "The repaired `itemdb/notes/codeql-plan.yml` was valid, but the next CodeQL database creation run still "
        "failed. Continue the same narrow CodeQL build repair task.\n\n"
        "Latest CodeQL failure details:\n"
        f"{validation_output}\n\n"
        "Repair only `itemdb/notes/codeql-plan.yml` and any helper scripts under workspace-relative `tmp/` or "
        "`sandbox/`. Do not modify target source code.\n\n"
        "Important execution model: CodeQL runs the manual `build_command` with the current working directory set "
        "to the analysis unit source path (`analysis_units[].path`). It is not run from the workspace root, and it "
        "is not run from the helper script directory. If a helper script changes directory, it must do so based on "
        "the analysis source root or explicit paths that work from that source root.\n\n"
        "CodeQL tokenizes `build_command` as argv; it does not execute it as a shell script. Do not put shell "
        "control syntax in `build_command`: no `&&`, `||`, `;`, pipes, comments, multi-line commands, or "
        "`bash -c` / `sh -c` snippets. If more than one command is needed, create a helper script under "
        "workspace-relative `tmp/` and set `build_command` to invoke it, for example `bash ../../tmp/codeql-build.sh`.\n\n"
        "Do not use absolute `/tmp/` paths. Use workspace-relative `tmp/` paths. Do not embed this workspace's "
        "absolute path in `build_command`; prefer paths relative to the analysis unit source path.\n\n"
        "Before ending, verify that the plan is valid YAML, that referenced helper scripts exist, and that shell "
        "helpers pass syntax-only validation."
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
