# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL full pipeline: run analysis, normalize SARIF, import risk, write summary."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from datetime import datetime, timezone

from codeql.config import ROOT, CodeQLConfig


def record_skipped_run(config: CodeQLConfig, reason: str) -> dict[str, Any]:
    """Write a skipped CodeQL manifest and summary for a deliberate skip."""
    from codeql.runner import _manifest, write_manifest, write_summary

    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = _manifest(
        "skipped",
        started_at,
        config,
        [],
        [],
        failures=[reason],
        skip_reason=reason,
    )
    output_dir = config.abs_output_dir
    normalized_dir = output_dir / "normalized"
    write_manifest(manifest, output_dir)
    write_summary(manifest, normalized_dir, output_dir)
    return manifest


def run_full_pipeline(config: CodeQLConfig, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Run the complete CodeQL analysis pipeline.

    Steps (all internal, no printing):
    1. run_codeql(config)             -> manifest
    2. write_manifest(manifest, output_dir)
    3. normalize_all(sarif_dir, ...)  -> alerts.yml, file-signals.yml  (if SARIF exist)
    4. import_risk(signals_path, risk_path)
    5. write_summary(manifest, normalized_dir, output_dir)

    Returns the manifest dict (with extra keys for artifact paths).
    """
    from codeql.runner import run_codeql, write_manifest, write_summary
    from codeql.normalize import normalize_all
    from codeql.import_risk import import_risk
    from codeql.packs import load_yaml_mapping

    output_dir = config.abs_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: run analysis
    manifest = run_codeql(config, progress=progress)

    # Step 2: write manifest
    write_manifest(manifest, output_dir)
    _progress(progress, "CodeQL: manifest written")

    status = manifest["status"]
    normalized_dir = output_dir / "normalized"
    resolved_path = output_dir / "selected-query-packs.yml"

    # Step 3: normalize SARIF (completed or soft-failed, with SARIF files present)
    if status in ("completed", "soft-failed") and resolved_path.is_file():
        sarif_dir = output_dir / "sarif"
        if list(sarif_dir.glob("*.sarif")):
            try:
                resolved = load_yaml_mapping(resolved_path, what="resolved packs")
                normalize_all(
                    sarif_dir, normalized_dir, resolved,
                    manifest.get("codeql_version", "unknown"), ROOT,
                )
                _progress(progress, "CodeQL: normalized SARIF artifacts")
            except Exception as exc:
                manifest.setdefault("warnings", []).append(
                    f"SARIF normalization failed: {exc}"
                )

    # Step 4: import risk
    signals_path = normalized_dir / "file-signals.yml"
    risk_path = ROOT / "itemdb/notes/file-risk-index.yml"
    if signals_path.is_file():
        try:
            import_risk(signals_path, risk_path)
            _progress(progress, "CodeQL: imported file risk signals")
        except Exception as exc:
            manifest.setdefault("warnings", []).append(
                f"Risk import failed: {exc}"
            )

    # Re-write manifest so any warnings appended above are on disk.
    write_manifest(manifest, output_dir)

    # Step 5: write summary
    write_summary(manifest, normalized_dir, output_dir)
    _progress(progress, "CodeQL: summary written")

    return manifest


def _progress(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)
