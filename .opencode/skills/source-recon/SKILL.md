# Source Reconnaissance Skill

Use this skill during CodeCome Phase 1: target reconnaissance and attack surface recognition.

The goal of reconnaissance is to understand the target before creating vulnerability findings.

Do not rush into reporting bugs. First build a useful target model.

## Purpose

Reconnaissance should answer:

- What kind of target is this?
- What languages and frameworks are used?
- How is it built?
- How is it executed?
- What are the attack surfaces?
- Where are the trust boundaries?
- What assets are at risk?
- What dangerous sinks exist?
- How can findings be validated later?

## Output files

Create or update these files under `itemdb/notes/`:

    itemdb/notes/target-profile.md
    itemdb/notes/attack-surface.md
    itemdb/notes/build-model.md
    itemdb/notes/execution-model.md
    itemdb/notes/trust-boundaries.md
    itemdb/notes/data-flow.md
    itemdb/notes/validation-model.md
    itemdb/notes/interesting-files.md
    itemdb/notes/security-assumptions.md

If the target has a specific nature, optional additional notes may be created.

Examples:

    itemdb/notes/web-routes.md
    itemdb/notes/cli-commands.md
    itemdb/notes/public-api.md
    itemdb/notes/cwe-map.md
    itemdb/notes/benchmark-notes.md
    itemdb/notes/iac-resources.md
    itemdb/notes/crypto-usage.md
    itemdb/notes/auth-model.md

## Reconnaissance rules

1. Do not create findings during reconnaissance unless the issue is extremely obvious and high confidence.
2. Prefer broad understanding over deep analysis of one bug.
3. Identify what should be reviewed in later phases.
4. Be explicit about uncertainty.
5. Do not assume the target is a web application.
6. Do not assume the target can be executed.
7. Do not assume filenames or comments are reliable vulnerability evidence.
8. Do not modify source code.
9. Keep notes concise but useful.
10. Write notes as Markdown artifacts.

## Target type detection

Infer the target type.

Possible target types include:

- web application,
- backend service,
- CLI tool,
- library,
- benchmark corpus,
- infrastructure-as-code repository,
- firmware tree,
- desktop application,
- mobile application,
- mixed repository,
- unknown.

Use evidence such as:

- repository structure,
- manifest files,
- build files,
- routes/controllers,
- command definitions,
- package metadata,
- Docker files,
- CI configuration,
- tests,
- documentation,
- source file extensions,
- framework imports,
- binary/build artifacts.

## Language and framework detection

Identify relevant languages and technologies.

Examples:

- C/C++: Makefile, CMakeLists.txt, `.c`, `.cpp`, `.h`, `.hpp`
- .NET: `.csproj`, `.sln`, ASP.NET controllers, `Program.cs`
- Java: `pom.xml`, `build.gradle`, Spring annotations
- Node: `package.json`, Express/Nest/Next files
- Python: `pyproject.toml`, `requirements.txt`, Flask/FastAPI/Django
- Go: `go.mod`, `cmd/`, `internal/`
- PHP: `composer.json`, Laravel/Symfony structure
- IaC: Terraform, Kubernetes YAML, Helm, Ansible, Salt, Nomad, Docker Compose

## Build model

Document how the target appears to be built.

Look for:

- Makefiles,
- CMake,
- Gradle,
- Maven,
- npm/yarn/pnpm,
- dotnet CLI,
- Python packaging,
- Go modules,
- Dockerfiles,
- CI scripts,
- build documentation.

Record:

- likely build command,
- required dependencies,
- generated artifacts,
- missing dependencies,
- build uncertainty,
- whether the sandbox needs adaptation.

## Execution model

Document how the target appears to run.

Examples:

- HTTP server,
- background worker,
- CLI executable,
- library imported by another program,
- test harness,
- benchmark testcase,
- firmware image,
- IaC deployment,
- scheduled job,
- message queue consumer.

Record:

- entrypoints,
- runtime dependencies,
- config files,
- required environment variables,
- ports,
- local services,
- databases,
- queues,
- external dependencies,
- test commands.

## Attack surface recognition

Identify attack surfaces.

An attack surface is any externally influenced way to reach code, configuration, state, or behavior.

Examples:

