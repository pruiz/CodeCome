#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
CodeCome helper CLI.

This tool intentionally starts small. It provides basic workspace checks,
finding status counts, and next-id discovery for Markdown findings.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = [
    "README.md",
    "AGENTS.md",
    "codecome.yml",
    "src",
    "sandbox",
    "itemdb",
    "itemdb/findings/PENDING",
    "itemdb/findings/CONFIRMED",
    "itemdb/findings/EXPLOITED",
    "itemdb/findings/REJECTED",
    "itemdb/findings/DUPLICATE",
    "itemdb/evidence",
    "itemdb/notes",
    "itemdb/reports",
    "runs",
    "templates",
    "templates/finding.md",
    "templates/target-recon.md",
    "templates/threat-model.md",
    "templates/evidence-readme.md",
    "templates/report.md",
    "templates/run-summary.md",
    "templates/exploit-readme.md",
    "tools",
    ".opencode/agents",
    ".opencode/skills",
]

FINDING_STATUS_DIRS = [
    "PENDING",
    "CONFIRMED",
    "EXPLOITED",
    "REJECTED",
    "DUPLICATE",
]

FINDING_ID_RE = re.compile(r"\bCC-(\d{4,})\b")


# --- Optional recording tools ------------------------------------------------
#
# Used by Phase 5 to capture exploit demonstrations. Missing tools are not
# fatal; we just warn so the user can install what they need before
# attempting a recording.

_INSTALL_HINTS_MAC = {
    "asciinema": "brew install asciinema",
    "agg": "brew install agg",
    "ffmpeg": "brew install ffmpeg",
    "Xvfb": "brew install --cask xquartz   # Xvfb ships with XQuartz",
    "docker": "brew install --cask docker",
}

_INSTALL_HINTS_DEBIAN = {
    "asciinema": "sudo apt-get install asciinema",
    "agg": (
        "cargo install --git https://github.com/asciinema/agg "
        "(no apt package; or use the docker fallback "
        "'docker pull ghcr.io/asciinema/agg')"
    ),
    "ffmpeg": "sudo apt-get install ffmpeg",
    "Xvfb": "sudo apt-get install xvfb",
    "docker": "https://docs.docker.com/engine/install/",
}

_INSTALL_HINTS_GENERIC = {
    "asciinema": "https://asciinema.org/docs/installation",
    "agg": "https://github.com/asciinema/agg (or docker pull ghcr.io/asciinema/agg)",
    "ffmpeg": "https://ffmpeg.org/download.html",
    "Xvfb": "package usually named 'xvfb' on Linux distributions",
    "docker": "https://docs.docker.com/engine/install/",
}


def _detect_os_family() -> str:
    system = platform.system()
    if system == "Darwin":
        return "mac"
    if system == "Linux":
        # Best-effort detection of Debian/Ubuntu family.
        try:
            os_release = Path("/etc/os-release").read_text(encoding="utf-8")
        except OSError:
            return "linux"
        lower = os_release.lower()
        if any(token in lower for token in ("debian", "ubuntu", "mint")):
            return "debian"
        return "linux"
    return "other"


def _install_hint(tool: str) -> str:
    family = _detect_os_family()
    if family == "mac":
        return _INSTALL_HINTS_MAC.get(tool, _INSTALL_HINTS_GENERIC[tool])
    if family == "debian":
        return _INSTALL_HINTS_DEBIAN.get(tool, _INSTALL_HINTS_GENERIC[tool])
    return _INSTALL_HINTS_GENERIC.get(tool, "")


def _which(tool: str) -> Optional[str]:
    return shutil.which(tool)


