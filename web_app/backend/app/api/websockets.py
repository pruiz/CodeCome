from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from uuid import UUID
import asyncio
import json

from app.database import SessionLocal
from app import crud

router = APIRouter()

# Connection manager
active_connections: dict[str, list[WebSocket]] = {}


async def safe_send_json(websocket: WebSocket, payload: dict) -> bool:
    try:
        await websocket.send_json(payload)
        return True
    except Exception:
        return False


@router.websocket("/audits/{audit_id}/logs")
async def websocket_logs(websocket: WebSocket, audit_id: str):
    """Stream real-time logs for an audit."""
    await websocket.accept()
    
    if audit_id not in active_connections:
        active_connections[audit_id] = []
    
    active_connections[audit_id].append(websocket)
    
    try:
        # Send historical logs first
        db = SessionLocal()
        try:
            last_id = 0
            total, logs = crud.get_audit_logs(db, UUID(audit_id), skip=0, limit=500)
            for log in reversed(logs):
                ok = await safe_send_json(websocket, {
                    "timestamp": log.timestamp.isoformat(),
                    "level": log.level,
                    "message": log.message[:2000],
                    "phase": log.phase,
                    "agent": log.agent,
                    "source": log.source
                })
                if not ok:
                    return
                last_id = max(last_id, log.id)
        finally:
            db.close()
        
        # Poll for new logs
        while True:
            await asyncio.sleep(1)
            
            db = SessionLocal()
            try:
                new_logs = crud.get_new_audit_logs(db, UUID(audit_id), last_id)
                
                for log in new_logs:
                    ok = await safe_send_json(websocket, {
                        "timestamp": log.timestamp.isoformat(),
                        "level": log.level,
                        "message": log.message[:2000],
                        "phase": log.phase,
                        "agent": log.agent,
                        "source": log.source
                    })
                    if not ok:
                        return
                    last_id = log.id
            except Exception as e:
                return
            finally:
                db.close()
                
    except WebSocketDisconnect:
        pass
    finally:
        if audit_id in active_connections and websocket in active_connections[audit_id]:
            active_connections[audit_id].remove(websocket)
            if not active_connections[audit_id]:
                del active_connections[audit_id]


@router.websocket("/audits/{audit_id}/status")
async def websocket_status(websocket: WebSocket, audit_id: str):
    """Stream audit status updates."""
    await websocket.accept()
    
    try:
        while True:
            db = SessionLocal()
            try:
                audit = crud.get_audit(db, UUID(audit_id))
                
                if audit:
                    ok = await safe_send_json(websocket, {
                        "audit_id": str(audit.id),
                        "status": audit.status,
                        "current_phase": audit.current_phase,
                        "total_findings": audit.total_findings,
                        "findings_by_status": audit.findings_by_status or {},
                        "updated_at": audit.updated_at.isoformat()
                    })
                    if not ok:
                        return
                else:
                    await safe_send_json(websocket, {"error": "Audit not found"})
                    break
            finally:
                db.close()
            
            await asyncio.sleep(2)
            
    except WebSocketDisconnect:
        pass
