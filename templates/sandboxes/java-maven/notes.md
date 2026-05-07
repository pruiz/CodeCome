# Notes for the Java + Maven sandbox baseline

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

- Java/Kotlin/Scala projects with Maven (`pom.xml`) or Gradle
  (`build.gradle*`).

## When NOT to use

- Target uses SBT or Bazel — extend this baseline or create a custom
  example.
- Target requires a database — combine with `multi-service-compose`.
- Target depends on internal artifact repositories — mount or copy
  the Maven settings.xml rather than baking secrets.
