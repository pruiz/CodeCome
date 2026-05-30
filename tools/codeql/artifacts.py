# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL artifact gate: validate post-run artifacts exist and are consistent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

VALID_STATUSES = frozenset({"completed", "skipped", "soft-failed", "failed"})


def check_artifacts(output_dir: Path) -> tuple[str, list[str]]:
    """Check CodeQL artifact state after a run.

    Returns (status_string, warnings).

    status_string values:
      "missing"      — run-manifest.yml does not exist
      "completed"    — analysis ran; normalized outputs expected
      "skipped"      — CodeQL was disabled or no plan existed
      "soft-failed"  — analysis failed but phase may continue
      "failed"       — hard failure
      "unknown"      — unrecognized status value in manifest
    """
    manifest_path = output_dir / "run-manifest.yml"
    if not manifest_path.is_file():
        return ("missing", [f"run-manifest.yml not found at {manifest_path}"])

    try:
        from codeql.packs import load_yaml_mapping

        manifest = load_yaml_mapping(manifest_path, what="run manifest")
    except Exception as exc:
        return ("unknown", [f"run-manifest.yml is not valid YAML: {exc}"])

    status = manifest.get("status", "")
    if status not in VALID_STATUSES:
        return ("unknown", [f"unrecognized status {status!r} in run-manifest.yml"])

    warnings: list[str] = []

    # Propagate recorded failures as warnings for the gate consumer.
    failures = manifest.get("failures", [])
    if isinstance(failures, list):
        warnings.extend(failures)

    # For completed runs, verify normalized outputs exist.
    if status == "completed":
        normalized_dir = output_dir / "normalized"
        for expected in ("alerts.yml", "file-signals.yml"):
            if not (normalized_dir / expected).is_file():
                warnings.append(f"expected normalized output missing: {expected}")

    return (status, warnings)