def check_recording_tools() -> List[str]:
    """Return a list of warning messages about missing optional recording tools.

    Empty list means everything is in place. Tools are grouped by recording
    path: preferred (asciinema + agg), and fallback (ffmpeg + Xvfb).
    Docker is reported separately because it provides a containerised agg
    fallback when agg itself is not on PATH.
    """

    warnings: List[str] = []

    asciinema = _which("asciinema")
    agg = _which("agg")
    docker = _which("docker")
    ffmpeg = _which("ffmpeg")
    xvfb = _which("Xvfb") or _which("xvfb-run")

    # Preferred path: asciinema + agg (or asciinema + docker for containerised agg).
    if not asciinema:
        warnings.append(
            f"asciinema not found on PATH "
            f"(preferred recording tool). Install hint: {_install_hint('asciinema')}"
        )

    if not agg:
        if docker:
            warnings.append(
                "agg not found on PATH; falling back to "
                "'docker run --rm -v \"$PWD:/data\" ghcr.io/asciinema/agg' "
                "may be usable because the docker CLI is present. Confirm the "
                "daemon, permissions, and image pull before recording."
            )
        else:
            warnings.append(
                f"agg not found on PATH and docker is not available either "
                f"(needed to render asciinema casts to GIF). "
                f"Install hint: {_install_hint('agg')}"
            )

    # Fallback path: ffmpeg + Xvfb (only required for GUI/browser exploits).
    if not ffmpeg:
        warnings.append(
            f"ffmpeg not found on PATH (fallback for GUI/browser exploits). "
            f"Install hint: {_install_hint('ffmpeg')}"
        )

    if not xvfb:
        warnings.append(
            f"Xvfb (or xvfb-run) not found on PATH "
            f"(headless fallback for GUI exploits). "
            f"Install hint: {_install_hint('Xvfb')}"
        )

    return warnings


