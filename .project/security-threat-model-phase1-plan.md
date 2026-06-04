# Plan: integrate curated security-threat-model ideas into CodeCome Phase 1

## Status

WIP planning document only. This PR intentionally does not implement the changes yet.

Related follow-up issues:

- #33 Track reusable open questions and re-run hints across all phases
- #35 Use threat-model.md in Phase 4 validation planning
- #36 Use threat-model.md in Phase 5 exploitation planning
- #37 Use threat-model.md in Phase 6 reporting context

## Goal

Adapt the useful parts of OpenAI's curated `security-threat-model` skill into CodeCome's existing phased workflow without adding a parallel standalone `security-threat-model` skill.

The result should make Phase 1 produce a durable, repository-grounded operational threat model that later phases consume for better hypothesis generation, counter-analysis, validation, exploitation, and reporting.

This plan is intentionally implementation-oriented: it names the files to change, how gates/checkers should behave, how Phase 2/3 should consume the new artifact, and how to keep `CODEQL=0` source-only recon working.

Phase 4/5/6 consumption of `threat-model.md` is intentionally deferred to follow-up issues #35, #36, and #37.

## Core decisions

### 1. Do not add a standalone `security-threat-model` skill

Do not create:

```text
.opencode/skills/security-threat-model/
```

Instead, extend the existing source reconnaissance skill:

```text
.opencode/skills/source-recon/
```

Rationale:

- CodeCome already has a Phase 1 recon model.
- `source-recon` is already the canonical skill for target model extraction.
- A standalone threat-model skill could accidentally produce a customer-facing threat model report instead of CodeCome phase artifacts.
- The threat model should be part of CodeCome's artifact graph, not a separate deliverable.

### 2. Make `threat-model.md` required in Phase 1b

Create a new required Phase 1b artifact:

```text
itemdb/notes/threat-model.md
```

Template:

```text
templates/threat-model.md
```

This file is not merely a summary of the other Phase 1b files. It is the operational risk model that consolidates:

- scope and runtime/non-runtime separation,
- primary runtime system model,
- assets and security objectives,
- attacker capabilities,
- attacker non-capabilities,
- trust-boundary summary,
- existing controls,
- abuse-path themes for Phase 2,
- qualitative risk calibration for review focus,
- open questions for the user,
- re-run prompt hints.

Phase 2 and Phase 3 should not read only `threat-model.md`; they should still read the detailed recon artifacts. However, `threat-model.md` should become the first risk-oriented Phase 1b artifact those phases consult.

`threat-model.md` is additive. It does not supersede existing Phase 1b recon notes. All current Phase 1b artifacts remain required. If the model produces `threat-model.md` but misses `trust-boundaries.md`, `data-flow.md`, or any other required Phase 1b note, the Phase 1b gate must still block.

### 3. Phase 1b is required even when `CODEQL=0`

Phase 1b must not be considered optional. `CODEQL=0` only disables CodeQL enrichment.

The intended flow is:

```text
Phase 1a: Target profile + build model + CodeQL plan
CodeQL: optional analysis/enrichment
Phase 1b: Detailed source reconnaissance, always required
Phase 1c: Sandbox bootstrap
```

Therefore `threat-model.md` can be a strict Phase 1b gate requirement.

If any current behavior skips Phase 1b when `CODEQL=0`, that should be treated as a bug. Without Phase 1b, CodeCome would also miss `attack-surface.md`, `trust-boundaries.md`, `data-flow.md`, `file-risk-index.yml`, and other required recon outputs.

### 4. Rename Phase 1b away from CodeQL-specific naming

Current name/path:

```text
prompts/phase-1b-codeql-recon.md
label: CodeQL-assisted Reconnaissance
```

Proposed new name/path:

```text
prompts/phase-1b-recon.md
label: Detailed Reconnaissance
```

The prompt should describe CodeQL as optional enrichment:

```text
If CodeQL artifacts exist, incorporate them as reconnaissance evidence.
If they do not exist, proceed with source-only reconnaissance.
Phase 1b must complete regardless of CodeQL availability.
```

Update all references in:

- `tools/codecome/phase_1.py`,
- `tools/phases/phase_1_gates.py`,
- docs/workflow docs if present,
- tests that reference the old filename or label,
- README/help text if applicable.

Prefer removing the old file once no active code references it. If backward compatibility is desired, keep only a minimal compatibility note, but avoid maintaining two prompt bodies.

### 5. Split validation responsibilities cleanly

Introduce:

```bash
tools/codecome.py check-phase-artifacts --phase X
```

This should become the complete phase-artifact validator.

Implementation location:

```text
tools/phases/artifact_checks.py
```

`tools/codecome.py` should only register a thin CLI subcommand wrapper that delegates to `phases.artifact_checks.check_phase_artifacts()`. Per `tools/AGENTS.md`, do not add large validation logic directly to `tools/codecome.py`.

Keep:

```bash
tools/check-frontmatter.py
make frontmatter
```

but narrow its conceptual role to validating Markdown frontmatter for itemdb Markdown files. It should remain as a user convenience and compatibility wrapper, not the primary phase-artifact gate.

Update Makefile to call the new command where complete phase validation is intended.

## Validation model

### `tools/gate-check.py`

Purpose: pre-phase readiness gate.

Examples:

