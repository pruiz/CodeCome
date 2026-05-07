# Notes for the Java + Maven sandbox baseline

## When to use

- Java/Kotlin/Scala projects with Maven (`pom.xml`) or Gradle
  (`build.gradle*`).

## When NOT to use

- Target uses SBT or Bazel — extend this baseline or create a custom
  example.
- Target requires a database — combine with `multi-service-compose`.
- Target depends on internal artifact repositories — mount or copy
  the Maven settings.xml rather than baking secrets.
