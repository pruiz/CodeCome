from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codeql.normalize import (
    _build_file_signals,
    _extract_flow,
    _extract_location,
    _map_category,
    _normalize_severity,
    normalize_all,
)


def _minimal_sarif(results: list[dict]) -> dict:
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "CodeQL",
                        "rules": [
                            {
                                "id": "py/path-injection",
                                "name": "Uncontrolled data used in path expression",
                                "properties": {
                                    "precision": "high",
                                    "security-severity": "7.5",
                                    "problem.severity": "error",
                                },
                            }
                        ],
                    }
                },
                "results": results,
            }
        ],
    }


def _simple_result(
    rule_id: str,
    uri: str,
    line: int = 42,
    kind: str | None = "path-problem",
    severity: str = "warning",
    fingerprint: str = "abc123",
) -> dict:
    return {
        "ruleId": rule_id,
        "ruleIndex": 0,
        "kind": kind,
        "level": severity,
        "message": {"text": "Test message"},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": line, "endLine": line},
                }
            }
        ],
        "partialFingerprints": {"primaryLocationLineHash": fingerprint},
    }


def test_normalize_all_empty_sarif_dir(tmp_path: Path) -> None:
    sarif_dir = tmp_path / "sarif"
    sarif_dir.mkdir()
    out_dir = tmp_path / "normalized"

    resolved = {"languages": []}
    alerts_path, signals_path = normalize_all(
        sarif_dir, out_dir, resolved, "2.21.0", tmp_path,
    )
    assert alerts_path.is_file()
    assert signals_path.is_file()

    import yaml
    alerts = yaml.safe_load(alerts_path.read_text())
    assert alerts["alerts"] == []


def test_normalize_one_sarif(tmp_path: Path) -> None:
    sarif_dir = tmp_path / "sarif"
    sarif_dir.mkdir()
    sarif_file = sarif_dir / "python.official.sarif"
    sarif_file.write_text(
        json.dumps(
            _minimal_sarif(
                [
                    _simple_result("py/path-injection", "src/upload.py", 88),
                ]
            )
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "normalized"

    resolved = {"languages": [{"id": "python", "profiles": ["official"]}]}
    alerts_path, signals_path = normalize_all(
        sarif_dir, out_dir, resolved, "2.21.0", tmp_path,
    )

    import yaml
    alerts = yaml.safe_load(alerts_path.read_text())
    assert len(alerts["alerts"]) == 1
    a = alerts["alerts"][0]
    assert a["id"] == "CQ-0001"
    assert a["language"] == "python"
    assert a["pack_profile"] == "official"
    assert a["rule_id"] == "py/path-injection"
    assert a["primary_location"]["path"] == "src/upload.py"
    assert a["primary_location"]["start_line"] == 88
    assert a["mapped"]["category"] == "Path traversal"

    signals = yaml.safe_load(signals_path.read_text())
    assert len(signals["files"]) == 1
    assert signals["files"][0]["path"] == "src/upload.py"
    assert signals["files"][0]["rules"] == ["py/path-injection"]


def test_normalize_ignores_non_matching_filenames(tmp_path: Path) -> None:
    sarif_dir = tmp_path / "sarif"
    sarif_dir.mkdir()
    (sarif_dir / "not-a-match.json").write_text("{}")
    (sarif_dir / "single.sarif").write_text(json.dumps(_minimal_sarif([])))
    out_dir = tmp_path / "normalized"

    resolved = {"languages": []}
    alerts_path, _ = normalize_all(
        sarif_dir, out_dir, resolved, "2.21.0", tmp_path,
    )

    import yaml
    alerts = yaml.safe_load(alerts_path.read_text())
    assert alerts["alerts"] == []


def test_normalize_handles_invalid_json(tmp_path: Path) -> None:
    sarif_dir = tmp_path / "sarif"
    sarif_dir.mkdir()
    (sarif_dir / "python.bad.sarif").write_text("not json", encoding="utf-8")
    out_dir = tmp_path / "normalized"

    resolved = {"languages": []}
    alerts_path, _ = normalize_all(
        sarif_dir, out_dir, resolved, "2.21.0", tmp_path,
    )

    import yaml
    alerts = yaml.safe_load(alerts_path.read_text())
    assert alerts["alerts"] == []


def test_extract_location() -> None:
    result = {
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": "src/x.py"},
                    "region": {"startLine": 42, "endLine": 44},
                }
            }
        ]
    }
    loc = _extract_location(result)
    assert loc is not None
    assert loc["path"] == "src/x.py"
    assert loc["start_line"] == 42
    assert loc["end_line"] == 44