- Can Phase 2 start?
- Are prerequisite Phase 1 artifacts present?
- Is there a PENDING finding for Phase 4?

It should remain focused on whether a phase is allowed to start.

When checking Phase 2 readiness, it must require the new Phase 1b artifact:

```text
itemdb/notes/threat-model.md
```

Important: Phase 2 readiness currently uses `REQUIRED_NOTES` in `tools/phases/gates.py`, not `REQUIRED_NOTES_1B` in `tools/phases/phase_1_gates.py`. Both lists serve different call sites and both must be updated:

```text
tools/phases/phase_1_gates.py::REQUIRED_NOTES_1B
tools/phases/gates.py::REQUIRED_NOTES
```

If the file is missing, the Phase 2 gate should block with a clear message, for example:

```text
[BLOCK] Missing Phase 1b threat model: itemdb/notes/threat-model.md
Run: make phase-1
```

`tools/gate-check.py` may reuse shared artifact helpers, but it should not become the main post-generation quality checker.

### `tools/codecome.py check-phase-artifacts --phase X`

Purpose: post-generation artifact quality validation.

Examples:

- Did Phase 1b produce every required note?
- Does `threat-model.md` contain required headings?
- Does `file-risk-index.yml` pass schema validation?
- Do run summaries include required sections?
- Do finding frontmatters pass validation where relevant?

This command can be used by:

- phase gates after model runs,
- `make tests`,
- manual user checks,
- future CI.

Supported phases:

```bash
tools/codecome.py check-phase-artifacts --phase 1a
tools/codecome.py check-phase-artifacts --phase 1b
tools/codecome.py check-phase-artifacts --phase 1c
tools/codecome.py check-phase-artifacts --phase 1
tools/codecome.py check-phase-artifacts --phase 2
tools/codecome.py check-phase-artifacts --phase 3
tools/codecome.py check-phase-artifacts --phase 4
tools/codecome.py check-phase-artifacts --phase 5
tools/codecome.py check-phase-artifacts --phase 6
tools/codecome.py check-phase-artifacts --phase all
```

`--phase 1` runs checks for 1a, 1b, and 1c in sequence and fails on the first failure. It does not implicitly allow missing generated artifacts; all three sub-phases must have run for `--phase 1` to pass. If a subset is desired, use `--phase 1a`, `--phase 1b`, or `--phase 1c` individually.

`--phase all` runs every implemented phase artifact check in sequence and fails on the first failure. It does not implicitly allow missing generated artifacts.

The CLI implementation should be thin. Suggested shape:

```python
def command_check_phase_artifacts(args: argparse.Namespace) -> int:
    from phases.artifact_checks import check_phase_artifacts
    return check_phase_artifacts(
        phase=args.phase,
        allow_missing_generated=args.allow_missing_generated_artifacts,
    )
```

### `--allow-missing-generated-artifacts`

Define a test/development convenience flag:

```bash
tools/codecome.py check-phase-artifacts --phase all --allow-missing-generated-artifacts
```

When enabled, the checker should:

- validate static templates, schemas, prompt references, and any artifacts that exist,
- skip errors for phase-generated artifacts that are normally created only after a phase run,
- still fail on malformed generated artifacts if those files do exist,
- still fail on static configuration/template errors.

Artifact classification:

Generated artifacts, skipped if missing but validated if present:

- everything under `itemdb/`,
- everything under `runs/`,
- `sandbox/CODECOME-GENERATED.md`.

Static artifacts, always required and always validated:

- everything under `templates/`,
- everything under `.opencode/`,
- everything under `prompts/`,
- everything under `tools/`,
- `codecome.yml`,
- `AGENTS.md`,
- `Makefile`,
- `README.md`.

Rule: generated artifacts are files that only exist after a phase run. Static artifacts must be present in a clean checkout.

This makes it safe to call from `make tests` in a clean checkout.

Non-goal: this flag must not be used by normal post-phase gates after an actual phase run. After Phase 1b completes, missing `itemdb/notes/threat-model.md` must remain a hard failure.

### Heading validation rules

`threat-model.md` heading validation should be strict and deterministic:

- match H1 headings only,
- strip leading/trailing whitespace from each line before matching,
- require exact case-sensitive text,
- require exactly one space after `#`, for example `# Scope`,
- do not accept malformed variants such as `#Scope`,
- do not validate subsection count or subsection content in the heading checker.

If the model produces malformed headings, the Phase 1b artifact auto-repair loop should repair them.

### `tools/check-frontmatter.py`

Purpose: compatibility/user convenience wrapper for frontmatter-only checks.

It should not remain the place where unrelated phase-artifact checks accumulate.

Possible final behavior:

```text
tools/check-frontmatter.py
  -> validates Markdown frontmatter for itemdb finding/report/note files where frontmatter applies
  -> may internally call a shared validator module
```

### `file-risk-index.yml` validation ownership

The current in-process frontmatter validation also validates `file-risk-index.yml`. This should be untangled without duplicating validation logic.

Do not add a standalone JSON schema in this PR unless existing code is already close to that shape.

Recommended implementation:

1. Extract or expose the existing `validate_file_risk_index()` logic as a reusable validator if needed.
2. Keep current validation behavior stable.
3. Have both compatibility paths call the same validator:
   - `tools/check-frontmatter.py` while it still validates the risk index for backward compatibility,
   - `tools/codecome.py check-phase-artifacts --phase 1b` as the new canonical phase-artifact path.
