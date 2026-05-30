# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""SARIF normalization: parse CodeQL SARIF into alerts.yml and file-signals.yml."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def normalize_all(
    sarif_dir: Path,
    output_dir: Path,
    resolved_plan: dict[str, Any],
    codeql_version: str,
    source_root: Path,
) -> tuple[Path, Path]:
    """Normalize all SARIF files, write alerts.yml and file-signals.yml.

    Returns (alerts_path, file_signals_path).
    """
    alerts: list[dict[str, Any]] = []
    alert_counter = 0

    for sarif_file in sorted(sarif_dir.glob("*.sarif")):
        stem = sarif_file.stem  # e.g. "python.official"
        parts = stem.split(".", 1)
        if len(parts) != 2:
            continue
        language_id, profile = parts

        new_alerts = _parse_sarif(sarif_file, language_id, profile, alert_counter, source_root)
        alert_counter += len(new_alerts)
        alerts.extend(new_alerts)

    file_signals = _build_file_signals(alerts)

    output_dir.mkdir(parents=True, exist_ok=True)

    alerts_path = output_dir / "alerts.yml"
    file_signals_path = output_dir / "file-signals.yml"

    from codeql.packs import dump_yaml

    alerts_path.write_text(
        dump_yaml(
            {
                "schema_version": 1,
                "generated_by": "codeql-normalize",
                "codeql_version": codeql_version,
                "target": "codecome-target",
                "alerts": alerts,
            }
        ),
        encoding="utf-8",
    )

    file_signals_path.write_text(
        dump_yaml(
            {
                "schema_version": 1,
                "generated_by": "codeql-normalize",
                "codeql_version": codeql_version,
                "files": file_signals,
            }
        ),
        encoding="utf-8",
    )

    return alerts_path, file_signals_path


def _parse_sarif(
    path: Path,
    language_id: str,
    pack_profile: str,
    start_index: int,
    source_root: Path,
) -> list[dict[str, Any]]:
    """Parse one SARIF file and return a list of normalized alert dicts."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    alerts: list[dict[str, Any]] = []
    runs = data.get("runs", [])
    if not isinstance(runs, list):
        return alerts

    for run in runs:
        if not isinstance(run, dict):
            continue
        results = run.get("results", [])
        if not isinstance(results, list):
            continue
        rules_lookup = _build_rules_lookup(run)

        for ri, result in enumerate(results):
            if not isinstance(result, dict):
                continue
            alert = _normalize_one_result(
                result, rules_lookup, language_id, pack_profile,
                start_index + ri + 1, source_root,
            )
            if alert:
                alerts.append(alert)

    return alerts


def _build_rules_lookup(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build {ruleId: {name, precision, ...}} from tool.driver.rules."""
    driver = run.get("tool", {}).get("driver", {})
    if not isinstance(driver, dict):
        return {}
    rules = driver.get("rules", [])
    if not isinstance(rules, list):
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rid = rule.get("id")
        if rid:
            props = rule.get("properties", {})
            lookup[rid] = {
                "name": rule.get("name", rid),
                "precision": _coerce_str(props.get("precision")) or _coerce_str(rule.get("precision")),
                "security_severity": _coerce_str(props.get("security-severity")) or _coerce_str(rule.get("security-severity")),
                "severity": _coerce_str(props.get("problem.severity")),
            }
    return lookup


def _normalize_one_result(
    result: dict[str, Any],
    rules_lookup: dict[str, dict[str, Any]],
    language_id: str,
    pack_profile: str,
    index: int,
    source_root: Path,
) -> dict[str, Any] | None:
    """Normalize a single SARIF result into a CodeCome alert dict."""
    rule_id = result.get("ruleId") or result.get("ruleIndex")
    if rule_id is None:
        return None

    rule_meta = rules_lookup.get(str(rule_id), {})

    primary_location = _extract_location(result)
    if primary_location is None:
        return None

    severity = result.get("level") if result.get("level") else "warning"

    fingerprints = result.get("partialFingerprints") or {}
    fingerprint = fingerprints.get("primaryLocationLineHash", "")

    flow = _extract_flow(result, source_root)

    return {
        "id": f"CQ-{index:04d}",
        "fingerprint": fingerprint,
        "language": language_id,
        "pack_profile": pack_profile,
        "pack": _first_pack(result, rules_lookup),
        "rule_id": str(rule_id),
        "rule_name": rule_meta.get("name", str(rule_id)),
        "severity": _normalize_severity(severity),
        "security_severity": rule_meta.get("security_severity"),
        "precision": rule_meta.get("precision"),
        "kind": result.get("kind"),
        "primary_location": primary_location,
        "flow": flow,
        "mapped": {
            "category": _map_category(str(rule_id), result),
            "suggested_validation_methods": _suggested_validation_methods(str(rule_id)),
        },
    }


