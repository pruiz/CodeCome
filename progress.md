# CodeCome Web Progress

Continue from `progress.md` and implement the next unfinished TODO.

## Rules

- Do not ask questions.
- Make reasonable assumptions.
- Mark completed TODO items with `[x]`.
- Add useful follow-up TODOs when needed.
- Run tests/lint/build when available.
- Do not run destructive commands such as `git reset`, `git clean`, `rm -rf`, force push, deploy, or production migrations.
- Keep going while work remains.
- Every new implementation must include or update tests before committing.
- Commit completed implementation increments when explicitly requested by the user. Current request requires each implementation increment to be committed separately after tests pass.
- Keep web app work isolated on `web-app-control-plane` or feature branches created from it, such as `feature/gap-scan-loop`.
- Keep web app separated from the CodeCome CLI core; prefer files under `web_app/` for the control plane.

## Current Branch

- [x] Create dedicated branch: `web-app-control-plane`.
- [x] Create feature branch for post-exploit gap scanning: `feature/gap-scan-loop`.

## TODO

- [x] Create `progress.md` to track web app work and quality rules.
- [x] Add backend test foundation with mocks/isolated database so API changes do not break silently.
- [x] Add tests for audit creation, worker listing, phase sequencing, logs API, and findings API.
- [x] Add tests for SSH worker behavior using mocks; never require a real SSH host in unit tests.
- [x] Add frontend test/lint setup for core components when practical.
- [x] Implement manual finding status changes from the web UI.
- [x] Add backend endpoint to update finding status, severity, confidence, category, and notes.
- [x] Add tests for manual finding status changes.
- [x] Update the finding Markdown file in `itemdb/findings/<STATUS>/` when status changes, or clearly document DB-only status behavior.
- [x] Add a finding review workflow: status history, reviewer note, and timestamp.
- [x] Add UI controls on finding detail page to change status manually.
- [x] Add integration tests for finding update API with a real test database/session.
- [x] Add frontend tests for finding filters and finding detail review form.
- [x] Add SSH worker reconnect/recovery support by persisting remote job PID/path.
- [x] Add live log polling from detached SSH job stdout/stderr while it runs.
- [x] Add audit delete confirmation and tests.
- [x] Add API and UI smoke tests to CI/local command.
- [x] Document development workflow and test commands in `web_app/README.md`.
- [x] Add global Findings page across all audits with filtering.
- [x] Fix long-text wrapping/collision issues in finding detail pages.
- [x] Add Preview Analysis configuration page with custom prompt.
- [x] Add tests for global findings API and preview config API.
- [x] Add optional `make sweep` phase after `phase-2` without adding it to automatic progression.
- [x] Replace web `phase-4`/`phase-5` steps with CodeCome batch commands `make validate-all` and `make exploit-all`.
- [x] Analyze what happens when the same agent has 2 or more audits; local workers now force one active job to avoid shared sandbox/Docker conflicts across audits.
- [x] POSSIBLE BUG: Make sure one agent running two or more audits always uses the correct original CodeCome sandbox for each audit and never crosses audit workspaces or sandbox instances.
- [x] TODO: Investigate and improve the worker bootstrap script so it registers the machine as a worker automatically, including creating/configuring a local execution user with Docker access when appropriate.
- [x] BUG: In the latest SmallCompany audit, rerunning `make validate-all` fails with `Rerun failed: No available worker`; investigate worker availability/release state and ensure failed phase reruns can be queued when capacity should be free.
- [x] TEST: Run full web app checks plus a live SmallCompany ZIP upload from `/opt/tools/08_TETools/SmallCompany.zip`, including general UI/API verification, before committing current model-selection changes.

## Current Major Feature: Post-Exploit Gap Scan Loop

Goal: after CodeCome finishes the normal workflow through `make exploit-all`, optionally run an independent SAST-style LLM gap scan, compare its candidate findings against CodeCome's existing findings, add missing areas to durable notes, run targeted `make sweep FILE=...`, then reuse existing `phase-3`, `validate-all`, and `exploit-all` flow. This feature must improve missed-finding coverage without lowering the finding quality bar.

### Product Rules

