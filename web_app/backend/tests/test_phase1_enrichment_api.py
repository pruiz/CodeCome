from types import SimpleNamespace

from app import schemas
from app.api import audits
from app.workers import phase_tasks


def test_phase1_enrichment_phases_are_supported():
    assert "phase-1-semgrep" in phase_tasks.ALL_PHASES
    assert "phase-1-prompt-enrich" in phase_tasks.ALL_PHASES


def test_phase1_enrichment_is_not_in_default_phase_progression():
    order = phase_tasks.phase_order_for_settings({})

    assert "phase-1-semgrep" not in order
    assert "phase-1-prompt-enrich" not in order


def test_run_phase1_semgrep_queues_optional_phase(monkeypatch, tmp_path):
    captured = {}
    audit_id = "11111111-2222-3333-4444-555555555555"
    audit = SimpleNamespace(id=audit_id, status="phase_1_complete", assigned_worker_id=2, model_settings={}, workspace_path=str(tmp_path), current_phase=None)
    worker = SimpleNamespace(id=2, name="local")
    db = SimpleNamespace(commits=0, commit=lambda: setattr(db, "commits", db.commits + 1))

    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, candidate_id: audit)
    monkeypatch.setattr(audits.crud, "audit_has_open_blocking_questions", lambda db_arg, candidate_id: False)
    monkeypatch.setattr(audits.crud, "select_available_worker", lambda db_arg, worker_id: worker)
    monkeypatch.setattr(audits.run_phase_task, "delay", lambda *args: captured.setdefault("delay", args))

    response = audits.run_phase1_semgrep(audit_id, db=db)

    assert response["phase"] == "phase-1-semgrep"
    assert response["message"] == "Phase 1 Semgrep enrichment queued"
    assert captured["delay"][1] == "phase-1-semgrep"
    assert captured["delay"][6] == 2


def test_phase1_enrichment_prompt_defaults_to_preview_prompt(monkeypatch, tmp_path):
    preview_path = tmp_path / "web_app" / "backend" / "data" / "preview-analysis.md"
    preview_path.parent.mkdir(parents=True)
    preview_path.write_text("Preview prompt", encoding="utf-8")
    audit = SimpleNamespace(id="audit-1", model_settings={})

    monkeypatch.setattr(audits.settings, "CODECOME_ROOT", tmp_path)

    response = audits.phase1_enrichment_prompt_payload(audit)

    assert response["prompt"] == "Preview prompt"
    assert response["default_prompt"] == "Preview prompt"
    assert response["custom"] is False


def test_update_phase1_enrichment_prompt_saves_settings_and_workspace_file(monkeypatch, tmp_path):
    audit_id = "11111111-2222-3333-4444-555555555555"
    audit = SimpleNamespace(id=audit_id, model_settings={}, workspace_path=str(tmp_path))
    db = SimpleNamespace(commits=0, refreshed=[], commit=lambda: setattr(db, "commits", db.commits + 1), refresh=lambda obj: db.refreshed.append(obj))

    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, candidate_id: audit)
    monkeypatch.setattr(audits.settings, "CODECOME_ROOT", tmp_path)

    response = audits.update_phase1_enrichment_prompt(
        audit_id,
        schemas.Phase1EnrichmentPromptUpdate(prompt="Prioritize auth boundaries."),
        db=db,
    )

    assert audit.model_settings["__audit_options"]["phase1_enrichment_prompt"] == "Prioritize auth boundaries."
    assert (tmp_path / "runs" / "phase-1-enrichment-user-prompt.md").read_text() == "Prioritize auth boundaries."
    assert response["prompt"] == "Prioritize auth boundaries."
    assert response["local_sync"] == "runs/phase-1-enrichment-user-prompt.md"


def test_run_phase1_prompt_enrichment_materializes_prompt_env(monkeypatch, tmp_path):
    captured = {}
    audit_id = "11111111-2222-3333-4444-555555555555"
    audit = SimpleNamespace(
        id=audit_id,
        status="phase_1_complete",
        assigned_worker_id=3,
        model_settings={"__audit_options": {"phase1_enrichment_prompt": "Review imports."}},
        workspace_path=str(tmp_path),
        current_phase=None,
    )
    worker = SimpleNamespace(id=3, name="local")
    db = SimpleNamespace(commits=0, commit=lambda: setattr(db, "commits", db.commits + 1))

    monkeypatch.setattr(audits.crud, "get_audit", lambda db_arg, candidate_id: audit)
    monkeypatch.setattr(audits.crud, "audit_has_open_blocking_questions", lambda db_arg, candidate_id: False)
    monkeypatch.setattr(audits.crud, "select_available_worker", lambda db_arg, worker_id: worker)
    monkeypatch.setattr(audits.run_phase_task, "delay", lambda *args: captured.setdefault("delay", args))

    response = audits.run_phase1_prompt_enrichment(audit_id, db=db)

    assert response["phase"] == "phase-1-prompt-enrich"
    assert (tmp_path / "runs" / "phase-1-enrichment-user-prompt.md").read_text() == "Review imports."
    assert captured["delay"][1] == "phase-1-prompt-enrich"
    assert captured["delay"][7] == {"CODECOME_PHASE1_ENRICHMENT_PROMPT_FILE": "runs/phase-1-enrichment-user-prompt.md"}


def test_phase1_enrichment_artifact_payload_reads_semgrep_summary(tmp_path):
    notes = tmp_path / "itemdb" / "notes"
    runs = tmp_path / "runs"
    notes.mkdir(parents=True)
    runs.mkdir()
    (notes / "semgrep-results.yml").write_text("summary:\n  total_results: 2\n", encoding="utf-8")
    (runs / "phase-1-semgrep-2026-06-30-120000.md").write_text("summary", encoding="utf-8")

    payload = audits.phase1_enrichment_artifact_payload(tmp_path)

    assert payload["semgrep_summary"]["total_results"] == 2
    assert "phase-1-semgrep-2026-06-30-120000.md" in payload["run_summaries"]
    assert any(item["path"] == "itemdb/notes/semgrep-results.yml" and item["exists"] for item in payload["artifacts"])
