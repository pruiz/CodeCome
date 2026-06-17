from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


def _write_phase2_finding(path: Path, *, title: str, category: str, target_area: str, summary: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        "id: \"CC-0099\"\n"
        f"title: \"{title}\"\n"
        "status: \"PENDING\"\n"
        "severity: \"MEDIUM\"\n"
        "cvss_v4:\n  vector: \"\"\n  score: 0.0\n  justification: \"\"\n"
        "confidence: \"MEDIUM\"\n"
        f"category: \"{category}\"\n"
        "cwe: [\"CWE-287\"]\n"
        "language: \"c\"\n"
        f"target_area: \"{target_area}\"\n"
        "files: [\"scheduler/ipp.c\"]\n"
        "symbols: [\"ippReadIO\"]\n"
        "entry_points: [\"IPP request parser\"]\n"
        "sources: [\"network IPP request\"]\n"
        "sinks: [\"authorization decision\"]\n"
        "trust_boundary: \"remote client to scheduler\"\n"
        "assets_at_risk: [\"scheduler authorization state\"]\n"
        "validation:\n  status: \"NOT_STARTED\"\n  methods: []\n  evidence_dir: \"itemdb/evidence/CC-0099\"\n  summary: \"\"\n"
        "exploitation:\n  status: \"NOT_STARTED\"\n  impact_demonstrated: \"\"\n  exploit_type: \"\"\n  severity_before: \"\"\n  severity_after: \"\"\n  artifacts_dir: \"itemdb/evidence/CC-0099/exploits\"\n  summary: \"\"\n"
        "created_at: \"2026-06-18\"\n"
        "updated_at: \"2026-06-18\"\n"
        "---\n\n"
        "# Summary\n\n"
        f"{summary}\n\n"
        "# Target context\n\n"
        "The CUPS scheduler accepts IPP requests from remote clients and maps request metadata into authorization state.\n\n"
        "# Affected code\n\n"
        "The affected path is `scheduler/ipp.c` in the IPP request parser and authorization handoff.\n\n"
        "# Vulnerability hypothesis\n\n"
        "A remote client may control the user identity attribute that reaches an authorization decision without canonicalization.\n\n"
        "# Source-to-sink reasoning\n\n"
        "The source is a network IPP request. The parser copies the identity attribute into scheduler request state. The sink is an authorization check that trusts that state.\n\n"
        "# Attackability / trigger conditions\n\n"
        "An unauthenticated remote client can send a crafted IPP request before authorization is evaluated.\n\n"
        "# Impact\n\n"
        "Successful exploitation could bypass authorization checks and perform scheduler operations as a more privileged user.\n\n"
        "# Validation plan\n\n"
        "Send crafted IPP requests with controlled identity attributes and compare the scheduler authorization outcome against a baseline request.\n\n"
        "# Counter-analysis\n\n"
        "Review parser normalization, authentication layers, and later authorization checks to determine whether attacker control is removed before the sink.\n\n"
        "# Validation result\n\n"
        "Pending.\n\n"
        "# Evidence\n\n"
        "Pending.\n",
        encoding="utf-8",
    )


def test_phase2_quality_rejects_test_template_artifact(tmp_path: Path) -> None:
    from findings.quality import validate_phase2_finding_quality

    finding = tmp_path / "itemdb" / "findings" / "PENDING" / "CC-0099-test-finding.md"
    _write_phase2_finding(
        finding,
        title="Test finding to see template",
        category="Test",
        target_area="Testing",
        summary="This is a test finding created to verify the template system. It does not represent an actual vulnerability.",
    )

    errors = validate_phase2_finding_quality(finding)

    assert any("test/template artifact" in error for error in errors), errors
    assert any("not an actual target vulnerability" in error for error in errors), errors
