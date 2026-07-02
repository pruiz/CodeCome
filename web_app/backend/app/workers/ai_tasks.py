import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from app import crud, models
from app.config import settings
from app.database import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

VALID_TRIAGE_DECISIONS = {"ACCEPT_AS_COMPLETE", "RERUN_SAME_OPTIONS", "RERUN_WITH_OPTIONS", "NEEDS_HUMAN"}


def _tail(value: str | None, limit: int = 12000) -> str:
    text = value or ""
    return text[-limit:]


def _clean_terminal_text(value: str | None) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value or "")


def _artifact_summary(workspace_path: Path, phase: str) -> str:
    lines = []
    runs_dir = workspace_path / "runs"
    if runs_dir.exists():
        phase_key = phase.replace("phase-", "phase-").replace("make ", "")
        summaries = sorted(path.name for path in runs_dir.glob("*.md") if phase_key in path.name or "summary" in path.name)
        lines.append(f"runs/*.md count: {len(summaries)}")
        lines.extend(f"- runs/{name}" for name in summaries[-30:])
    else:
        lines.append("runs/ does not exist")

    pending_dir = workspace_path / "itemdb" / "findings" / "PENDING"
    if pending_dir.exists():
        pending_files = sorted(path for path in pending_dir.glob("*.md") if not path.name.startswith("."))
        reviewed = []
        unreviewed = []
        for path in pending_files:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = ""
            finding_id = path.name.split("-", 2)[0] if path.name.startswith("CC-") else path.stem
            if "Reviewer conclusion:" in content:
                reviewed.append(finding_id)
            else:
                unreviewed.append(finding_id)
        lines.append(f"PENDING findings: {len(pending_files)}")
        lines.append(f"PENDING with Reviewer conclusion: {len(reviewed)}")
        lines.append(f"PENDING without Reviewer conclusion: {', '.join(unreviewed) if unreviewed else 'none'}")
    else:
        lines.append("itemdb/findings/PENDING/ does not exist")

    return "\n".join(lines)


