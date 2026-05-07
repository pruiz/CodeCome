# Notes for the .NET sandbox baseline

## Seed reminder

This template is a starting point, not a finished sandbox. During
Phase 1b the agent must extend it into a fully functional
`sandbox/`, including authoring missing canonical scripts:

    check.sh   up.sh   down.sh   shell.sh   logs.sh
    clean.sh   reset.sh

The agent should also adapt the starter `build-target.sh` and
`test-target.sh` to the actual project layout, and add
target-specific scripts when they help. Document any extras in
`itemdb/notes/sandbox-plan.md`. See
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
