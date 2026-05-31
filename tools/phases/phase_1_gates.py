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
from codeql.capabilities import is_supported_language, supported_build_modes

try:
    from codeql.config import resolve_config as _resolve_codeql_config
except ImportError:
    _resolve_codeql_config = None  # type: ignore[assignment]


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
    formatter = fn_map.get(level)
    print(formatter(text) if formatter else text)


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


def _codeql_fail_policy() -> str:
    """Return configured CodeQL fail policy, defaulting to soft on errors."""
    if _resolve_codeql_config is None:
        return "soft"
    try:
        return _resolve_codeql_config().fail_policy
    except Exception:
        return "soft"


def _validate_codeql_language_entry(
    *,
    console,
    unit_id: str,
    lang: object,
    index: int,
    seen_databases: set[tuple[str, str]],
    valid_confidences: set[str],
) -> int | None:
    """Validate one language entry from codeql-plan.yml."""
    if not isinstance(lang, dict):
        _emit(console, "fail", f"codeql-plan.yml: analysis unit '{unit_id}' language entry {index} is not a mapping")
        return 1
    language_id = lang.get("id")
    if not isinstance(language_id, str) or not language_id:
        _emit(console, "fail", f"codeql-plan.yml: analysis unit '{unit_id}' language entry {index} missing valid 'id'")
        return 1
    if not is_supported_language(language_id):
        fail_policy = _codeql_fail_policy()
        if fail_policy == "hard":
            _emit(console, "fail", f"codeql-plan.yml: unsupported CodeQL language '{language_id}' in analysis unit '{unit_id}'")
            return 1
        _emit(console, "warn", f"codeql-plan.yml: unsupported CodeQL language '{language_id}' in analysis unit '{unit_id}' — will be skipped (fail_policy=soft)")
        return None
    db_key = (unit_id, language_id)
    if db_key in seen_databases:
        _emit(console, "fail", f"codeql-plan.yml: duplicate language '{language_id}' in analysis unit '{unit_id}'")
        return 1
    seen_databases.add(db_key)
    if lang.get("confidence") not in valid_confidences:
        _emit(
            console,
            "warn",
            f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' has unexpected confidence '{lang.get('confidence')}'",
        )
    build_mode = lang.get("build_mode")
    supported_modes = supported_build_modes(language_id)
    if build_mode not in supported_modes:
        allowed = ", ".join(sorted(supported_modes))
        _emit(console, "fail", f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' has unsupported build_mode '{build_mode}' (allowed: {allowed})")
        return 1
    build_command = lang.get("build_command")
    if build_mode == "manual" and not (isinstance(build_command, str) and build_command.strip()):
        _emit(console, "fail", f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' uses manual build without build_command")
        return 1
    if "packs" not in lang:
        _emit(console, "fail", f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' missing 'packs'")
        return 1
    if not isinstance(lang["packs"], list) or len(lang["packs"]) == 0:
        _emit(console, "fail", f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' has empty packs list")
        return 1
    return None


def _validate_codeql_analysis_unit(
    *,
    console,
    unit: object,
    index: int,
    seen_unit_ids: set[str],
    seen_databases: set[tuple[str, str]],
    valid_confidences: set[str],
) -> int | None:
    """Validate one analysis unit from codeql-plan.yml."""
    if not isinstance(unit, dict):
        _emit(console, "fail", f"codeql-plan.yml: analysis unit {index} is not a mapping")
        return 1
    unit_id = unit.get("id")
    if not isinstance(unit_id, str) or not unit_id:
        _emit(console, "fail", f"codeql-plan.yml: analysis unit {index} missing valid 'id'")
        return 1
    if unit_id in seen_unit_ids:
        _emit(console, "fail", f"codeql-plan.yml: duplicate analysis unit id '{unit_id}'")
        return 1
    seen_unit_ids.add(unit_id)

    unit_path = unit.get("path")
    if not isinstance(unit_path, str) or not unit_path:
        _emit(console, "fail", f"codeql-plan.yml: analysis unit '{unit_id}' missing valid 'path'")
        return 1
    resolved_path = (ROOT / unit_path).resolve()
    src_root = (ROOT / "src").resolve()
    try:
        under_src = resolved_path == src_root or resolved_path.is_relative_to(src_root)
    except ValueError:
        under_src = False
    if not under_src:
        _emit(console, "fail", f"codeql-plan.yml: analysis unit '{unit_id}' path must be under src/: {unit_path}")
        return 1
    if "_codeql_detected_source_root" in resolved_path.parts:
        _emit(console, "fail", f"codeql-plan.yml: analysis unit '{unit_id}' path uses CodeQL-generated helper path")
        return 1
    if not resolved_path.exists():
        _emit(console, "fail", f"codeql-plan.yml: analysis unit '{unit_id}' path does not exist: {unit_path}")
        return 1

    languages = unit.get("languages")
    if unit.get("recommended") is False and (languages is None or languages == []):
        _emit(console, "info", f"codeql-plan.yml: analysis unit '{unit_id}' is not recommended for CodeQL; skipping language validation")
        return None
    if not isinstance(languages, list) or len(languages) == 0:
        _emit(console, "fail", f"codeql-plan.yml: analysis unit '{unit_id}' has no languages")
        return 1

    for j, lang in enumerate(languages):
        result = _validate_codeql_language_entry(
            console=console,
            unit_id=unit_id,
            lang=lang,
            index=j,
            seen_databases=seen_databases,
            valid_confidences=valid_confidences,
        )
        if result is not None:
            return result
    return None


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


def check_phase_1a(console=None, findings_snapshot: dict[str, int] | None = None) -> int:
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

    if findings_snapshot is not None:
        delta = count_findings_snapshot(findings_snapshot)
        new_findings = sum(delta.values())
        if new_findings > 0:
            _emit(
                console,
                "warn",
                f"{new_findings} new finding(s) were created during Phase 1a. Findings should not be created during reconnaissance.",
            )
            for status, count in delta.items():
                if count > 0:
                    _emit(console, "info", f"    {status}: +{count}")

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
            units = plan.get("analysis_units", [])
            if not isinstance(units, list) or len(units) == 0:
                _emit(console, "fail", "codeql-plan.yml: recommended=true but no analysis_units entries")
                return 1

            valid_confidences = {"HIGH", "MEDIUM", "LOW"}
            seen_unit_ids: set[str] = set()
            seen_databases: set[tuple[str, str]] = set()
            for i, unit in enumerate(units):
                result = _validate_codeql_analysis_unit(
                    console=console,
                    unit=unit,
                    index=i,
                    seen_unit_ids=seen_unit_ids,
                    seen_databases=seen_databases,
                    valid_confidences=valid_confidences,
                )
                if result is not None:
                    return result

            _emit(console, "ok", f"codeql-plan.yml: {len(units)} analysis unit(s) configured")

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
            if path_val == "src/example/path/to/file.ext":
                _emit(console, "fail", "file-risk-index.yml: contains template placeholder entry ('src/example/path/to/file.ext')")
                return 1
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
