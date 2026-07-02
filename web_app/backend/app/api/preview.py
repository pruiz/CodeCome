from pathlib import Path

from fastapi import APIRouter

from app import schemas
from app.config import settings

router = APIRouter()


DEFAULT_USER_PROMPT_ENRICHMENT_PROMPT = """You are running optional User Prompt Enrichment after normal `make phase-1` and before `make phase-2`.

This is a reconnaissance enrichment pass, similar in discipline to CodeCome Phase 1c. The operator may add target-specific context, suspicious areas, business-risk concerns, deployment assumptions, historical bug themes, or review priorities. Use that input to enrich Phase 1 artifacts so Phase 2 can create better CodeCome findings. Do not create findings directly.

Required reading:
- Existing Phase 1 notes under `itemdb/notes/`.
- Semgrep enrichment artifacts if present: `itemdb/notes/semgrep-results.yml`, `itemdb/notes/semgrep-interesting-files.md`, and `itemdb/notes/semgrep-file-risk-index.yml`.
- High-risk files referenced by `itemdb/notes/file-risk-index.yml`, Semgrep signals, or the operator prompt.

Required outputs:
- Update standard Phase 1 notes only when useful: `attack-surface.md`, `trust-boundaries.md`, `data-flow.md`, `interesting-files.md`, `file-risk-index.yml`, `security-assumptions.md`, and `threat-model.md`.
- Add clearly marked `User Prompt Enrichment` sections when adding prompt-derived context.
- Write `itemdb/notes/user-prompt-enrichment.md` as a human-readable summary of what the operator prompt added.
- Write `itemdb/notes/user-prompt-candidates.yml` as structured candidate leads for Phase 2. These are not findings.

Candidate lead schema for `user-prompt-candidates.yml`:

schema_version: 1
generated_by: user-prompt-enrichment
candidates:
  - id: UPE-0001
    title: Short source-backed candidate lead
    files:
      - src/path/file.ext
    entry_points: []
    sources: []
    sinks: []
    trust_boundary: ""
    evidence:
      - source-backed observation or Semgrep/user-prompt basis
    phase2_focus: What Phase 2 should verify before creating any finding
    not_a_finding_reason: Why this still needs Phase 2 source-to-sink reasoning

Rules:
- Keep every claim grounded in source paths, symbols, routes, configuration keys, Semgrep evidence, or clearly labeled operator assumptions.
- Distinguish user-provided hypotheses, Semgrep signals, and confirmed source-backed observations.
- Do not write under `itemdb/findings/`, do not run `make findings-create`, and do not claim anything is confirmed.
- Preserve the normal CodeCome lifecycle: Phase 2 decides whether candidate leads become `PENDING` findings.

The output should improve Phase 2 focus by identifying source-backed attack surfaces, trust boundaries, high-risk files, abuse-path themes, candidate leads, and validation ideas."""


def default_user_prompt_enrichment_prompt() -> str:
    return DEFAULT_USER_PROMPT_ENRICHMENT_PROMPT


def preview_config_path() -> Path:
    data_dir = Path(settings.CODECOME_ROOT) / "web_app" / "backend" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "preview-analysis.md"


@router.get("/config", response_model=schemas.PreviewAnalysisConfig)
def get_preview_config():
    path = preview_config_path()
    if not path.exists():
        return schemas.PreviewAnalysisConfig(
            prompt=default_user_prompt_enrichment_prompt(),
            updated=False,
        )
    prompt = path.read_text()
    return schemas.PreviewAnalysisConfig(prompt=prompt if prompt.strip() else default_user_prompt_enrichment_prompt(), updated=bool(prompt.strip()))


@router.put("/config", response_model=schemas.PreviewAnalysisConfig)
def update_preview_config(config: schemas.PreviewAnalysisConfig):
    path = preview_config_path()
    path.write_text(config.prompt)
    return schemas.PreviewAnalysisConfig(prompt=config.prompt, updated=True)
