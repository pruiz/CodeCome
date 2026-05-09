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
import platform
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

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
                "is available."
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

    # Warn (do not fail) about missing optional recording tools used by Phase 5.
    recording_warnings = check_recording_tools()
    if recording_warnings:
        print()
        print(C.header("Optional recording tools (used by phase-5 exploit demonstrations):"))
        for message in recording_warnings:
            print(C.warn(message))
    else:
        print(C.ok("Optional recording tools available (asciinema, agg, ffmpeg, Xvfb)."))

    return 0


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

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