4. In a later cleanup, decide whether `check-frontmatter.py` should stop validating `file-risk-index.yml` entirely.

Rule:

```text
There must be one source of truth for file-risk-index schema validation.
```

`templates/file-risk-index.yml` itself requires no structural changes for this integration. The existing file-centric schema is sufficient. New risk metadata such as attacker model, abuse-path themes, and risk calibration belongs in `threat-model.md`, not in the file risk index.

## Interactive/chat vs non-interactive behavior

Phase 1 should adopt this behavior now. The broader harness-level version is tracked in #33.

### Interactive/chat mode

The agent may ask targeted questions when missing context materially affects:

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

The agent must not block waiting for answers unless the phase cannot proceed safely or meaningfully.

Instead it must:

- infer conservative assumptions,
- record assumptions in `itemdb/notes/security-assumptions.md`,
- record unresolved questions in `itemdb/notes/threat-model.md`,
- include unresolved questions in `runs/phase-1*-summary.md`,
- print unresolved questions in the final model summary,
- provide copy/paste re-run prompt hints for `PROMPT_EXTRA` or `PROMPT_EXTRA_FILE`.

For now, do not implement centralized harness extraction/rendering of these questions. That belongs to #33.

## File changes

## A. Add source-recon references

Create:

```text
.opencode/skills/source-recon/references/threat-model-checklist.md
.opencode/skills/source-recon/references/security-controls-and-assets.md
```

### `threat-model-checklist.md`

Purpose: compact checklist adapted for CodeCome Phase 1b.

Add this comment at the top of the file:

```markdown
<!--
Some guidance in this reference was informed by OpenAI's curated
security-threat-model skill and adapted for CodeCome's phased workflow.
-->
```

Required content:

```markdown
# Threat Model Checklist for Source Recon

Use this reference during CodeCome Phase 1b.

The goal is not to produce a standalone threat-modeling report. The goal is to
produce a durable operational model that improves later hypothesis generation,
counter-analysis, validation, exploitation, and reporting.

## Grounding rules

- Do not invent components, data stores, endpoints, flows, controls, or deployment properties.
- Anchor important architectural and security claims to repository evidence.
- Mark missing context as assumptions.
- Separate runtime behavior from CI/build/dev/test behavior.
- Separate attacker-controlled, operator-controlled, developer-controlled, and trusted internal inputs.

## Required model elements

### System model

Identify primary runtime components, relevant data stores, external integrations,
entrypoints, build/release artifacts that materially affect security, deployment
assumptions, and out-of-scope components.

### Trust boundaries

For each important boundary, document source actor/component, destination
component, data/control crossing, channel/protocol, authentication,
authorization, encryption or transport protection, validation/normalization,
schema enforcement, rate/resource controls, evidence anchors, and uncertainty.

### Assets and security objectives

For each relevant asset, document asset name, where it appears, why it matters,
security objective (confidentiality, integrity, availability), related attack
surfaces or trust boundaries, and evidence anchors.

### Attacker model

Document realistic attacker capabilities and explicit non-capabilities.
Non-capabilities are required to avoid inflated severity.

### Existing controls

Document observed controls with evidence: what the control protects, where it is
enforced, what assumptions it relies on, and known uncertainty or gaps.

### Abuse-path themes

Record review leads, not findings. Each theme should include attacker goal,
entrypoint, boundary crossed, impacted asset, existing controls, assumptions,
relevant files, and suggested Phase 2 focus.

### Risk calibration

Use qualitative risk only to prioritize review focus. Consider exposure,
attacker control, affected asset, privilege boundary, tenant boundary, exploit
preconditions, existing controls, and validation feasibility.
```

### `security-controls-and-assets.md`

Purpose: lightweight checklist used only when applicable.

Include categories for:

- user data,
- authentication artifacts,
- authorization state,
- secrets and keys,
- configuration and feature flags,
- source/build artifacts,
- audit logs and telemetry,
- availability-critical resources,
- tenant isolation boundaries,
- integrity-critical state,
- privileged execution context,
- internal service reachability.

Include control categories for:

- identity/access,
- input protection,
- network safeguards,
- data protection,
- isolation,
- observability,
- supply chain,
- change control,
- resource controls.

Include concrete mitigation phrasing patterns, but warn agents not to copy generic controls blindly.

## B. Update `.opencode/skills/source-recon/SKILL.md`

Add references section:

```markdown
## References

When Phase 1b produces detailed reconnaissance notes, also use:

- `references/threat-model-checklist.md`
- `references/security-controls-and-assets.md`

Use these references to improve grounding, threat-model quality, assets,
controls, attacker assumptions, and Phase 2 review focus.

Do not copy checklist categories blindly. Only include repository-specific items
supported by evidence or explicitly marked assumptions.
```

Add `threat-model.md` to Phase 1b output expectations.

Add create-or-update semantics:

```markdown
If `itemdb/notes/threat-model.md` already exists, update it. Do not replace it wholesale. Preserve manually refined sections, evidence anchors, user-provided answers, and resolved open questions unless new repository evidence contradicts them.
```

Add sections:

