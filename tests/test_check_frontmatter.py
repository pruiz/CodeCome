from __future__ import annotations

from conftest import load_tool_module


VALID_FRONTMATTER = """---
id: "CC-0001"
title: "Valid finding"
status: "PENDING"
severity: "MEDIUM"
cvss_v4:
  vector: "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:L/VI:L/VA:N/SC:N/SI:N/SA:N"
  score: 5.0
  justification: "Unit-test fixture with medium impact."
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


EXPLOITED_FRONTMATTER_TEMPLATE = """---
id: "CC-0001"
title: "Exploited finding"
status: "EXPLOITED"
severity: "HIGH"
cvss_v4:
  vector: "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:L/VA:N/SC:N/SI:N/SA:N/E:A"
  score: 8.0
  justification: "Unit-test fixture with demonstrated high impact."
confidence: "CONFIRMED"
category: "Test"
cwe: {cwe}
language: "c"
target_area: "parser"
files: []
symbols: []
entry_points: []
sources: []
sinks: []
trust_boundary: "input"
assets_at_risk: []
validation:
  status: "CONFIRMED"
  methods: []
  evidence_dir: "itemdb/evidence/CC-0001"
  summary: ""
exploitation:
  status: "DEMONSTRATED"
  impact_demonstrated: "RCE demonstrated"
  exploit_type: "stack_overflow_rce"
  severity_before: "HIGH"
  severity_after: "HIGH"
  artifacts_dir: "itemdb/evidence/CC-0001/exploits"
  summary: ""
created_at: "2026-01-01"
updated_at: "2026-01-01"
---

# Summary

Exploited.

# Root cause analysis

The vulnerable code reaches a dangerous sink without the required validation.

# Data flow

Not applicable. This fixture is not modeling an input-driven bug.

# Inputs and preconditions

The test fixture assumes the vulnerable path is reachable.

# Recording

No recording exists for this unit-test fixture.

# Remediation idea

```c
safe_call();
```
"""


def test_validate_frontmatter_exploited_requires_cwe(tmp_path):
    module = load_tool_module("check_frontmatter_cwe_required", "tools/check-frontmatter.py")
    finding = tmp_path / "itemdb" / "findings" / "EXPLOITED" / "CC-0001-no-cwe.md"
    finding.parent.mkdir(parents=True)
    finding.write_text(
        EXPLOITED_FRONTMATTER_TEMPLATE.format(cwe="[]"),
        encoding="utf-8",
    )

    errors = module.validate_finding(finding)
    assert any("EXPLOITED status requires at least one CWE id" in e for e in errors)


def test_validate_frontmatter_exploited_with_cwe_passes(tmp_path):
    module = load_tool_module("check_frontmatter_cwe_ok", "tools/check-frontmatter.py")
    finding = tmp_path / "itemdb" / "findings" / "EXPLOITED" / "CC-0001-with-cwe.md"
    finding.parent.mkdir(parents=True)
    finding.write_text(
        EXPLOITED_FRONTMATTER_TEMPLATE.format(cwe='["CWE-121"]'),
        encoding="utf-8",
    )

    errors = module.validate_finding(finding)
    assert errors == []


def test_validate_frontmatter_rejects_malformed_cwe(tmp_path):
    module = load_tool_module("check_frontmatter_cwe_bad", "tools/check-frontmatter.py")
    finding = tmp_path / "itemdb" / "findings" / "EXPLOITED" / "CC-0001-bad-cwe.md"
    finding.parent.mkdir(parents=True)
    finding.write_text(
        EXPLOITED_FRONTMATTER_TEMPLATE.format(cwe='["not-a-cwe"]'),
        encoding="utf-8",
    )

    errors = module.validate_finding(finding)
    assert any("invalid cwe entry" in e for e in errors)


def test_validate_frontmatter_exploited_requires_body_sections(tmp_path):
    module = load_tool_module("check_frontmatter_exploited_body", "tools/check-frontmatter.py")
    finding = tmp_path / "itemdb" / "findings" / "EXPLOITED" / "CC-0001-missing-body.md"
    finding.parent.mkdir(parents=True)
    finding.write_text(
        EXPLOITED_FRONTMATTER_TEMPLATE.format(cwe='["CWE-121"]')
        .split("# Root cause analysis", 1)[0],
        encoding="utf-8",
    )

    errors = module.validate_finding(finding)
    assert any("EXPLOITED status requires #Root cause analysis section" in e for e in errors)


def test_validate_frontmatter_confirmed_requires_remediation_code(tmp_path):
    module = load_tool_module("check_frontmatter_remediation_code", "tools/check-frontmatter.py")
    finding = tmp_path / "itemdb" / "findings" / "CONFIRMED" / "CC-0001-no-remediation-code.md"
    finding.parent.mkdir(parents=True)
    finding.write_text(
        VALID_FRONTMATTER.replace('status: "PENDING"', 'status: "CONFIRMED"')
        + "\n# Remediation idea\n\nUse a safe call, but no code block.\n",
        encoding="utf-8",
    )

    errors = module.validate_finding(finding)
    assert any("requires #Remediation idea with corrected-code excerpt" in e for e in errors)


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


def test_validate_rejects_bare_cc_xxxx_filename(tmp_path):
    module = load_tool_module("check_frontmatter_bare_name", "tools/check-frontmatter.py")
    finding = tmp_path / "itemdb" / "findings" / "PENDING" / "CC-0001.md"
    finding.parent.mkdir(parents=True)
    finding.write_text(VALID_FRONTMATTER, encoding="utf-8")

    errors = module.validate_finding(finding)
    assert any("bare CC-XXXX.md names are not allowed" in e for e in errors)


def test_validate_accepts_slug_filename(tmp_path):
    module = load_tool_module("check_frontmatter_slug", "tools/check-frontmatter.py")
    finding = tmp_path / "itemdb" / "findings" / "PENDING" / "CC-0001-some-finding.md"
    finding.parent.mkdir(parents=True)
    finding.write_text(VALID_FRONTMATTER, encoding="utf-8")

    errors = module.validate_finding(finding)
    assert errors == []


def test_validate_rejects_bare_with_valid_frontmatter(tmp_path):
    module = load_tool_module("check_frontmatter_bare_valid_fm", "tools/check-frontmatter.py")
    finding = tmp_path / "itemdb" / "findings" / "CONFIRMED" / "CC-0003.md"
    finding.parent.mkdir(parents=True)
    finding.write_text(
        VALID_FRONTMATTER.replace('status: "PENDING"', 'status: "CONFIRMED"').replace(
            'id: "CC-0001"', 'id: "CC-0003"'
        )
        + "\n# Remediation idea\n\n```c\nsafe();\n```\n",
        encoding="utf-8",
    )

    errors = module.validate_finding(finding)
    filename_errors = [e for e in errors if "bare CC-XXXX.md names" in e]
    assert len(filename_errors) == 1
    assert "CC-0003.md" in filename_errors[0]
