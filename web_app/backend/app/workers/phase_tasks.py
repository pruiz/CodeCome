from app.workers.celery_app import celery_app
from app.database import SessionLocal
from app import crud
from app import models
from app.utils.codecome_wrapper import CodeComeExecutor
from app.utils.ssh_executor import SSHCodeComeExecutor
from app.workers.question_answering import auto_answer_open_questions, with_user_answers_env
from app.workers.question_detection import create_questions_for_phase, has_open_blocking_questions
from pathlib import Path
from datetime import datetime
import logging
import queue
import shlex
import threading

logger = logging.getLogger(__name__)

# CodeCome execution sequence. Setup steps are first-class steps in the UI/history.
PHASE_ORDER = ["make init", "make check", "phase-1", "phase-2", "phase-3", "make validate-all", "make exploit-all", "phase-6"]
OPTIONAL_PHASES = ["make sweep"]
ALL_PHASES = ["make init", "make check", "phase-1", "phase-2", "make sweep", "phase-3", "make validate-all", "make exploit-all", "phase-6", "gap-scan", "gap-compare", "gap-sweep"]
AUDIT_ENV_KEY = "__audit_env"
AUDIT_OPTIONS_KEY = "__audit_options"


def audit_options(model_settings: dict | None) -> dict:
    settings = model_settings or {}
    options = settings.get(AUDIT_OPTIONS_KEY) or {}
    return options if isinstance(options, dict) else {}


def phase_order_for_settings(model_settings: dict | None) -> list[str]:
    if audit_options(model_settings).get("run_sweep_auto"):
        return ["make init", "make check", "phase-1", "phase-2", "make sweep", "phase-3", "make validate-all", "make exploit-all", "phase-6"]
    return PHASE_ORDER


def merged_phase_env(model_settings: dict | None, phase: str) -> dict:
    settings = model_settings or {}
    default_env = {}
    selected_model = audit_options(settings).get("worker_model")
    if selected_model:
        default_env["CODECOME_MODEL"] = selected_model
    audit_env_block = settings.get(AUDIT_ENV_KEY) or {}
    audit_env = audit_env_block.get("env") if isinstance(audit_env_block, dict) else {}
    phase_config = settings.get(phase) or {}
    phase_env = phase_config.get("env") or phase_config.get("env_overrides") or {}
    return {**default_env, **(audit_env or {}), **(phase_env or {})}


def build_command_line(phase: str, model: str = None, variant: str = None, finding_id: str = None, worker_type: str = "local", env_overrides: dict = None) -> str:
    env_parts = []
    if model:
        env_parts.append(f"CODECOME_MODEL={shlex.quote(model)}")
    if variant:
        env_parts.append(f"CODECOME_MODEL_VARIANT={shlex.quote(variant)}")
    for key, value in (env_overrides or {}).items():
        env_parts.append(f"{shlex.quote(str(key))}={shlex.quote(str(value))}")
    if phase.startswith("make "):
        cmd = ["make", phase.split(" ", 1)[1]]
    else:
        cmd = ["make", phase]
    if finding_id and not phase.startswith("make "):
        cmd.append(f"FINDING={finding_id}")
    prefix = " ".join(env_parts)
    command = " ".join(shlex.quote(part) for part in cmd)
    if prefix:
        command = f"{prefix} {command}"
    if worker_type != "local":
        command = f"ssh remote-worker -- {command}"
    return command


def status_phase(phase: str) -> str:
    return phase.replace("-", "_").replace(" ", "_")


def start_log_writer(audit_id: str, phase: str):
    log_queue: queue.Queue[tuple[str, str] | None] = queue.Queue()

    def writer():
        writer_db = SessionLocal()
        try:
            while True:
                item = log_queue.get()
                if item is None:
                    break
                source, message = item
                if not message.strip():
                    continue
                level = "WARN" if source == "stderr" else "INFO"
                try:
                    crud.create_audit_log(writer_db, audit_id, level, message[:2000], phase=phase, source=source)
                except Exception:
                    writer_db.rollback()
                    logger.exception("Failed to persist audit log line")
        finally:
            writer_db.close()

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()

    def log_output(source: str, message: str):
        log_queue.put((source, message))

    def stop_writer():
        log_queue.put(None)
        thread.join(timeout=10)

    return log_output, stop_writer


