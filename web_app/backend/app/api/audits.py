from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional, List
from uuid import UUID
from pathlib import Path
from fastapi.responses import FileResponse
import sys
import posixpath
from datetime import datetime
import json
import os
import re
import secrets
import socket
import subprocess

from app.database import get_db
from app import crud, models, schemas
from app.services.workspace import workspace_manager
from app.workers.phase_tasks import ALL_PHASES, PHASE_ORDER, audit_options, merged_phase_env, phase_order_for_settings, run_phase_task, run_sequential_workflow
from app.workers.question_answering import write_user_answers_context, with_user_answers_env
from app.utils.codecome_wrapper import CodeComeExecutor, codecome_executor
from app.utils.ssh_executor import SSHCodeComeExecutor
from app.config import settings
from app.api.preview import default_user_prompt_enrichment_prompt
import shutil
import zipfile
import yaml

router = APIRouter()

CODE_SERVER_SESSIONS: dict[str, dict] = {}


def tools_path() -> Path:
    return Path(settings.CODECOME_ROOT) / "tools"


def ensure_tools_import_path() -> None:
    path = str(tools_path())
    if path not in sys.path:
        sys.path.insert(0, path)


def sandbox_start_command(audit) -> str:
    try:
        config = yaml.safe_load(audit.codecome_yml or "") or {}
    except Exception:
        config = {}
    command = ((config.get("environment") or {}).get("startup_command") or "./sandbox/scripts/up.sh")
    return str(command).strip() or "./sandbox/scripts/up.sh"


def latest_report_path(workspace_path: Path) -> Path | None:
    reports_dir = workspace_path / "itemdb" / "reports"
    if not reports_dir.exists():
        return None
    candidates = [path for path in reports_dir.rglob("*") if path.is_file() and not path.name.startswith(".")]
    if not candidates:
        return None
    markdown = [path for path in candidates if path.suffix.lower() in {".md", ".markdown"}]
    return max(markdown or candidates, key=lambda path: path.stat().st_mtime)


def free_local_port() -> int:
    from app.api.settings import load_code_server_settings

    bind_addr = load_code_server_settings().bind_addr
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((bind_addr, 0))
        return int(sock.getsockname()[1])


def code_server_public_url(port: int) -> str:
    from app.api.settings import load_code_server_settings

    config = load_code_server_settings()
    base = (config.public_base_url or "").strip().rstrip("/")
    if base:
        return f"{base}:{port}"
    host = "localhost" if config.bind_addr in ("127.0.0.1", "localhost") else config.bind_addr
    return f"http://{host}:{port}"


def code_server_status_for_audit(audit_id: str) -> dict:
    session = CODE_SERVER_SESSIONS.get(str(audit_id))
    if not session:
        return {"running": False}
    process = session.get("process")
    if process and process.poll() is None:
        return {
            "running": True,
            "url": session["url"],
            "password": session["password"],
            "pid": process.pid,
            "port": session["port"],
            "bind_addr": session.get("bind_addr", settings.CODE_SERVER_BIND_ADDR),
            "workspace_path": session["workspace_path"],
            "started_at": session["started_at"],
        }
    CODE_SERVER_SESSIONS.pop(str(audit_id), None)
    return {"running": False}


def sync_remote_reports_if_needed(audit, workspace_path: Path, db: Session) -> None:
    if not audit.assigned_worker_id:
        return
    worker = crud.get_worker(db, audit.assigned_worker_id)
    if not worker or worker.type not in ("ssh", "proxmox-vm", "proxmox-lxc"):
        return
    SSHCodeComeExecutor(worker).download_reports(str(audit.id), workspace_path)


def gap_candidate_payloads(workspace_path: Path) -> list[dict]:
    ensure_tools_import_path()
    from findings.constants import FindingsContext
    from gap.compare import compare_candidate, load_candidates, load_finding_records

    ctx = FindingsContext(
        root=workspace_path,
        itemdb_root=workspace_path / "itemdb",
        findings_root=workspace_path / "itemdb" / "findings",
        evidence_root=workspace_path / "itemdb" / "evidence",
        notes_root=workspace_path / "itemdb" / "notes",
        reports_root=workspace_path / "itemdb" / "reports",
        template_path=workspace_path / "templates" / "finding.md",
        evidence_template_path=workspace_path / "templates" / "evidence-readme.md",
    )
    candidates = load_candidates(ctx.notes_root / "sast-gap-candidates.yml")
    findings = load_finding_records(ctx)
    payloads = []
    for candidate in candidates:
        result = compare_candidate(candidate, findings, ctx.notes_root)
        raw = dict(candidate.raw)
        manual_decision = raw.get("manual_decision") if isinstance(raw.get("manual_decision"), dict) else None
        if manual_decision:
            manual_value = manual_decision.get("decision")
            result_decision = "needs_human" if manual_value == "needs_human" else "defer_low_signal"
            result_action = {"ignored": "ignore", "deferred": "defer", "needs_human": "review"}.get(str(manual_value), "none")
            result_rationale = manual_decision.get("note") or f"Manually marked as {manual_value}."
        else:
            result_decision = result.decision
            result_action = result.action
            result_rationale = result.rationale
        raw.update({
            "id": candidate.id,
            "title": candidate.title,
            "category": candidate.category,
            "decision": result_decision,
            "action": result_action,
            "match_confidence": result.match_confidence,
            "matched_existing_findings": result.matched_findings,
            "matched_notes": result.matched_notes,
            "comparison_rationale": result_rationale,
            "sweep_files": result.sweep_files or candidate.sweep_files,
        })
        payloads.append(raw)
    return payloads


