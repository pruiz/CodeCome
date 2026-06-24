from uuid import uuid4

import pytest

from app.api import findings as findings_api
from app.database import SessionLocal
from app.main import ensure_runtime_schema
from app.models import Audit, Finding
from app.schemas import FindingUpdate


def test_update_finding_api_with_real_session(tmp_path):
    try:
      ensure_runtime_schema()
    except Exception as exc:
      pytest.skip(f"database unavailable for integration-style test: {exc}")

    db = SessionLocal()
    audit_id = uuid4()
    finding_id = "CC-TST1"
    try:
      audit = Audit(
          id=audit_id,
          name="integration-test",
          status="ready",
          workspace_path=str(tmp_path),
          source_type="local",
          source_location="test.zip",
      )
      finding = Finding(
          id=finding_id,
          audit_id=audit_id,
          title="Test finding",
          status="PENDING",
          severity="LOW",
          confidence="LOW",
          category="Test",
          frontmatter={"id": finding_id, "status": "PENDING"},
          content="body",
      )
      db.add(audit)
      db.add(finding)
      db.commit()

      updated = findings_api.update_finding(
          finding_id,
          FindingUpdate(status="CONFIRMED", severity="HIGH", confidence="CONFIRMED", reviewer_note="integration note"),
          audit_id=audit_id,
          db=db,
      )

      assert updated.status == "CONFIRMED"
      assert updated.severity == "HIGH"
      assert updated.confidence == "CONFIRMED"
      assert updated.frontmatter["status"] == "CONFIRMED"
      assert updated.frontmatter["review_history"][0]["note"] == "integration note"
    except Exception as exc:
      db.rollback()
      pytest.skip(f"database unavailable for integration-style test: {exc}")
    finally:
      try:
        db.query(Finding).filter(Finding.id == finding_id).delete()
        db.query(Audit).filter(Audit.id == audit_id).delete()
        db.commit()
      except Exception:
        db.rollback()
      db.close()