def run_visible_make_target(db, audit_id: str, worker, workspace_path: Path, target: str, attempt: int, log_output) -> bool:
    command_line = f"make {target}"
    display_phase = f"make {target}"
    crud.create_audit_log(db, audit_id, "INFO", f"Starting setup step: {display_phase}", phase=display_phase, source="system")
    phase_exec = crud.create_phase_execution(db, {
        "audit_id": audit_id,
        "worker_id": worker.id,
        "phase": display_phase,
        "attempt": attempt,
        "status": "running",
        "started_at": datetime.now(),
        "command_line": command_line,
    })
    executor = CodeComeExecutor()
    result = executor.execute_make_target(
        workspace_path,
        target,
        output_callback=log_output,
        process_callback=lambda pid, cmd: crud.update_phase_execution(db, phase_exec.id, {"local_pid": pid}),
    )
    status = "success" if result.exit_code == 0 else "failed"
    crud.update_phase_execution(db, phase_exec.id, {
        "status": status,
        "completed_at": datetime.now(),
        "duration_seconds": int(result.duration),
        "exit_code": result.exit_code,
        "stdout_log": result.stdout[:50000],
        "stderr_log": result.stderr[:10000],
    })
    if result.exit_code == 0:
        crud.create_audit_log(db, audit_id, "INFO", f"Setup step {display_phase} completed", phase=display_phase, source="system")
        return True
    crud.create_audit_log(db, audit_id, "ERROR", f"Setup step {display_phase} failed with exit code {result.exit_code}", phase=display_phase, source="system")
    return False


def is_make_step(phase: str) -> bool:
    return phase.startswith("make ")


def make_step_target(phase: str) -> str:
    return phase.split(" ", 1)[1]


def queue_failure_triage_if_enabled(db, audit, phase_exec) -> None:
    try:
        from app.workers.ai_tasks import triage_enabled, triage_failed_phase_task

        if not triage_enabled(audit.model_settings):
            return
        existing = crud.latest_phase_triage(db, phase_exec.id)
        if existing and existing.status in {"queued", "running", "completed", "applied"}:
            return
        crud.create_audit_log(
            db,
            str(audit.id),
            "INFO",
            f"Queued AI failure triage for {phase_exec.phase} execution #{phase_exec.id}",
            phase=phase_exec.phase,
            source="triage",
        )
        triage_failed_phase_task.delay(phase_exec.id)
    except Exception:
        logger.exception("Failed to queue failure triage")