def read_remote_gap_scan_prompt(audit, worker) -> tuple[str, str] | None:
    if not worker or worker.type not in ("ssh", "proxmox-vm", "proxmox-lxc"):
        return None
    executor = SSHCodeComeExecutor(worker)
    client = None
    try:
        client = executor._connect()
        sftp = client.open_sftp()
        remote_path = posixpath.join(executor.remote_workspace_path(str(audit.id)), "prompts", "phase-2-gap-sast.md")
        if not executor._remote_exists(sftp, remote_path):
            return None
        return remote_path, executor._read_remote_file(sftp, remote_path)
    except Exception:
        return None
    finally:
        if client:
            client.close()


def default_gap_scan_prompt_for_audit(audit=None, worker=None) -> tuple[str, str]:
    if audit:
        remote_prompt = read_remote_gap_scan_prompt(audit, worker)
        if remote_prompt and remote_prompt[1].strip():
            return remote_prompt
        workspace_path = Path(getattr(audit, "workspace_path", "") or "")
        workspace_prompt = workspace_path / "prompts" / "phase-2-gap-sast.md"
        if workspace_prompt.exists():
            content = workspace_prompt.read_text(encoding="utf-8", errors="replace")
            if content.strip():
                return str(workspace_prompt), content
    root_prompt = Path(settings.CODECOME_ROOT) / "prompts" / "phase-2-gap-sast.md"
    if root_prompt.exists():
        content = root_prompt.read_text(encoding="utf-8", errors="replace")
        if content.strip():
            return "prompts/phase-2-gap-sast.md", content
    raise HTTPException(status_code=404, detail="Gap scan prompt not found in worker, audit workspace, or CodeCome root")


def gap_scan_prompt_payload(audit=None, worker=None) -> dict:
    prompt_path, default_prompt = default_gap_scan_prompt_for_audit(audit, worker)
    custom_prompt = audit_options(getattr(audit, "model_settings", None)).get("gap_scan_prompt") if audit else None
    return {
        "path": prompt_path,
        "default_prompt": default_prompt,
        "prompt": custom_prompt if isinstance(custom_prompt, str) and custom_prompt.strip() else default_prompt,
        "custom": bool(isinstance(custom_prompt, str) and custom_prompt.strip()),
    }


def sync_local_gap_scan_prompt(audit, prompt: str) -> str:
    raw_workspace_path = getattr(audit, "workspace_path", "") or ""
    if not raw_workspace_path:
        return "skipped"
    workspace_path = Path(raw_workspace_path)
    path = workspace_path / "runs" / "gap-scan-prompt.md"
    if prompt.strip():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt, encoding="utf-8")
        return str(path)
    if path.exists():
        path.unlink()
    return "removed"


def sync_remote_gap_scan_prompt(audit, worker, prompt: str) -> str:
    if not worker or worker.type not in ("ssh", "proxmox-vm", "proxmox-lxc"):
        return "skipped"
    executor = SSHCodeComeExecutor(worker)
    client = None
    try:
        client = executor._connect()
        sftp = client.open_sftp()
        remote_path = posixpath.join(executor.remote_workspace_path(str(audit.id)), "runs", "gap-scan-prompt.md")
        if prompt.strip():
            executor._mkdir_p(sftp, posixpath.dirname(remote_path))
            with sftp.open(remote_path, "w") as handle:
                handle.write(prompt)
            return remote_path
        if executor._remote_exists(sftp, remote_path):
            sftp.remove(remote_path)
        return "removed"
    except Exception as exc:
        return f"failed: {exc}"
    finally:
        if client:
            client.close()


PHASE1_ENRICHMENT_PROMPT_OPTION = "phase1_enrichment_prompt"
PHASE1_ENRICHMENT_PROMPT_PATH = "runs/phase-1-enrichment-user-prompt.md"


def preview_analysis_prompt_text() -> str:
    path = Path(settings.CODECOME_ROOT) / "web_app" / "backend" / "data" / "preview-analysis.md"
    if path.exists():
        prompt = path.read_text(encoding="utf-8", errors="replace")
        if prompt.strip():
            return prompt
    return default_user_prompt_enrichment_prompt()