- [x] Add a new optional workflow step named `gap-scan`; it must not run automatically unless explicitly enabled by audit settings or clicked in the UI.
- [x] Keep CodeCome CLI core behavior stable; add orchestration through web app and thin Make/tool wrappers only where needed.
- [x] Do not let the gap-scan LLM directly mark findings as confirmed, exploited, rejected, or duplicate.
- [x] Prefer creating durable candidate-gap artifacts first; targeted sweeps should create real `PENDING` findings using existing Phase 2 mechanisms.
- [x] Bound the loop to avoid infinite rescans: maximum scan rounds, maximum candidates, maximum sweep files, and maximum sweeps per audit must be configurable.
- [x] Never re-open `REJECTED` or `DUPLICATE` findings automatically; flag strong conflicts for human review.
- [x] Preserve existing CodeCome status lifecycle: `PENDING` -> Phase 3 counter-analysis -> Phase 4 validation -> Phase 5 exploitation.
- [x] Every gap-scan claim must distinguish notes-only evidence from active findings.
- [x] Store all gap-scan outputs under `itemdb/notes/`, `runs/`, or `itemdb/reports/`; do not leave important analysis only in logs.

### Gap-Scan Artifact TODO

- [x] Define `itemdb/notes/sast-gap-scan.md` as the human-readable summary of the independent SAST pass.
- [x] Define `itemdb/notes/sast-gap-candidates.yml` as the structured candidate list.
- [x] Define `itemdb/notes/sast-gap-interesting-files.md` as the sweep planning file for missing candidates.
- [x] Define `itemdb/notes/sast-gap-file-risk-index.yml` as an optional machine-readable file priority index for targeted sweeps.
- [x] Define `runs/sast-gap-scan-YYYY-MM-DD-HHMMSS.md` run summary using `templates/run-summary.md` style.
- [x] Define `runs/sast-gap-compare-YYYY-MM-DD-HHMMSS.md` for the semantic comparison result.
- [x] Define `runs/sast-gap-sweep-YYYY-MM-DD-HHMMSS.md` for files swept and resulting finding IDs.

### Candidate Schema TODO

- [x] Define candidate IDs such as `GAP-0001`, stable within a scan run.
- [x] Include candidate fields: title, category, CWE hint, severity hint, confidence, affected files, symbols, entry points, source, sink, trust boundary, evidence snippets, impact, and validation idea.
- [x] Include comparison fields: matched existing findings, matched notes, match confidence, decision, and action.
- [x] Include action values: `covered`, `missing_sweep`, `missing_create_candidate`, `duplicate`, `rejected_conflict`, `needs_human`, `defer_low_signal`.
- [x] Include sweep planning fields: sweep files, rationale for each file, and expected vulnerability class.
- [x] Include safety fields: why this candidate is source-backed and why it is not merely a generic bug-class guess.

### Prompt/Agent TODO

- [x] Add prompt `prompts/phase-2-gap-sast.md` for independent SAST-style gap scanning.
- [x] The prompt must read `AGENTS.md`, `codecome.yml`, `itemdb/notes/`, all existing findings across statuses, and high-risk source files.
- [x] The prompt must specifically ask for missed low/medium information disclosure patterns such as exception/stack trace exposure when externally reachable.
- [x] The prompt must require structured output to `itemdb/notes/sast-gap-candidates.yml` and summary to `itemdb/notes/sast-gap-scan.md`.
- [x] The prompt must forbid direct confirmation/exploitation and forbid moving findings across statuses.
- [x] The prompt must require semantic deduplication against existing active and inactive findings.
- [x] Decide whether to reuse `auditor` or add a new `.opencode/agents/gap-scanner.md` agent.
- [x] If adding `gap-scanner`, define its role as independent SAST reviewer, not validator/exploiter.

### Comparison Engine TODO

- [x] Add a comparator that reads all findings under `itemdb/findings/{PENDING,CONFIRMED,EXPLOITED,REJECTED,DUPLICATE}`.
- [x] Compare candidates against findings by vulnerability class, files, symbols, source, sink, trust boundary, impact, and validation path.
- [x] Compare candidates against Phase 1 notes to detect cases that are mentioned in notes but missing as findings.
- [x] Mark candidates as `covered` when a semantically equivalent finding exists in any status.
- [x] Mark candidates as `missing_sweep` when only notes mention the issue or no finding covers it.
- [x] Mark candidates as `needs_human` when the candidate conflicts with a rejected/duplicate finding but has stronger evidence.
- [x] Write comparison decisions to `runs/sast-gap-compare-YYYY-MM-DD-HHMMSS.md`.

### Targeted Sweep TODO

