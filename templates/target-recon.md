# Target Reconnaissance Notes

Date: YYYY-MM-DD  
Phase: reconnaissance  
Target path: `./src`

# Executive summary

Briefly summarize what the target appears to be.

Include:

- target type,
- main languages,
- main frameworks or technologies,
- execution model,
- most relevant attack surfaces,
- most relevant validation approach.

# Target profile

## Detected target type

Examples:

- web application,
- backend service,
- CLI tool,
- library,
- benchmark corpus,
- infrastructure-as-code repository,
- firmware tree,
- desktop application,
- mobile application,
- mixed repository.

Detected type:

    TBD

Confidence:

    LOW / MEDIUM / HIGH

## Languages

List detected languages and relevant file patterns.

## Frameworks and technologies

List relevant frameworks, runtimes, package managers, build systems, and deployment technologies.

## Repository structure

Describe the relevant directory layout.

Focus on directories that matter for security review.

# Build model

Describe how the target appears to be built.

Include:

- build files,
- package manifests,
- compiler/interpreter requirements,
- test commands,
- generated artifacts,
- build assumptions,
- missing information.

# Execution model

Describe how the target appears to run.

Examples:

- HTTP service,
- background worker,
- CLI executable,
- library imported by callers,
- benchmark testcase,
- firmware component,
- IaC deployment.

Include entrypoints and runtime dependencies.

# Attack surface

List the detected attack surfaces.

For each surface, include:

- name,
- type,
- entrypoints,
- input sources,
- likely attacker control,
- relevant files,
- initial risk notes.

Example surface types:

- HTTP route,
- RPC method,
- CLI argument,
- config file,
- environment variable,
- input file parser,
- public library API,
- message queue consumer,
- database migration,
- template renderer,
- authentication flow,
- authorization decision,
- file upload,
- filesystem operation,
- external command execution,
- cryptographic operation,
- deserialization boundary,
- network listener,
- infrastructure exposure.

# Trust boundaries

Describe where untrusted or lower-trust data crosses into higher-trust components.

Examples:

- anonymous user to authenticated area,
- authenticated user to admin function,
- tenant A to tenant B,
- external webhook to internal processing,
- CLI user input to shell command,
- input file to parser,
- config file to privileged operation,
- network packet to firmware parser,
- user-controlled path to filesystem access.

# Assets at risk

List security-relevant assets.

Examples:

- user data,
- tenant data,
- credentials,
- private keys,
- tokens,
- certificates,
- filesystem contents,
- database records,
- admin functions,
- signing operations,
- internal network access,
- service availability,
- code execution context.

# Dangerous sinks

List security-sensitive sinks found or suspected.

Examples:

- raw SQL construction,
- shell command execution,
- filesystem reads/writes,
- path joins,
- template rendering,
- unsafe deserialization,
- memory copy operations,
- pointer arithmetic,
- cryptographic signing,
- token validation,
- authorization checks,
- SSRF-capable HTTP clients,
- XML parsers,
- archive extraction,
- dynamic code loading,
- eval-like behavior,
- privileged API calls.

# Data flow notes

Summarize important data flows.

Focus on flows that may be security-relevant.

# Security assumptions

List assumptions made during reconnaissance.

Mark each as:

- confirmed,
- likely,
- unknown,
- risky.

# Interesting files

List files or directories that should be reviewed during hypothesis generation.

For each item, explain why it is interesting.

# Recommended audit focus

List the vulnerability classes that appear most relevant for this target.

# Validation model

Describe how findings should be validated for this target.

Include:

- whether the target can be built,
- whether it can be run locally,
- whether Docker is sufficient,
- whether tests exist,
- whether sanitizers/debuggers are useful,
- whether HTTP/CLI/file-based validation applies,
- what evidence should be captured.

# Limitations

List what could not be determined during reconnaissance.

# Next steps

Concrete recommendations for phase 2.