def _docker_daemon_reachable() -> bool:
    if not _which("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _detect_script_flavor() -> Optional[str]:
    """Return 'util-linux', 'bsd', or None depending on which `script(1)` is on PATH."""

    if not _which("script"):
        return None
    try:
        result = subprocess.run(
            ["script", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "bsd"
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0 and "util-linux" in output.lower():
        return "util-linux"
    return "bsd"


def probe_recording_environment() -> List[Tuple[str, str, str]]:
    """Probe runtime conditions for the current invocation context.

    Returns a list of (label, status, detail) tuples. `status` is one of
    "ok", "warn", "info" and is used purely for colouring.
    """

    rows: List[Tuple[str, str, str]] = []

    stdin_tty = os.isatty(0)
    stdout_tty = os.isatty(1)
    if stdin_tty and stdout_tty:
        rows.append(("stdin/stdout TTY", "ok", "yes (tier 1 'asciinema rec' should work directly)"))
    else:
        rows.append((
            "stdin/stdout TTY",
            "warn",
            (
                f"no (stdin={stdin_tty}, stdout={stdout_tty}); direct tier-1 "
                "`asciinema rec` is unlikely to work from this exact invocation"
            ),
        ))

    flavor = _detect_script_flavor()
    if flavor == "util-linux":
        rows.append((
            "script(1) shim (tier 2)",
            "ok",
            "yes, util-linux flavor — `script -qfc '<cmd>' /dev/null`",
        ))
    elif flavor == "bsd":
        rows.append((
            "script(1) shim (tier 2)",
            "ok",
            "yes, BSD/macOS flavor — `script -q /dev/null <cmd>`",
        ))
    else:
        rows.append(("script(1) shim (tier 2)", "warn", "no — script(1) not on PATH"))

    if _which("unbuffer"):
        rows.append(("unbuffer shim (tier 3)", "ok", "yes — `unbuffer -p <cmd>`"))
    else:
        rows.append((
            "unbuffer shim (tier 3)",
            "info",
            "no (ships with the `expect` package; optional)",
        ))

    if _docker_daemon_reachable():
        rows.append((
            "docker daemon (tier 4)",
            "ok",
            "reachable — `docker run --rm -t …` can supply a PTY",
        ))
    elif _which("docker"):
        rows.append((
            "docker daemon (tier 4)",
            "warn",
            "docker CLI present but daemon not reachable",
        ))
    else:
        rows.append(("docker daemon (tier 4)", "info", "docker not installed"))

    return rows


def fail(message: str) -> int:
    print(C.fail(message), file=sys.stderr)
    return 1


def load_config() -> dict:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: pip install -r requirements.txt")

    config_path = ROOT / "codecome.yml"
    with config_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise RuntimeError("codecome.yml did not parse as a YAML object")

    return data


def iter_finding_files() -> Iterable[Path]:
    findings_root = ROOT / "itemdb" / "findings"

    for status in FINDING_STATUS_DIRS:
        status_dir = findings_root / status
        if not status_dir.exists():
            continue

        yield from sorted(status_dir.glob("CC-*.md"))


def collect_finding_ids(paths: Iterable[Path]) -> List[int]:
    ids: List[int] = []

    for path in paths:
        match = FINDING_ID_RE.search(path.name)
        if match:
            ids.append(int(match.group(1)))

    return sorted(set(ids))


def count_findings() -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for status in FINDING_STATUS_DIRS:
        status_dir = ROOT / "itemdb" / "findings" / status
        counts[status] = len(list(status_dir.glob("CC-*.md"))) if status_dir.exists() else 0

    return counts


def _phase_1_notes_exist() -> bool:
    notes_dir = ROOT / "itemdb" / "notes"
    return (notes_dir / "target-profile.md").is_file() and (notes_dir / "build-model.md").is_file()


def check_phase_progress() -> None:
    """Print a summary of which phases have been run based on durable artifacts."""
    from phases.phase_1_gates import REQUIRED_NOTES_1B

    notes_dir = ROOT / "itemdb" / "notes"
    evidence_root = ROOT / "itemdb" / "evidence"
    counts = count_findings()
    rows: list[tuple[str, str, str]] = []

    # Phase 1a
    has_1a = all(
        (notes_dir / name).is_file()
        for name in ("target-profile.md", "build-model.md", "codeql-plan.yml")
    )
    rows.append(("Phase 1a", "ok" if has_1a else "info", "completed" if has_1a else "not run"))

    # CodeQL
    manifest_path = ROOT / "itemdb" / "codeql" / "run-manifest.yml"
    if manifest_path.is_file():
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            status = manifest.get("status", "unknown") if isinstance(manifest, dict) else "unknown"
        except Exception:
            status = "unknown"
        level = "ok" if status == "completed" else "warn" if status == "soft-failed" else "info"
        rows.append(("CodeQL", level, status))
    else:
        rows.append(("CodeQL", "info", "not run"))

    # Phase 1b
    missing_1b = [n for n in REQUIRED_NOTES_1B if not (notes_dir / n).is_file()]
    if not missing_1b:
        rows.append(("Phase 1b", "ok", "completed"))
    elif len(missing_1b) < len(REQUIRED_NOTES_1B):
        rows.append(("Phase 1b", "warn", f"{len(missing_1b)} of {len(REQUIRED_NOTES_1B)} notes missing"))
    else:
        rows.append(("Phase 1b", "info", "not run"))

    # Phase 1c
    has_1c = (notes_dir / "sandbox-plan.md").is_file()
    rows.append(("Phase 1c", "ok" if has_1c else "info", "completed" if has_1c else "not run"))

    # Phase 2
    pending = counts["PENDING"]
    rows.append(("Phase 2", "ok" if pending else "info", f"{pending} PENDING findings" if pending else "not run"))

    # Phase 3
    reviewed = counts["CONFIRMED"] + counts["EXPLOITED"] + counts["REJECTED"] + counts["DUPLICATE"]
    rows.append(("Phase 3", "ok" if reviewed else "info", f"{reviewed} reviewed" if reviewed else "not run"))

    # Phase 4
    confirmed = counts["CONFIRMED"] + counts["EXPLOITED"]
    rows.append(("Phase 4", "ok" if confirmed else "info", f"{confirmed} confirmed" if confirmed else "not run"))

    # Phase 5
    exploited = counts["EXPLOITED"]
    rows.append(("Phase 5", "ok" if exploited else "info", f"{exploited} exploited" if exploited else "not run"))

    # Phase 6
    has_report = (ROOT / "itemdb" / "reports" / "report.md").is_file()
    rows.append(("Phase 6", "ok" if has_report else "info", "completed" if has_report else "not run"))

    print()
    print(C.header("Phase progress:"))
    label_width = max(len(label) for label, _, _ in rows)
    for label, level, detail in rows:
        prefix = "  " + label.ljust(label_width)
        if level == "ok":
            print(C.ok(f"{prefix}  {detail}"))
        elif level == "warn":
            print(C.warn(f"{prefix}  {detail}"))
        else:
            print(C.info(f"{prefix}  {detail}"))


def check_codeql_status() -> int:
    """Check CodeQL configuration and last recorded artifact state."""
    print()
    print(C.header("CodeQL:"))
    # TODO: move CodeQL check logic to tools/codecome/checks.py (see GH issue)
    try:
        from codeql.config import resolve_config
        from codeql.artifacts import check_artifacts
        from codeql.packs import load_codeql_plan
    except ImportError as exc:
        print(C.warn(f"CodeQL checks unavailable: {exc}"))
        return 0

    config = resolve_config()
    manifest_path = config.abs_output_dir / "run-manifest.yml"
    manifest = None

    if manifest_path.is_file() and yaml is not None:
        try:
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest = loaded if isinstance(loaded, dict) else None
        except (OSError, yaml.YAMLError, UnicodeDecodeError):
            manifest = None

    current_state = "enabled" if config.enabled else "disabled"
    print(C.ok(f"current config: CodeQL {current_state}"))

    if manifest and manifest.get("status") == "skipped" and manifest.get("codeql_enabled") is False:
        reason = manifest.get("skip_reason") or "CodeQL disabled during recorded run"
        print(C.ok(f"last phase-1 CodeQL state: skipped ({reason})"))
        print(C.info("No CodeQL artifacts are required for that recorded run."))
        return 0

    if not config.enabled:
        print(C.ok("CodeQL disabled for current invocation; artifact checks skipped."))
        return 0

    exit_code = 0
    if config.phase_1_enabled:
        print(C.ok("phase-1 integration: enabled"))
    else:
        print(C.ok("phase-1 integration: disabled; artifact checks skipped."))
        return 0

    if config.abs_install_path.is_file():
        print(C.ok(f"binary: {config.abs_install_path.relative_to(ROOT) if config.abs_install_path.is_relative_to(ROOT) else config.abs_install_path}"))
    else:
        print(C.fail(f"binary missing: {config.abs_install_path}"))
        exit_code = 1

    if config.abs_pack_catalog.is_file():
        print(C.ok(f"pack catalog: {config.abs_pack_catalog.relative_to(ROOT) if config.abs_pack_catalog.is_relative_to(ROOT) else config.abs_pack_catalog}"))
    else:
        print(C.fail(f"pack catalog missing: {config.abs_pack_catalog}"))
        exit_code = 1

    plan_path = ROOT / "itemdb" / "notes" / "codeql-plan.yml"
    if plan_path.is_file():
        try:
            load_codeql_plan(plan_path)
            print(C.ok("plan: itemdb/notes/codeql-plan.yml"))
        except Exception as exc:
            print(C.fail(f"plan invalid: {exc}"))
            exit_code = 1
    elif _phase_1_notes_exist():
        print(C.warn("plan missing after Phase 1 notes exist: itemdb/notes/codeql-plan.yml"))
    else:
        print(C.info("Phase 1 has not produced a CodeQL plan yet; no artifacts expected."))
        return exit_code

    artifact_status, warnings = check_artifacts(config.abs_output_dir)
    if artifact_status == "missing":
        if _phase_1_notes_exist():
            print(C.warn("artifacts: missing run-manifest.yml; run make phase-1 to refresh CodeQL state."))
        else:
            print(C.info("artifacts: not present yet; Phase 1 has not run."))
    elif artifact_status == "completed" and not warnings:
        print(C.ok("artifacts: completed"))
    elif artifact_status == "soft-failed":
        print(C.warn("artifacts: soft-failed"))
        for warning in warnings:
            print(C.warn(f"  {warning}"))
        if (manifest or {}).get("fail_policy", config.fail_policy) == "hard":
            exit_code = 1
    elif artifact_status == "skipped":
        print(C.ok("artifacts: skipped"))
        for warning in warnings:
            print(C.info(f"  {warning}"))
    else:
        formatter = C.fail if artifact_status in {"failed", "unknown"} else C.warn
        print(formatter(f"artifacts: {artifact_status}"))
        for warning in warnings:
            print(formatter(f"  {warning}"))
        if artifact_status in {"completed", "failed", "unknown"}:
            exit_code = 1

    return exit_code


def check_sandbox_status() -> None:
    """Print sandbox state, gate result, and capability summary."""
    import importlib

    try:
        sb = importlib.import_module("sandbox-bootstrap")
    except Exception:
        print()
        print(C.header("Sandbox:"))
        print(C.warn("sandbox-bootstrap module unavailable"))
        return

    print()
    print(C.header("Sandbox:"))

    provenance = sb.read_provenance()
    last_validation = sb._last_validation_outcome()
    allow_no_sandbox = bool(os.environ.get("CODECOME_ALLOW_NO_SANDBOX"))
    sandbox_state = sb.classify_sandbox_state()

    # Gate logic (mirrors cmd_status)
    if allow_no_sandbox:
        gate_pass = True
        gate_reason = "override (CODECOME_ALLOW_NO_SANDBOX=1)"
    elif sandbox_state == "pending":
        gate_pass = False
        gate_reason = "sandbox bootstrap pending; run make phase-1"
    elif sandbox_state == "missing":
        gate_pass = False
        gate_reason = "sandbox is missing"
    elif sandbox_state == "generated" and last_validation == "failed":
        gate_pass = False
        gate_reason = "last validation failed"
    elif sandbox_state == "generated" and last_validation == "skipped":
        gate_pass = False
        gate_reason = "last validation has no real outcomes (all tiers skipped)"
    else:
        gate_pass = True
        if sandbox_state == "user-managed":
            gate_reason = "sandbox is user-managed (validation not enforced)"
        elif last_validation is None:
            gate_reason = "no validation run on record"
        elif last_validation == "passed":
            gate_reason = "last validation passed"
        elif last_validation == "mixed":
            gate_reason = "last validation passed (some tiers skipped)"
        else:
            gate_reason = f"last validation: {last_validation}"

    # Print summary
    state_detail = sandbox_state
    if sandbox_state == "generated" and provenance:
        state_detail = "generated (provenance present)"
    print(f"  {C.DIM}state:{C.RESET}            {state_detail}")
    print(f"  {C.DIM}last validation:{C.RESET}  {last_validation or '-'}")
    if gate_pass:
        print(C.ok(f"  Phase 2 gate:     pass ({gate_reason})"))
    else:
        print(C.warn(f"  Phase 2 gate:     block ({gate_reason})"))

    # Capabilities
    capability_status = sb._capability_status()
    print(f"  {C.DIM}capabilities:{C.RESET}")
    for name in ("setup", "start", "check", "build", "test", "stop", "shell", "logs", "clean", "reset"):
        status = capability_status[name]
        satisfied = status.get("satisfied", False)
        missing_label = "pending" if sandbox_state == "pending" else "missing"
        state_str = C.ok("ok") if satisfied else C.warn(missing_label)
        print(f"    {name:<8} {state_str}  {status['path']}")


def command_check(_: argparse.Namespace) -> int:
    missing = []

    for relative_path in REQUIRED_PATHS:
        path = ROOT / relative_path
        if not path.exists():
            missing.append(relative_path)

    try:
        config = load_config()
    except Exception as exc:
        return fail(str(exc))

    if missing:
        print(C.fail("Missing required paths:"))
        for item in missing:
            print(f"  {C.SYM_BULLET} {item}")
        return 1

    project_name = config.get("project", {}).get("name", "unknown")
    print(C.ok(f"Workspace OK: {C.BOLD}{project_name}{C.RESET}"))

    # Warn if src/ has no actual content (only .gitkeep or empty).
    src_dir = ROOT / "src"
    has_source = any(
        p.name != ".gitkeep" for p in src_dir.iterdir()
    ) if src_dir.is_dir() else False
    if not has_source:
        print(C.warn("src/ is empty — place your target source code there before running phase-1."))

    check_phase_progress()
    check_exit = check_codeql_status()
    check_sandbox_status()

    print()

    # Warn (do not fail) about missing optional recording tools used by Phase 5.
    recording_warnings = check_recording_tools()
    if recording_warnings:
        print(C.header("Recording tools:"))
        for message in recording_warnings:
            print(C.warn(message))
    else:
        print(C.header("Recording tools:"))
        print(C.ok("all tools available (asciinema, agg, ffmpeg, Xvfb)."))

    # Probe only the current helper invocation context; phase-5 may later run
    # from a different shell, container, or PTY wrapper.
    print()
    print(C.header("Recording probe (current invocation context):"))
    probe_rows = probe_recording_environment()
    label_width = max(len(label) for label, _, _ in probe_rows)
    for label, status, detail in probe_rows:
        line = f"  {label.ljust(label_width)}  {detail}"
        if status == "ok":
            print(C.ok(line))
        elif status == "warn":
            print(C.warn(line))
        else:
            print(C.info(line))
    print(
        "  Recording may still succeed from a different context "
        "(host shell, sandbox shell, container exec session, or PTY wrapper)."
    )
    print(
        "  See `.opencode/skills/exploit-recording/SKILL.md` for context selection "
        "and PTY-acquisition guidance."
    )

    return check_exit


def command_status(_: argparse.Namespace) -> int:
    try:
        config = load_config()
    except Exception as exc:
        return fail(str(exc))

    project_name = config.get("project", {}).get("name", "unknown")
    source_path = config.get("project", {}).get("source_path", "./src")

    print(f"{C.BOLD}Project:{C.RESET} {project_name}")
    print(f"{C.BOLD}Source:{C.RESET}  {source_path}")
    print()
    print(f"{C.BOLD}Findings:{C.RESET}")

    for status, count in count_findings().items():
        colored_status = C.status_color(f"{status:20}")
        print(f"  {colored_status} {count}")

    return 0


def command_next_id(_: argparse.Namespace) -> int:
    ids = collect_finding_ids(iter_finding_files())
    next_id = max(ids, default=0) + 1
    print(f"CC-{next_id:04d}")
    return 0


def command_check_codeql_plan(_: argparse.Namespace) -> int:
    from codecome.phase_1 import _validate_codeql_plan_for_repair
    rc, out = _validate_codeql_plan_for_repair()
    if out:
        print(out)
    return rc


def command_hints(_: argparse.Namespace) -> int:
    from codecome.run_summary_questions import (
        find_latest_summary,
        parse_summary,
    )

    phases = ("1a", "1b", "1c", "2", "3", "4", "5", "6")
    found_any = False

    print()
    print(C.header("Open questions & re-run hints"))
    print()

    for phase_id in phases:
        summary_path = find_latest_summary(phase_id)
        if not summary_path:
            continue

        try:
            qs = parse_summary(summary_path)
        except Exception:
            continue

        if not qs.has_content():
            continue

        found_any = True
        rel = summary_path.relative_to(ROOT)
        print(f"  {C.BOLD_CYAN}Phase {phase_id}{C.RESET}  {C.DIM}·  {rel}{C.RESET}")
        print()

        for q in qs.open_questions:
            print(f"  {C.colorize(q.question, C.YELLOW)}")
            if q.why_it_matters:
                print(f"    {C.DIM}Why:{C.RESET} {q.why_it_matters}")
            if q.affects:
                print(f"    {C.DIM}Affects:{C.RESET} {q.affects}")
            if q.suggested_format:
                print(f"    {C.DIM}Answer:{C.RESET} {q.suggested_format}")
            print()

        if qs.rerun_hints:
            print(f"  {C.BOLD_CYAN}Re-run hints:{C.RESET}")
            for line in qs.rerun_hints.split("\n"):
                stripped = line.strip()
                if stripped:
                    print(f"    {stripped}")
            print()

    if found_any:
        print(C.SYM_DASH * 62)
        print("Answer questions by re-running the phase with:")
        print()
        print("    PROMPT_EXTRA=\"your answer\" make phase-<N>")
        print("    PROMPT_EXTRA_FILE=path/to/answers.txt make phase-<N>")
    else:
        print("  No open questions or re-run hints found.")
        print("  Run phases first to populate run summaries.")

    print()
    return 0


def command_check_phase_artifacts(args: argparse.Namespace) -> int:
    from phases.artifact_checks import check_phase_artifacts
    return check_phase_artifacts(
        phase=args.phase,
        allow_missing_generated=args.allow_missing_generated_artifacts,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codecome",
        description="Small helper CLI for the CodeCome workspace.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Validate the workspace structure and config.")
    check_parser.set_defaults(func=command_check)

    status_parser = subparsers.add_parser("status", help="Show a basic workspace status summary.")
    status_parser.set_defaults(func=command_status)

    next_id_parser = subparsers.add_parser("next-id", help="Print the next available finding id.")
    next_id_parser.set_defaults(func=command_next_id)

    check_plan_parser = subparsers.add_parser("check-codeql-plan", help="Validate itemdb/notes/codeql-plan.yml")
    check_plan_parser.set_defaults(func=command_check_codeql_plan)

    hints_parser = subparsers.add_parser("hints", help="Print open questions and re-run hints from all phase run summaries.")
    hints_parser.set_defaults(func=command_hints)

    check_artifacts_parser = subparsers.add_parser(
        "check-phase-artifacts",
        help="Validate phase-generated artifacts (post-generation quality).",
    )
    check_artifacts_parser.add_argument(
        "--phase", required=True,
        help="Phase to validate: 1a, 1b, 1c, 1, all"
    )
    check_artifacts_parser.add_argument(
        "--allow-missing-generated-artifacts", action="store_true",
        dest="allow_missing_generated_artifacts",
        help="Skip errors for phase-generated artifacts not yet produced.",
    )
    check_artifacts_parser.set_defaults(func=command_check_phase_artifacts)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