- [x] Add `make gap-scan` to run the independent SAST prompt and write candidate artifacts.
- [x] Add `make gap-compare` to compare candidates against current findings and notes.
- [x] Add `make gap-sweep` to run `make sweep FILE=...` for selected missing candidates.
- [x] Add `make gap-loop` as an optional bounded sequence: `gap-scan`, `gap-compare`, `gap-sweep`, `phase-3`, `validate-all`, `exploit-all`.
- [x] Ensure `gap-sweep` can run one selected candidate or all candidates marked `missing_sweep`.
- [x] Ensure `gap-sweep` records which files were swept and which findings were created.
- [x] Prevent duplicate sweeps of the same file/candidate in the same audit unless explicitly forced.
- [x] Use existing `make sweep FILE=...` rather than duplicating line-by-line audit logic.

### Backend/API TODO

- [x] Add API endpoint to start `gap-scan` for an audit.
- [x] Add API endpoint to start `gap-compare` for an audit.
- [x] Add API endpoint to start `gap-sweep` for an audit or selected candidate.
- [x] Add API endpoint to list gap candidates and their comparison decisions.
- [ ] Add API endpoint to mark a candidate as ignored/deferred/needs-human.
- [ ] Add phase execution or job metadata support for `gap-scan`, `gap-compare`, and `gap-sweep` steps.
- [ ] Ensure remote workers receive the workspace before gap-sweep and return `itemdb/notes`, `itemdb/findings`, `runs`, and evidence artifacts after execution.
- [ ] Ensure worker capacity accounting treats gap steps like existing phase jobs.

### Frontend/UI TODO

- [ ] Add `Gap Scan` tab or Overview panel in audit details.
- [ ] Add button `Run Gap Scan` after `make exploit-all` or whenever the user explicitly chooses.
- [ ] Add button `Compare Candidates` after gap scan completes.
- [ ] Add table of gap candidates with status/action, severity hint, files, matched findings, and recommended sweep files.
- [ ] Add action buttons: `Run Sweep`, `Ignore`, `Needs Human`, and `Open Candidate Details`.
- [ ] Show whether a candidate is covered by an existing finding, only mentioned in notes, or missing entirely.
- [ ] Show a clear warning that gap candidates are not confirmed vulnerabilities.
- [ ] Add audit creation option `Run gap scan after exploit-all` defaulting to disabled.

### Quality/Safety TODO

- [x] Add unit tests for candidate schema parsing and validation.
- [x] Add unit tests for semantic comparison against existing findings.
- [x] Add backend API tests for starting/listing gap scans.
- [ ] Add frontend tests for Gap Scan UI states and candidate table actions.
- [ ] Add integration test using a small fixture where Phase 1 notes mention stack trace disclosure but no finding exists, and gap-compare marks it `missing_sweep`.
- [ ] Add regression test that a covered finding is not re-swept.
- [ ] Run full `./web_app/run-checks.sh` before every commit.
- [ ] For live verification, upload `/opt/tools/08_TETools/SmallCompany.zip`, run a bounded gap scan, and confirm missing note-only issues become targeted sweeps or candidates.

### Open Design TODO

- [x] Decide default max candidates per scan, proposed default: `10`.
- [x] Decide default max sweep files per gap loop, proposed default: `5`.
- [x] Decide default max gap loop rounds, proposed default: `1`.
- [ ] Decide whether candidate comparison should use only deterministic rules first or an LLM-assisted comparator.
- [x] Decide whether `gap-loop` should run automatically before `phase-6` when enabled, or stay manual-only in the first release.

## Current Major Feature: Users, Question Owners, and Fake AI Answerers

Goal: successful phases that produce questions for the user must pause the workflow until the audit's assigned question owner answers them. The owner may be a human user answering in the web app, or a fake AI user that answers automatically and allows the workflow to continue.

### Product Rules

- [x] Add web app users for authentication and question ownership.
- [x] All authenticated users can see everything; no roles are needed for now.
- [x] Each audit can be associated with one question owner user.
- [x] The question owner can be a human user or a fake AI user.
- [x] More than one fake AI user can exist globally.
- [x] If the owner is human, blocking questions pause the audit until answered or dismissed in the web UI.
- [x] If the owner is a fake AI user, the backend auto-answers assigned questions and continues the workflow when all blocking questions are resolved.
- [x] Telegram and Office Teams notifications are deferred until after web UI and fake AI users work.

### Data Model TODO

- [x] Add `users` table with username, password hash, display name, active flag, fake-AI fields, and timestamps.
- [x] Add `audits.question_owner_user_id` runtime-schema column and model/schema/API support.
- [x] Add `phase_questions` table with audit, phase execution, phase, question, context, blocking flag, status, assignment, answer metadata, and timestamps.
- [x] Add durable answer context file generation at `runs/user-answers-context.md`.

