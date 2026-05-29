# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Reusable Phase 1 subphase gate logic.

This module holds the implementation for the Phase 1a/1b/1c checks so the
root ``tools/gate-check.py`` script can remain a thin CLI wrapper.
"""

from __future__ import annotations

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

import _colors as C

from codecome.config import ROOT


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

FINDING_STATUS_DIRS = [
    "PENDING",
    "CONFIRMED",
    "EXPLOITED",
    "REJECTED",
    "DUPLICATE",
]

try:
    from rich.console import Console as _RichConsole

    HAVE_RICH = True
except ImportError:  # pragma: no cover
    _RichConsole = None  # type: ignore[assignment]
    HAVE_RICH = False


def _emit(console, level: str, text: str) -> None:
    """Emit a gate message through rich Console or plain output."""
    if console is not None and HAVE_RICH:
        from rich.text import Text

        style_map = {
            "header": "bold cyan",
            "ok": "green",
            "fail": "bold red",
            "warn": "yellow",
            "info": "dim",
        }
        console.print(Text(text, style=style_map.get(level, "")))
        return

    fn_map = {
        "header": C.header,
        "ok": C.ok,
        "fail": C.fail,
        "warn": C.warn,
        "info": C.info,
    }
    fn_map.get(level, print)(text)


def _emit_separator(console, style: str = "green") -> None:
    """Emit a visual separator for rich/plain output."""
    if console is not None and HAVE_RICH:
        from rich.rule import Rule

        console.print(Rule(style=style))
    else:
        print()


def _notes_exist(*names: str) -> list[str]:
    """Return names of note files missing from ``itemdb/notes``."""
    notes_dir = ROOT / "itemdb" / "notes"
    return [name for name in names if not (notes_dir / name).exists()]


def count_findings_snapshot(snapshot: dict[str, int] | None = None) -> dict[str, int]:
    """Return finding counts, or deltas from a previous snapshot."""
    findings_root = ROOT / "itemdb" / "findings"
    current: dict[str, int] = {}
    for status in FINDING_STATUS_DIRS:
        status_dir = findings_root / status
        current[status] = len(list(status_dir.glob("CC-*.md"))) if status_dir.exists() else 0
    if snapshot is None:
        return current
    return {status: max(0, current[status] - snapshot.get(status, 0)) for status in FINDING_STATUS_DIRS}


def check_phase_1a(console=None) -> int:
    """Gate 1a: target-profile/build-model/codeql-plan outputs must exist."""
    _emit(console, "header", "Gate 1a: Target Profile")
    _emit_separator(console, "cyan")

    notes_dir = ROOT / "itemdb" / "notes"
    required = ["target-profile.md", "build-model.md", "codeql-plan.yml"]
    missing = [name for name in required if not (notes_dir / name).exists()]
    if missing:
        _emit(console, "fail", "Required Phase 1a outputs are missing:")
        for name in missing:
            _emit(console, "info", f"    itemdb/notes/{name}")
        _emit(console, "info", "Run Phase 1a first.")
        return 1

    _emit(console, "ok", "itemdb/notes/target-profile.md exists")
    _emit(console, "ok", "itemdb/notes/build-model.md exists")
    _emit(console, "ok", "itemdb/notes/codeql-plan.yml exists")

    plan_path = notes_dir / "codeql-plan.yml"
    if yaml is None:
        _emit(console, "warn", "Cannot validate codeql-plan.yml: PyYAML not available")
    else:
        try:
            plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
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
                    _emit(
                        console,
                        "warn",
                        f"codeql-plan.yml: language '{lang.get('id', '?')}' has unexpected confidence '{lang.get('confidence')}'",
                    )
                if lang.get("build_mode") not in valid_build_modes:
                    _emit(
                        console,
                        "warn",
                        f"codeql-plan.yml: language '{lang.get('id', '?')}' has unexpected build_mode '{lang.get('build_mode')}'",
                    )
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
    """Gate 1b: recon notes and file-risk-index.yml must be valid."""
    _emit(console, "header", "Gate 1b: CodeQL-assisted Reconnaissance")
    _emit_separator(console, "cyan")

    missing = _notes_exist(*REQUIRED_NOTES_1B)
    if missing:
        _emit(console, "fail", "Required Phase 1b reconnaissance notes are missing:")
        for name in missing:
            _emit(console, "info", f"    itemdb/notes/{name}")
        _emit(console, "info", "Run Phase 1b first.")
        return 1

    for name in REQUIRED_NOTES_1B:
        _emit(console, "ok", f"itemdb/notes/{name} exists")

    risk_path = ROOT / "itemdb" / "notes" / "file-risk-index.yml"
    if yaml is not None:
        try:
            data = yaml.safe_load(risk_path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
            _emit(console, "fail", f"file-risk-index.yml is not valid YAML: {exc}")
            return 1

        if not isinstance(data, dict):
            _emit(console, "fail", "file-risk-index.yml: must be a mapping")
            return 1

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
                _emit(console, "warn", f"file-risk-index.yml: path '{path_val}' is not workspace-relative")
            score = entry.get("score")
            if score is not None:
                try:
                    score_int = int(score)
                    if score_int < 1 or score_int > 5:
                        _emit(console, "warn", f"file-risk-index.yml: score {score} for '{path_val}' is not in 1..5")
                except (TypeError, ValueError):
                    _emit(console, "warn", f"file-risk-index.yml: non-integer score '{score}' for '{path_val}'")

        _emit(console, "ok", f"file-risk-index.yml: {len(files)} file(s) indexed")

    if findings_snapshot is not None:
        delta = count_findings_snapshot(findings_snapshot)
        new_findings = sum(delta.values())
        if new_findings > 0:
            _emit(
                console,
                "warn",
                f"{new_findings} new finding(s) were created during Phase 1b. Findings should not be created during reconnaissance.",
            )
            for status, count in delta.items():
                if count > 0:
                    _emit(console, "info", f"    {status}: +{count}")

    _emit_separator(console, "green")
    _emit(console, "ok", "Ready to run Phase 1c (Sandbox Bootstrap).")
    return 0


def check_phase_1c(console=None) -> int:
    """Gate 1c: sandbox-plan.md must exist and sandbox provenance is checked."""
    _emit(console, "header", "Gate 1c: Sandbox Bootstrap")
    _emit_separator(console, "cyan")

    plan_path = ROOT / "itemdb" / "notes" / "sandbox-plan.md"
    if not plan_path.exists():
        _emit(console, "fail", "itemdb/notes/sandbox-plan.md does not exist")
        _emit(console, "info", "Run Phase 1c first.")
        return 1

    _emit(console, "ok", "itemdb/notes/sandbox-plan.md exists")

    provenance = ROOT / "sandbox" / "CODECOME-GENERATED.md"
    has_provenance = provenance.exists()
    sandbox_dir = ROOT / "sandbox"
    has_sandbox = sandbox_dir.exists() and any(entry.name != ".gitkeep" for entry in sandbox_dir.iterdir())

    if has_provenance:
        _emit(console, "ok", "sandbox/CODECOME-GENERATED.md exists")
    elif has_sandbox:
        _emit(console, "warn", "sandbox/ exists without CODECOME-GENERATED.md - may be user-managed")
    else:
        _emit(console, "warn", "sandbox/ is empty or does not exist")

    _emit_separator(console, "green")
    _emit(console, "ok", "Phase 1 complete. Ready to run Phase 2.")
    return 0
