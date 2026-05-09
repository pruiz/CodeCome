# Notes for the .NET sandbox baseline

## Seed reminder

This template is a starting point, not a finished sandbox. During
Phase 1b the agent must extend it into a fully functional
`sandbox/` with durable ways to:

    sandbox setup
    sandbox start
    sandbox sanity
    target build
    target test
    sandbox stop

Use the canonical helper set under `sandbox/scripts/`:
`setup.sh`, `up.sh`, `check.sh`, `build.sh`, `test.sh`, `down.sh`.
Add operational helpers such as `shell.sh`, `logs.sh`, `clean.sh`,
and `reset.sh` when they make sense for the target. Document any
extras or omitted helpers in `itemdb/notes/sandbox-plan.md`. See
`.opencode/skills/sandbox-bootstrap/SKILL.md`.

## When to use

- C#, F#, or VB.NET targets.
- Any project with `*.sln`, `*.csproj`, `*.fsproj`, or `*.vbproj`.

## When NOT to use

- Target requires Windows-only frameworks (.NET Framework 4.x).
  Use a Windows-based sandbox or static-only review.
- Target requires SQL Server / Postgres / Redis — combine with
  `multi-service-compose`.
- Target relies on Identity provider auth in production — do not
  bring real secrets into the sandbox.
