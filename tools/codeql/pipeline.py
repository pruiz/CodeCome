# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL full pipeline: run analysis, normalize SARIF, import risk, write summary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codeql.config import ROOT, CodeQLConfig


def run_full_pipeline(config: CodeQLConfig) -> dict[str, Any]:
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
    manifest = run_codeql(config)

    # Step 2: write manifest
    write_manifest(manifest, output_dir)

    status = manifest["status"]
    normalized_dir = output_dir / "normalized"
    resolved_path = output_dir / "selected-query-packs.yml"

    # Step 3: normalize SARIF (only if completed and SARIF files exist)
    if status == "completed" and resolved_path.is_file():
        sarif_dir = output_dir / "sarif"
        if list(sarif_dir.glob("*.sarif")):
            try:
                resolved = load_yaml_mapping(resolved_path, what="resolved packs")
                normalize_all(
                    sarif_dir, normalized_dir, resolved,
                    manifest.get("codeql_version", "unknown"), ROOT,
                )
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
        except Exception as exc:
            manifest.setdefault("warnings", []).append(
                f"Risk import failed: {exc}"
            )

    # Step 5: write summary
    write_summary(manifest, normalized_dir, output_dir)

    return manifest