@celery_app.task(bind=True, max_retries=0)
def run_phase_task(
    self,
    audit_id: str,
    phase: str,
    model: str = None,
    variant: str = None,
    finding_id: str = None,
    attempt: int = 1,
    worker_id: int = None,
    env_overrides: dict = None,
):
    """
    Execute a single phase for an audit.
    """
    db = SessionLocal()
    
    try:
        logger.info(f"Starting phase {phase} for audit {audit_id}")
        
        # Update audit status
        crud.update_audit_status(db, audit_id, f"{status_phase(phase)}_running")

        # Get audit and worker details
        audit = crud.get_audit(db, audit_id)
        if worker_id is None:
            worker = crud.select_available_worker(db, audit.assigned_worker_id)
            worker_id = worker.id if worker else None
        else:
            worker = crud.get_worker(db, worker_id)

        if not worker:
            raise RuntimeError("No available worker")

        workspace_path = Path(audit.workspace_path)
        env_overrides = env_overrides or {}
        command_line = build_command_line(phase, model, variant, finding_id, worker.type, env_overrides)

        audit.assigned_worker_id = worker.id
        db.commit()
        crud.mark_worker_job_started(db, worker.id)
        
        log_output, stop_log_writer = start_log_writer(audit_id, phase)

        # Create phase execution record
        phase_exec = crud.create_phase_execution(db, {
            "audit_id": audit_id,
            "worker_id": worker.id,
            "phase": phase,
            "attempt": attempt,
            "status": "running",
            "started_at": datetime.now(),
            "command_line": command_line,
            "model_used": model,
            "variant_used": variant
        })
        
        # Log phase start
        crud.create_audit_log(db, audit_id, "INFO", f"Starting {phase} on worker {worker.name}", phase=phase, source="system")
        crud.create_audit_log(db, audit_id, "INFO", f"Command: {command_line}", phase=phase, source="system")

        # Execute phase
        if worker.type == "local":
            executor = CodeComeExecutor()
            if is_make_step(phase):
                result = executor.execute_make_target(
                    workspace_path=workspace_path,
                    target=make_step_target(phase),
                    output_callback=log_output,
                    env_overrides=env_overrides,
                    process_callback=lambda pid, cmd: crud.update_phase_execution(db, phase_exec.id, {"local_pid": pid}),
                )
            else:
                result = executor.execute_phase(
                    workspace_path=workspace_path,
                    phase=phase,
                    model=model,
                    variant=variant,
                    finding_id=finding_id,
                    env_overrides=env_overrides,
                    thinking=(variant and variant == "thinking"),
                    output_callback=log_output,
                    process_callback=lambda pid, cmd: crud.update_phase_execution(db, phase_exec.id, {"local_pid": pid}),
                )
        elif worker.type in ("ssh", "proxmox-vm", "proxmox-lxc"):
            executor = SSHCodeComeExecutor(worker)
            crud.create_audit_log(
                db,
                audit_id,
                "INFO",
                f"Uploading workspace and executing remotely at {worker.username}@{worker.host}:{worker.port or 22}",
                phase=phase,
                source="ssh",
            )
            result = executor.execute_phase(
                audit_id=str(audit_id),
                local_workspace_path=workspace_path,
                phase=phase,
                model=model,
                variant=variant,
                finding_id=finding_id,
                thinking=(variant and variant == "thinking"),
                env_overrides=env_overrides,
                output_callback=log_output,
                job_callback=lambda job: crud.update_phase_execution(db, phase_exec.id, {
                    "remote_job_dir": job.get("job_dir"),
                    "remote_pid": job.get("pid"),
                }),
            )
        else:
            raise RuntimeError(f"Unsupported worker type: {worker.type}")
        
        stop_log_writer()

        db.refresh(audit)
        db.refresh(phase_exec)
        if audit.status == "paused" or phase_exec.status == "cancelled":
            crud.update_phase_execution(db, phase_exec.id, {
                "status": "cancelled",
                "completed_at": datetime.now(),
                "duration_seconds": int(result.duration),
                "exit_code": result.exit_code,
                "stdout_log": result.stdout[:50000],
                "stderr_log": result.stderr[:10000],
                "error_message": "Cancelled by pause request",
            })
            crud.create_audit_log(db, audit_id, "WARN", f"Phase {phase} cancelled by pause request", phase=phase, source="system")
            return
        
        # Update phase execution record
        exec_status = "success" if result.exit_code == 0 else "failed"
        
        crud.update_phase_execution(db, phase_exec.id, {
            "status": exec_status,
            "completed_at": datetime.now(),
            "duration_seconds": int(result.duration),
            "exit_code": result.exit_code,
            "stdout_log": result.stdout[:50000],  # Keep last 50K chars
            "stderr_log": result.stderr[:10000],
            "remote_job_dir": result.metadata.get("remote_job_dir") if result.metadata else None,
            "remote_pid": result.metadata.get("remote_pid") if result.metadata else None,
        })
        
        # Parse and sync findings from itemdb
        findings = executor.parse_findings(workspace_path)
        
        for finding in findings:
            finding["audit_id"] = audit_id
            crud.upsert_finding(db, finding)
        
        # Update audit findings count
        crud.update_audit_findings_count(db, audit_id)
        db.refresh(audit)
        
        # Log completion
        if result.exit_code == 0:
            crud.create_audit_log(db, audit_id, "INFO", 
                                    f"Phase {phase} completed successfully in {result.duration:.1f}s",
                                    phase=phase, source="system")
            created_questions = create_questions_for_phase(db, audit, phase_exec, result.stdout, result.stderr, workspace_path)
            if created_questions:
                crud.create_audit_log(db, audit_id, "WARN",
                                      f"Detected {len(created_questions)} blocking question(s) for user review",
                                      phase=phase, source="questions")
                fake_owner = crud.get_user(db, audit.question_owner_user_id) if audit.question_owner_user_id else None
                if fake_owner and fake_owner.is_llm_user:
                    try:
                        answered_count = auto_answer_open_questions(db, audit, phase_exec, fake_owner, workspace_path, result.stdout)
                        crud.create_audit_log(db, audit_id, "INFO",
                                              f"Fake AI question owner answered {answered_count} question(s)",
                                              phase=phase, source="questions")
                    except Exception as exc:
                        logger.exception("Fake AI question answering failed")
                        crud.create_audit_log(db, audit_id, "ERROR",
                                              f"Fake AI question answering failed: {exc}",
                                              phase=phase, source="questions")
        else:
            crud.create_audit_log(db, audit_id, "ERROR",
                                    f"Phase {phase} failed with exit code {result.exit_code}",
                                    phase=phase, source="system")
        
        # Decide next action
        if result.exit_code == 0:
            db.refresh(phase_exec)
            if has_open_blocking_questions(db, phase_exec.id):
                crud.update_audit_status(db, audit_id, "paused_for_questions")
                audit.current_phase = phase
                db.commit()
                logger.info("Phase %s paused for blocking questions", phase)
                return
            if audit.auto_continue:
                # Queue next phase
                next_phase = _get_next_phase(phase, audit.model_settings)
                if next_phase:
                    crud.update_audit_status(db, audit_id, f"{status_phase(phase)}_complete")
                    audit.current_phase = next_phase
                    db.commit()
                    next_env = with_user_answers_env(workspace_path, merged_phase_env(audit.model_settings, next_phase))
                    run_phase_task.delay(audit_id, next_phase, model, variant, None, 1, worker.id, next_env)
                else:
                    # All phases complete
                    crud.update_audit_status(db, audit_id, "completed")
            else:
                # Pause for user action
                crud.update_audit_status(db, audit_id, f"{status_phase(phase)}_complete")
        else:
            # Failed - pause and wait
            crud.update_audit_status(db, audit_id, f"{status_phase(phase)}_failed")
            db.refresh(phase_exec)
            queue_failure_triage_if_enabled(db, audit, phase_exec)
        
        logger.info(f"Phase {phase} task completed with status {exec_status}")
        
    except Exception as e:
        logger.error(f"Error in run_phase_task: {str(e)}", exc_info=True)
        crud.update_audit_status(db, audit_id, f"{status_phase(phase)}_failed")
        crud.create_audit_log(db, audit_id, "ERROR", f"Task error: {str(e)}", phase=phase, source="system")
        raise
    finally:
        if 'stop_log_writer' in locals():
            stop_log_writer()
        if 'worker' in locals() and worker:
            crud.mark_worker_job_finished(db, worker.id)
        db.close()