### Backend/API TODO

- [x] Add user CRUD APIs for listing users and creating/editing fake AI users.
- [x] Add minimal auth foundation for human login users.
- [x] Add audit update support for `question_owner_user_id`.
- [x] Add question APIs: list by audit, list by phase execution, answer, dismiss.
- [x] Add question APIs: auto-answer and continue-after-questions.
- [x] Add question extraction/detection after successful phase completion.
- [x] Add auto-continue gate: do not queue next phase while blocking questions are open.
- [x] Add fake AI auto-answer flow using the assigned fake AI user's model/context.
- [x] Inject answered questions into subsequent phase runs via `PROMPT_EXTRA_FILE` or merged env.

### Frontend TODO

- [x] Add login/logout UI once auth API exists.
- [x] Add users/fake-AI user management UI.
- [x] Add audit question owner selector in audit overview/config.
- [x] Add audit Questions tab listing open/answered/dismissed questions by phase.
- [x] Add question panel to Current Phase for selected execution questions.
- [x] Add answer/dismiss controls for human users.
- [x] Add fake AI answer/regenerate controls for fake-AI-owned questions.
- [x] Add paused-for-questions status display and continue-after-questions button.
- [x] Add an option to launch the "sandbox" in an active audit.
 
### Testing/Quality TODO

- [x] Add backend tests for user/fake-AI CRUD.
- [x] Add backend tests for question creation, answer, and dismiss.
- [x] Add backend tests for question blocking gate.
- [x] Add backend tests for fake AI answer normalization and continuation.
- [x] Add frontend tests for question owner selector and question answer UI.
- [x] Add frontend tests for fake AI user management or auto-answer controls.
- [x] Run `web_app/run-checks.sh` before each implementation commit when practical.
- [x] Smoke test locally through `http://localhost:3000` and `http://localhost:8000/health`.
- [x] Use `/opt/tools/08_TETools/SmallCompany.zip` for manual audit smoke tests when an end-to-end workflow is needed.

### Commit Policy For This Feature

- [x] Commit 1: progress tracking and explicit implementation plan.
- [x] Commit 2: user/fake-AI and audit question-owner backend foundation with tests.
- [x] Commit 3: phase-question model/API and web answering UI with tests.
- [x] Commit 4: successful-phase question detector and pause gate with tests.
- [x] Commit 5: fake AI auto-answer and resume workflow with tests.
- [x] Commit 6: end-to-end UI polish and local smoke-test fixes, if needed.

## Done Recently

- [x] Web app scaffold: FastAPI backend, React frontend, Docker DBs.
- [x] Worker registry and local worker support.
- [x] Worker bootstrap script with OpenCode config support.
- [x] Worker detail page and CodeCome prerequisite checks.
- [x] SSH credentials storage with redaction.
- [x] SSH executor for remote worker phase execution.
- [x] Detached SSH remote job mode for long-running phases.
- [x] Audit phase bar and per-phase filtered logs.
- [x] Environment override editor per phase.
- [x] Finding list fixed to show DB findings.
- [x] Dedicated finding URL and Markdown rendering.
- [x] Pill-style finding filters.
- [x] Manual finding review/status UI and backend endpoint.
- [x] Global findings page across audits.
- [x] Preview analysis prompt configuration page.
- [x] Finding detail long-text wrapping fixes.
- [x] Backend core logic tests for audit creation, workers, phase command lines, logs, findings, SSH executor, and Markdown sync.
- [x] Frontend Vitest setup with global findings filter/link tests.
- [x] `web_app/run-checks.sh` local quality gate.
- [x] Finding Markdown status synchronization when manual status changes.
- [x] Remote SSH phase executions persist `remote_job_dir` and `remote_pid`.
- [x] Dashboard delete confirmation covered by frontend tests.
- [x] Backend integration-style finding update test with real session.
- [x] Finding detail manual review form covered by frontend test.
- [x] SSH recovery task is queued at backend startup for running remote jobs with persisted metadata.
- [x] Optional deep sweep can be launched manually from the audit phase bar.
- [x] Batch validation/exploitation commands are first-class audit steps.
- [x] Failed-phase OpenCode triage records and manual apply flow.
- [x] Automatic stale-local-phase startup reconciliation.
- [x] All Findings API includes `audit_name`; global findings can search by audit name.
- [x] Finding detail lifecycle timeline.
- [x] Spain 24-hour date/time formatting in frontend.

## Follow-up TODO

