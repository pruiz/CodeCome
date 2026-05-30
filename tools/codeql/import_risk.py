# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Enrich file-risk-index.yml from CodeQL file-signals.yml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codeql.packs import PackResolverError, _load_yaml_mapping, dump_yaml


def import_risk(file_signals_path: Path, risk_index_path: Path) -> tuple[str | None, list[str]]:
    """Enrich the file-risk-index with CodeQL signals.

    Returns (status or None, warnings).

    - Preserves existing entries and model-authored reasons.
    - Does not duplicate file entries.
    - Caps scores at 5.
    - Adds ``codeql_score_boost`` and ``external_signals.codeql`` block.

    If the risk index does not exist, no-op with a warning.
    """
    warnings: list[str] = []

    if not file_signals_path.is_file():
        return None, [f"file-signals.yml not found at {file_signals_path}"]

    if not risk_index_path.is_file():
        return "skipped", [f"file-risk-index.yml not found at {risk_index_path}"]

    try:
        signals = _load_yaml_mapping(file_signals_path, what="CodeQL file signals")
    except PackResolverError as exc:
        return None, [str(exc)]

    try:
        risk_index = _load_yaml_mapping(risk_index_path, what="file risk index")
    except PackResolverError as exc:
        return None, [str(exc)]

    risks = risk_index.get("files")
    if not isinstance(risks, list):
        return None, ["file-risk-index.yml missing 'files' list"]

    signal_files = signals.get("files", [])
    if not isinstance(signal_files, list):
        return "skipped", ["file-signals.yml has no files"]

    existing_paths = {entry.get("path", "") for entry in risks if isinstance(entry, dict)}
    modified = False

    for signal in signal_files:
        if not isinstance(signal, dict):
            continue
        file_path = signal.get("path", "")
        if not file_path:
            continue
        if file_path in existing_paths:
            _update_existing_entry(risks, file_path, signal)
            modified = True
        else:
            _add_new_entry(risks, file_path, signal)
            existing_paths.add(file_path)
            modified = True

    if modified:
        risk_index["files"] = risks
        risk_index_path.write_text(dump_yaml(risk_index), encoding="utf-8")

    return None, warnings


def _update_existing_entry(entries: list[dict[str, Any]], file_path: str, signal: dict[str, Any]) -> None:
    """Enrich an existing file-risk-index entry with CodeQL signals."""
    for entry in entries:
        if entry.get("path") != file_path:
            continue

        boost = signal.get("codeql_score_boost", 0)
        if isinstance(boost, (int, float)):
            current = entry.get("score", 1)
            current = int(current) if isinstance(current, (int, float)) else 1
            entry["score"] = min(5, current + int(boost))

        codeql_alerts = signal.get("alerts", {})
        rules = signal.get("rules", [])
        if isinstance(codeql_alerts, dict):
            entry.setdefault("external_signals", {})
            entry["external_signals"]["codeql"] = {
                "alerts": codeql_alerts.get("total", 0),
                "path_problems": codeql_alerts.get("path_problems", 0),
                "highest_precision": "high" if codeql_alerts.get("high_precision", 0) > 0 else "medium",
                "rules": rules if isinstance(rules, list) else [],
            }

        return


def _add_new_entry(entries: list[dict[str, Any]], file_path: str, signal: dict[str, Any]) -> None:
    """Append a new file-risk-index entry from CodeQL signals."""
    boost = signal.get("codeql_score_boost", 1)
    codeql_alerts = signal.get("alerts", {})
    rules = signal.get("rules", [])

    entry: dict[str, Any] = {
        "path": file_path,
        "score": min(5, int(boost) if isinstance(boost, (int, float)) else 1),
        "confidence": "MEDIUM",
        "target_area": "",
        "reasons": ["CodeQL static analysis signal."],
        "sources": [],
        "sinks": [],
        "trust_boundaries": [],
        "suggested_vulnerability_classes": [],
        "suggested_skills": [],
        "suggested_validation_methods": [],
        "external_signals": {
            "codeql": {
                "alerts": codeql_alerts.get("total", 0) if isinstance(codeql_alerts, dict) else 0,
                "path_problems": codeql_alerts.get("path_problems", 0) if isinstance(codeql_alerts, dict) else 0,
                "highest_precision": "high" if (isinstance(codeql_alerts, dict) and codeql_alerts.get("high_precision", 0) > 0) else "medium",
                "rules": rules if isinstance(rules, list) else [],
            }
        },
    }

    entries.append(entry)
