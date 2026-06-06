# Copyright (C) 2025-2026 Pablo Ruiz Garcia <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL run health: classify a CodeQL run as usable or not."""

from __future__ import annotations

from pathlib import Path
from typing import Any


VALID_HEALTH_CLASSIFICATIONS = frozenset(
    {
        "disabled",
        "skipped",
        "unavailable",
        "failed",
        "soft-failed",
        "extraction-failed",
        "analysis-failed",
        "completed-empty-valid",
        "completed-with-signals",
        "completed-partial",
        "stale-output-detected",
    }
)

COMPILED_LANGUAGES = frozenset({"c-cpp", "go", "swift"})


def compute_health(
    *,
    manifest: dict[str, Any],
    run_dir: Path,
    output_dir: Path,
    resolved_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify a CodeQL run and return a health dict.

    The health dict is merged into the manifest and also written as
    ``health.yml`` inside *run_dir*.

    Parameters
    ----------
    manifest: run manifest (with status, languages, failures, warnings).
    run_dir: per-run directory (``itemdb/codeql/runs/<id>/``).
    output_dir: top-level CodeQL output directory (``itemdb/codeql/``).
    resolved_plan: optional resolved analysis plan to determine
      compiled vs non-compiled languages.
    """
    status = manifest.get("status", "unknown")

    checks = _build_checks(manifest, run_dir, output_dir, resolved_plan)
    classification, reason = _classify(status, checks, manifest)

    return {
        "usable": _is_usable(classification),
        "classification": classification,
        "reason": reason,
        "checks": checks,
    }


def _build_checks(
    manifest: dict[str, Any],
    run_dir: Path,
    output_dir: Path,
    resolved_plan: dict[str, Any] | None,
) -> dict[str, Any]:
    codes: dict[str, Any] = {
        "database_create_exit_zero": _db_create_ok(manifest),
        "database_exists": _db_dir_exists(run_dir),
        "analyze_exit_zero": _any_analyze_ok(manifest),
        "official_profile_analyzed": _official_analyzed(manifest),
        "sarif_fresh": _sarif_fresh(run_dir),
        "normalized_fresh": _normalized_fresh(run_dir, output_dir),
        "extractor_successes": _extractor_successes(manifest),
        "extractor_failures": _extractor_failures(manifest),
        "trap_files_detected": _unknown("trap_files"),
        "has_languages": bool(manifest.get("languages")),
        "has_compiled_languages": _has_compiled(resolved_plan),
    }
    return codes


# --------------- check helpers ----------------------------------------------


def _db_create_ok(manifest: dict[str, Any]) -> bool:
    failures = manifest.get("failures", [])
    if not isinstance(failures, list):
        return True
    return not any("Database create failed" in str(f) for f in failures)


def _db_dir_exists(run_dir: Path) -> bool:
    db_dir = run_dir / "databases"
    if not db_dir.exists():
        return False
    return any(db_dir.iterdir())


def _any_analyze_ok(manifest: dict[str, Any]) -> bool:
    failures = manifest.get("failures", [])
    if not isinstance(failures, list):
        return True
    return not any("Analyze failed" in str(f) for f in failures)


def _official_analyzed(manifest: dict[str, Any]) -> bool:
    languages = manifest.get("languages", [])
    failures = manifest.get("failures", [])
    if not isinstance(failures, list):
        return bool(languages)
    return bool(languages) and not any("official" in str(f) for f in failures)


def _sarif_fresh(run_dir: Path) -> bool:
    sarif_dir = run_dir / "sarif"
    if not sarif_dir.exists():
        return False
    sarif_files = list(sarif_dir.glob("*.sarif"))
    return len(sarif_files) > 0


def _normalized_fresh(run_dir: Path, output_dir: Path) -> bool:
    normalized = run_dir / "normalized"
    if not normalized.is_dir():
        return False
    for expected in ("alerts.yml", "file-signals.yml"):
        if not (normalized / expected).is_file():
            return False
    return True


def _extractor_successes(manifest: dict[str, Any]) -> int:
    return manifest.get("extractor_successes", _unknown_int("extractor_successes"))


def _extractor_failures(manifest: dict[str, Any]) -> int:
    return manifest.get("extractor_failures", _unknown_int("extractor_failures"))


def _has_compiled(resolved_plan: dict[str, Any] | None) -> bool:
    if not resolved_plan or not isinstance(resolved_plan, dict):
        return False
    for unit in resolved_plan.get("analysis_units", []) or []:
        if not isinstance(unit, dict):
            continue
        for lang in unit.get("languages", []) or []:
            if not isinstance(lang, dict):
                continue
            if lang.get("id") in COMPILED_LANGUAGES:
                return True
    return False


# --------------- classification --------------------------------------------


def _classify(
    status: str,
    checks: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[str, str]:
    if status == "skipped":
        return "skipped", "CodeQL was skipped (disabled or no plan)."
    if status == "disabled":
        return "disabled", "CodeQL is disabled."
    if status == "unavailable":
        return "unavailable", "CodeQL is unavailable for this target."

    db_ok = checks.get("database_create_exit_zero", False)
    db_exists = checks.get("database_exists", False)
    analyze_ok = checks.get("analyze_exit_zero", False)
    official_ok = checks.get("official_profile_analyzed", False)
    sarif_ok = checks.get("sarif_fresh", False)
    normalized_ok = checks.get("normalized_fresh", False)
    has_languages = checks.get("has_languages", False)
    has_compiled = checks.get("has_compiled_languages", False)
    extract_ok = checks.get("extractor_successes", 0)

    if not has_languages:
        return "skipped", "No languages were resolved for analysis."

    if status == "failed":
        if not db_ok:
            return "failed", "CodeQL database creation failed."
        if not analyze_ok:
            return "failed", "CodeQL analysis failed."
        return "failed", "CodeQL pipeline failed."

    if status == "soft-failed":
        if not db_ok and not db_exists:
            return "soft-failed", "CodeQL database creation soft-failed."
        return "soft-failed", "CodeQL pipeline soft-failed."

    if not analyze_ok:
        return "analysis-failed", "One or more CodeQL query profiles failed to analyze."

    if db_ok and db_exists and not sarif_ok:
        return "failed", "Database created but no SARIF files found."

    if db_ok and db_exists and has_compiled and not extract_ok:
        return "extraction-failed", (
            "CodeQL database creation reported success but "
            f"extractor_successes={extract_ok} for compiled languages. "
            "The database may be empty or extraction did not observe the build."
        )

    if db_ok and db_exists and not normalized_ok:
        return "failed", "SARIF normalization failed."

    if not db_ok and not db_exists:
        return "failed", "CodeQL database creation failed and database directory is missing."

    if not sarif_ok:
        return "failed", "SARIF files are missing."

    if not normalized_ok:
        return "failed", "Normalized signals are missing."

    if sarif_ok and normalized_ok:
        sarif_dir = Path(checks.get("_sarif_dir", "")) if "_sarif_dir" in checks else None
        alert_count = _count_alerts(manifest)
        if alert_count == 0:
            return "completed-empty-valid", (
                "CodeQL ran successfully and found zero alerts. "
                "Zero alerts is not a failure — the output is usable."
            )
        return "completed-with-signals", (
            f"CodeQL ran successfully and found {alert_count} alert(s)."
        )

    return "failed", "CodeQL run did not meet usability criteria."


def _count_alerts(manifest: dict[str, Any]) -> int:
    try:
        return int(manifest.get("total_alerts", _unknown_int("total_alerts")))
    except (TypeError, ValueError):
        return _unknown_int("total_alerts")


def _is_usable(classification: str) -> bool:
    return classification in {
        "completed-empty-valid",
        "completed-with-signals",
        "completed-partial",
    }


def _unknown(key: str) -> str:
    return f"<unknown:{key}>"


def _unknown_int(key: str) -> int:
    return -1