def test_extract_location_empty() -> None:
    assert _extract_location({"locations": []}) is None
    assert _extract_location({}) is None


def test_extract_flow_with_code_flows() -> None:
    result = {
        "codeFlows": [
            {
                "threadFlows": [
                    {
                        "locations": [
                            {
                                "location": {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": "src/a.py"},
                                        "region": {"startLine": 10},
                                    }
                                },
                                "message": {"text": "source"},
                            },
                            {
                                "location": {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": "src/b.py"},
                                        "region": {"startLine": 20},
                                    }
                                },
                                "message": {"text": "mid"},
                            },
                            {
                                "location": {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": "src/c.py"},
                                        "region": {"startLine": 30},
                                    }
                                },
                                "message": {"text": "sink"},
                            },
                        ]
                    }
                ]
            }
        ]
    }
    flow = _extract_flow(result, Path("."))
    assert flow is not None
    assert flow["source"]["path"] == "src/a.py"
    assert flow["source"]["line"] == 10
    assert flow["sink"]["path"] == "src/c.py"
    assert flow["sink"]["line"] == 30
    assert len(flow["steps"]) == 1
    assert flow["steps"][0]["path"] == "src/b.py"


def test_extract_flow_single_step_no_steps() -> None:
    """Two-location flow yields source+sink but no intermediate steps."""
    result = {
        "codeFlows": [
            {
                "threadFlows": [
                    {
                        "locations": [
                            {
                                "location": {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": "src/x.py"},
                                        "region": {"startLine": 1},
                                    }
                                },
                                "message": {"text": "s"},
                            },
                            {
                                "location": {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": "src/x.py"},
                                        "region": {"startLine": 99},
                                    }
                                },
                                "message": {"text": "k"},
                            },
                        ]
                    }
                ]
            }
        ]
    }
    flow = _extract_flow(result, Path("."))
    assert flow is not None
    assert flow["steps"] == []


def test_extract_flow_no_code_flows() -> None:
    assert _extract_flow({}, Path(".")) is None


def test_build_file_signals() -> None:
    alerts = [
        {
            "id": "CQ-0001",
            "rule_id": "py/injection",
            "kind": "path-problem",
            "precision": "high",
            "primary_location": {"path": "src/a.py", "start_line": 10, "end_line": 10},
        },
        {
            "id": "CQ-0002",
            "rule_id": "py/injection",
            "kind": "path-problem",
            "precision": "high",
            "primary_location": {"path": "src/a.py", "start_line": 20, "end_line": 20},
        },
        {
            "id": "CQ-0003",
            "rule_id": "py/xss",
            "kind": "problem",
            "precision": "medium",
            "primary_location": {"path": "src/b.py", "start_line": 5, "end_line": 5},
        },
    ]
    signals = _build_file_signals(alerts)
    assert len(signals) == 2
    a = [s for s in signals if s["path"] == "src/a.py"][0]
    assert a["alerts"]["total"] == 2
    assert a["alerts"]["path_problems"] == 2
    assert a["alerts"]["high_precision"] == 2
    assert a["suggested_sweep"] is True
    assert a["codeql_score_boost"] >= 4


def test_map_category() -> None:
    assert _map_category("py/path-injection", {}) == "Path traversal"
    assert _map_category("java/sql-injection", {}) == "SQL injection"
    assert _map_category("js/nosql-injection", {}) == "NoSQL injection"
    assert _map_category("js/xss", {}) == "Cross-site scripting"
    assert _map_category("unknown-rule", {}) == "unknown-rule"


def test_normalize_severity() -> None:
    assert _normalize_severity("error") == "error"
    assert _normalize_severity("warning") == "warning"
    assert _normalize_severity("note") == "note"
    assert _normalize_severity("none") == "info"
    assert _normalize_severity("unknown") == "warning"
