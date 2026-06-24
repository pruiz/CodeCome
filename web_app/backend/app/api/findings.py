from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
from pathlib import Path
from fastapi.responses import FileResponse, JSONResponse

from app.database import get_db
from app import crud, schemas
from app.models import Audit, Finding
from app.config import settings
from app.utils.codecome_wrapper import CodeComeExecutor
import mimetypes
import shutil
import yaml

router = APIRouter()

FINDING_STATUSES = ["PENDING", "CONFIRMED", "EXPLOITED", "REJECTED", "DUPLICATE"]


def finding_payload(finding: Finding, audit_name: Optional[str] = None) -> dict:
    return {
        "id": finding.id,
        "audit_id": finding.audit_id,
        "audit_name": audit_name,
        "title": finding.title,
        "status": finding.status,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "category": finding.category,
        "file_path": finding.file_path,
        "frontmatter": finding.frontmatter or {},
        "content": finding.content,
        "evidence_dir": finding.evidence_dir,
        "has_evidence": finding.has_evidence,
        "has_exploit": finding.has_exploit,
        "created_at": finding.created_at,
        "updated_at": finding.updated_at,
    }


def sync_audit_findings_from_workspace(db: Session, audit_id: Optional[UUID] = None):
    """Sync DB findings from itemdb so UI sees status moves immediately."""
    query = db.query(crud.models.Audit)
    if audit_id:
        query = query.filter(crud.models.Audit.id == audit_id)
    audits = query.all()
    executor = CodeComeExecutor()
    for audit in audits:
        if not audit.workspace_path:
            continue
        workspace = Path(audit.workspace_path)
        if not workspace.exists():
            continue
        for finding in executor.parse_findings(workspace):
            finding["audit_id"] = audit.id
            crud.upsert_finding(db, finding)
        crud.update_audit_findings_count(db, audit.id)


def sync_finding_markdown_status(audit, finding):
    if not audit or not audit.workspace_path:
        return
    workspace = Path(audit.workspace_path)
    findings_root = workspace / "itemdb" / "findings"
    if not findings_root.exists():
        return

    matches = []
    for status in FINDING_STATUSES:
        status_dir = findings_root / status
        if status_dir.exists():
            matches.extend(status_dir.glob(f"{finding.id}*.md"))
    if not matches:
        return

    source_path = matches[0]
    target_dir = findings_root / finding.status
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / source_path.name

    content = source_path.read_text()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = yaml.safe_load(parts[1]) or {}
            frontmatter["status"] = finding.status
            frontmatter["severity"] = finding.severity
            frontmatter["confidence"] = finding.confidence
            frontmatter["category"] = finding.category
            content = "---\n" + yaml.safe_dump(frontmatter, sort_keys=False).strip() + "\n---" + parts[2]

    if source_path != target_path:
        shutil.move(str(source_path), str(target_path))
    target_path.write_text(content)


@router.get("/", response_model=schemas.FindingListResponse)
def list_findings(
    audit_id: Optional[UUID] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """List findings globally or for one audit with filtering."""
    sync_audit_findings_from_workspace(db, audit_id)
    total, findings = crud.get_findings(db, audit_id, skip, limit, status, severity, category)
    audit_ids = {finding.audit_id for finding in findings}
    audit_names = {
        audit.id: audit.name
        for audit in db.query(Audit).filter(Audit.id.in_(audit_ids)).all()
    } if audit_ids else {}
    return schemas.FindingListResponse(
        total=total,
        findings=[finding_payload(finding, audit_names.get(finding.audit_id)) for finding in findings],
    )


@router.get("/{finding_id}", response_model=schemas.FindingResponse)
def get_finding(finding_id: str, audit_id: Optional[UUID] = Query(None), db: Session = Depends(get_db)):
    """Get finding detail."""
    sync_audit_findings_from_workspace(db, audit_id)
    query = db.query(Finding).filter(Finding.id == finding_id)
    if audit_id:
        query = query.filter(Finding.audit_id == audit_id)
    finding = query.first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    audit = crud.get_audit(db, finding.audit_id)
    return finding_payload(finding, audit.name if audit else None)


@router.patch("/{finding_id}", response_model=schemas.FindingResponse)
def update_finding(
    finding_id: str,
    finding_data: schemas.FindingUpdate,
    audit_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
):
    """Manually update finding review metadata."""
    finding = crud.update_finding(db, finding_id, finding_data, audit_id=audit_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    sync_finding_markdown_status(crud.get_audit(db, finding.audit_id), finding)
    audit = crud.get_audit(db, finding.audit_id)
    return finding_payload(finding, audit.name if audit else None)


@router.get("/{finding_id}/evidence", response_model=schemas.EvidenceListResponse)
def list_evidence(finding_id: str, db: Session = Depends(get_db)):
    """List evidence files for a finding."""
    finding = crud.get_finding(db, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    
    evidence_files = []
    
    if finding.evidence_dir:
        # Get audit to find workspace path
        audit = crud.get_audit(db, finding.audit_id)
        if audit:
            evidence_path = Path(audit.workspace_path) / finding.evidence_dir
            if evidence_path.exists():
                for file_path in evidence_path.rglob("*"):
                    if file_path.is_file():
                        mime_type, _ = mimetypes.guess_type(str(file_path))
                        evidence_files.append(schemas.EvidenceFile(
                            name=file_path.name,
                            path=str(file_path.relative_to(Path(audit.workspace_path))),
                            size=file_path.stat().st_size,
                            mime_type=mime_type or "application/octet-stream"
                        ))
    
    return schemas.EvidenceListResponse(
        finding_id=finding_id,
        evidence_dir=finding.evidence_dir,
        files=evidence_files
    )


@router.get("/{finding_id}/evidence/{filename}")
def download_evidence(finding_id: str, filename: str, db: Session = Depends(get_db)):
    """Download an evidence file."""
    finding = crud.get_finding(db, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    
    audit = crud.get_audit(db, finding.audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    
    evidence_path = Path(audit.workspace_path) / finding.evidence_dir / filename
    
    if not evidence_path.exists() or not audit.workspace_path:
        raise HTTPException(status_code=404, detail="Evidence file not found")
    
    return FileResponse(str(evidence_path), filename=filename)