- Evidence anchors,
- User clarification behavior,
- Threat model summary,
- Attacker model,
- Existing controls,
- Abuse-path themes.

Update completion checklist to require:

- `threat-model.md` exists after Phase 1b,
- `file-risk-index.yml` exists after Phase 1b,
- architectural claims have evidence anchors,
- runtime behavior is separated from CI/build/dev/test behavior,
- attacker-controlled inputs are distinguished from operator/developer inputs,
- high-priority trust boundaries include source, destination, data/control, channel, controls, and evidence,
- assets include why they matter and C/I/A objectives,
- attacker capabilities and non-capabilities are explicit,
- existing controls are documented with evidence,
- unresolved user-context questions are present in the run summary,
- Phase 2 focus follows from assets, boundaries, entrypoints, controls, and sinks.

## C. Add `templates/threat-model.md`

Create:

```text
templates/threat-model.md
```

Avoid dense 5-7 column tables for qualitative content. Use structured subsections and nested bullets instead, because wide tables are fragile for LLM generation and tend to truncate useful reasoning.

Required template shape:

```markdown
# Threat Model Summary

Date: YYYY-MM-DD  
Phase: 1b - Detailed Reconnaissance  
Target path: `./src`

# Scope

## In scope

## Out of scope

## Runtime vs non-runtime separation

# System model

## Primary runtime components

## Data stores

## External integrations

## Entrypoints

# Assets and security objectives

## Asset: <name>

- Where observed:
- Why it matters:
- Security objective:
  - Confidentiality:
  - Integrity:
  - Availability:
- Related attack surfaces:
- Evidence:

# Attacker model

## Capabilities

## Non-capabilities

# Trust boundary summary

## Boundary: <source> -> <destination>

- Data/control crossing:
- Channel/protocol:
- Authentication:
- Authorization:
- Encryption / transport protection:
- Validation / normalization / schema enforcement:
- Rate/resource controls:
- Existing controls:
- Evidence:
- Uncertainty:

# Existing controls

## Control: <name>

- Location:
- Protects:
- Evidence:
- Gaps / uncertainty:

# Abuse-path themes for Phase 2

These are review leads, not findings.

## Theme: <short name>

- Attacker goal:
- Entrypoint:
- Boundary crossed:
- Asset affected:
- Existing controls:
- Key assumptions:
- Relevant files:
- Suggested Phase 2 focus:
- Why this is not yet a finding:

# Risk calibration for review focus

## High-priority review themes

## Medium-priority review themes

## Low-priority / deferred themes

# Open questions for the user

## Question: <short question>

- Why it matters:
- Affects:
- Suggested answer format:

# Re-run prompt hints
```

Mermaid diagrams are intentionally not required in this first integration.

Artifact validation should require headings, not exact subsection count. Required headings:

- `# Threat Model Summary`,
- `# Scope`,
- `# System model`,
- `# Assets and security objectives`,
- `# Attacker model`,
- `# Trust boundary summary`,
- `# Existing controls`,
- `# Abuse-path themes for Phase 2`,
- `# Risk calibration for review focus`,
- `# Open questions for the user`,
- `# Re-run prompt hints`.

### Re-run and relationship to other Phase 1b artifacts

When `itemdb/notes/threat-model.md` already exists on a Phase 1b re-run, the agent should update it rather than regenerate it from scratch. Preserve manually curated sections, refined evidence anchors, and user-provided answers to open questions.

`threat-model.md` does not replace existing Phase 1b artifacts. All required Phase 1b notes remain required and independently validated.

## D. Update `templates/target-recon.md`

Add/extend:

- attack-surface input control classification,
- reachable assets,
- existing controls,
- assumptions,
- detailed trust-boundary fields,
- assets/security objectives table or structured asset sections,
- explicit references to `threat-model.md` in recommended audit focus.

## E. Update `templates/run-summary.md`

Add sections after `# Assumptions` using structured subsections, not a qualitative wide table:

```markdown
# Open questions for the user

List questions that would materially improve a later re-run.

## Question: <short question>

- Why it matters:
- Affects:
- Suggested answer format:

# Re-run prompt hints

If useful, provide a short copy/paste prompt that the user can pass into a
future re-run with the missing context.

If there are no useful hints, write:

None.
```

This template change is general, but this PR should only enforce it for Phase 1 summaries. Full harness rendering is tracked in #33.

## F. Rename and update Phase 1b prompt

Rename:

```text
prompts/phase-1b-codeql-recon.md
```

To:

```text
prompts/phase-1b-recon.md
```

Update `tools/codecome/phase_1.py`:

```python
# ---- Phase 1b: Detailed Reconnaissance ----
phase_id="1b"
label="Detailed Reconnaissance"
prompt_file="prompts/phase-1b-recon.md"
```

Update `tools/phases/phase_1_gates.py` labels:

```python
_emit(console, "ok", "Ready to run Phase 1b (Detailed Reconnaissance).")
_emit(console, "header", "Gate 1b: Detailed Reconnaissance")
```

Update prompt title:

```markdown
# CodeCome Phase 1b: Detailed Reconnaissance
```

Replace CodeQL-centric wording with:

```text
Phase 1b produces detailed reconnaissance notes. If CodeQL artifacts are
available, use them as optional enrichment. If they are absent or CodeQL was
disabled, continue with source-only reconnaissance.
```

