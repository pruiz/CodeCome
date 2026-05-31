# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL runner: database create, analyze, and run manifest."""

from __future__ import annotations

import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from codeql.capabilities import supported_build_modes
from codeql.config import ROOT, CodeQLConfig
from codeql.packs import PackResolverError, dump_yaml, load_codeql_plan, load_pack_catalog, resolve_plan_packs


def run_codeql(config: CodeQLConfig, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Run CodeQL analysis for every language in the plan.

    Returns the run manifest as a dict.
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    binary_path = config.abs_install_path
    if not binary_path.is_file():
        if config.fail_policy == "hard":
            return _manifest("failed", now_utc, config, [], [], failures=[f"CodeQL binary not found at {binary_path}"])
        else:
            return _manifest("soft-failed", now_utc, config, [], [f"CodeQL binary not found at {binary_path}"])

    version = _get_codeql_version(binary_path)
    _progress(progress, f"CodeQL: using {version}")

    plan_path = ROOT / "itemdb/notes/codeql-plan.yml"
    if not plan_path.is_file():
        return _manifest("skipped", now_utc, config, [version], [], failures=["codeql-plan.yml not found"])

    catalog_path = config.abs_pack_catalog
    if not catalog_path.is_file():
        return _manifest("skipped", now_utc, config, [version], [], failures=[f"Pack catalog not found at {catalog_path}"])

    try:
        _progress(progress, f"CodeQL: loading plan {_rel(plan_path)}")
        catalog = load_pack_catalog(catalog_path)
        plan = load_codeql_plan(plan_path)
        resolved = resolve_plan_packs(plan, catalog)
    except PackResolverError as exc:
        return _manifest("failed", now_utc, config, [version], [], failures=[str(exc)])

    resolved_path = config.abs_output_dir / "selected-query-packs.yml"
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(dump_yaml(resolved), encoding="utf-8")
    _progress(progress, f"CodeQL: resolved packs for {len(resolved['analysis_units'])} analysis unit(s)")

    exclude_patterns = plan.get("exclude", [])

    warnings: list[str] = []
    failures: list[str] = []
    language_ids: list[str] = []
    analysis_units: list[str] = []

    for unit_entry in resolved["analysis_units"]:
        unit_id = unit_entry["id"]
        source_path = unit_entry["path"]
        analysis_units.append(unit_id)
        plan_unit = _lookup_unit(unit_id, plan.get("analysis_units", []))

        for lang_entry in unit_entry["languages"]:
            language_id = lang_entry["id"]
            profiles = lang_entry.get("profiles", [])
            profile_packs = lang_entry.get("profile_packs", {})
            language_ids.append(f"{unit_id}:{language_id}")

            build_mode, build_command = _lookup_build(language_id, plan_unit.get("languages", []))
            plan_languages = plan_unit.get("languages", [])
            db_timeout = _lookup_timeout("db_create_timeout", language_id, plan_languages, config.db_create_timeout)
            analyze_timeout = _lookup_timeout("analyze_timeout", language_id, plan_languages, config.analyze_timeout)

            supported_modes = supported_build_modes(language_id)
            if build_mode not in supported_modes:
                failures.append(
                    f"Unsupported build_mode '{build_mode}' for {language_id} in analysis unit {unit_id}. "
                    f"Allowed: {', '.join(sorted(supported_modes))}"
                )
                return _manifest(_tool_failure_status(config), now_utc, config, [version], warnings, failures, language_ids, analysis_units)

            db_dir = config.abs_database_dir / unit_id / language_id
            sarif_dir = config.abs_output_dir / "sarif"
            sarif_dir.mkdir(parents=True, exist_ok=True)

            _progress(progress, f"CodeQL: creating database {unit_id}:{language_id} ({build_mode})")
            ok, msg = _create_database(binary_path, language_id, source_path, db_dir, build_mode, build_command, exclude_patterns, timeout=db_timeout, progress=progress)
            if not ok:
                failures.append(msg)
                return _manifest(_tool_failure_status(config), now_utc, config, [version], warnings, failures, language_ids, analysis_units)
            _progress(progress, f"CodeQL: database ready {unit_id}:{language_id}")

            for profile in profiles:
                packs = profile_packs.get(profile, [])
                if not packs:
                    continue
                sarif_path = sarif_dir / f"{unit_id}.{language_id}.{profile}.sarif"
                _progress(progress, f"CodeQL: analyzing {unit_id}:{language_id} profile {profile}")
                ok, msg = _run_analyze(binary_path, db_dir, packs, sarif_path, timeout=analyze_timeout, progress=progress)
                if not ok:
                    failures.append(msg)
                    return _manifest(_tool_failure_status(config), now_utc, config, [version], warnings, failures, language_ids, analysis_units)
                _progress(progress, f"CodeQL: SARIF written {_rel(sarif_path)}")

    if failures:
        return _manifest("failed", now_utc, config, [version], warnings, failures, language_ids, analysis_units)

    return _manifest("completed", now_utc, config, [version], warnings, failures, language_ids, analysis_units)


def _tool_failure_status(config: CodeQLConfig) -> str:
    return "failed" if config.fail_policy == "hard" else "soft-failed"


def _progress(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _lookup_unit(unit_id: str, plan_units: list[dict]) -> dict:
    """Return the plan analysis unit with *unit_id*."""
    for unit in plan_units:
        if unit.get("id") == unit_id:
            return unit
    return {}


def _lookup_build(language_id: str, plan_languages: list[dict]) -> tuple[str, str | None]:
    """Return (build_mode, build_command) for a language entry."""
    for pl in plan_languages:
        if pl.get("id") == language_id:
            mode = pl.get("build_mode", "none")
            cmd = pl.get("build_command")
            return mode if isinstance(mode, str) and mode else "none", cmd if isinstance(cmd, str) and cmd else None
    return "none", None


def _lookup_timeout(field: str, language_id: str, plan_languages: list[dict], default: int) -> int:
    """Return a per-language timeout, falling back to *default*."""
    for pl in plan_languages:
        if pl.get("id") == language_id:
            value = pl.get(field)
            if isinstance(value, (int, float)) and value > 0:
                return int(value)
    return default


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
    timeout: int = 600,
    progress: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Create a CodeQL database.  Returns (success, message)."""
    db_dir.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(binary), "database", "create",
        str(db_dir),
        "-l", language_id,
        "-s", str(ROOT / source_path),
        "--overwrite",
        "--no-run-unnecessary-builds",
    ]

    if build_mode == "none":
        cmd += ["--build-mode=none"]
    elif build_mode == "manual" and build_command:
        cmd += ["--build-mode=manual", "-c", build_command]
    elif build_mode == "autobuild":
        cmd += ["--build-mode=autobuild"]

    return _run_with_progress(cmd, f"Database create timed out for {language_id} after {timeout}s",
                              f"Database create failed for {language_id}", timeout, progress)


def _run_analyze(
    binary: Path,
    db_dir: Path,
    packs: list[str],
    sarif_path: Path,
    timeout: int = 600,
    progress: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Run codeql database analyze.  Returns (success, message)."""
    cmd = [
        str(binary), "database", "analyze",
        str(db_dir),
        "--format=sarif-latest",
        f"--output={sarif_path}",
        "--no-sarif-add-query-help",
    ] + packs

    return _run_with_progress(cmd, f"Analyze timed out for {db_dir.name} after {timeout}s",
                              f"Analyze failed for {db_dir.name}", timeout, progress)


def _run_with_progress(
    cmd: list[str],
    timeout_msg_prefix: str,
    failure_msg_prefix: str,
    timeout: int,
    progress: Callable[[str], None] | None,
) -> tuple[bool, str]:
    """Run a subprocess, streaming stderr line-by-line to *progress*."""
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception as exc:
        return False, f"{failure_msg_prefix}: {exc}"

    stderr_lines: list[str] = []

    def _read_stderr() -> None:
        for line in process.stderr:
            stripped = line.rstrip()
            if stripped:
                stderr_lines.append(stripped)
                _progress(progress, f"CodeQL: {stripped}")

    reader = threading.Thread(target=_read_stderr, daemon=True)
    reader.start()

    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        reader.join(timeout=5)
        detail = "\n".join(stderr_lines[-40:])
        return False, f"{timeout_msg_prefix}\n{detail}" if detail else timeout_msg_prefix

    reader.join(timeout=5)

    if returncode != 0:
        detail = "\n".join(stderr_lines[-40:])
        return False, f"{failure_msg_prefix}:\n{detail}" if detail else failure_msg_prefix

    return True, ""


def _manifest(
    status: str,
    started_at: str,
    config: CodeQLConfig,
    versions: list[str],
    warnings: list[str],
    failures: list[str] | None = None,
    languages: list[str] | None = None,
    analysis_units: list[str] | None = None,
    skip_reason: str | None = None,
) -> dict[str, Any]:
    if failures is None:
        failures = []
    if languages is None:
        languages = []
    if analysis_units is None:
        analysis_units = []

    codeql_version = versions[0] if versions else "unknown"
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest = {
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
        "analysis_units": analysis_units,
        "languages": languages,
        "warnings": warnings,
        "failures": failures if failures else [],
    }
    if skip_reason:
        manifest["skip_reason"] = skip_reason
    return manifest


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _rel(path: Path) -> str:
    """Return a workspace-relative path when under ROOT, else the absolute path."""
    try:
        rel = path.relative_to(ROOT)
        return str(rel)
    except ValueError:
        return str(path)
