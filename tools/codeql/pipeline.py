# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL full pipeline: run analysis, normalize SARIF, import risk, write summary."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable
from datetime import datetime, timezone

from codeql.config import ROOT, CodeQLConfig


def _generate_run_id() -> str:
    import uuid
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fingerprint = uuid.uuid4().hex[:8]
    return f"{ts}-{fingerprint}"


def _inject_total_alerts(manifest: dict[str, Any], normalized_dir: Path) -> None:
    """Read total_alerts from normalized alerts.yml and inject into manifest."""
    alerts_path = normalized_dir / "alerts.yml"
    if not alerts_path.is_file():
        return
    try:
        from codeql.packs import load_yaml_mapping
        data = load_yaml_mapping(alerts_path, what="alerts")
        manifest["total_alerts"] = len(data.get("alerts", []))
    except Exception:
        pass


def _set_run_dir(config: CodeQLConfig) -> tuple[str, Path]:
    output_dir = config.abs_output_dir
    run_id = _generate_run_id()
    run_dir = output_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "sarif").mkdir(exist_ok=True)
    (run_dir / "normalized").mkdir(exist_ok=True)
    (run_dir / "databases").mkdir(exist_ok=True)
    (run_dir / "logs").mkdir(exist_ok=True)

    return run_id, run_dir


def record_skipped_run(config: CodeQLConfig, reason: str) -> dict[str, Any]:
    """Write a skipped CodeQL manifest and summary for a deliberate skip."""
    from codeql.runner import _manifest, write_manifest, write_summary

    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_id, run_dir = _set_run_dir(config)
    output_dir = config.abs_output_dir

    manifest = _manifest(
        "skipped", started_at, config, [], [],
        failures=[reason], skip_reason=reason,
    )
    manifest["run_id"] = run_id
    _write_health_for_skipped(manifest, run_dir, output_dir)
    write_manifest(manifest, run_dir)
    _copy_last_manifest(manifest, output_dir)
    _clear_current_run_txt(output_dir)
    write_summary(manifest, run_dir / "normalized", run_dir)
    return manifest


def run_full_pipeline(config: CodeQLConfig, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Run the complete CodeQL analysis pipeline.

    Steps:
    1. Create per-run directory.
    2. run_codeql(config, run_dir) -> manifest.
    3. Write per-run manifest.
    4. normalize SARIF from run_dir.
    5. Compute health.
    6. Import risk only when health says usable.
    7. Write last-run-manifest.yml, current-run.txt, summary.
    """
    from codeql.runner import run_codeql, write_manifest, write_summary
    from codeql.normalize import normalize_all
    from codeql.import_risk import import_risk
    from codeql.packs import load_yaml_mapping, dump_yaml
    from codeql.health import compute_health

    output_dir = config.abs_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id, run_dir = _set_run_dir(config)

    # Step 1: run analysis (runner writes into run_dir)
    manifest = run_codeql(config, run_dir=run_dir, progress=progress)
    manifest["run_id"] = run_id

    # Step 2: write per-run manifest
    write_manifest(manifest, run_dir)
    _progress(progress, "CodeQL: manifest written")

    status = manifest["status"]
    normalized_dir = run_dir / "normalized"
    resolved_path = run_dir / "selected-query-packs.yml"

    # Step 3: normalize SARIF
    normalized_ok = False
    if status in ("completed", "soft-failed") and resolved_path.is_file():
        sarif_dir = run_dir / "sarif"
        if list(sarif_dir.glob("*.sarif")):
            try:
                resolved = load_yaml_mapping(resolved_path, what="resolved packs")
                normalize_all(
                    sarif_dir, normalized_dir, resolved,
                    manifest.get("codeql_version", "unknown"), ROOT,
                )
                normalized_ok = True
                _progress(progress, "CodeQL: normalized SARIF artifacts")
            except Exception as exc:
                manifest.setdefault("warnings", []).append(
                    f"SARIF normalization failed: {exc}"
                )
                manifest["status"] = "failed" if config.fail_policy == "hard" else "soft-failed"

    # Inject total_alerts from normalized alerts before health computation
    _inject_total_alerts(manifest, normalized_dir)

    # Step 4: compute health
    health = compute_health(
        manifest=manifest,
        run_dir=run_dir,
        output_dir=output_dir,
        resolved_plan=_load_resolved(resolved_path),
    )
    manifest.setdefault("health", health)

    # Write health.yml
    health_path = run_dir / "health.yml"
    health_path.write_text(dump_yaml(health), encoding="utf-8")

    _progress(progress, f"CodeQL: health classification={health['classification']} usable={health['usable']}")

    # Step 5: import risk only when health says usable
    if normalized_ok and health["usable"]:
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

    # Step 6: re-write per-run manifest with health and any appended warnings
    write_manifest(manifest, run_dir)

    # Step 7: update top-level pointers
    _copy_last_manifest(manifest, output_dir)
    if health["usable"]:
        _write_current_run_txt(output_dir, run_id)
    else:
        _clear_current_run_txt(output_dir)

    # Step 8: write summary
    write_summary(manifest, normalized_dir, run_dir)
    _progress(progress, "CodeQL: summary written")

    return manifest


def _load_resolved(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        from codeql.packs import load_yaml_mapping, dump_yaml
        return load_yaml_mapping(path, what="resolved packs")
    except Exception:
        return None


def _write_health_for_skipped(manifest: dict[str, Any], run_dir: Path, output_dir: Path) -> None:
    from codeql.packs import dump_yaml
    health = {
        "usable": False,
        "classification": "skipped",
        "reason": manifest.get("skip_reason", manifest.get("failures", ["Unknown"])[0] if manifest.get("failures") else "Unknown reason"),
        "checks": {},
    }
    manifest["health"] = health
    (run_dir / "health.yml").write_text(dump_yaml(health), encoding="utf-8")


def _copy_last_manifest(manifest: dict[str, Any], output_dir: Path) -> None:
    from codeql.packs import dump_yaml
    last_manifest_path = output_dir / "last-run-manifest.yml"
    last_manifest_path.write_text(dump_yaml(manifest), encoding="utf-8")


def _write_current_run_txt(output_dir: Path, run_id: str) -> None:
    (output_dir / "current-run.txt").write_text(run_id, encoding="utf-8")


def _clear_current_run_txt(output_dir: Path) -> None:
    current = output_dir / "current-run.txt"
    if current.exists():
        current.unlink()


def _progress(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)
