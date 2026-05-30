# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL runner: database create, analyze, and run manifest."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codeql.config import ROOT, CodeQLConfig
from codeql.packs import PackResolverError, dump_yaml, load_codeql_plan, load_pack_catalog, resolve_plan_packs


def run_codeql(config: CodeQLConfig) -> dict[str, Any]:
    """Run CodeQL analysis for every language in the plan.

    Returns the run manifest as a dict.
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    binary_path = config.abs_install_path
    if not binary_path.is_file():
        return _manifest("failed", now_utc, config, [], [], failures=[f"CodeQL binary not found at {binary_path}"])

    version = _get_codeql_version(binary_path)

    plan_path = ROOT / "itemdb/notes/codeql-plan.yml"
    if not plan_path.is_file():
        return _manifest("skipped", now_utc, config, [version], [], failures=["codeql-plan.yml not found"])

    catalog_path = config.abs_pack_catalog
    if not catalog_path.is_file():
        return _manifest("skipped", now_utc, config, [version], [], failures=[f"Pack catalog not found at {catalog_path}"])

    try:
        catalog = load_pack_catalog(catalog_path)
        plan = load_codeql_plan(plan_path)
        resolved = resolve_plan_packs(plan, catalog)
    except PackResolverError as exc:
        return _manifest("failed", now_utc, config, [version], [], failures=[str(exc)])

    resolved_path = config.abs_output_dir / "selected-query-packs.yml"
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(dump_yaml(resolved), encoding="utf-8")

    source_path = plan.get("source_path", "./src")
    exclude_patterns = plan.get("exclude", [])

    warnings: list[str] = []
    failures: list[str] = []
    language_ids: list[str] = []

    for lang_entry in resolved["languages"]:
        language_id = lang_entry["id"]
        profiles = lang_entry.get("profiles", [])
        profile_packs = lang_entry.get("profile_packs", {})
        language_ids.append(language_id)

        build_mode, build_command = _lookup_build(lang_entry, plan.get("languages", []))

        db_dir = config.abs_database_dir / language_id
        sarif_dir = config.abs_output_dir / "sarif"
        sarif_dir.mkdir(parents=True, exist_ok=True)

        ok, msg = _create_database(binary_path, language_id, source_path, db_dir, build_mode, build_command, exclude_patterns)
        if not ok:
            failures.append(msg)
            if config.fail_policy == "hard":
                return _manifest("failed", now_utc, config, [version], warnings, failures, language_ids)
            continue

        for profile in profiles:
            packs = profile_packs.get(profile, [])
            if not packs:
                continue
            sarif_path = sarif_dir / f"{language_id}.{profile}.sarif"
            ok, msg = _run_analyze(binary_path, db_dir, packs, sarif_path)
            if not ok:
                if config.fail_policy == "hard":
                    failures.append(msg)
                    return _manifest("failed", now_utc, config, [version], warnings, failures, language_ids)
                warnings.append(msg)

    if failures:
        return _manifest("failed", now_utc, config, [version], warnings, failures, language_ids)

    return _manifest("completed", now_utc, config, [version], warnings, failures, language_ids)


def _lookup_build(lang_entry: dict, plan_languages: list[dict]) -> tuple[str, str | None]:
    """Return (build_mode, build_command) for a language entry."""
    language_id = lang_entry["id"]
    for pl in plan_languages:
        if pl.get("id") == language_id:
            mode = pl.get("build_mode", "none")
            cmd = pl.get("build_command")
            return mode if isinstance(mode, str) and mode else "none", cmd if isinstance(cmd, str) and cmd else None
    return "none", None


def _get_codeql_version(binary: Path) -> str:
    try:
        result = subprocess.run(
            [str(binary), "--version"],
            capture_output=True, text=True, timeout=30,
        )
        line = result.stdout.strip().split("\n")[0]
        return line.removeprefix("CodeQL version ")
    except Exception:
        return "unknown"


def _create_database(
    binary: Path,
    language_id: str,
    source_path: str,
    db_dir: Path,
    build_mode: str,
    build_command: str | None,
    exclude_patterns: list[str],
) -> tuple[bool, str]:
    """Create a CodeQL database.  Returns (success, message)."""
    cmd = [
        str(binary), "database", "create",
        str(db_dir),
        "-l", language_id,
        "-s", str(ROOT / source_path),
        "--overwrite",
        "--no-run-unnecessary-builds",
    ]

    if build_mode == "manual" and build_command:
        cmd += ["-c", build_command]
    elif build_mode == "autobuild":
        pass  # let CodeQL auto-detect

    for pattern in exclude_patterns:
        cmd += ["--no-source-unpack", "--additional-build-options", f"--exclude={pattern}"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return False, f"Database create timed out for {language_id}"
    except Exception as exc:
        return False, f"Database create failed for {language_id}: {exc}"

    if result.returncode != 0:
        return False, f"Database create failed for {language_id}:\n{result.stderr[:2000]}"

    return True, ""


def _run_analyze(
    binary: Path,
    db_dir: Path,
    packs: list[str],
    sarif_path: Path,
) -> tuple[bool, str]:
    """Run codeql database analyze.  Returns (success, message)."""
    cmd = [
        str(binary), "database", "analyze",
        str(db_dir),
        "--format=sarif-latest",
        f"--output={sarif_path}",
        "--no-sarif-add-query-help",
    ] + packs

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return False, f"Analyze timed out for {db_dir.name} with packs {packs}"
    except Exception as exc:
        return False, f"Analyze failed for {db_dir.name} with packs {packs}: {exc}"

    if result.returncode != 0:
        return False, f"Analyze failed for {db_dir.name} with packs {packs}:\n{result.stderr[:2000]}"

    return True, ""


def _manifest(
    status: str,
    started_at: str,
    config: CodeQLConfig,
    versions: list[str],
    warnings: list[str],
    failures: list[str] | None = None,
    languages: list[str] | None = None,
) -> dict[str, Any]:
    if failures is None:
        failures = []
    if languages is None:
        languages = []

    codeql_version = versions[0] if versions else "unknown"
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "schema_version": 1,
        "phase": "phase-1",
        "status": status,
        "codeql_enabled": config.enabled,
        "codeql_version": codeql_version,
        "started_at": started_at,
        "finished_at": now_utc,
        "plan_file": "itemdb/notes/codeql-plan.yml",
        "pack_catalog": str(_rel(config.abs_pack_catalog)),
        "fail_policy": config.fail_policy,
        "languages": languages,
        "warnings": warnings,
        "failures": failures if failures else [],
    }


def write_manifest(manifest: dict[str, Any], output_dir: Path) -> Path:
    """Write the run manifest to *output_dir*/run-manifest.yml."""
    import json

    path = output_dir / "run-manifest.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(manifest), encoding="utf-8")
    return path


def write_summary(manifest: dict[str, Any], normalized_dir: Path, output_dir: Path) -> Path:
    """Write codeql-summary.md."""
    status = manifest.get("status", "unknown")
    version = manifest.get("codeql_version", "unknown")
    languages = manifest.get("languages", [])
    warnings = manifest.get("warnings", [])
    failures = manifest.get("failures", [])
    fail_policy = manifest.get("fail_policy", "soft")

    lines = [
        "# CodeQL Analysis Summary",
        "",
        f"- **Status**: {status}",
        f"- **CodeQL version**: {version}",
        f"- **Fail policy**: {fail_policy}",
        f"- **Started**: {manifest.get('started_at', '')}",
        f"- **Finished**: {manifest.get('finished_at', '')}",
        "",
    ]

    if languages:
        lines.append(f"- **Languages**: {', '.join(languages)}")
        lines.append("")

    alerts_path = normalized_dir / "alerts.yml"

    if alerts_path.is_file():
        from codeql.packs import load_yaml_mapping
        try:
            data = load_yaml_mapping(alerts_path, what="alerts")
            total_alerts = len(data.get("alerts", []))
            lines.append(f"- **Total alerts**: {total_alerts}")
            lines.append("")
        except Exception:
            pass

    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    if failures:
        lines.append("## Failures")
        lines.append("")
        for f in failures:
            lines.append(f"- {f}")
        lines.append("")

    path = output_dir / "codeql-summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _rel(path: Path) -> str:
    """Return a workspace-relative path when under ROOT, else the absolute path."""
    try:
        rel = path.relative_to(ROOT)
        return str(rel)
    except ValueError:
        return str(path)
