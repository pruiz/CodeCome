from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
from fastapi.responses import StreamingResponse
import io
import re

from app.database import get_db
from app import crud
from app.models import AuditLog

router = APIRouter()

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
TOKEN_RE = re.compile(r"step finished: ([^(]+) \(input=(\d+), output=(\d+), reasoning=(\d+), total=(\d+)\)")
MODEL_RE = re.compile(r"^> Assistant · (.+?)(?: \(|$)")


def clean_terminal_text(value: str) -> str:
    return ANSI_RE.sub("", value or "")


def summarize_token_logs(logs):
    summary = {
        "turns": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 0,
        "models": {},
        "steps": {},
    }
    last_model = None
    for log in logs:
        message = clean_terminal_text(log.message)
        model_match = MODEL_RE.search(message)
        if model_match:
            last_model = model_match.group(1)
            summary["models"].setdefault(last_model, {"turns": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0})
            continue

        token_match = TOKEN_RE.search(message)
        if not token_match:
            continue

        step = token_match.group(1).strip()
        input_tokens = int(token_match.group(2))
        output_tokens = int(token_match.group(3))
        reasoning_tokens = int(token_match.group(4))
        total_tokens = int(token_match.group(5))

        summary["turns"] += 1
        summary["input_tokens"] += input_tokens
        summary["output_tokens"] += output_tokens
        summary["reasoning_tokens"] += reasoning_tokens
        summary["total_tokens"] += total_tokens

        step_summary = summary["steps"].setdefault(step, {"turns": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0})
        step_summary["turns"] += 1
        step_summary["input_tokens"] += input_tokens
        step_summary["output_tokens"] += output_tokens
        step_summary["reasoning_tokens"] += reasoning_tokens
        step_summary["total_tokens"] += total_tokens

        if last_model:
            model_summary = summary["models"].setdefault(last_model, {"turns": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0})
            model_summary["turns"] += 1
            model_summary["input_tokens"] += input_tokens
            model_summary["output_tokens"] += output_tokens
            model_summary["reasoning_tokens"] += reasoning_tokens
            model_summary["total_tokens"] += total_tokens
            last_model = None

    return summary


@router.get("/{audit_id}")
def list_audit_logs(
    audit_id: UUID = Path(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    level: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get audit logs with pagination and level filtering."""
    total, logs = crud.get_audit_logs(db, audit_id, skip, limit, level, phase)
    
    return {
        "audit_id": str(audit_id),
        "total": total,
        "logs": [{
            "id": log.id,
            "audit_id": str(log.audit_id),
            "timestamp": log.timestamp.isoformat(),
            "level": log.level,
            "message": clean_terminal_text(log.message),
            "phase": log.phase,
            "agent": log.agent,
            "source": log.source
        } for log in logs]
    }


@router.get("/{audit_id}/export")
def export_logs(
    audit_id: UUID = Path(...),
    db: Session = Depends(get_db)
):
    """Export all audit logs as text file."""
    total, logs = crud.get_audit_logs(db, audit_id, skip=0, limit=10000)
    
    # Format logs as text
    output = io.StringIO()
    for log in logs:
        output.write(f"[{log.timestamp}] {log.level}")
        if log.phase:
            output.write(f" [{log.phase}]")
        if log.agent:
            output.write(f" {log.agent}")
        output.write(f": {clean_terminal_text(log.message)}\n")
    
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8')),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=audit-{audit_id}-logs.txt"}
    )


@router.get("/{audit_id}/token-summary")
def token_summary(
    audit_id: UUID = Path(...),
    phase: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Approximate token usage summary parsed from OpenCode step-finished log lines."""
    query = db.query(AuditLog).filter(AuditLog.audit_id == audit_id)
    if phase:
        query = query.filter(AuditLog.phase == phase)
    logs = query.order_by(AuditLog.timestamp.asc(), AuditLog.id.asc()).all()
    return {
        "audit_id": str(audit_id),
        "phase": phase,
        "approximate": True,
        "note": "Parsed from OpenCode per-turn step finished lines; retries/resumes may duplicate context.",
        "summary": summarize_token_logs(logs),
    }
