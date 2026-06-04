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
    itemdb/notes/threat-model.md
    itemdb/notes/file-risk-index.yml

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
- `threat-model.md` exists after Phase 1b.
- `file-risk-index.yml` exists after Phase 1b.
- architectural claims have evidence anchors.
- runtime behavior is separated from CI/build/dev/test behavior.
- attacker-controlled inputs are distinguished from operator/developer inputs.
- high-priority trust boundaries include source, destination, data/control, channel, controls, and evidence.
- assets include why they matter and C/I/A objectives.
- attacker capabilities and non-capabilities are explicit.
- existing controls are documented with evidence.
- unresolved user-context questions are present in the run summary.
- Phase 2 focus follows from assets, boundaries, entrypoints, controls, and sinks.
- no low-quality findings were created prematurely.

## References

When Phase 1b produces detailed reconnaissance notes, also use:

- `references/threat-model-checklist.md`
- `references/security-controls-and-assets.md`

Use these references to improve grounding, threat-model quality, assets,
controls, attacker assumptions, and Phase 2 review focus.

Do not copy checklist categories blindly. Only include repository-specific items
supported by evidence or explicitly marked assumptions.

## Create-or-update semantics

If `itemdb/notes/threat-model.md` already exists, update it. Do not replace it
wholesale. Preserve manually refined sections, evidence anchors, user-provided
answers, and resolved open questions unless new repository evidence contradicts
them.

## User clarification behavior

### Interactive/chat mode
You may ask targeted questions when missing context materially affects scope,
deployment model, internet exposure, authn/authz assumptions, data sensitivity,
multi-tenancy, risk ranking, or validation strategy. Questions must be few,
specific, and useful.

### Non-interactive phase execution
Do not block waiting for answers unless the phase cannot proceed safely or
meaningfully. Instead: infer conservative assumptions, record assumptions in
`security-assumptions.md`, record unresolved questions in `threat-model.md`,
include unresolved questions in the run summary, and provide re-run prompt hints.

## Threat model summary

Produce `threat-model.md` as an operational risk model that consolidates scope,
system model, assets and security objectives, attacker capabilities and
non-capabilities, trust-boundary summary, existing controls, abuse-path themes,
risk calibration, open questions, and re-run prompt hints.

## Evidence anchors

For every architectural or security claim in `threat-model.md`, include an
evidence anchor: a file path, code reference, configuration key, or observable
runtime behavior. Mark claims without evidence as assumptions.

## Attacker model

Document realistic attacker capabilities and explicit non-capabilities.
Non-capabilities prevent inflated severity judgments in later phases.

## Existing controls

Document controls observed in the repository with evidence: what each control
protects, where it is enforced, what assumptions it relies on, and known gaps.

## Abuse-path themes

Record abuse-path themes in `threat-model.md` as review leads, not findings.
Each theme should include attacker goal, entrypoint, boundary crossed, impacted
asset, existing controls, key assumptions, relevant files, and suggested Phase 2
focus. Explain why each theme is not yet a finding.
