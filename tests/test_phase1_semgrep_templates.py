from pathlib import Path

import yaml


def test_semgrep_enrichment_templates_define_required_artifacts():
    expected = [
        "semgrep-scan.md",
        "semgrep-results.yml",
        "semgrep-interesting-files.md",
        "semgrep-file-risk-index.yml",
    ]

    for name in expected:
        assert (Path("templates") / name).is_file(), f"missing template {name}"

    scan = Path("templates/semgrep-scan.md").read_text(encoding="utf-8")
    assert "Semgrep results are reconnaissance signals only" in scan
    assert "Phase 2 must perform source-to-sink reasoning" in scan
    assert "itemdb/notes/semgrep-results.yml" in scan

    results = yaml.safe_load(Path("templates/semgrep-results.yml").read_text(encoding="utf-8"))
    assert results["schema_version"] == 1
    assert results["tool"] == "semgrep"
    assert results["summary"]["total_results"] == 1
    result = results["results"][0]
    for field in [
        "id",
        "rule_id",
        "path",
        "start_line",
        "end_line",
        "message",
        "severity",
        "confidence",
        "cwe",
        "owasp",
        "category",
        "lines",
    ]:
        assert field in result

    risk = yaml.safe_load(Path("templates/semgrep-file-risk-index.yml").read_text(encoding="utf-8"))
    assert risk["source"] == "semgrep"
    assert risk["files"][0]["external_signals"]["semgrep"][0]["rule_id"]

    interesting = Path("templates/semgrep-interesting-files.md").read_text(encoding="utf-8")
    assert "These files are Phase 2 leads, not findings." in interesting
    assert "Do not copy entries directly into `itemdb/findings/`" in interesting
