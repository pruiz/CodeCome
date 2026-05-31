# CodeCome Phase 1: CodeQL Build Repair

You are performing a narrow repair step after Phase 1a generated a CodeQL plan and the CodeQL database creation step failed.

Your task is to make the smallest durable change needed so CodeQL can create a database on the next run.

## Required Reading

Read these files if they exist:

- `AGENTS.md`
- `itemdb/notes/target-profile.md`
- `itemdb/notes/build-model.md`
- `itemdb/notes/codeql-plan.yml`
- `itemdb/codeql/run-manifest.yml`
- `itemdb/codeql/codeql-summary.md`

Also inspect relevant CodeQL database logs under:

- `itemdb/codeql/databases/**/log/*.log`

Focus on the last useful `[build-stderr]`, `[build-stdout]`, `ERROR`, and `Exception caught` lines.

## Goal

Repair `itemdb/notes/codeql-plan.yml` so the next CodeQL run can create databases.

For C/C++, Go, and Swift, do not use `build_mode: none`. Use only `manual` or `autobuild` as supported by the CodeQL integration.

If autobuild failed because no supported root build system was detected, prefer `build_mode: manual` with a concrete `build_command`.

## Allowed Writes

You may write only:

- `itemdb/notes/codeql-plan.yml`
- helper scripts under `tmp/`
- helper scripts under `sandbox/`
- a short run summary under `runs/` if useful

Do not write helper scripts under `tools/`.

Do not write helper scripts under `itemdb/`.

Do not modify files under `src/`.

Do not modify project orchestration or configuration files.

If the manual command is simple enough, put it directly in `build_command` instead of creating a helper script.

## Build Command Rules

- CodeQL runs the manual `build_command` from the analysis unit source path.
- Prefer commands that are deterministic and non-interactive.
- Prefer commands that avoid modifying `src/` when possible.
- If existing target build files naturally write object files or binaries into `src/`, document that limitation in the `notes` field.
- Use workspace-relative helper script paths that work from the CodeQL source path.
- Keep the plan schema and existing pack selections intact unless a minimal change requires otherwise.

## Output Requirements

Make the repair directly in files. At the end, summarize:

- why the previous CodeQL build failed,
- what changed in `itemdb/notes/codeql-plan.yml`,
- any helper script created,
- the exact manual build command CodeQL will run next.
