from pathlib import Path
from types import SimpleNamespace

from app.api import findings, preview


class FakeQuery:
    def __init__(self):
        self.filters = []
        self.offset_value = None
        self.limit_value = None

    def filter(self, *args):
        self.filters.extend(args)
        return self

    def order_by(self, *args):
        return self

    def offset(self, value):
        self.offset_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def all(self):
        return []

    def scalar(self):
        return 0


class FakeSession:
    def __init__(self):
        self.queries = []

    def query(self, *args):
        query = FakeQuery()
        self.queries.append(query)
        return query


def test_get_findings_allows_global_query_without_audit_id():
    from app import crud

    db = FakeSession()
    total, findings = crud.get_findings(db, audit_id=None, skip=0, limit=20)

    assert total == 0
    assert findings == []
    assert len(db.queries) == 2
    # No audit_id filter should be added for global queries.
    assert db.queries[0].filters == []


def test_finding_payload_includes_audit_name():
    finding = SimpleNamespace(
        id="CC-0001",
        audit_id="audit-1",
        title="Demo finding",
        status="PENDING",
        severity="HIGH",
        confidence="MEDIUM",
        category="RCE",
        file_path="src/App.java",
        frontmatter={},
        content="body",
        evidence_dir=None,
        has_evidence=False,
        has_exploit=False,
        created_at=None,
        updated_at=None,
    )

    payload = findings.finding_payload(finding, "Audit One")

    assert payload["audit_name"] == "Audit One"
    assert payload["audit_id"] == "audit-1"


def test_preview_config_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "preview-analysis.md"
    monkeypatch.setattr(preview, "preview_config_path", lambda: path)

    empty = preview.get_preview_config()
    assert empty.prompt == ""
    assert empty.updated is False

    saved = preview.update_preview_config(SimpleNamespace(prompt="Analyze auth first"))
    assert saved.prompt == "Analyze auth first"
    assert saved.updated is True
    assert path.read_text() == "Analyze auth first"

    loaded = preview.get_preview_config()
    assert loaded.prompt == "Analyze auth first"
    assert loaded.updated is True