Add required reading:

```text
- `templates/threat-model.md`
- `.opencode/skills/source-recon/references/threat-model-checklist.md`
- `.opencode/skills/source-recon/references/security-controls-and-assets.md`
```

Add required output:

```text
- `threat-model.md`
```

Add a section for `threat-model.md` explaining the required contents.

Add interactive/non-interactive user-context behavior.

Update final response requirements to include:

- threat model summary,
- highest-risk assets,
- attacker capabilities/non-capabilities,
- top abuse-path themes,
- open questions for the user,
- re-run prompt hints,
- files created.

### Disposition of `prompts/phase-1-recon.md`

`prompts/phase-1-recon.md` is the pre-split monolithic Phase 1 prompt. It is not consumed by the Phase 1 runner, which uses the 1a/1b/1c prompts instead.

Delete it as part of this integration and update active references in:

- `README.md`,
- `docs/workflow.md`,
- `docs/target-setup.md`,
- `docs/development.md`,
- `prompts/README.md`.

Update `prompts/README.md` explicitly:

- remove `phase-1-recon.md` from the prompt inventory,
- replace manual Phase 1 invocation examples with subphase examples or a reference to `make phase-1`,
- ensure the Phase 1b prompt is listed as `phase-1b-recon.md`.

Leave `.project/` references alone because they are historical planning records.

## G. Update Phase 1a prompt

Update `prompts/phase-1a-profile.md` to clarify:

- Phase 1a does not produce `threat-model.md`.
- Phase 1a does not produce attack-surface/trust-boundary/data-flow notes.
- Phase 1a does not bootstrap sandbox.
- Non-blocking open questions should go into `runs/phase-1a-summary.md`.

## H. Update Phase 1c prompt

Update `prompts/phase-1c-sandbox.md` required reading to include:

```text
- `itemdb/notes/threat-model.md`
- `itemdb/notes/execution-model.md`
- `itemdb/notes/validation-model.md`
```

Reason: sandbox fidelity should be informed by threat model, execution model, and validation needs.

Add rule:

```text
If sandbox bootstrap depends on missing user context, do not ask in non-interactive mode unless bootstrap is blocked. Record the question in `sandbox-plan.md` and `runs/phase-1c-summary.md`. If bootstrap is blocked, use the halt protocol.
```

## I. Update Phase 2 prompt

Update:

```text
prompts/phase-2-audit.md
```

Current Phase 2 already reads all relevant files under `itemdb/notes/`, but `threat-model.md` should be explicit because it becomes the primary risk-oriented Phase 1b handoff.

Add to Required reading:

```markdown
- `itemdb/notes/threat-model.md` — operational threat model from Phase 1b: assets, attacker model, trust-boundary summary, existing controls, abuse-path themes, risk calibration, and open assumptions.
```

Add guidance near the `file-risk-index.yml` paragraph:

```markdown
Use `itemdb/notes/threat-model.md` to prioritize hypotheses around assets, attacker capabilities, explicit non-capabilities, existing controls, and abuse-path themes. Do not convert an abuse-path theme into a finding unless you identify a concrete, repository-backed vulnerable path with attacker control, trust-boundary crossing, security-relevant impact, and an actionable validation plan.
```

Update final response requirements to mention:

- threat-model themes consumed,
- assumptions from `threat-model.md` that materially influenced hypotheses,
- abuse-path themes not converted into findings and why.

## J. Update Phase 3 prompt

Update:

```text
prompts/phase-3-review.md
```

Current Phase 3 also reads all relevant files under `itemdb/notes/`, but it should explicitly use the threat model for counter-analysis.

Add to Required reading:

```markdown
- `itemdb/notes/threat-model.md` — operational threat model from Phase 1b: assets, attacker model, trust-boundary summary, existing controls, abuse-path themes, risk calibration, and open assumptions.
```

Add review questions:

```markdown
- Does the finding align with the attacker capabilities and non-capabilities documented in `threat-model.md`?
- Does the claimed impact map to an asset and security objective from `threat-model.md`?
- Do existing controls documented in `threat-model.md` weaken, block, or narrow the finding?
- Is the finding based on an abuse-path theme from Phase 1b, and if so, has it been grounded into a concrete vulnerable path?
```

Update final response requirements to mention:

- threat-model assumptions that affected counter-analysis,
- findings weakened or rejected due to attacker non-capabilities or existing controls,
- findings kept because they cross a documented trust boundary or affect a documented asset.

## K. Phase artifact checks

Implement the validator in:

```text
tools/phases/artifact_checks.py
```

Expose it through a thin wrapper command:

```bash
tools/codecome.py check-phase-artifacts --phase 1b
```

Update `tools/codecome.py::REQUIRED_PATHS` to include:

```text
templates/threat-model.md
```

### Phase 1a artifact checks

Required files:

- `itemdb/notes/target-profile.md`,
- `itemdb/notes/build-model.md`,
- `itemdb/notes/codeql-plan.yml`,
- `runs/phase-1a-summary.md`.

Required summary headings:

- `# Open questions for the user`,
- `# Re-run prompt hints`.

Negative checks:

- Phase 1a should not create or modify `itemdb/notes/threat-model.md`.
- Phase 1a should not create or modify `itemdb/notes/sandbox-plan.md`.

