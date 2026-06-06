# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL artifact gate: validate run outputs via health model and run layout."""

from __future__ import annotations

from pathlib import Path
from typing import Any

VALID_STATUSES = frozenset({"completed", "skipped", "soft-failed", "failed"})


def check_artifacts(output_dir: Path) -> tuple[str, list[str]]:
    """Check CodeQL artifact state after a run.

    Reads ``output_dir/last-run-manifest.yml`` (falling back to
    ``output_dir/run-manifest.yml`` for legacy runs) and evaluates
    whether the most recent CodeQL run produced usable outputs.
    Delegates to the health block when present.

    Returns (status_string, warnings).
    """
    manifest_path = _find_manifest(output_dir)
    if manifest_path is None:
        return ("missing", [f"No run manifest found at {output_dir}"])

    try:
        from codeql.packs import load_yaml_mapping
        manifest = load_yaml_mapping(manifest_path, what="run manifest")
    except Exception as exc:
        return ("unknown", [f"Run manifest is not valid YAML: {exc}"])

    status = manifest.get("status", "")
    warnings: list[str] = []

    # Propagate recorded failures as warnings
    failures = manifest.get("failures", [])
    if isinstance(failures, list):
        warnings.extend(failures)

    # Use health block when present
    health = manifest.get("health")
    if isinstance(health, dict):
        usable = health.get("usable", False)
        classification = health.get("classification", "unknown")
        reason = health.get("reason", "")
        if reason and reason not in warnings:
            warnings.insert(0, reason)

        if classification in ("disabled", "skipped", "unavailable"):
            return ("skipped", warnings)

        if usable:
            return ("completed", warnings)

        fail_policy = manifest.get("fail_policy", "soft")
        if fail_policy == "hard":
            return ("failed", warnings)
        return ("soft-failed", warnings)

    # Legacy: no health block — fall back to status-based checks
    if status not in VALID_STATUSES:
        return ("unknown", [f"unrecognized status {status!r} in run manifest"])

    languages = manifest.get("languages", [])
    if status == "completed" and languages:
        run_id = manifest.get("run_id")
        normalized_dir = _normalized_dir(output_dir, manifest)
        for expected in ("alerts.yml", "file-signals.yml"):
            if not (normalized_dir / expected).is_file():
                warnings.append(f"expected normalized output missing: {expected}")

    return (status, warnings)


def _find_manifest(output_dir: Path) -> Path | None:
    """Return the manifest path, preferring ``last-run-manifest.yml``."""
    last = output_dir / "last-run-manifest.yml"
    if last.is_file():
        return last
    legacy = output_dir / "run-manifest.yml"
    if legacy.is_file():
        return legacy
    return None


def _normalized_dir(output_dir: Path, manifest: dict[str, Any]) -> Path:
    run_id = manifest.get("run_id")
    if run_id:
        return output_dir / "runs" / str(run_id) / "normalized"
    return output_dir / "normalized"
