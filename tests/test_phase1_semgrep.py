from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from findings.constants import FindingsContext
from phase1_enrichment.semgrep import normalize_semgrep_results, run_semgrep_enrichment


def temp_ctx(root: Path) -> FindingsContext:
    return FindingsContext(
        root=root,
        itemdb_root=root / "itemdb",
        findings_root=root / "itemdb" / "findings",
        evidence_root=root / "itemdb" / "evidence",
        notes_root=root / "itemdb" / "notes",
        reports_root=root / "itemdb" / "reports",
        template_path=root / "templates" / "finding.md",
        evidence_template_path=root / "templates" / "evidence-readme.md",
    )


def test_normalize_semgrep_results_extracts_recon_fields():
    findings = normalize_semgrep_results({
        "results": [{
            "check_id": "php.lang.security.sql-injection",
            "path": "src/app.php",
            "start": {"line": 12, "col": 5},
            "end": {"line": 13, "col": 1},
            "extra": {
                "message": "Possible SQL injection",
                "severity": "WARNING",
                "lines": "$db->query($_GET['q']);",
                "metadata": {
                    "confidence": "MEDIUM",
                    "cwe": ["CWE-89"],
                    "owasp": ["A03:2021"],
                    "category": "security",
                },
            },
        }]
    })

    assert len(findings) == 1
    assert findings[0].id == "SG-0001"
    assert findings[0].rule_id == "php.lang.security.sql-injection"
    assert findings[0].path == "src/app.php"
    assert findings[0].start_line == 12
    assert findings[0].severity == "WARNING"
    assert findings[0].confidence == "MEDIUM"
    assert findings[0].cwe == ["CWE-89"]


def test_run_semgrep_enrichment_writes_durable_artifacts(tmp_path):
    ctx = temp_ctx(tmp_path)
    (tmp_path / "src").mkdir()
    ctx.notes_root.mkdir(parents=True)
    (ctx.notes_root / "file-risk-index.yml").write_text(
        yaml.safe_dump({
            "schema_version": 1,
            "files": [{"path": "src/app.php", "score": 2, "reasons": ["Phase 1 lead."]}],
        }, sort_keys=False),
        encoding="utf-8",
    )
    (ctx.notes_root / "interesting-files.md").write_text("# Interesting Files\n\nExisting note.\n", encoding="utf-8")
    payload = {
        "results": [{
            "check_id": "php.lang.security.sql-injection",
            "path": "src/app.php",
            "start": {"line": 42},
            "end": {"line": 42},
            "extra": {
                "message": "Possible SQL injection",
                "severity": "ERROR",
                "metadata": {"cwe": ["CWE-89"], "confidence": "HIGH"},
            },
        }]
    }

    def fake_runner(command, **kwargs):
        assert command == ["semgrep", "--json", "--config", "auto", "src"]
        assert kwargs["cwd"] == str(tmp_path)
        assert kwargs["check"] is False
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    run = run_semgrep_enrichment(ctx=ctx, runner=fake_runner)

    assert run.status == "completed"
    assert len(run.findings) == 1
    assert (ctx.notes_root / "semgrep-raw.json").exists()
    assert (ctx.notes_root / "semgrep-results.yml").exists()
    assert (ctx.notes_root / "semgrep-scan.md").exists()
    assert (ctx.notes_root / "semgrep-interesting-files.md").exists()
    assert (ctx.notes_root / "semgrep-file-risk-index.yml").exists()
    assert list((tmp_path / "runs").glob("phase-1-semgrep-*.md"))
    assert not list((ctx.findings_root / "PENDING").glob("CC-*.md"))

    results = yaml.safe_load((ctx.notes_root / "semgrep-results.yml").read_text(encoding="utf-8"))
    assert results["status"] == "completed"
    assert results["summary"]["total_results"] == 1
    assert results["results"][0]["rule_id"] == "php.lang.security.sql-injection"

    risk = yaml.safe_load((ctx.notes_root / "semgrep-file-risk-index.yml").read_text(encoding="utf-8"))
    assert risk["files"][0]["path"] == "src/app.php"
    assert risk["files"][0]["score"] == 4
    assert risk["files"][0]["external_signals"]["semgrep"][0]["rule_id"] == "php.lang.security.sql-injection"

    merged_risk = yaml.safe_load((ctx.notes_root / "file-risk-index.yml").read_text(encoding="utf-8"))
    assert merged_risk["files"][0]["path"] == "src/app.php"
    assert merged_risk["files"][0]["score"] == 4
    assert "Phase 1 lead." in merged_risk["files"][0]["reasons"]
    assert merged_risk["files"][0]["external_signals"]["semgrep"][0]["rule_id"] == "php.lang.security.sql-injection"

    interesting = (ctx.notes_root / "interesting-files.md").read_text(encoding="utf-8")
    assert "Existing note." in interesting
    assert "# Semgrep Enrichment" in interesting
    assert "php.lang.security.sql-injection" in interesting


def test_run_semgrep_enrichment_skips_when_semgrep_missing(tmp_path):
    ctx = temp_ctx(tmp_path)
    (tmp_path / "src").mkdir()

    def missing_runner(command, **kwargs):
        raise FileNotFoundError("semgrep not found")

    run = run_semgrep_enrichment(ctx=ctx, runner=missing_runner)

    assert run.status == "skipped"
    assert run.returncode is None
    results = yaml.safe_load((ctx.notes_root / "semgrep-results.yml").read_text(encoding="utf-8"))
    assert results["status"] == "skipped"
    assert results["summary"]["total_results"] == 0
