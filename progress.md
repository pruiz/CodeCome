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
- Keep web app work isolated on branch `web-app-control-plane`.
- Keep web app separated from the CodeCome CLI core; prefer files under `web_app/` for the control plane.

## Current Branch

- [x] Create dedicated branch: `web-app-control-plane`.

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

## Notes

- Databases run in Docker: PostgreSQL on `15432`, Redis on `6379`.
- FastAPI, Celery, React, and CodeCome CLI run natively.
- CodeCome CLI core should remain separate; web app orchestrates it, not replaces it.
- Current quality gate for web app: `cd web_app && ./run-checks.sh`.
- Current services: `./web_app/start-services.sh`; stop with `./web_app/stop.sh`.
