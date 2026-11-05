from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from findings import checks  # noqa: E402
from findings.constants import FindingsContext, STATUSES  # noqa: E402
from findings.move import move_finding  # noqa: E402

BASE = """---
id: "{id}"
title: "Finding"
status: "{status}"
capability:
  forbidden: true
  disposition: ""
  exposure: ""
  gate: ""
  cooperation: ""
  boundary: ""
  effect: ""
  scope: ""
  durability: ""
confidence: "MEDIUM"
category: "Test"
cwe: []
language: "python"
target_area: "api"
files: []
symbols: []
entry_points: []
sources: []
sinks: []
trust_boundary: "http"
assets_at_risk: []
{extra}validation:
  status: "NOT_STARTED"
  methods: []
  evidence_dir: "itemdb/evidence/{id}"
  summary: ""
exploitation:
  status: "NOT_STARTED"
  impact_demonstrated: ""
  exploit_type: ""
  capability_before: {{}}
  capability_after: {{}}
  artifacts_dir: "itemdb/evidence/{id}/exploits"
  summary: ""
created_at: "2026-01-01"
updated_at: "2026-01-01"
---

# Summary

Pending.
"""

NV_BLOCK = """fingerprint: "authz:src/api/orders.py#get:missing-owner-check"
needs_validation:
  blockers:
    - "Whether the ingress strips X-Forwarded-User is not visible in the repository."
  local_check: ""
  owner_check: "Ask the platform owner to show the ingress header policy for /api/orders."
"""


def _write(tmp_path: Path, status: str, extra: str = "", fid: str = "CC-0001") -> Path:
    path = tmp_path / "itemdb" / "findings" / status / f"{fid}-finding.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(BASE.format(id=fid, status=status, extra=extra), encoding="utf-8")
    return path


def test_needs_validation_is_a_known_status():
    assert "NEEDS_VALIDATION" in STATUSES
    assert STATUSES.index("PENDING") < STATUSES.index("NEEDS_VALIDATION") < STATUSES.index("CONFIRMED")


def test_valid_needs_validation_finding(tmp_path):
    assert checks.validate_finding(_write(tmp_path, "NEEDS_VALIDATION", NV_BLOCK)) == []


def test_needs_validation_requires_block_and_fingerprint(tmp_path):
    errors = checks.validate_finding(_write(tmp_path, "NEEDS_VALIDATION"))
    assert any("requires a populated fingerprint" in e for e in errors)
    assert any("requires a needs_validation block" in e for e in errors)


def test_needs_validation_requires_blocker_and_a_check(tmp_path):
    extra = """fingerprint: "x:y"
needs_validation:
  blockers: []
  local_check: "Pending."
  owner_check: ""
"""
    errors = checks.validate_finding(_write(tmp_path, "NEEDS_VALIDATION", extra))
    assert any("blockers entry" in e for e in errors)
    assert any("local_check or needs_validation.owner_check" in e for e in errors)


def test_pending_finding_without_new_fields_still_valid(tmp_path):
    # Backwards compatibility: pre-existing findings have neither field.
    assert checks.validate_finding(_write(tmp_path, "PENDING")) == []


def test_bad_fingerprint_rejected(tmp_path):
    errors = checks.validate_finding(_write(tmp_path, "PENDING", 'fingerprint: "has spaces in it"\n'))
    assert any("invalid fingerprint" in e for e in errors)


def test_duplicate_live_fingerprints_detected(tmp_path):
    fp = 'fingerprint: "sqli:src/db.py#query"\n'
    a = _write(tmp_path, "PENDING", fp, "CC-0001")
    b = _write(tmp_path, "CONFIRMED", fp, "CC-0002")
    c = _write(tmp_path, "DUPLICATE", fp, "CC-0003")
    dups = checks.find_duplicate_fingerprints([a, b, c])
    assert list(dups) == ["sqli:src/db.py#query"]
    assert set(dups["sqli:src/db.py#query"]) == {a, b}


def test_rejected_and_duplicate_may_share_fingerprint(tmp_path):
    fp = 'fingerprint: "sqli:src/db.py#query"\n'
    a = _write(tmp_path, "PENDING", fp, "CC-0001")
    b = _write(tmp_path, "REJECTED", fp, "CC-0002")
    assert checks.find_duplicate_fingerprints([a, b]) == {}


def test_move_to_needs_validation_sets_blocked(tmp_path):
    src = _write(tmp_path, "PENDING", NV_BLOCK)
    ctx = FindingsContext(root=tmp_path, findings_root=tmp_path / "itemdb" / "findings")
    target = move_finding(src, "NEEDS_VALIDATION", ctx=ctx)
    text = target.read_text(encoding="utf-8")
    assert target.parent.name == "NEEDS_VALIDATION"
    assert 'status: "NEEDS_VALIDATION"' in text
    assert "BLOCKED" in text
    assert checks.validate_finding(target) == []


def test_report_lists_needs_validation_without_severity():
    from findings.render_report import render_needs_validation_block

    lines = render_needs_validation_block(
        [
            {
                "id": "CC-0007",
                "title": "Header trust | ingress",
                "blockers": "Ingress header policy not in repo",
                "local_check": "",
                "owner_check": "Show ingress config",
            }
        ]
    )
    text = "\n".join(lines)
    assert "NEEDS_VALIDATION" in text
    assert "CC-0007" in text and "Show ingress config" in text
    assert "Header trust \\| ingress" in text
    assert "MEDIUM" not in text and "Severity" not in text
