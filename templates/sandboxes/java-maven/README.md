# Java + Maven sandbox example

Baseline image for JVM projects, including Kotlin and Scala.

## What's included

- `eclipse-temurin:__JDK_VERSION__-jdk-jammy` base image
- Maven (apt) and Gradle (downloaded)
- Common Linux utilities: `git`, `make`, `python3`, `ripgrep`, `jq`,
  `strace`, `curl`.

## Markers

| Marker | Purpose |
|---|---|
| `__TARGET_NAME__` | Target name. |
| `__JDK_VERSION__` | JDK major version (e.g. `21`, `17`, `11`). |
| `__APP_PORT__` | Exposed app port. |

## Build heuristics

`scripts/build.sh` chooses Maven if `pom.xml` exists,
otherwise Gradle. Local caches under `/root/.m2` and `/root/.gradle`
are persisted across runs.

## When to extend

- For Spring Boot, ensure `application.properties` references
  `__APP_PORT__`.
- For SBT or Bazel projects, swap Maven/Gradle for the appropriate
  tool here.
