# Notes for the .NET sandbox baseline

## Seed reminder

This template is a starting point, not a finished sandbox. During
Phase 1b the agent must extend it into a fully functional
`sandbox/` with durable ways to:

    start/build the environment
    run sandbox sanity checks
    build the target
    test the target

Prefer helpers such as `build-sandbox.sh`, `up.sh`, `check.sh`,
`build-target.sh`, and `test-target.sh` under `sandbox/scripts/`. Add
operational helpers such as `down.sh`, `shell.sh`, `logs.sh`,
`clean.sh`, and `reset.sh`
when they make sense for the target. Document any extras or omitted
helpers in `itemdb/notes/sandbox-plan.md`. See
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