@celery_app.task
def run_sequential_workflow(audit_id: str, model: str = None, variant: str = None):
    """Orchestrate all phases sequentially."""
    db = SessionLocal()
    try:
        audit = crud.get_audit(db, audit_id)
        worker = crud.select_available_worker(db, audit.assigned_worker_id if audit else None)
        run_phase_task.delay(audit_id, "phase-1", model, variant, None, 1, worker.id if worker else None, {})
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=0)
def recover_remote_phase_task(self, phase_execution_id: int):
    db = SessionLocal()
    try:
        phase_exec = db.query(models.PhaseExecution).filter(models.PhaseExecution.id == phase_execution_id).first()
        if not phase_exec or phase_exec.status != "running" or not phase_exec.remote_job_dir:
            return
        audit = crud.get_audit(db, phase_exec.audit_id)
        worker = crud.get_worker(db, phase_exec.worker_id)
        if not audit or not worker:
            return

        workspace_path = Path(audit.workspace_path)
        executor = SSHCodeComeExecutor(worker)
        remote_workspace = executor.remote_workspace_path(str(audit.id))

        def log_output(source: str, message: str):
            level = "WARN" if source == "stderr" else "INFO"
            crud.create_audit_log(db, str(audit.id), level, message[:2000], phase=phase_exec.phase, source=f"recovery-{source}")

        result = executor.recover_phase(
            local_workspace_path=workspace_path,
            remote_workspace=remote_workspace,
            remote_job_dir=phase_exec.remote_job_dir,
            remote_pid=phase_exec.remote_pid,
            output_callback=log_output,
        )
        status = "success" if result.exit_code == 0 else "failed"
        crud.update_phase_execution(db, phase_exec.id, {
            "status": status,
            "completed_at": datetime.now(),
            "duration_seconds": int(result.duration),
            "exit_code": result.exit_code,
            "stdout_log": result.stdout[:50000],
            "stderr_log": result.stderr[:10000],
        })
        findings = executor.parse_findings(workspace_path)
        for finding in findings:
            finding["audit_id"] = str(audit.id)
            crud.upsert_finding(db, finding)
        crud.update_audit_findings_count(db, audit.id)
        db.refresh(audit)
        if result.exit_code == 0 and audit.auto_continue:
            next_phase = _get_next_phase(phase_exec.phase, audit.model_settings)
            if next_phase:
                crud.update_audit_status(db, audit.id, f"{status_phase(phase_exec.phase)}_complete")
                audit.current_phase = next_phase
                db.commit()
                next_env = with_user_answers_env(workspace_path, merged_phase_env(audit.model_settings, next_phase))
                run_phase_task.delay(str(audit.id), next_phase, None, None, None, 1, worker.id, next_env)
            else:
                crud.update_audit_status(db, audit.id, "completed")
        else:
            crud.update_audit_status(db, audit.id, f"{status_phase(phase_exec.phase)}_{'complete' if status == 'success' else 'failed'}")
            if status != "success":
                db.refresh(phase_exec)
                queue_failure_triage_if_enabled(db, audit, phase_exec)
    finally:
        db.close()


def _get_next_phase(current_phase: str, model_settings: dict | None = None) -> str | None:
    """Get the next phase in sequence."""
    phase_order = phase_order_for_settings(model_settings)
    if current_phase not in phase_order:
        return None
    
    idx = phase_order.index(current_phase)
    if idx < len(phase_order) - 1:
        return phase_order[idx + 1]
    return None