These negative checks must be based on mtime or a pre-run snapshot, not mere existence. If `threat-model.md` already exists from a previous Phase 1b run, Phase 1a must not fail unless the file was created or modified after the Phase 1a run started.

### Phase 1b artifact checks

Required files:

- `itemdb/notes/attack-surface.md`,
- `itemdb/notes/execution-model.md`,
- `itemdb/notes/trust-boundaries.md`,
- `itemdb/notes/data-flow.md`,
- `itemdb/notes/threat-model.md`,
- `itemdb/notes/validation-model.md`,
- `itemdb/notes/interesting-files.md`,
- `itemdb/notes/file-risk-index.yml`,
- `itemdb/notes/security-assumptions.md`,
- `runs/phase-1b-summary.md`.

`threat-model.md` required headings:

- `# Threat Model Summary`,
- `# Scope`,
- `# System model`,
- `# Assets and security objectives`,
- `# Attacker model`,
- `# Trust boundary summary`,
- `# Existing controls`,
- `# Abuse-path themes for Phase 2`,
- `# Risk calibration for review focus`,
- `# Open questions for the user`,
- `# Re-run prompt hints`.

Required summary headings:

- `# Open questions for the user`,
- `# Re-run prompt hints`.

Also run `file-risk-index.yml` validation through the shared validator.

### Phase 1c artifact checks

Required files:

- `itemdb/notes/sandbox-plan.md`,
- `runs/phase-1c-summary.md`.

Required summary headings:

- `# Open questions for the user`,
- `# Re-run prompt hints`.

Keep existing sandbox gate behavior.

### Phase 2-6 artifact checks

Implement checks for all phases where current artifacts are already well-defined. Keep them compatible with existing workflows and avoid introducing new threat-model requirements beyond Phase 2/3 in this PR.

Phase 4/5/6 integration with `threat-model.md` is deferred to #35, #36, and #37.

## L. Update existing gates, completion helpers, and auto-repair

Update `check_phase_1b` to require `threat-model.md` and validate minimum headings via the shared validator from `tools/phases/artifact_checks.py`. Avoid duplicating heading-check logic in multiple places.

Specific Phase 1b gate changes:

- `tools/phases/phase_1_gates.py::REQUIRED_NOTES_1B`: add `"threat-model.md"`.
- `tools/phases/phase_1_gates.py`: change the ready label to `"Ready to run Phase 1b (Detailed Reconnaissance)."`.
- `tools/phases/phase_1_gates.py`: change the gate header to `"Gate 1b: Detailed Reconnaissance"`.

Update Phase 2 readiness in `tools/phases/gates.py`:

- `tools/phases/gates.py::REQUIRED_NOTES`: add `"threat-model.md"`. This is the list actually consumed by `gate_phase_2()`.

Update `tools/phases/completion.py`:

- `_PHASE1_REQUIRED_ARTIFACT_NAMES`: add `"threat-model.md"`.
- `phase_checklist_lines()` for Phase 1: add a checklist line requiring `itemdb/notes/threat-model.md` with all required headings.
- Add `build_artifact_repair_resume_prompt(phase: str, finding: str | None, validation_output: str) -> str`.

`build_artifact_repair_resume_prompt()` should:

- include the validation output from `check_phase_1b_artifacts()`,
- instruct the model to repair only missing or malformed Phase 1b artifacts,
- include the Phase 1 completion checklist from `phase_checklist_lines()`,
- explicitly tell the model not to rewrite unrelated files.

Update `check_phase_1a` and `check_phase_1c` only as needed to enforce summary sections and prevent phase leakage.

Add a Phase 1b artifact auto-repair loop in `tools/codecome/phase_1.py::_run_subphase()`.

Validation sequence inside the existing retry loop should be:

1. CodeQL plan validation.
   - On failure with retries remaining: resume with `build_codeql_plan_resume_prompt()` and `continue`.
   - On exhausted retries: set `returncode = 2` and `break`.
2. Frontmatter validation.
   - On failure with retries remaining: resume with `build_frontmatter_resume_prompt()` and `continue`.
   - On exhausted retries: set `returncode = 2` and `break`.
3. Phase 1b artifact validation.
   - Run only when `phase_id == "1b"`.
   - Call `check_phase_1b_artifacts()` from `tools/phases/artifact_checks.py`.
   - On failure with retries remaining: resume with `build_artifact_repair_resume_prompt()` and `continue`.
   - On exhausted retries: set `returncode = 2`, emit validation output, and `break`.
4. All validations passed: `break`.

The artifact repair prompt should ask the model to repair only missing or malformed Phase 1b artifacts and avoid rewriting unrelated files.

This keeps `threat-model.md` validation consistent with the existing harness behavior for CodeQL plan validation and frontmatter validation.

`tools/gate-check.py` should remain pre-phase readiness. It may call shared artifact validators when checking prerequisites for the next phase, but it should not become the main post-run artifact checker.

## M. Makefile updates

Update Makefile so complete validation uses the new command.

Current:

```make
frontmatter: env-check
	$(PYTHON) tools/check-frontmatter.py

tests: env-check
	$(PYTHON) -m pytest -q tests
	$(PYTHON) tools/check-frontmatter.py
```

Proposed:

