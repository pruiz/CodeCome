import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from app import crud, schemas


def _extract_json(text: str) -> dict:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    match = re.search(r"```json\s*(\{.*?\})\s*```", text or "", re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(1))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def normalize_ai_answer(data: dict) -> dict:
    confidence = str(data.get("confidence") or "LOW").upper()
    if confidence not in {"LOW", "MEDIUM", "HIGH"}:
        confidence = "LOW"
    return {
        "answer": str(data.get("answer") or "").strip(),
        "confidence": confidence,
        "reasoning": str(data.get("reasoning") or "").strip(),
    }


def build_ai_answer_prompt(audit, phase_question, fake_user, phase_output_tail: str = "") -> str:
    return f"""You are answering a blocking CodeCome audit question as the assigned fake AI user.

Audit: {audit.name} ({audit.id})
Phase: {phase_question.phase}
Question: {phase_question.question}
Context: {phase_question.context or '-'}

Fake AI user: {fake_user.display_name}
User context/persona:
{fake_user.llm_context or 'Answer concisely and safely. If unsure, state assumptions.'}

Phase output tail:
```text
{phase_output_tail[-8000:]}
```

Return one fenced json block only:

```json
{{
  "answer": "Concrete answer to use in future phase context.",
  "confidence": "HIGH",
  "reasoning": "Short rationale."
}}
```
"""


def generate_ai_answer(audit, phase_question, fake_user, phase_output_tail: str = "") -> dict:
    prompt = build_ai_answer_prompt(audit, phase_question, fake_user, phase_output_tail)
    env = os.environ.copy()
    if fake_user.llm_model:
        env["CODECOME_MODEL"] = fake_user.llm_model
    env.setdefault("CODECOME_THINKING", "0")
    result = subprocess.run(
        ["opencode", "run", "--agent", "reviewer", prompt],
        text=True,
        capture_output=True,
        timeout=1800,
        env=env,
    )
    parsed = _extract_json((result.stdout or "") + "\n" + (result.stderr or ""))
    answer = normalize_ai_answer(parsed)
    if result.returncode != 0 or not answer["answer"]:
        raise RuntimeError("Fake AI user did not return a valid answer")
    return answer


def write_user_answers_context(db, audit, workspace_path: Path) -> Path:
    _, questions = crud.get_phase_questions(db, audit_id=audit.id)
    answered = [q for q in questions if q.status in {"ANSWERED", "AUTO_ANSWERED"} and q.answer]
    runs_dir = workspace_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    output = runs_dir / "user-answers-context.md"
    lines = [
        "# User Answers Context",
        "",
        f"Audit: {audit.name} ({audit.id})",
        f"Updated: {datetime.now().isoformat()}",
        "",
    ]
    for question in sorted(answered, key=lambda q: (q.phase, q.id)):
        lines.extend([
            f"## {question.phase} question #{question.id}",
            "",
            f"Question: {question.question}",
            "",
            f"Answer ({question.status}): {question.answer}",
            "",
        ])
        if question.answer_model:
            lines.append(f"Model: {question.answer_model}")
            lines.append("")
        if question.answer_confidence:
            lines.append(f"Confidence: {question.answer_confidence}")
            lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def with_user_answers_env(workspace_path: Path, env_overrides: dict | None) -> dict:
    env = dict(env_overrides or {})
    answers_path = workspace_path / "runs" / "user-answers-context.md"
    if answers_path.exists() and "PROMPT_EXTRA_FILE" not in env:
        env["PROMPT_EXTRA_FILE"] = "runs/user-answers-context.md"
    return env


def auto_answer_open_questions(db, audit, phase_exec, fake_user, workspace_path: Path, phase_output_tail: str = "") -> int:
    if not fake_user or not fake_user.is_llm_user or not fake_user.auto_answer_enabled:
        return 0
    _, questions = crud.get_phase_questions(db, phase_execution_id=phase_exec.id, status_filter="OPEN")
    answered = 0
    for question in questions:
        if not question.blocking:
            continue
        answer = generate_ai_answer(audit, question, fake_user, phase_output_tail)
        crud.answer_phase_question(db, question.id, schemas.PhaseQuestionAnswer(
            answer=answer["answer"],
            status="AUTO_ANSWERED",
            answered_by_user_id=fake_user.id,
            answer_model=fake_user.llm_model,
            answer_confidence=answer["confidence"],
        ))
        answered += 1
    if answered:
        write_user_answers_context(db, audit, workspace_path)
    return answered