- HTTP routes,
- RPC methods,
- GraphQL operations,
- WebSocket handlers,
- CLI arguments,
- stdin,
- input files,
- uploaded files,
- config files,
- environment variables,
- public library APIs,
- message consumers,
- webhooks,
- scheduled jobs,
- database migrations,
- template rendering,
- archive extraction,
- XML parsing,
- JSON/YAML deserialization,
- filesystem paths,
- external command invocation,
- dynamic code loading,
- authentication flows,
- authorization decisions,
- cryptographic operations,
- signing operations,
- network listeners,
- IaC resources.

For each attack surface, document:

- name,
- type,
- entrypoints,
- input sources,
- likely attacker control,
- relevant files,
- trust boundary,
- likely vulnerability classes.

## Trust boundaries

Identify where data or control crosses from lower trust to higher trust.

Examples:

- anonymous user to application,
- authenticated user to tenant data,
- tenant A to tenant B,
- regular user to admin operation,
- external webhook to internal processing,
- CLI argument to privileged operation,
- input file to parser,
- config file to service behavior,
- network packet to parser,
- user-controlled path to filesystem,
- untrusted archive to extraction path,
- untrusted template to renderer,
- external identity provider to local session,
- local code to HSM/signing operation.

## Assets at risk

Identify assets that matter.

Examples:

- user data,
- tenant data,
- credentials,
- API tokens,
- private keys,
- certificates,
- signing keys,
- session cookies,
- database records,
- filesystem contents,
- generated documents,
- audit logs,
- admin actions,
- internal network access,
- compute resources,
- service availability,
- code execution context.

## Dangerous sinks

Identify security-sensitive sinks.

Examples:

- SQL query construction,
- shell command execution,
- filesystem read/write/delete,
- path normalization/joining,
- archive extraction,
- XML parsing,
- YAML/object deserialization,
- template rendering,
- eval/dynamic code execution,
- dynamic imports,
- memory copy functions,
- pointer arithmetic,
- integer-size calculations,
- cryptographic signing,
- token validation,
- password verification,
- authorization decisions,
- SSRF-capable HTTP clients,
- LDAP queries,
- XPath queries,
- logging of secrets,
- file upload storage,
- privilege-changing operations.

## Data flow notes

Capture important flows.

Prioritize flows involving:

- untrusted input,
- authentication,
- authorization,
- tenant isolation,
- secret handling,
- file paths,
- external commands,
- parsers,
- serialization,
- crypto,
- network calls,
- memory unsafe operations.

Do not attempt full formal data-flow analysis in Phase 1. Create useful notes for Phase 2.

## Security assumptions

Record assumptions explicitly.

Use these labels:

- `confirmed`
- `likely`
- `unknown`
- `risky`

Examples:

    - [likely] The service is intended to be exposed over HTTP.
    - [unknown] It is unclear whether file paths come from authenticated users.
    - [risky] Several shell command wrappers appear to accept string arguments.
    - [confirmed] The target contains C code compiled with Make.

## Interesting files

Create `itemdb/notes/interesting-files.md`.

Include files that deserve deeper review.

For each file or directory, record:

- path,
- why it is interesting,
- likely vulnerability classes,
- recommended follow-up.

## Validation model

Create `itemdb/notes/validation-model.md`.

Explain how findings can be validated.

Examples:

- build and run locally,
- run unit tests,
- create integration tests,
- send HTTP requests,
- call CLI commands,
- craft input files,
- run with sanitizers,
- run under debugger,
- compare benchmark oracle,
- inspect generated configuration,
- use static proof only.

Include limitations and sandbox changes needed.

## Recommended phase 2 focus

At the end of reconnaissance, provide a prioritized list of areas for hypothesis generation.

Example:

    1. Review authorization checks around document access.
    2. Review file upload and archive extraction paths.
    3. Review shell command wrappers.
    4. Review XML parsing and deserialization.
    5. Review C/C++ buffer handling in parser module.

## Completion checklist

Before finishing reconnaissance, ensure that:

- `target-profile.md` exists.
- `attack-surface.md` exists.
- `build-model.md` exists.
- `execution-model.md` exists.
- `trust-boundaries.md` exists.
- `data-flow.md` exists.
- `validation-model.md` exists.
- `interesting-files.md` exists.
- `security-assumptions.md` exists.
- no low-quality findings were created prematurely.
