from __future__ import annotations

from conftest import load_tool_module


VALID_FRONTMATTER = """---
id: "CC-0001"
title: "Valid finding"
status: "PENDING"
severity: "MEDIUM"
confidence: "LOW"
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
validation:
  status: "NOT_STARTED"
  methods: []
  evidence_dir: "itemdb/evidence/CC-0001"
  summary: ""
exploitation:
  status: "NOT_STARTED"
  impact_demonstrated: ""
  exploit_type: ""
  severity_before: ""
  severity_after: ""
  artifacts_dir: "itemdb/evidence/CC-0001/exploits"
  summary: ""
created_at: "2026-01-01"
updated_at: "2026-01-01"
---

# Summary

Pending.
"""


def test_validate_frontmatter_happy_path(tmp_path):
    module = load_tool_module("check_frontmatter", "tools/check-frontmatter.py")
    finding = tmp_path / "itemdb" / "findings" / "PENDING" / "CC-0001-valid.md"
    finding.parent.mkdir(parents=True)
    finding.write_text(VALID_FRONTMATTER, encoding="utf-8")

    errors = module.validate_finding(finding)
    assert errors == []


def test_validate_frontmatter_status_directory_mismatch(tmp_path):
    module = load_tool_module("check_frontmatter_mismatch", "tools/check-frontmatter.py")
    finding = tmp_path / "itemdb" / "findings" / "CONFIRMED" / "CC-0001-valid.md"
    finding.parent.mkdir(parents=True)
    finding.write_text(VALID_FRONTMATTER, encoding="utf-8")

    errors = module.validate_finding(finding)
    assert any("status mismatch" in e for e in errors)


def test_validate_frontmatter_reports_yaml_parse_error(tmp_path):
    module = load_tool_module("check_frontmatter_yaml_error", "tools/check-frontmatter.py")
    finding = tmp_path / "itemdb" / "findings" / "PENDING" / "CC-0002-invalid-yaml.md"
    finding.parent.mkdir(parents=True)
    finding.write_text(
        """---
id: "CC-0002"
title: "Invalid yaml"
status: "PENDING"
validation:
status: "NOT_STARTED"
  methods: []
---

# Summary

Broken.
""",
        encoding="utf-8",
    )

    errors = module.validate_finding(finding)
    assert len(errors) == 1
    assert "while parsing a block mapping" in errors[0]