```make
frontmatter: env-check
	$(PYTHON) tools/check-frontmatter.py

check-phase-artifacts: env-check
	$(PYTHON) tools/codecome.py check-phase-artifacts --phase $(or $(PHASE),all)

tests: env-check
	$(PYTHON) -m pytest -q tests
	$(PYTHON) tools/check-frontmatter.py
	$(PYTHON) tools/codecome.py check-phase-artifacts --phase all --allow-missing-generated-artifacts
```

Important: `tools/check-frontmatter.py` remains available but should no longer be the full artifact gate.

## N. Tests

Add tests:

```text
tests/test_phase_1_threat_model_templates.py
tests/test_phase_1_prompts_threat_model.py
tests/test_phase_1_gates_threat_model.py
tests/test_phase_artifacts_cli.py
tests/test_phase_completion_threat_model.py
```

### Template tests

Assert:

- `templates/threat-model.md` exists.
- `templates/threat-model.md` has all required headings.
- `templates/threat-model.md` uses structured subsection markers such as:
  - `## Boundary: <source> -> <destination>`
  - `## Theme: <short name>`
  - `## Question: <short question>`
- `templates/run-summary.md` has `# Open questions for the user` and `# Re-run prompt hints`.
- `templates/run-summary.md` uses structured open-question subsections, not a qualitative wide table.
- `templates/target-recon.md` mentions attacker model, existing controls, and assets/security objectives.

### Prompt tests

Assert:

- `prompts/phase-1b-recon.md` exists.
- old `prompts/phase-1b-codeql-recon.md` is not referenced by active code.
- `prompts/phase-1-recon.md` is removed and active documentation references subphase prompts instead.
- `prompts/README.md` no longer references the deleted monolithic Phase 1 prompt and uses the renamed Phase 1b prompt.
- `tools/codecome/phase_1.py` uses `prompts/phase-1b-recon.md`.
- Phase 1b prompt says CodeQL artifacts are optional enrichment.
- Phase 1b prompt requires `threat-model.md`.
- Phase 1b prompt references source-recon threat-model references.
- Phase 1b prompt mentions attacker capabilities, non-capabilities, existing controls, abuse-path themes, open questions, and re-run prompt hints.
- Phase 1a prompt explicitly does not produce `threat-model.md`.
- Phase 1c prompt reads `threat-model.md`.
- `prompts/phase-2-audit.md` explicitly references `itemdb/notes/threat-model.md`.
- `prompts/phase-2-audit.md` says abuse-path themes are leads, not findings.
- `prompts/phase-3-review.md` explicitly references `itemdb/notes/threat-model.md`.
- `prompts/phase-3-review.md` uses attacker capabilities, non-capabilities, existing controls, and assets/security objectives during counter-analysis.

### Gate/artifact tests

Assert:

- Phase 1b artifact checker fails when `threat-model.md` is missing.
- Phase 1b artifact checker fails when `threat-model.md` lacks required headings.
- Phase 1b artifact checker passes with minimal valid threat model plus other required artifacts.
- Phase 1b artifact checker still fails when `threat-model.md` exists but another required Phase 1b recon note is missing.
- Phase 1b artifact checker requires run-summary open questions/re-run hint sections.
- Phase 1a negative checks do not fail on pre-existing `threat-model.md`; they fail only if Phase 1a creates or modifies it.
- Phase 2 readiness gate fails when `itemdb/notes/threat-model.md` is missing.
- Phase 2 readiness gate passes the threat-model prerequisite when the file exists.
- Phase 2 gate output names the missing file and tells the user to re-run Phase 1.
- Phase 1b gate labels say `Detailed Reconnaissance`, not `CodeQL-assisted Reconnaissance`.
- `tools/codecome.py::REQUIRED_PATHS` includes `templates/threat-model.md`.
- `check-frontmatter.py` remains callable.

### Completion/auto-resume tests

Assert:

- `completion.py::_PHASE1_REQUIRED_ARTIFACT_NAMES` includes `threat-model.md`.
- `completion.py::phase_checklist_lines("1")` mentions `threat-model.md`.
- `build_artifact_repair_resume_prompt()` includes validation output and the Phase 1 checklist.
- Phase 1b invokes artifact validation after CodeQL plan and frontmatter validation pass.
- Phase 1b retries when `threat-model.md` is missing required headings.
- Phase 1b repair prompt asks for minimal repair and avoids unrelated rewrites.
- Phase 1b stops after the configured max artifact repair attempts.

### `--allow-missing-generated-artifacts` tests

Assert:

- clean checkout / missing generated artifacts passes with `--allow-missing-generated-artifacts`,
- malformed existing `threat-model.md` still fails even with `--allow-missing-generated-artifacts`,
- missing required Phase 1b artifacts fail without the flag,
- `--phase 1` runs 1a/1b/1c checks in sequence,
- `--phase all` runs all implemented phase checks.

### `file-risk-index.yml` validation tests

Assert:

- existing valid `file-risk-index.yml` fixtures still pass,
- malformed `file-risk-index.yml` fails through `check-phase-artifacts --phase 1b`,
- existing `tools/check-frontmatter.py` compatibility path still reports risk-index errors until deliberately changed.

## O. Documentation updates

Update docs as needed:

