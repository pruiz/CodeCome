from types import SimpleNamespace

from app import crud, schemas


def test_apply_finding_update_changes_status_and_frontmatter():
    finding = SimpleNamespace(
        status="PENDING",
        severity="HIGH",
        confidence="MEDIUM",
        category="Injection",
        frontmatter={
            "id": "CC-0001",
            "status": "PENDING",
            "severity": "HIGH",
            "confidence": "MEDIUM",
            "category": "Injection",
        },
    )

    update = schemas.FindingUpdate(
        status="CONFIRMED",
        severity="CRITICAL",
        confidence="CONFIRMED",
        category="Command Injection",
        reviewer_note="Validated manually.",
    )

    crud.apply_finding_update(finding, update)

    assert finding.status == "CONFIRMED"
    assert finding.severity == "CRITICAL"
    assert finding.confidence == "CONFIRMED"
    assert finding.category == "Command Injection"
    assert finding.frontmatter["status"] == "CONFIRMED"
    assert finding.frontmatter["severity"] == "CRITICAL"
    assert finding.frontmatter["confidence"] == "CONFIRMED"
    assert finding.frontmatter["category"] == "Command Injection"
    assert finding.frontmatter["review_history"][0]["note"] == "Validated manually."
    assert "timestamp" in finding.frontmatter["review_history"][0]


def test_apply_finding_update_preserves_unset_fields():
    finding = SimpleNamespace(
        status="PENDING",
        severity="MEDIUM",
        confidence="HIGH",
        category="SSRF",
        frontmatter={"id": "CC-0002", "status": "PENDING", "severity": "MEDIUM"},
    )

    update = schemas.FindingUpdate(status="REJECTED")

    crud.apply_finding_update(finding, update)

    assert finding.status == "REJECTED"
    assert finding.severity == "MEDIUM"
    assert finding.confidence == "HIGH"
    assert finding.category == "SSRF"
    assert finding.frontmatter["status"] == "REJECTED"
    assert finding.frontmatter["severity"] == "MEDIUM"