def _safe_phase_slug(phase: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", phase).strip("-") or "phase"


def _load_triage_prompt(**values) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "phase_failure_triage.md"
    return prompt_path.read_text(encoding="utf-8").format(**values)


def _extract_json(text: str) -> dict:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _normalize_decision(data: dict) -> dict:
    decision = str(data.get("decision") or "NEEDS_HUMAN").strip().upper()
    if decision not in VALID_TRIAGE_DECISIONS:
        decision = "NEEDS_HUMAN"
    confidence = str(data.get("confidence") or "LOW").strip().upper()
    if confidence not in {"LOW", "MEDIUM", "HIGH"}:
        confidence = "LOW"
    recommended_env = data.get("recommended_env") or {}
    if not isinstance(recommended_env, dict):
        recommended_env = {}
    evidence = data.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = [str(evidence)]
    return {
        "decision": decision,
        "confidence": confidence,
        "reason": str(data.get("reason") or "No reason provided."),
        "recommended_env": {str(k): str(v) for k, v in recommended_env.items()},
        "evidence": [str(item) for item in evidence],
    }


def triage_enabled(model_settings: dict | None) -> bool:
    options = (model_settings or {}).get("__audit_options") or {}
    if not isinstance(options, dict):
        return True
    return options.get("failure_triage_enabled", True) is not False


def triage_ai_user(db, audit):
    """Return the assigned fake AI user allowed to run web-side triage."""
    owner_id = getattr(audit, "question_owner_user_id", None)
    if not owner_id:
        return None
    owner = crud.get_user(db, owner_id)
    if not owner or not owner.active or not owner.is_llm_user:
        return None
    return owner


@celery_app.task(bind=True, max_retries=0)
def triage_failed_phase_task(self, phase_execution_id: int):
    db = SessionLocal()
    triage = None
    try:
        phase_exec = db.query(models.PhaseExecution).filter(models.PhaseExecution.id == phase_execution_id).first()
        if not phase_exec:
            logger.warning("Phase execution not found for triage: %s", phase_execution_id)
            return
        audit = crud.get_audit(db, phase_exec.audit_id)
        if not audit:
            logger.warning("Audit not found for triage: %s", phase_exec.audit_id)
            return
        if not triage_enabled(audit.model_settings):
            return
        ai_user = triage_ai_user(db, audit)
        if not ai_user:
            crud.create_audit_log(db, str(audit.id), "INFO", "Skipped AI failure triage because the audit has no active fake AI question owner", phase=phase_exec.phase, source="triage")
            return

        existing = crud.latest_phase_triage(db, phase_execution_id)
        if existing and existing.status in {"queued", "running", "completed", "applied"}:
            return

        timestamp = datetime.utcnow().strftime("%Y-%m-%d-%H%M%S")
        workspace_path = Path(audit.workspace_path)
        runs_dir = workspace_path / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        slug = _safe_phase_slug(phase_exec.phase)
        report_rel = f"runs/phase-triage-{slug}-{phase_exec.id}-{timestamp}.md"
        decision_rel = f"runs/phase-triage-{slug}-{phase_exec.id}-{timestamp}.json"
        report_path = workspace_path / report_rel
        decision_path = workspace_path / decision_rel

        triage = crud.create_phase_triage(db, {
            "audit_id": str(audit.id),
            "phase_execution_id": phase_exec.id,
            "phase": phase_exec.phase,
            "status": "running",
            "report_path": report_rel,
            "decision_path": decision_rel,
        })
        crud.create_audit_log(db, str(audit.id), "INFO", f"AI failure triage started for {phase_exec.phase} execution #{phase_exec.id}", phase=phase_exec.phase, source="triage")

        prompt = _load_triage_prompt(
            audit_id=str(audit.id),
            phase_execution_id=phase_exec.id,
            phase=phase_exec.phase,
            attempt=phase_exec.attempt,
            status=phase_exec.status,
            exit_code=phase_exec.exit_code,
            command_line=phase_exec.command_line or "",
            workspace_path=str(workspace_path),
            report_path=report_rel,
            decision_path=decision_rel,
            stdout_tail=_tail(phase_exec.stdout_log),
            stderr_tail=_tail(phase_exec.stderr_log),
            artifact_summary=_artifact_summary(workspace_path, phase_exec.phase),
        )

        env = os.environ.copy()
        audit_env = ((audit.model_settings or {}).get("__audit_env") or {}).get("env") or {}
        if isinstance(audit_env, dict):
            env.update({str(k): str(v) for k, v in audit_env.items()})
        if ai_user.llm_model:
            env["CODECOME_MODEL"] = ai_user.llm_model
        env.setdefault("CODECOME_THINKING", "0")

        result = subprocess.run(
            ["opencode", "run", "--agent", "reviewer", prompt],
            cwd=str(workspace_path),
            env=env,
            text=True,
            capture_output=True,
            timeout=1800,
        )

        combined_output = _clean_terminal_text((result.stdout or "") + "\n" + (result.stderr or ""))
        decision_data = {}
        if decision_path.exists():
            decision_data = _extract_json(decision_path.read_text(encoding="utf-8"))
        if not decision_data:
            decision_data = _extract_json(combined_output)
        normalized = _normalize_decision(decision_data)

        decision_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
        report_path.write_text(
            "# Phase Failure Triage\n\n"
            f"OpenCode exit code: {result.returncode}\n\n"
            f"Decision: {normalized['decision']}\n\n"
            f"Confidence: {normalized['confidence']}\n\n"
            f"Reason: {normalized['reason']}\n\n"
            "## Evidence\n\n"
            + "\n".join(f"- {item}" for item in normalized["evidence"])
            + "\n\n## Recommended Env\n\n```json\n"
            + json.dumps(normalized["recommended_env"], indent=2)
            + "\n```\n\n## Raw OpenCode Output\n\n```text\n"
            + _tail(combined_output, 50000)
            + "\n```\n",
            encoding="utf-8",
        )

        status = "completed" if result.returncode == 0 and decision_data else "failed"
        error_message = None if status == "completed" else f"OpenCode triage failed or did not write valid JSON (exit {result.returncode})"
        crud.update_phase_triage(db, triage.id, {
            "status": status,
            "decision": normalized["decision"],
            "confidence": normalized["confidence"],
            "reason": normalized["reason"],
            "recommended_env": normalized["recommended_env"],
            "evidence": normalized["evidence"],
            "raw_response": _tail(combined_output, 50000),
            "error_message": error_message,
            "completed_at": datetime.utcnow(),
        })
        level = "INFO" if status == "completed" else "WARN"
        crud.create_audit_log(db, str(audit.id), level, f"AI failure triage {status}: {normalized['decision']}", phase=phase_exec.phase, source="triage")
    except Exception as exc:
        logger.exception("Failed phase triage task failed")
        if triage:
            crud.update_phase_triage(db, triage.id, {
                "status": "failed",
                "error_message": str(exc),
                "completed_at": datetime.utcnow(),
            })
        raise
    finally:
        db.close()


@celery_app.task
def ai_review_phase_task(audit_id: str, phase: str):
    logger.info("AI review phase task: audit=%s, phase=%s", audit_id, phase)


@celery_app.task
def execute_ai_decision_task(audit_id: str, decision_id: int):
    logger.info("Executing AI decision: audit=%s, decision=%s", audit_id, decision_id)