- `docs/workflow.md` for Phase 1a/1b/1c naming,
- any docs mentioning `Phase 1b: CodeQL-assisted Reconnaissance`,
- docs that still reference `prompts/phase-1-recon.md`,
- any docs describing `make frontmatter`, `make tests`, or phase validation.

Specific `AGENTS.md` changes:

1. Phase 1 artifact list: add:
   - `itemdb/notes/threat-model.md`,
   - `itemdb/notes/file-risk-index.yml`,
   - `itemdb/notes/sandbox-plan.md`.
2. Phase 2 readiness: add:
   - `itemdb/notes/threat-model.md` must exist.

Specific `prompts/README.md` changes:

- remove `phase-1-recon.md` from the prompt inventory,
- replace monolithic manual Phase 1 invocation examples with subphase examples or a reference to `make phase-1`,
- update references from `phase-1b-codeql-recon.md` to `phase-1b-recon.md`.

## P. Deferred Phase 4/5/6 threat-model consumption

This PR intentionally wires `threat-model.md` into Phase 2 and Phase 3 only.

Deferred follow-ups:

- #35: Phase 4 validation planning should use `threat-model.md`.
- #36: Phase 5 exploitation planning should use `threat-model.md`.
- #37: Phase 6 reporting context should use `threat-model.md`.

Do not expand this PR to implement Phase 4/5/6 threat-model consumption.

## Implementation order

Several work streams can be implemented in parallel, but shared validators should land before gates consume them.

Recommended order:

1. Add `tools/phases/artifact_checks.py` and define shared Phase 1 artifact validation, including `threat-model.md` headings and `file-risk-index.yml` validation reuse.
2. Update `tools/phases/completion.py` with `threat-model.md` required artifacts, Phase 1 checklist changes, and `build_artifact_repair_resume_prompt()`.
3. Rename Phase 1b prompt and update references.
4. Delete `prompts/phase-1-recon.md` and update active docs that reference it.
5. Add `templates/threat-model.md` using structured subsections, not wide tables.
6. Add source-recon reference files.
7. Update `source-recon/SKILL.md`.
8. Update Phase 1a/1b/1c prompts.
9. Update Phase 2 and Phase 3 prompts to explicitly consume `threat-model.md`.
10. Update `templates/target-recon.md` and `templates/run-summary.md`.
11. Add the thin `tools/codecome.py check-phase-artifacts` wrapper and define `--allow-missing-generated-artifacts`.
12. Update `tools/codecome.py::REQUIRED_PATHS` with `templates/threat-model.md`.
13. Update `check_phase_1b` gate to call the shared validator rather than duplicating heading-check logic.
14. Add the Phase 1b artifact auto-repair loop in `tools/codecome/phase_1.py`.
15. Update Phase 2 readiness in `tools/phases/gates.py` to require `threat-model.md`.
16. Update `AGENTS.md`.
17. Update Makefile target(s).
18. Add tests.
19. Update docs.

## Acceptance criteria

- `make tests` passes.
- Phase 1b no longer appears to be CodeQL-only.
- `CODEQL=0 make phase-1` still runs Phase 1b as source-only detailed recon.
- Phase 1b requires `itemdb/notes/threat-model.md`.
- `completion.py::_PHASE1_REQUIRED_ARTIFACT_NAMES` includes `threat-model.md`.
- `completion.py::phase_checklist_lines("1")` mentions `threat-model.md`.
- `build_artifact_repair_resume_prompt()` exists and is used by the Phase 1b artifact repair loop.
- `threat-model.md` has required strict H1 headings and is validated by shared gates/checkers.
- Phase 1b auto-repairs malformed `threat-model.md` headings up to the configured retry limit.
- `templates/threat-model.md` avoids wide 6-7 column tables for qualitative content.
- `templates/run-summary.md` uses structured open-question subsections.
- Phase 1 summaries include open questions and re-run prompt hints.
- `prompts/phase-1-recon.md` is removed and active docs point to subphase prompts.
- `prompts/README.md` reflects the Phase 1b rename and monolithic Phase 1 prompt deletion.
- `AGENTS.md` lists `threat-model.md`, `file-risk-index.yml`, and `sandbox-plan.md` as Phase 1 artifacts.
- `AGENTS.md` Phase 2 readiness requires `threat-model.md`.
- `prompts/phase-2-audit.md` explicitly reads and uses `itemdb/notes/threat-model.md`.
- `prompts/phase-3-review.md` explicitly reads and uses `itemdb/notes/threat-model.md`.
- Phase 2 readiness blocks if `itemdb/notes/threat-model.md` is missing.
- `tools/codecome.py check-phase-artifacts --phase 1b` exists as a thin wrapper.
- Artifact validation implementation lives under `tools/phases/artifact_checks.py`.
- `tools/codecome.py::REQUIRED_PATHS` includes `templates/threat-model.md`.
- `--allow-missing-generated-artifacts` is defined and tested.
- `--phase 1` and `--phase all` behavior is defined and tested.
- `file-risk-index.yml` validation has one reusable source of truth.
- `templates/file-risk-index.yml` requires no structural threat-model changes in this integration.
- `tools/check-frontmatter.py` remains available.
- `make frontmatter` still works.
- Makefile complete validation path uses the new phase artifact checker where appropriate.
- Phase 4/5/6 threat-model consumption is tracked by issues #35, #36, and #37.
- Future harness-level open-question rendering is tracked by issue #33.
