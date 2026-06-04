# CodeCome Phase 1b: Detailed Reconnaissance

You are performing CodeCome **Phase 1b** — the second sub-stage of Phase 1.

Phase 1b produces detailed reconnaissance notes. If CodeQL artifacts are available, use them as optional enrichment. If they are absent or CodeQL was disabled, continue with source-only reconnaissance. Phase 1b must complete regardless of CodeQL availability.

## Required reading

Read the following files (all paths are relative to the project/workspace root):

- `AGENTS.md`
- `codecome.yml`
- `templates/target-recon.md`
- `templates/file-risk-index.yml`
- `templates/threat-model.md`
- `.opencode/agents/recon.md`
- `.opencode/skills/source-recon/SKILL.md`
- `.opencode/skills/source-recon/references/threat-model-checklist.md`
- `.opencode/skills/source-recon/references/security-controls-and-assets.md`

Also read the Phase 1a outputs:

- `itemdb/notes/target-profile.md`
- `itemdb/notes/build-model.md`
- `itemdb/notes/codeql-plan.yml`

## CodeQL artifacts (conditional)

If CodeQL analysis was performed, the following artifacts may exist. Treat them as reconnaissance evidence, not proof of vulnerability:

- `itemdb/codeql/run-manifest.yml` — CodeQL run outcome and metadata.
- `itemdb/codeql/normalized/alerts.yml` — Normalized CodeQL alerts with source/sink/flow.
- `itemdb/codeql/normalized/file-signals.yml` — Per-file CodeQL signal scores.
- `itemdb/codeql/codeql-summary.md` — Human-readable CodeQL summary.

If these files exist:

1. Read them and extract relevant signals.
2. Use alert data to enrich your understanding of potential sources, sinks, and trust-boundary crossings.
3. Use file-signals to prioritize files for the file-risk-index.
4. Do not treat CodeQL alerts as confirmed vulnerabilities. They are static-analysis hints.

If these files do not exist, proceed with reconnaissance based on source analysis alone. Phase 1b must complete regardless of CodeQL availability.

## Target

Analyze the source tree under:

    ./src

## Required outputs

Create these files under `itemdb/notes/`:

- `attack-surface.md`
- `execution-model.md`
- `trust-boundaries.md`
- `data-flow.md`
- `validation-model.md`
- `interesting-files.md`
- `file-risk-index.yml`
- `security-assumptions.md`
- `threat-model.md`

### `threat-model.md`

Use the template at `templates/threat-model.md`.

This file consolidates the operational risk model. It is not merely a summary of the other Phase 1b files. It should contain:

- **Scope**: in-scope and out-of-scope components, runtime vs non-runtime separation.
- **System model**: primary runtime components, data stores, external integrations, entrypoints.
- **Assets and security objectives**: for each relevant asset, document where observed, why it matters, C/I/A objectives, related attack surfaces, and evidence.
- **Attacker model**: realistic attacker capabilities and explicit non-capabilities. Non-capabilities are required to avoid inflated severity.
- **Trust boundary summary**: for each important boundary, document source/destination, data/control crossing, channel, authn, authz, encryption, validation, rate controls, existing controls, evidence, and uncertainty.
- **Existing controls**: observed controls with evidence — what the control protects, where enforced, assumptions, gaps.
- **Abuse-path themes for Phase 2**: review leads, not findings. Each theme includes attacker goal, entrypoint, boundary crossed, impacted asset, existing controls, assumptions, relevant files, and suggested Phase 2 focus.
- **Risk calibration**: qualitative prioritization into high/medium/low priority review themes.
- **Open questions for the user**: questions that would materially improve a re-run, with why each matters and what it affects.
- **Re-run prompt hints**: copy/paste hints the user can pass via `PROMPT_EXTRA` or `PROMPT_EXTRA_FILE` on re-run.

Grounding rules:

- Anchor architectural and security claims to repository evidence.
- Mark missing context as assumptions.
- Separate attacker-controlled, operator-controlled, developer-controlled, and trusted internal inputs.
- If `itemdb/notes/threat-model.md` already exists, update it rather than replacing it. Preserve manually refined sections, evidence anchors, and user-provided answers.

### `attack-surface.md`

Document:

- **Network-facing attack surfaces**: HTTP endpoints, RPC services, WebSocket handlers, TCP/UDP listeners, message queue consumers.
- **Local attack surfaces**: CLI argument parsing, config file loading, environment variable consumption, file I/O, IPC.
- **API surface**: routes, controllers, handlers, middleware, GraphQL schemas, gRPC service definitions.
- **Input vectors**: query parameters, request bodies, file uploads, headers, cookies, WebSocket frames, serialized objects.
- **Output vectors**: response bodies, rendered templates, log emissions, file writes.

### `execution-model.md`

Document:

- **Runtime environment**: interpreter, JVM, CLR, native binary, container, serverless.
- **Process model**: single-process, multi-process, worker pool, event loop, thread pool.
- **Startup and lifecycle**: initialization, configuration loading, connection pooling, shutdown.
- **Concurrency model**: async/await, threads, multiprocessing, greenlets, coroutines.

### `trust-boundaries.md`

Document:

- **Network boundary**: remote client ↔ server.
- **Process boundary**: separate processes or containers.
- **User boundary**: authenticated vs unauthenticated, role-based.
- **Data boundary**: tenant isolation, database per tenant, shared database.
- **Component boundary**: plugin system, library interfaces, IPC channels.

### `data-flow.md`

Document key data flows from entry points to dangerous sinks:

- Source (entry point) → transformation/validation → sink (filesystem, DB, network, command execution).
- For each flow, note whether input is attacker-controlled, partially controlled, or trusted.
- Flag missing or weak validation points.

### `validation-model.md`

Document:

