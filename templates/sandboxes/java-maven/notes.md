# Notes for the Java + Maven sandbox baseline

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

- Java/Kotlin/Scala projects with Maven (`pom.xml`) or Gradle
  (`build.gradle*`).

## When NOT to use

- Target uses SBT or Bazel — extend this baseline or create a custom
  example.
- Target requires a database — combine with `multi-service-compose`.
- Target depends on internal artifact repositories — mount or copy
  the Maven settings.xml rather than baking secrets.
