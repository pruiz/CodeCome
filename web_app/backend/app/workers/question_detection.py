import re
from pathlib import Path

from app import crud, schemas

QUESTION_SECTION_RE = re.compile(
    r"(?:^|\n)\s*(?:#{1,4}\s*)?Open questions(?:\s+for\s+the\s+user)?\s*:?\s*(?P<body>.*?)(?=\n\s*(?:#{1,4}\s+|[A-Z][A-Za-z /-]+:\s*$)|\Z)",
    re.IGNORECASE | re.DOTALL,
)

QUESTION_LINE_RE = re.compile(r"^\s*(?:[-*]\s+|\d+[.)]?\s+)(?P<question>.+?\?)\s*$")


def clean_terminal_text(value: str | None) -> str:
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value or "")


def extract_open_questions(text: str | None) -> list[str]:
    cleaned = clean_terminal_text(text)
    questions: list[str] = []
    seen = set()
    for section in QUESTION_SECTION_RE.finditer(cleaned):
        body = section.group("body") or ""
        for line in body.splitlines():
            match = QUESTION_LINE_RE.match(line.strip())
            if not match:
                continue
            question = " ".join(match.group("question").split())
            key = question.lower()
            if key not in seen:
                questions.append(question)
                seen.add(key)
    return questions


def latest_run_summary_text(workspace_path: Path, phase: str) -> str:
    runs_dir = workspace_path / "runs"
    if not runs_dir.exists():
        return ""
    phase_key = phase.replace("phase-", "phase-")
    candidates = sorted(runs_dir.glob(f"{phase_key}-summary*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates and phase.startswith("phase-"):
        candidates = sorted(runs_dir.glob(f"phase-{phase.split('-', 1)[1]}-summary*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        return ""
    try:
        return candidates[0].read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def create_questions_for_phase(db, audit, phase_exec, stdout: str | None, stderr: str | None, workspace_path: Path) -> list:
    combined = "\n".join([
        stdout or "",
        stderr or "",
        latest_run_summary_text(workspace_path, phase_exec.phase),
    ])
    existing_questions = {
        question.question.strip().lower()
        for question in crud.get_phase_questions(db, phase_execution_id=phase_exec.id)[1]
    }
    created = []
    for question in extract_open_questions(combined):
        if question.lower() in existing_questions:
            continue
        created.append(crud.create_phase_question(db, schemas.PhaseQuestionCreate(
            audit_id=audit.id,
            phase_execution_id=phase_exec.id,
            phase=phase_exec.phase,
            question=question,
            context="Detected from successful phase output or run summary.",
            source="phase_success_detector",
            blocking=True,
            assigned_user_id=audit.question_owner_user_id,
        )))
    return created


def has_open_blocking_questions(db, phase_execution_id: int) -> bool:
    _, questions = crud.get_phase_questions(db, phase_execution_id=phase_execution_id, status_filter="OPEN")
    return any(question.blocking for question in questions)
