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

from codecome.config import ROOT
from codeql.capabilities import is_supported_language, supported_build_modes
from rendering.output import get_output, T

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
    "threat-model.md",
]

FINDING_STATUS_DIRS = [
    "PENDING",
    "CONFIRMED",
    "EXPLOITED",
    "REJECTED",
    "DUPLICATE",
]


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
    out,
    unit_id: str,
    lang: object,
    index: int,
    seen_databases: set[tuple[str, str]],
    valid_confidences: set[str],
) -> int | None:
    """Validate one language entry from codeql-plan.yml."""
    if not isinstance(lang, dict):
        out.error(f"codeql-plan.yml: analysis unit '{unit_id}' language entry {index} is not a mapping")
        return 1
    language_id = lang.get("id")
    if not isinstance(language_id, str) or not language_id:
        out.error(f"codeql-plan.yml: analysis unit '{unit_id}' language entry {index} missing valid 'id'")
        return 1
    if not is_supported_language(language_id):
        fail_policy = _codeql_fail_policy()
        if fail_policy == "hard":
            out.error(f"codeql-plan.yml: unsupported CodeQL language '{language_id}' in analysis unit '{unit_id}'")
            return 1
        out.warn(f"codeql-plan.yml: unsupported CodeQL language '{language_id}' in analysis unit '{unit_id}' — will be skipped (fail_policy=soft)")
        return None
    db_key = (unit_id, language_id)
    if db_key in seen_databases:
        out.error(f"codeql-plan.yml: duplicate language '{language_id}' in analysis unit '{unit_id}'")
        return 1
    seen_databases.add(db_key)
    if lang.get("confidence") not in valid_confidences:
        out.warn(
            f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' has unexpected confidence '{lang.get('confidence')}'",
        )
    build_mode = lang.get("build_mode")
    supported_modes = supported_build_modes(language_id)
    if build_mode not in supported_modes:
        allowed = ", ".join(sorted(supported_modes))
        out.error(f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' has unsupported build_mode '{build_mode}' (allowed: {allowed})")
        return 1
    build_command = lang.get("build_command")
    build_provider = lang.get("build_provider")
    recipe_backed = build_provider == "sandbox-recipe"
    if build_mode == "manual" and not recipe_backed and not (isinstance(build_command, str) and build_command.strip()):
        out.error(f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' uses manual build without build_command")
        return 1
    if "packs" not in lang:
        out.error(f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' missing 'packs'")
        return 1
    if not isinstance(lang["packs"], list) or len(lang["packs"]) == 0:
        out.error(f"codeql-plan.yml: language '{language_id}' in analysis unit '{unit_id}' has empty packs list")
        return 1
    return None


def _validate_codeql_analysis_unit(
    *,
    out,
    unit: object,
    index: int,
    seen_unit_ids: set[str],
    seen_databases: set[tuple[str, str]],
    valid_confidences: set[str],
) -> int | None:
    """Validate one analysis unit from codeql-plan.yml."""
    if not isinstance(unit, dict):
        out.error(f"codeql-plan.yml: analysis unit {index} is not a mapping")
        return 1
    unit_id = unit.get("id")
    if not isinstance(unit_id, str) or not unit_id:
        out.error(f"codeql-plan.yml: analysis unit {index} missing valid 'id'")
        return 1
    if unit_id in seen_unit_ids:
        out.error(f"codeql-plan.yml: duplicate analysis unit id '{unit_id}'")
        return 1
    seen_unit_ids.add(unit_id)

    unit_path = unit.get("path")
    if not isinstance(unit_path, str) or not unit_path:
        out.error(f"codeql-plan.yml: analysis unit '{unit_id}' missing valid 'path'")
        return 1
    resolved_path = (ROOT / unit_path).resolve()
    src_root = (ROOT / "src").resolve()
    try:
        under_src = resolved_path == src_root or resolved_path.is_relative_to(src_root)
    except ValueError:
        under_src = False
    if not under_src:
        out.error(f"codeql-plan.yml: analysis unit '{unit_id}' path must be under src/: {unit_path}")
        return 1
    if "_codeql_detected_source_root" in resolved_path.parts:
        out.error(f"codeql-plan.yml: analysis unit '{unit_id}' path uses CodeQL-generated helper path")
        return 1
    if not resolved_path.exists():
        out.error(f"codeql-plan.yml: analysis unit '{unit_id}' path does not exist: {unit_path}")
        return 1

    languages = unit.get("languages")
    if unit.get("recommended") is False and (languages is None or languages == []):
        out.info(f"codeql-plan.yml: analysis unit '{unit_id}' is not recommended for CodeQL; skipping language validation")
        return None
    if not isinstance(languages, list):
        out.error(f"codeql-plan.yml: analysis unit '{unit_id}' has no languages")
        return 1
    if len(languages) == 0:
        fail_policy = _codeql_fail_policy()
        if fail_policy == "hard":
            out.error(f"codeql-plan.yml: analysis unit '{unit_id}' has no CodeQL languages and is not marked recommended=false")
            return 1
        out.warn(
            f"codeql-plan.yml: analysis unit '{unit_id}' has no CodeQL languages — will be skipped (fail_policy=soft); "
            "mark recommended=false or move unsupported-language inventory to top-level notes"
        )
        return None

    for j, lang in enumerate(languages):
        result = _validate_codeql_language_entry(
            out=out,
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
    out = get_output(console)
    out.header("Gate 1a: Target Profile")
    out.separator(tone=T.SECTION)

    notes_dir = ROOT / "itemdb" / "notes"
    required = ["target-profile.md", "build-model.md", "codeql-plan.yml"]
    missing = [name for name in required if not (notes_dir / name).exists()]
    if missing:
        out.error("Required Phase 1a outputs are missing:")
        for name in missing:
            out.info(f"    itemdb/notes/{name}")
        out.info("Run Phase 1a first.")
        return 1

    out.success("itemdb/notes/target-profile.md exists")
    out.success("itemdb/notes/build-model.md exists")
    out.success("itemdb/notes/codeql-plan.yml exists")

    if findings_snapshot is not None:
        delta = count_findings_snapshot(findings_snapshot)
        new_findings = sum(delta.values())
        if new_findings > 0:
            out.warn(
                f"{new_findings} new finding(s) were created during Phase 1a. Findings should not be created during reconnaissance.",
            )
            for status, count in delta.items():
                if count > 0:
                    out.info(f"    {status}: +{count}")

    plan_path = notes_dir / "codeql-plan.yml"
    if yaml is None:
        out.warn("Cannot validate codeql-plan.yml: PyYAML not available")
    else:
        try:
            from codeql.packs import load_codeql_plan
            plan = load_codeql_plan(plan_path)
        except Exception as exc:
            out.error(f"codeql-plan.yml: {exc}")
            return 1

        if plan.get("recommended") is True:
            units = plan.get("analysis_units", [])
            if not isinstance(units, list) or len(units) == 0:
                out.error("codeql-plan.yml: recommended=true but no analysis_units entries")
                return 1

            valid_confidences = {"HIGH", "MEDIUM", "LOW"}
            seen_unit_ids: set[str] = set()
            seen_databases: set[tuple[str, str]] = set()
            for i, unit in enumerate(units):
                result = _validate_codeql_analysis_unit(
                    out=out,
                    unit=unit,
                    index=i,
                    seen_unit_ids=seen_unit_ids,
                    seen_databases=seen_databases,
                    valid_confidences=valid_confidences,
                )
                if result is not None:
                    return result

            out.success(f"codeql-plan.yml: {len(units)} analysis unit(s) configured")

    out.separator(tone=T.SUCCESS)
    out.success("Ready to run Phase 1b (Sandbox Bootstrap).")
    return 0


def check_phase_1c(console=None, findings_snapshot: dict[str, int] | None = None) -> int:
    """Gate 1c: recon notes and file-risk-index.yml must be valid."""
    out = get_output(console)
    out.header("Gate 1c: Detailed Reconnaissance")
    out.separator(tone=T.SECTION)

    missing = _notes_exist(*REQUIRED_NOTES_1B)
    if missing:
        out.error("Required Phase 1c reconnaissance notes are missing:")
        for name in missing:
            out.info(f"    itemdb/notes/{name}")
        out.info("Run Phase 1c first.")
        return 1

    for name in REQUIRED_NOTES_1B:
        out.success(f"itemdb/notes/{name} exists")

    risk_path = ROOT / "itemdb" / "notes" / "file-risk-index.yml"
    if yaml is not None:
        try:
            data = yaml.safe_load(risk_path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
            out.error(f"file-risk-index.yml is not valid YAML: {exc}")
            return 1

        if not isinstance(data, dict):
            out.error("file-risk-index.yml: must be a mapping")
            return 1

        if "schema_version" not in data:
            out.warn("file-risk-index.yml: missing 'schema_version'")
        files = data.get("files")
        if files is None:
            out.error("file-risk-index.yml: missing 'files' key")
            return 1
        if not isinstance(files, list):
            out.error("file-risk-index.yml: 'files' is not a list")
            return 1

        for entry in files:
            if not isinstance(entry, dict):
                continue
            path_val = entry.get("path", "")
            if path_val == "src/example/path/to/file.ext":
                out.error("file-risk-index.yml: contains template placeholder entry ('src/example/path/to/file.ext')")
                return 1
            if "../" in str(path_val) or str(path_val).startswith("/"):
                out.warn(f"file-risk-index.yml: path '{path_val}' is not workspace-relative")
            score = entry.get("score")
            if score is not None:
                try:
                    score_int = int(score)
                    if score_int < 1 or score_int > 5:
                        out.warn(f"file-risk-index.yml: score {score} for '{path_val}' is not in 1..5")
                except (TypeError, ValueError):
                    out.warn(f"file-risk-index.yml: non-integer score '{score}' for '{path_val}'")

        out.success(f"file-risk-index.yml: {len(files)} file(s) indexed")

    if findings_snapshot is not None:
        delta = count_findings_snapshot(findings_snapshot)
        new_findings = sum(delta.values())
        if new_findings > 0:
            out.warn(
                f"{new_findings} new finding(s) were created during Phase 1c. Findings should not be created during reconnaissance.",
            )
            for status, count in delta.items():
                if count > 0:
                    out.info(f"    {status}: +{count}")

    out.separator(tone=T.SUCCESS)
    out.success("Phase 1 complete. Ready to run Phase 2.")
    return 0


def check_phase_1b(console=None) -> int:
    """Gate 1b: sandbox-plan.md must exist and sandbox provenance is checked."""
    out = get_output(console)
    out.header("Gate 1b: Sandbox Bootstrap")
    out.separator(tone=T.SECTION)

    plan_path = ROOT / "itemdb" / "notes" / "sandbox-plan.md"
    if not plan_path.exists():
        out.error("itemdb/notes/sandbox-plan.md does not exist")
        out.info("Run Phase 1b first.")
        return 1

    out.success("itemdb/notes/sandbox-plan.md exists")

    provenance = ROOT / "sandbox" / "CODECOME-GENERATED.md"
    has_provenance = provenance.exists()
    sandbox_dir = ROOT / "sandbox"
    has_sandbox = sandbox_dir.exists() and any(entry.name != ".gitkeep" for entry in sandbox_dir.iterdir())

    if has_provenance:
        out.success("sandbox/CODECOME-GENERATED.md exists")
    elif has_sandbox:
        out.warn("sandbox/ exists without CODECOME-GENERATED.md - may be user-managed")
    else:
        out.warn("sandbox/ is empty or does not exist")

    out.separator(tone=T.SUCCESS)
    out.success("Ready to run Phase 1c (Detailed Reconnaissance).")
    return 0