def _extract_location(result: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the primary_location from the first result location."""
    locations = result.get("locations", [])
    if not isinstance(locations, list) or not locations:
        return None
    first = locations[0]
    if not isinstance(first, dict):
        return None
    pl = first.get("physicalLocation", {})
    if not isinstance(pl, dict):
        return None
    artifact = pl.get("artifactLocation", {})
    if not isinstance(artifact, dict):
        return None
    uri = artifact.get("uri", "")
    if not uri:
        return None
    region = pl.get("region", {})
    if not isinstance(region, dict):
        return {"path": uri, "start_line": 1, "end_line": 1}
    start_line = region.get("startLine", 1)
    return {
        "path": uri,
        "start_line": start_line,
        "end_line": region.get("endLine", start_line),
    }


def _extract_flow(result: dict[str, Any], source_root: Path) -> dict[str, Any] | None:
    """Extract source/sink/steps from codeFlows."""
    code_flows = result.get("codeFlows", [])
    if not isinstance(code_flows, list) or not code_flows:
        return None

    first_flow = code_flows[0]
    if not isinstance(first_flow, dict):
        return None

    thread_flows = first_flow.get("threadFlows", [])
    if not isinstance(thread_flows, list) or not thread_flows:
        return None

    locations = thread_flows[0].get("locations", [])
    if not isinstance(locations, list) or not locations:
        return None

    def _loc_to_entry(loc: dict[str, Any]) -> dict[str, Any] | None:
        loc_obj = loc.get("location", {})
        if not isinstance(loc_obj, dict):
            return None
        pl = loc_obj.get("physicalLocation", {})
        if not isinstance(pl, dict):
            return None
        artifact = pl.get("artifactLocation", {})
        if not isinstance(artifact, dict):
            return None
        uri = artifact.get("uri", "")
        region = pl.get("region", {})
        start_line = region.get("startLine", 1) if isinstance(region, dict) else 1
        message = loc.get("message", {})
        text = message.get("text", "") if isinstance(message, dict) else ""
        return {"path": uri, "line": start_line, "message": text}

    entries = []
    for loc in locations:
        if isinstance(loc, dict):
            entry = _loc_to_entry(loc)
            if entry:
                entries.append(entry)

    if len(entries) < 2:
        return None

    source = {"path": entries[0]["path"], "line": entries[0]["line"], "label": entries[0]["message"]}
    sink = {"path": entries[-1]["path"], "line": entries[-1]["line"], "label": entries[-1]["message"]}
    steps = []
    for entry in entries[1:-1]:
        steps.append({"path": entry["path"], "line": entry["line"], "message": entry["message"]})

    return {"source": source, "sink": sink, "steps": steps}


def _build_file_signals(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate alerts into per-file signals."""
    groups: dict[str, dict[str, Any]] = {}

    for alert in alerts:
        path = alert.get("primary_location", {}).get("path", "")
        if not path:
            continue
        if path not in groups:
            groups[path] = {
                "path": path,
                "codeql_score_boost": 0,
                "suggested_sweep": False,
                "alerts": {"total": 0, "path_problems": 0, "high_precision": 0},
                "rules": [],
            }
        grp = groups[path]
        grp["alerts"]["total"] += 1
        if alert.get("kind") == "path-problem":
            grp["alerts"]["path_problems"] += 1
        if alert.get("precision") == "high":
            grp["alerts"]["high_precision"] += 1
        rule_id = alert.get("rule_id", "")
        if rule_id and rule_id not in grp["rules"]:
            grp["rules"].append(rule_id)

    for grp in groups.values():
        total = grp["alerts"]["total"]
        path_problems = grp["alerts"]["path_problems"]
        high_prec = grp["alerts"]["high_precision"]
        boost = min(5, max(1, total + path_problems))
        if high_prec >= 2:
            boost = min(5, boost + 1)
        grp["codeql_score_boost"] = boost
        grp["suggested_sweep"] = total >= 2

    return sorted(groups.values(), key=lambda g: g["path"])


def _map_category(rule_id: str, result: dict[str, Any]) -> str:
    """Map a CodeQL rule ID to a vulnerability category."""
    mapping = {
        "path-injection": "Path traversal",
        "command-line-injection": "Command injection",
        "code-injection": "Code injection",
        "nosql-injection": "NoSQL injection",
        "sql-injection": "SQL injection",
        "xss": "Cross-site scripting",
        "hardcoded-credentials": "Hardcoded credentials",
        "incomplete-url-substring-sanitization": "URL redirection",
        "uncontrolled-deserialization": "Insecure deserialization",
        "open-redirect": "Open redirect",
        "information-exposure": "Information exposure",
        "cleartext-transmission": "Cleartext transmission",
        "codeql": "",  # catch-all
    }
    for suffix, category in mapping.items():
        if rule_id.endswith(suffix):
            return category
    # For CWE-prefixed rules or other unknown forms
    if "/" in rule_id:
        last = rule_id.rsplit("/", 1)[-1].replace("-", " ").title()
        return last
    return rule_id


def _suggested_validation_methods(rule_id: str) -> list[str]:
    """Suggest validation methods based on rule type."""
    if "sql" in rule_id or "nosql" in rule_id:
        return ["static_proof", "database_evidence"]
    if "injection" in rule_id:
        return ["static_proof", "runtime_reproduction"]
    if "xss" in rule_id or "cross-site" in rule_id.lower():
        return ["http_exploit"]
    return ["static_proof"]


def _normalize_severity(level: str) -> str:
    """Normalize SARIF severity levels."""
    mapping = {"error": "error", "warning": "warning", "note": "note", "none": "info"}
    return mapping.get(level, "warning")


def _first_pack(result: dict[str, Any], rules_lookup: dict[str, dict[str, Any]]) -> str:
    """Guess a pack reference from the result, fall back to rule metadata."""
    for loc in result.get("relatedLocations", []) or []:
        if isinstance(loc, dict):
            try:
                pr = loc.get("physicalLocation", {}).get("artifactLocation", {}).get("uri", "")
                if pr and "codeql/" in pr:
                    return pr
            except Exception:
                pass
    return ""


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _rel(path_str: str, source_root: Path) -> str:
    """Make a path workspace-relative when possible."""
    return str(path_str)