- [x] Add actual SSH recovery loop that resumes polling persisted `remote_job_dir` and `remote_pid` after backend/Celery restart.
- [x] Add UI indication for recoverable remote jobs.

## Backlog

- [x] Replace deprecated Pydantic class-based `Config` with `ConfigDict`.
- [x] Replace SQLAlchemy `declarative_base()` import with `sqlalchemy.orm.declarative_base`.
- [x] Add coverage thresholds once the test suite is broader.
- [x] Enforce authentication on API routes with first-user bootstrap.
- [x] Prevent creating active human users without passwords.
- [x] Enforce authentication on WebSocket log/status streams.
- [x] Add frontend auth gate before loading protected app routes.
- [x] Reject API bearer tokens for inactive or missing users.
- [x] Clear stale frontend auth tokens on protected API 401 responses.
- [x] Refresh frontend auth gate immediately on logout or stale-token cleanup.
- [x] Preserve audit settings when creating audits from uploaded ZIP files.
- [x] Add inline editing for fake AI user model/context.
- [x] Add question owner selection to audit creation.
- [x] Add tests for API auth middleware route enforcement.
- [x] Prevent disabling or converting the last active human user.
- [x] Show audit-level open/blocking question counts in audit header.
- [x] Show open/blocking question counts on dashboard audit cards.
- [x] Clear stale frontend auth tokens when WebSocket auth is rejected.
- [x] Pass selected ZIP file into multipart audit upload from AuditCreator.
- [x] Omit large audit config blobs from audit list responses.
- [x] Clear stale frontend auth tokens for raw-response API calls.
- [x] Add human user password reset in Users page.
- [x] Force first-user bootstrap to create an active human user.
- [x] Show assigned question owner name/type in audit header.
- [x] Show assigned question owner name/type on dashboard audit cards.
- [x] Include question owner names in dashboard audit search.
- [x] Disable dashboard start/retry action while blocking questions are open.
- [x] Disable audit detail start/continue action while blocking questions are open.
- [x] Remove obsolete AI review checkbox from audit creation.
- [x] Add manual refresh for audit detail question counts.
- [x] Add text search to Users page.
- [x] Add All/Human/AI filters to the Users page.
- [x] Remove obsolete AI review badge from audit detail header.
- [x] Add active/inactive filters to the Users page.
- [x] Show only relevant fields when creating human or fake AI users.
- [x] Strip hidden user creation fields before submit.
- [x] Strip hidden user edit fields before saving existing users.
- [x] Normalize hidden human/fake-AI user fields on the backend.
- [x] Raise backend coverage floor to 48%.
- [x] Default new audits to the first active human question owner when none is selected.
- [x] Replace checkbox-style controls in the user creation form with coherent toggle switches matching the project UI.
- [x] Replace checkbox-style controls in the audit creation form with coherent toggle switches matching the project UI.
- [x] Ensure Launch Sandbox starts the audit-specific Docker sandbox instance; each audit must use its own sandbox, not a shared/global sandbox.
- [x] BUG: Audits created with auto-continue enabled can remain stuck in `initializing` instead of automatically starting the first phase.
- [x] Let fake AI users choose an available model from the assigned agent/OpenCode JSON configuration instead of manually typing the model name.
- [x] Add worker-aware model selection during audit creation: when a worker is selected, load the models supported by that worker from its OpenCode config, allow choosing one, and apply it as an audit-wide environment setting for every phase.
- [x] Improve Proxmox VM/LXC worker bootstrap so the target runs a self-registration script that pulls required configuration from the web app and registers itself as a worker automatically, avoiding manual keyfile/user/password entry when possible.
- [x] BUG: Investigate audit `13555161-ddba-422d-bff8-47b149bac988` `make validate-all` failure from latest logs and add a durable guard so this failure mode cannot recur.
- [x] CHECK: Verify audits created from a local folder are copied to the selected worker before execution; remote workers receive the materialized workspace snapshot via SFTP upload, not the original local path.
- [x] POSSIBLE BUG: Make sure one agent running two or more audits always uses the correct original CodeCome sandbox for each audit and never crosses audit workspaces or sandbox instances.

## Notes

- Databases run in Docker: PostgreSQL on `15432`, Redis on `6379`.
- FastAPI, Celery, React, and CodeCome CLI run natively.
- CodeCome CLI core should remain separate; web app orchestrates it, not replaces it.
- Current quality gate for web app: `cd web_app && ./run-checks.sh`.
- Current services: `./web_app/start-services.sh`; stop with `./web_app/stop.sh`.