def phase1_enrichment_prompt_payload(audit) -> dict:
    custom_prompt = audit_options(getattr(audit, "model_settings", None)).get(PHASE1_ENRICHMENT_PROMPT_OPTION)
    default_prompt = preview_analysis_prompt_text()
    return {
        "path": "web_app/backend/data/preview-analysis.md",
        "default_prompt": default_prompt,
        "prompt": custom_prompt if isinstance(custom_prompt, str) and custom_prompt.strip() else default_prompt,
        "custom": bool(isinstance(custom_prompt, str) and custom_prompt.strip()),
    }


def sync_local_phase1_enrichment_prompt(audit, prompt: str) -> str:
    raw_workspace_path = getattr(audit, "workspace_path", "") or ""
    if not raw_workspace_path:
        return "skipped"
    workspace_path = Path(raw_workspace_path)
    path = workspace_path / PHASE1_ENRICHMENT_PROMPT_PATH
    if prompt.strip():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt, encoding="utf-8")
        return PHASE1_ENRICHMENT_PROMPT_PATH
    if path.exists():
        path.unlink()
    return "removed"


def phase1_enrichment_artifact_payload(workspace_path: Path) -> dict:
    notes = workspace_path / "itemdb" / "notes"
    runs = workspace_path / "runs"
    semgrep_results = notes / "semgrep-results.yml"
    semgrep_summary = {}
    if semgrep_results.exists():
        try:
            data = yaml.safe_load(semgrep_results.read_text(encoding="utf-8")) or {}
            semgrep_summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        except Exception:
            semgrep_summary = {}
    artifact_paths = [
        "itemdb/notes/semgrep-results.yml",
        "itemdb/notes/semgrep-scan.md",
        "itemdb/notes/semgrep-interesting-files.md",
        "itemdb/notes/semgrep-file-risk-index.yml",
        "runs/phase-1-enrichment-prompt.md",
    ]
    artifacts = []
    for rel_path in artifact_paths:
        path = workspace_path / rel_path
        artifacts.append({"path": rel_path, "exists": path.exists()})
    summaries = []
    if runs.exists():
        for pattern in ("phase-1-semgrep-*.md", "phase-1-prompt-enrichment-*.md"):
            summaries.extend(path.name for path in runs.glob(pattern))
    summaries = sorted(set(summaries))
    return {"semgrep_summary": semgrep_summary, "artifacts": artifacts, "run_summaries": summaries}