- How the target is tested (unit, integration, E2E, fuzzing).
- Whether a sandbox runtime is achievable.
- Recommended validation methods for each vulnerability class identified in `attack-surface.md`.
- Whether static-only or nested-virt validation models apply (requires explicit justification).

### `interesting-files.md`

List files that warrant deeper Phase 2 or sweep attention:

- Files containing authentication/authorization logic.
- Files with dangerous sink usage (exec, eval, SQL construction, file I/O, crypto).
- Files handling deserialization, parsing, or format conversion.
- Files at trust boundaries.
- Files with high CodeQL alert density (if CodeQL artifacts exist).
- Configuration files affecting security behavior.

### `file-risk-index.yml`

Create `itemdb/notes/file-risk-index.yml` using the schema in `templates/file-risk-index.yml`.

This is a structured, machine-readable companion to `interesting-files.md`. It is consumed by optional file-scoped Phase 2 sweeps.

Score files from 1 to 5 using the scoring scale in the template:

- `1`: low security interest,
- `2`: weak or indirect security relevance,
- `3`: moderate security interest,
- `4`: high security interest,
- `5`: very high security interest.

Prioritize files that contain or strongly influence:

- attacker-controlled or externally influenced input,
- trust-boundary crossings,
- authentication or authorization decisions,
- dangerous sinks,
- parsers and decoders,
- file upload or archive handling,
- cryptographic or secret-handling logic,
- privilege boundaries,
- tenant/account/resource isolation,
- network-facing protocol handlers,
- sandbox, policy, or permission enforcement.

For each high-risk file, include concrete reasons, likely entry points, sources, sinks, trust boundaries, suggested vulnerability classes, suggested skills, and suggested validation methods when inferable.

If CodeQL file signals exist (`itemdb/codeql/normalized/file-signals.yml`), incorporate them:
- Add `external_signals.codeql` blocks to file entries with CodeQL alerts.
- Boost scores where CodeQL reports high-precision alerts, but cap at 5.
- Explain every CodeQL-driven score boost in the `reasons` field.

Do not include every source file. Prefer a concise ranked set that Phase 2 can act on.

### `security-assumptions.md`

Document:

- Assumptions the codebase appears to make about its environment, inputs, and callers.
- Implicit trust relationships (e.g., "this internal API assumes the caller is already authorized").
- Cryptographic assumptions.
- Assumptions about input validation performed by upstream components.

## Additional reconnaissance

Recursively scan `src/` for high-signal documentation such as `README*`, `SECURITY*`, `THREAT_MODEL*`, `CONTRIBUTING*`, `docs/`, and similar. Also inspect `CHANGELOG*`, `HISTORY*`, and `NEWS*`, but prefer top-level or component-relevant files.

If the repository has dozens of changelog/history/news files, do not process them exhaustively. Summarize the pattern, prioritize files near the primary target or security-relevant components, and record that scope decision.

Review external public context for prior security advisories, CVE references, historical security fixes, release notes, and recurring bug classes affecting this project or closely related upstream components. Prefer project advisories, GitHub Security Advisories, NVD/CVE entries, issue trackers, release notes, and distribution advisories.

Use external context only as reconnaissance input: distill affected components, historical bug patterns, trust boundaries, and fixed attack surfaces into the notes. Do not treat external claims as proof that the current source tree is affected; verify everything against `src/` before creating findings.

Distill declared threat model, past CVEs, trust boundaries, and third-party components into the relevant notes; treat author claims as input to verify, not facts.

## User clarification behavior

### Interactive/chat mode

You may ask targeted questions when missing context materially affects:

- scope,
- deployment model,
- internet exposure,
- authn/authz assumptions,
- data sensitivity,
- multi-tenancy,
- risk ranking,
- validation strategy.

Questions must be few, specific, and useful.

### Non-interactive phase execution

Do not block waiting for answers unless the phase cannot proceed safely or meaningfully.

Instead:

- infer conservative assumptions,
- record assumptions in `itemdb/notes/security-assumptions.md`,
- record unresolved questions in `itemdb/notes/threat-model.md`,
- include unresolved questions in `runs/phase-1b-summary.md`,
- print unresolved questions in the final model summary,
- provide copy/paste re-run prompt hints for `PROMPT_EXTRA` or `PROMPT_EXTRA_FILE`.

## Important rules

- Do not assume the target is a web application.
- Do not assume the target can be built.
- Do not assume the target can be executed.
- Do not modify files under `src/`.
- Do not generate low-confidence vulnerability findings during reconnaissance.
- Do not rely only on filenames, comments, or labels.
- Be explicit about uncertainty.
- Prefer useful notes over exhaustive dumps.
- Focus on what later phases need.
- Do not let any target-specific skill narrow the target model before broad mapping is complete.
- Do not ask the user to choose Phase 2 scope when a reasonable default can be inferred. Pick the primary target from repository evidence, document secondary surfaces as optional follow-up, and continue.
- Do not phrase optional preferences as "User input requested". Use "Optional follow-up" unless Phase 1 is blocked.
- Reading `.env` files is allowed only in two places during reconnaissance: target inputs under `src/**` and CodeCome-generated sandbox metadata in `sandbox/.env`. Avoid unrelated `.env` files elsewhere in the workspace.

## Final response

At the end, summarize:

- Target type (from Phase 1a),
- Most important attack surfaces identified,
- Threat model summary,
- Highest-risk assets,
- Attacker capabilities and non-capabilities,
- Top abuse-path themes for Phase 2,
- Recommended Phase 2 focus,
- Highest-risk files from `file-risk-index.yml`,
- CodeQL signals incorporated (if any),
- Open questions for the user,
- Re-run prompt hints,
- Files created in this sub-stage,
- Key limitations and uncertainties.

## Run summary

Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-1b-summary.md