def mark_gap_candidate(workspace_path: Path, candidate_id: str, request: schemas.GapCandidateMarkRequest) -> dict:
    if not re.fullmatch(r"GAP-\d{4,}", candidate_id):
        raise HTTPException(status_code=400, detail="candidate_id must look like GAP-0001")
    path = workspace_path / "itemdb" / "notes" / "sast-gap-candidates.yml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Gap candidates file not found")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    candidates = data.get("candidates") or []
    if not isinstance(candidates, list):
        raise HTTPException(status_code=400, detail="Gap candidates file has invalid candidates list")
    for candidate in candidates:
        if isinstance(candidate, dict) and str(candidate.get("id")) == candidate_id:
            candidate["manual_decision"] = {
                "decision": request.decision,
                "note": request.note or "",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            return candidate
    raise HTTPException(status_code=404, detail="Gap candidate not found")


def sandbox_runtime_env(audit, workspace_path: Path) -> dict:
    audit_slug = re.sub(r"[^a-z0-9]+", "", str(audit.id).lower()) or "audit"
    project_name = f"codecome_{audit_slug}"[:63]
    env = os.environ.copy()
    env.update({
        "COMPOSE_PROJECT_NAME": project_name,
        "CODECOME_AUDIT_ID": str(audit.id),
        "CODECOME_WORKSPACE": str(workspace_path),
    })
    return env


def audit_response(audit, db: Session, phase_executions=None, include_config: bool = True) -> schemas.AuditResponse:
    question_counts = crud.question_counts_for_audit(db, audit.id)
    question_owner = crud.get_user(db, audit.question_owner_user_id) if audit.question_owner_user_id else None
    return schemas.AuditResponse(
        id=audit.id,
        name=audit.name,
        status=audit.status,
        current_phase=audit.current_phase,
        assigned_worker_id=audit.assigned_worker_id,
        question_owner_user_id=audit.question_owner_user_id,
        question_owner_name=question_owner.display_name if question_owner else None,
        question_owner_is_llm=question_owner.is_llm_user if question_owner else None,
        workspace_path=audit.workspace_path,
        source_type=audit.source_type,
        source_location=audit.source_location,
        has_codecome_yml=bool(audit.codecome_yml),
        codecome_yml=audit.codecome_yml if include_config else None,
        model_settings=(audit.model_settings or {}) if include_config else {},
        ai_review_enabled=audit.ai_review_enabled,
        auto_continue=audit.auto_continue,
        total_findings=audit.total_findings,
        findings_by_status=audit.findings_by_status or {},
        open_questions=question_counts["open_questions"],
        blocking_questions=question_counts["blocking_questions"],
        created_at=audit.created_at,
        updated_at=audit.updated_at,
        phase_executions=phase_executions,
    )


def next_audit_step(phase_executions, model_settings: dict | None = None) -> str:
    by_phase = {execution.phase: execution for execution in phase_executions}
    legacy_aliases = {
        "make validate-all": "phase-4",
        "make exploit-all": "phase-5",
    }
    for phase in phase_order_for_settings(model_settings):
        execution = by_phase.get(phase)
        if not execution and phase in legacy_aliases:
            execution = by_phase.get(legacy_aliases[phase])
        if not execution:
            return phase
        if execution.status in ("failed", "cancelled"):
            return phase
        if execution.status == "running":
            return phase
    return "phase-6"


def queue_audit_phase(db: Session, audit, phase: str, extra_env: dict | None = None):
    if phase not in ALL_PHASES:
        raise HTTPException(status_code=400, detail="Unsupported phase")
    if "running" in audit.status:
        raise HTTPException(status_code=409, detail="Audit is already running")

    worker = crud.select_available_worker(db, audit.assigned_worker_id)
    if not worker:
        raise HTTPException(status_code=409, detail="No available worker")
    audit.assigned_worker_id = worker.id

    model_settings = audit.model_settings or {}
    phase_config = model_settings.get(phase, {})
    model = phase_config.get("model")
    variant = phase_config.get("variant")
    env_overrides = with_user_answers_env(Path(audit.workspace_path), {**merged_phase_env(model_settings, phase), **(extra_env or {})})

    audit.current_phase = phase
    db.commit()
    run_phase_task.delay(str(audit.id), phase, model, variant, None, 1, worker.id, env_overrides)
    return worker


def start_created_audit_if_requested(db: Session, audit):
    if not audit.auto_continue:
        return None
    return queue_audit_phase(db, audit, next_audit_step([], audit.model_settings))


@router.post("/", response_model=schemas.AuditResponse, status_code=201)
def create_audit(audit_data: schemas.AuditCreate, db: Session = Depends(get_db)):
    """Create a new audit from source code."""
    from uuid import uuid4
    
    audit_id = uuid4()
    workspace_path = workspace_manager.create_workspace(str(audit_id))
    
    # Setup source code
    success = False
    if audit_data.source_type == "git":
        success = workspace_manager.setup_source_from_git(workspace_path, audit_data.source_location)
    elif audit_data.source_type == "zip":
        success = workspace_manager.setup_source_from_zip(workspace_path, audit_data.source_location)
    elif audit_data.source_type == "local":
        # For local type, check if it's a ZIP file first
        import os
        if audit_data.source_location.endswith('.zip'):
            success = workspace_manager.setup_source_from_zip(workspace_path, audit_data.source_location)
        else:
            success = workspace_manager.setup_source_from_local(workspace_path, audit_data.source_location)
    
    if not success:
        workspace_manager.cleanup_workspace(workspace_path)
        raise HTTPException(status_code=400, detail="Failed to setup source code")
    
    # Write codecome.yml
    yml_content = audit_data.codecome_yml
    if not yml_content:
        # Use default from CodeCome root
        default_yml = settings.CODECOME_ROOT / "codecome.yml"
        if default_yml.exists():
            yml_content = default_yml.read_text()
        else:
            yml_content = f"project:\n  name: \"{audit_data.name}\"\n  source_path: \"./src\"\n"
    
    workspace_manager.write_codecome_yml(workspace_path, yml_content)
    
    # Create audit record
    worker = crud.get_worker(db, audit_data.worker_id) if audit_data.worker_id else None
    if audit_data.worker_id and not worker:
        workspace_manager.cleanup_workspace(workspace_path)
        raise HTTPException(status_code=404, detail="Worker not found")
    if audit_data.question_owner_user_id and not crud.get_user(db, audit_data.question_owner_user_id):
        workspace_manager.cleanup_workspace(workspace_path)
        raise HTTPException(status_code=404, detail="Question owner user not found")
    question_owner_user_id = audit_data.question_owner_user_id
    if not question_owner_user_id:
        default_owner = crud.default_question_owner(db)
        question_owner_user_id = default_owner.id if default_owner else None

    db_audit = crud.create_audit(db, schemas.AuditCreate(
        name=audit_data.name,
        source_type=audit_data.source_type,
        source_location=audit_data.source_location,
        codecome_yml=yml_content,
        model_settings=audit_data.model_settings,
        ai_review_enabled=audit_data.ai_review_enabled,
        auto_continue=audit_data.auto_continue,
        worker_id=audit_data.worker_id,
        question_owner_user_id=question_owner_user_id,
        workspace_path=str(workspace_path),
    ))
    start_created_audit_if_requested(db, db_audit)
    
    return db_audit


@router.get("/", response_model=schemas.AuditListResponse)
def list_audits(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """List all audits with pagination and status filtering."""
    total, audits = crud.get_audits(db, skip, limit, status)
    return schemas.AuditListResponse(total=total, audits=[audit_response(audit, db, include_config=False) for audit in audits])


@router.get("/{audit_id}", response_model=schemas.AuditResponse)
def get_audit(audit_id: UUID, db: Session = Depends(get_db)):
    """Get audit details including phase executions."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    phase_execs = crud.get_phase_executions(db, audit_id)
    
    return audit_response(audit, db, phase_execs)


@router.patch("/{audit_id}", response_model=schemas.AuditResponse)
def update_audit(audit_id: UUID, audit_data: schemas.AuditUpdate, db: Session = Depends(get_db)):
    """Update audit configuration."""
    update_payload = audit_data.model_dump(exclude_unset=True)
    if update_payload.get("question_owner_user_id") and not crud.get_user(db, update_payload["question_owner_user_id"]):
        raise HTTPException(status_code=404, detail="Question owner user not found")
    audit = crud.update_audit(db, audit_id, audit_data)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    return audit


@router.delete("/{audit_id}", status_code=204)
def delete_audit(audit_id: UUID, db: Session = Depends(get_db)):
    """Delete audit and its workspace."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    
    # Cleanup workspace
    workspace_manager.cleanup_workspace(Path(audit.workspace_path))
    
    # Delete from database
    crud.delete_audit(db, audit_id)


@router.post("/{audit_id}/start")
def start_audit(audit_id: UUID, db: Session = Depends(get_db)):
    """Start or resume audit workflow."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    if crud.audit_has_open_blocking_questions(db, audit_id):
        raise HTTPException(status_code=409, detail="Audit has open blocking questions")

    phase_executions = crud.get_phase_executions(db, audit_id)
    starting_phase = next_audit_step(phase_executions, audit.model_settings)
    worker = queue_audit_phase(db, audit, starting_phase)
    
    return {
        "audit_id": str(audit_id),
        "status": f"{starting_phase.replace('-', '_')}_running",
        "worker_id": worker.id,
        "worker_name": worker.name,
        "message": "Audit workflow started",
    }


@router.post("/{audit_id}/run-phase")
def run_audit_phase(audit_id: UUID, phase: str = Query(...), db: Session = Depends(get_db)):
    """Run a specific phase, including optional phases such as make sweep."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    if crud.audit_has_open_blocking_questions(db, audit_id):
        raise HTTPException(status_code=409, detail="Audit has open blocking questions")
    worker = queue_audit_phase(db, audit, phase)
    return {
        "audit_id": str(audit_id),
        "status": f"{phase.replace('-', '_').replace(' ', '_')}_running",
        "phase": phase,
        "worker_id": worker.id,
        "worker_name": worker.name,
        "message": "Audit phase queued",
    }


@router.post("/{audit_id}/gap-scan")
def run_gap_scan(audit_id: UUID, db: Session = Depends(get_db)):
    """Manually queue the optional post-exploit gap-scan step."""
    return queue_gap_step(db, audit_id, "gap-scan", "Gap scan queued")


@router.post("/{audit_id}/phase-1-semgrep")
def run_phase1_semgrep(audit_id: UUID, db: Session = Depends(get_db)):
    """Manually queue optional Phase 1 Semgrep enrichment."""
    return queue_gap_step(db, audit_id, "phase-1-semgrep", "Phase 1 Semgrep enrichment queued")


@router.post("/{audit_id}/phase-1-prompt-enrich")
def run_phase1_prompt_enrichment(audit_id: UUID, db: Session = Depends(get_db)):
    """Manually queue optional Phase 1 user-prompt enrichment."""
    return queue_gap_step(db, audit_id, "phase-1-prompt-enrich", "Phase 1 prompt enrichment queued")


def queue_gap_step(db: Session, audit_id: UUID, phase: str, message: str, extra_env: dict | None = None):
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    if crud.audit_has_open_blocking_questions(db, audit_id):
        raise HTTPException(status_code=409, detail="Audit has open blocking questions")
    worker = queue_audit_phase(db, audit, phase, extra_env=extra_env)
    return {
        "audit_id": str(audit_id),
        "status": f"{phase.replace('-', '_')}_running",
        "phase": phase,
        "worker_id": worker.id,
        "worker_name": worker.name,
        "message": message,
    }


@router.post("/{audit_id}/gap-compare")
def run_gap_compare(audit_id: UUID, db: Session = Depends(get_db)):
    """Manually queue comparison of gap candidates against existing findings."""
    return queue_gap_step(db, audit_id, "gap-compare", "Gap compare queued")


@router.post("/{audit_id}/gap-sweep")
def run_gap_sweep(audit_id: UUID, candidate: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Manually queue targeted sweeps for missing gap candidates."""
    extra_env = None
    candidate = candidate if isinstance(candidate, str) else None
    if candidate:
        if not re.fullmatch(r"GAP-\d{4,}", candidate):
            raise HTTPException(status_code=400, detail="candidate must look like GAP-0001")
        extra_env = {"ARGS": f"--candidate {candidate}"}
    return queue_gap_step(db, audit_id, "gap-sweep", "Gap sweep queued", extra_env=extra_env)


@router.get("/{audit_id}/gap-candidates")
def list_gap_candidates(audit_id: UUID, db: Session = Depends(get_db)):
    """List gap-scan candidates with current deterministic comparison decisions."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    workspace_path = Path(audit.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Audit workspace not found")
    candidates = gap_candidate_payloads(workspace_path)
    return {
        "audit_id": str(audit_id),
        "total": len(candidates),
        "candidates": candidates,
    }


@router.get("/{audit_id}/phase-1-enrichment-artifacts")
def list_phase1_enrichment_artifacts(audit_id: UUID, db: Session = Depends(get_db)):
    """List optional Phase 1 enrichment artifacts currently present in the workspace."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    workspace_path = Path(audit.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Audit workspace not found")
    payload = phase1_enrichment_artifact_payload(workspace_path)
    payload.update({"audit_id": str(audit_id)})
    return payload


@router.get("/{audit_id}/phase-1-enrichment-prompt")
def get_phase1_enrichment_prompt(audit_id: UUID, db: Session = Depends(get_db)):
    """Return the prompt used by optional Phase 1 prompt enrichment."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    return phase1_enrichment_prompt_payload(audit)


@router.put("/{audit_id}/phase-1-enrichment-prompt")
def update_phase1_enrichment_prompt(audit_id: UUID, request: schemas.Phase1EnrichmentPromptUpdate, db: Session = Depends(get_db)):
    """Save or reset an audit-specific Phase 1 enrichment prompt."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    prompt = request.prompt or ""
    model_settings = dict(audit.model_settings or {})
    options = dict(model_settings.get("__audit_options") or {})
    if prompt.strip():
        options[PHASE1_ENRICHMENT_PROMPT_OPTION] = prompt
    else:
        options.pop(PHASE1_ENRICHMENT_PROMPT_OPTION, None)
    model_settings["__audit_options"] = options
    audit.model_settings = model_settings
    db.commit()
    db.refresh(audit)
    local_sync = sync_local_phase1_enrichment_prompt(audit, prompt)
    payload = phase1_enrichment_prompt_payload(audit)
    payload.update({"local_sync": local_sync})
    return payload


@router.get("/{audit_id}/gap-prompt")
def get_gap_prompt(audit_id: UUID, db: Session = Depends(get_db)):
    """Return the prompt file used by make gap-scan for review in the UI."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    assigned_worker_id = getattr(audit, "assigned_worker_id", None)
    worker = crud.get_worker(db, assigned_worker_id) if assigned_worker_id else None
    return gap_scan_prompt_payload(audit, worker)


@router.put("/{audit_id}/gap-prompt")
def update_gap_prompt(audit_id: UUID, request: schemas.GapPromptUpdate, db: Session = Depends(get_db)):
    """Save or reset the audit-specific gap-scan prompt and sync it to the worker workspace."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    prompt = request.prompt or ""
    model_settings = dict(audit.model_settings or {})
    options = dict(model_settings.get("__audit_options") or {})
    if prompt.strip():
        options["gap_scan_prompt"] = prompt
    else:
        options.pop("gap_scan_prompt", None)
    model_settings["__audit_options"] = options
    audit.model_settings = model_settings
    db.commit()
    db.refresh(audit)

    assigned_worker_id = getattr(audit, "assigned_worker_id", None)
    worker = crud.get_worker(db, assigned_worker_id) if assigned_worker_id else None
    local_sync = sync_local_gap_scan_prompt(audit, prompt)
    remote_sync = sync_remote_gap_scan_prompt(audit, worker, prompt)
    payload = gap_scan_prompt_payload(audit, worker)
    payload.update({"local_sync": local_sync, "remote_sync": remote_sync})
    return payload


@router.post("/{audit_id}/gap-candidates/{candidate_id}/mark")
def mark_gap_candidate_decision(
    audit_id: UUID,
    candidate_id: str,
    request: schemas.GapCandidateMarkRequest,
    db: Session = Depends(get_db),
):
    """Manually mark a gap candidate as ignored, deferred, or needing human review."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    workspace_path = Path(audit.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Audit workspace not found")
    candidate = mark_gap_candidate(workspace_path, candidate_id, request)
    return {
        "audit_id": str(audit_id),
        "candidate_id": candidate_id,
        "candidate": candidate,
        "message": f"Gap candidate marked as {request.decision}",
    }


@router.post("/{audit_id}/continue-after-questions")
def continue_after_questions(audit_id: UUID, db: Session = Depends(get_db)):
    """Continue an audit once all blocking questions are answered or dismissed."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    if crud.audit_has_open_blocking_questions(db, audit_id):
        raise HTTPException(status_code=409, detail="Audit has open blocking questions")
    write_user_answers_context(db, audit, Path(audit.workspace_path))
    phase_executions = crud.get_phase_executions(db, audit_id)
    starting_phase = next_audit_step(phase_executions, audit.model_settings)
    worker = queue_audit_phase(db, audit, starting_phase)
    return {
        "audit_id": str(audit_id),
        "phase": starting_phase,
        "worker_id": worker.id,
        "worker_name": worker.name,
        "message": "Audit continued after questions",
    }


@router.post("/{audit_id}/sandbox/start")
def start_audit_sandbox(audit_id: UUID, db: Session = Depends(get_db)):
    """Queue audit sandbox startup on the assigned worker."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    if crud.audit_has_open_blocking_questions(db, audit_id):
        raise HTTPException(status_code=409, detail="Audit has open blocking questions")
    worker = queue_audit_phase(db, audit, "make sandbox-up")
    return {
        "audit_id": str(audit_id),
        "phase": "make sandbox-up",
        "worker_id": worker.id,
        "worker_name": worker.name,
        "message": "Sandbox startup queued on worker",
    }


@router.get("/{audit_id}/report/download")
def download_latest_report(audit_id: UUID, db: Session = Depends(get_db)):
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    workspace_path = Path(audit.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Audit workspace not found")

    report_path = latest_report_path(workspace_path)
    if report_path is None:
        try:
            sync_remote_reports_if_needed(audit, workspace_path, db)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch remote report artifacts: {exc}")
        report_path = latest_report_path(workspace_path)
    if report_path is None:
        raise HTTPException(status_code=404, detail="No report file found under itemdb/reports")
    return FileResponse(str(report_path), filename=report_path.name, media_type="text/markdown")


@router.get("/{audit_id}/code-server/status")
def code_server_status(audit_id: UUID, db: Session = Depends(get_db)):
    """Return local web-host code-server status for an audit workspace."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    status = code_server_status_for_audit(str(audit_id))
    status["audit_id"] = str(audit_id)
    return status


@router.post("/{audit_id}/code-server/start")
def start_code_server(audit_id: UUID, db: Session = Depends(get_db)):
    """Start code-server on the web host for the local synced audit workspace."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    workspace_path = Path(audit.workspace_path)
    if not workspace_path.exists():
        raise HTTPException(status_code=404, detail="Audit workspace not found")
    existing = code_server_status_for_audit(str(audit_id))
    if existing.get("running"):
        existing["audit_id"] = str(audit_id)
        return existing
    if not shutil.which("code-server"):
        raise HTTPException(status_code=503, detail="code-server is not installed on the web host")
    from app.api.settings import load_code_server_settings

    code_server_config = load_code_server_settings()
    port = free_local_port()
    password = secrets.token_urlsafe(18)
    data_dir = workspace_path / "runs" / "code-server-data"
    extensions_dir = workspace_path / "runs" / "code-server-extensions"
    data_dir.mkdir(parents=True, exist_ok=True)
    extensions_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PASSWORD"] = password
    cmd = [
        "code-server",
        "--bind-addr",
        f"{code_server_config.bind_addr}:{port}",
        "--auth",
        "password",
        "--disable-telemetry",
        "--user-data-dir",
        str(data_dir),
        "--extensions-dir",
        str(extensions_dir),
        str(workspace_path),
    ]
    process = subprocess.Popen(cmd, cwd=str(workspace_path), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
    session = {
        "process": process,
        "port": port,
        "password": password,
        "url": code_server_public_url(port),
        "bind_addr": code_server_config.bind_addr,
        "workspace_path": str(workspace_path),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    CODE_SERVER_SESSIONS[str(audit_id)] = session
    return {"audit_id": str(audit_id), **code_server_status_for_audit(str(audit_id))}


@router.post("/{audit_id}/code-server/stop")
def stop_code_server(audit_id: UUID, db: Session = Depends(get_db)):
    """Stop local web-host code-server for an audit workspace."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    session = CODE_SERVER_SESSIONS.pop(str(audit_id), None)
    process = session.get("process") if session else None
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    return {"audit_id": str(audit_id), "running": False}


@router.post("/{audit_id}/pause")
def pause_audit(audit_id: UUID, db: Session = Depends(get_db)):
    """Pause audit workflow after current phase."""
    audit = crud.get_audit(db, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    running_execution = db.query(models.PhaseExecution).filter(
        models.PhaseExecution.audit_id == audit_id,
        models.PhaseExecution.status == "running",
    ).order_by(models.PhaseExecution.started_at.desc()).first()

    if running_execution:
        worker = crud.get_worker(db, running_execution.worker_id) if running_execution.worker_id else None
        if worker and worker.type == "local" and running_execution.local_pid:
            try:
                CodeComeExecutor.terminate_process_group(running_execution.local_pid)
                crud.create_audit_log(db, audit_id, "WARN", f"Sent SIGTERM to local process group {running_execution.local_pid}", phase=running_execution.phase, source="system")
            except ProcessLookupError:
                crud.create_audit_log(db, audit_id, "WARN", f"Local process {running_execution.local_pid} was already gone", phase=running_execution.phase, source="system")
            except Exception as exc:
                crud.create_audit_log(db, audit_id, "ERROR", f"Failed to stop local process {running_execution.local_pid}: {exc}", phase=running_execution.phase, source="system")
        elif worker and worker.type in ("ssh", "proxmox-vm", "proxmox-lxc") and running_execution.remote_pid:
            try:
                SSHCodeComeExecutor(worker).cancel_remote_pid(running_execution.remote_pid)
                crud.create_audit_log(db, audit_id, "WARN", f"Sent SIGTERM to remote process {running_execution.remote_pid}", phase=running_execution.phase, source="system")
            except Exception as exc:
                crud.create_audit_log(db, audit_id, "ERROR", f"Failed to stop remote process {running_execution.remote_pid}: {exc}", phase=running_execution.phase, source="system")

        crud.update_phase_execution(db, running_execution.id, {
            "status": "cancelled",
            "completed_at": datetime.now(),
            "error_message": "Cancelled by user pause request",
        })

    crud.update_audit_status(db, audit_id, "paused")

    return {
        "audit_id": str(audit_id),
        "status": "paused",
        "cancelled_execution_id": running_execution.id if running_execution else None,
        "message": "Audit paused",
    }


@router.post("/upload-zip", response_model=schemas.AuditResponse)
async def upload_zip(
    name: str = Form(...),
    file: UploadFile = File(...),
    codecome_yml: Optional[str] = Form(None),
    model_settings: Optional[str] = Form(None),
    worker_id: Optional[int] = Form(None),
    question_owner_user_id: Optional[int] = Form(None),
    ai_review_enabled: bool = Form(False),
    auto_continue: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Upload ZIP file and create audit."""
    from uuid import uuid4
    
    # Save uploaded file
    temp_dir = settings.WORKSPACES_DIR / "uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = temp_dir / f"{uuid4().hex}_{file.filename}"
    
    content = await file.read()
    file_path.write_bytes(content)
    
    # Create workspace
    audit_id = uuid4()
    workspace_path = workspace_manager.create_workspace(str(audit_id))
    
    # Extract source
    success = workspace_manager.setup_source_from_zip(workspace_path, str(file_path))
    
    # Cleanup uploaded file
    file_path.unlink(missing_ok=True)
    
    if not success:
        workspace_manager.cleanup_workspace(workspace_path)
        raise HTTPException(status_code=400, detail="Failed to extract ZIP file")
    
    # Write codecome.yml
    yml_content = codecome_yml
    if not yml_content:
        default_yml = settings.CODECOME_ROOT / "codecome.yml"
        if default_yml.exists():
            yml_content = default_yml.read_text()
    
    workspace_manager.write_codecome_yml(workspace_path, yml_content)

    if worker_id and not crud.get_worker(db, worker_id):
        workspace_manager.cleanup_workspace(workspace_path)
        raise HTTPException(status_code=404, detail="Worker not found")
    if question_owner_user_id and not crud.get_user(db, question_owner_user_id):
        workspace_manager.cleanup_workspace(workspace_path)
        raise HTTPException(status_code=404, detail="Question owner user not found")
    if not question_owner_user_id:
        default_owner = crud.default_question_owner(db)
        question_owner_user_id = default_owner.id if default_owner else None
    parsed_model_settings = None
    if isinstance(model_settings, (str, bytes, bytearray)) and model_settings:
        try:
            parsed_model_settings = json.loads(model_settings)
        except Exception:
            raise HTTPException(status_code=400, detail="model_settings must be valid JSON")
      
    # Create audit record
    db_audit = crud.create_audit(db, schemas.AuditCreate(
        name=name,
        source_type="zip",
        source_location=file.filename,
        codecome_yml=yml_content,
        model_settings=parsed_model_settings,
        worker_id=worker_id,
        question_owner_user_id=question_owner_user_id,
        ai_review_enabled=ai_review_enabled,
        auto_continue=auto_continue,
        workspace_path=str(workspace_path),
    ))
    start_created_audit_if_requested(db, db_audit)
    
    return db_audit
