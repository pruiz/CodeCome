# Plan: integrate curated security-threat-model ideas into CodeCome Phase 1

## Status

WIP planning document only. This PR intentionally does not implement the changes yet.

Related follow-up issue:

- #33 Track reusable open questions and re-run hints across all phases

## Goal

Adapt the useful parts of OpenAI's curated `security-threat-model` skill into CodeCome's existing Phase 1 workflow without adding a parallel `security-threat-model` skill.

The result should make Phase 1 produce a durable, repo-grounded operational threat model that later phases can consume for better hypothesis generation, counter-analysis, validation, exploitation, and reporting.

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
- A standalone threat-model skill could accidentally produce a customer-facing threat model report instead of CodeCome's phase artifacts.
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

This is not merely a summary of the other Phase 1b files. It is the operational risk model that consolidates:

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

Phase 2 should not read only `threat-model.md`; it should still read the detailed recon artifacts. However, `threat-model.md` should be the first risk-oriented Phase 1b artifact Phase 2 consults.

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

- `tools/codecome/phase_1.py`
- docs/workflow docs if present,
- tests that reference the old filename or label,
- any README/help text if applicable.

Keep the old prompt file only if backward compatibility is needed. Prefer removing it or replacing it with a short redirect comment only if no code references remain.

### 5. Split validation responsibilities cleanly

Introduce:

```bash
tools/codecome.py check-phase-artifacts --phase X
```

This should become the complete phase-artifact validator.

Keep:

```bash
tools/check-frontmatter.py
make frontmatter
```

But narrow its conceptual role to validating Markdown frontmatter for itemdb Markdown files. It should remain as a user convenience and compatibility wrapper, not the primary phase gate.

Update Makefile to call the new command where complete phase validation is intended.

## Current validation relationship target

### `tools/gate-check.py`

Purpose: pre-phase readiness gate.

Examples:

- Can Phase 2 start?
- Are prerequisite Phase 1 artifacts present?
- Is there a PENDING finding for Phase 4?

It should remain focused on whether a phase is allowed to start.

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

### `tools/check-frontmatter.py`

Purpose: compatibility/user convenience wrapper for frontmatter-only checks.

It should not remain the place where unrelated phase-artifact checks accumulate.

Possible final behavior:

```text
tools/check-frontmatter.py
  -> validates Markdown frontmatter for itemdb finding/report/note files where frontmatter applies
  -> may internally call a shared validator module
```

### Existing in-process validation

`run_frontmatter_validation()` currently validates finding frontmatter and `file-risk-index.yml`. This should be untangled over time:

- finding frontmatter validation stays in findings validators,
- `file-risk-index.yml` moves under phase artifact validation,
- `check-phase-artifacts --phase 1b` calls both as needed.

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

Add sections:

- Evidence anchors
- User clarification behavior
- Threat model summary
- Attacker model
- Existing controls
- Abuse-path themes

Update completion checklist to require:

- `threat-model.md` exists after Phase 1b,
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

Required headings:

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

| Asset | Where observed | Why it matters | Objective (C/I/A) | Evidence |
|---|---|---|---|---|

# Attacker model

## Capabilities

## Non-capabilities

# Trust boundary summary

| Boundary | Data/control crossing | Channel/protocol | Existing controls | Evidence | Uncertainty |
|---|---|---|---|---|---|

# Existing controls

| Control | Location | Protects | Evidence | Gaps/uncertainty |
|---|---|---|---|---|

# Abuse-path themes for Phase 2

These are review leads, not findings.

| Theme | Attacker goal | Entrypoint | Boundary | Asset | Existing controls | Suggested Phase 2 focus |
|---|---|---|---|---|---|---|

# Risk calibration for review focus

## High-priority review themes

## Medium-priority review themes

## Low-priority / deferred themes

# Open questions for the user

| Question | Why it matters | Affects | Suggested answer format |
|---|---|---|---|

# Re-run prompt hints
```

Mermaid diagrams are intentionally not required in this first integration.

## D. Update `templates/target-recon.md`

Add/extend:

- attack-surface input control classification,
- reachable assets,
- existing controls,
- assumptions,
- detailed trust-boundary fields,
- assets/security objectives table,
- explicit references to `threat-model.md` in recommended audit focus.

## E. Update `templates/run-summary.md`

Add sections after `# Assumptions`:

```markdown
# Open questions for the user

List questions that would materially improve a later re-run.

| Question | Why it matters | Affects | Suggested answer format |
|---|---|---|---|
| - | None. | - | - |

# Re-run prompt hints

If useful, provide a short copy/paste prompt that the user can pass into a
future re-run with the missing context.

If there are no useful hints, write:

None.
```

This template change is general, but this PR should only enforce it for Phase 1 summaries. Full harness rendering is tracked in #33.

## F. Rename Phase 1b prompt

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
phase_id="1b"
label="Detailed Reconnaissance"
prompt_file="prompts/phase-1b-recon.md"
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

Add section for `threat-model.md` explaining the required contents.

Add interactive/non-interactive user-context behavior.

Update final response requirements to include:

- threat model summary,
- highest-risk assets,
- attacker capabilities/non-capabilities,
- top abuse-path themes,
- open questions for the user,
- re-run prompt hints,
- files created.

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

## I. Validation command and gates

Add command:

```bash
tools/codecome.py check-phase-artifacts --phase 1b
```

Eventually support:

```bash
tools/codecome.py check-phase-artifacts --phase 1a
tools/codecome.py check-phase-artifacts --phase 1b
tools/codecome.py check-phase-artifacts --phase 1c
tools/codecome.py check-phase-artifacts --phase 1
tools/codecome.py check-phase-artifacts --phase all
```

### Phase 1a artifact checks

Required files:

- `itemdb/notes/target-profile.md`
- `itemdb/notes/build-model.md`
- `itemdb/notes/codeql-plan.yml`
- `runs/phase-1a-summary.md`

Required summary headings:

- `# Open questions for the user`
- `# Re-run prompt hints`

Negative checks:

- Phase 1a should not produce `itemdb/notes/threat-model.md`.
- Phase 1a should not produce `itemdb/notes/sandbox-plan.md`.

### Phase 1b artifact checks

Required files:

- `itemdb/notes/attack-surface.md`
- `itemdb/notes/execution-model.md`
- `itemdb/notes/trust-boundaries.md`
- `itemdb/notes/data-flow.md`
- `itemdb/notes/threat-model.md`
- `itemdb/notes/validation-model.md`
- `itemdb/notes/interesting-files.md`
- `itemdb/notes/file-risk-index.yml`
- `itemdb/notes/security-assumptions.md`
- `runs/phase-1b-summary.md`

`threat-model.md` required headings:

- `# Threat Model Summary`
- `# Scope`
- `# System model`
- `# Assets and security objectives`
- `# Attacker model`
- `# Trust boundary summary`
- `# Existing controls`
- `# Abuse-path themes for Phase 2`
- `# Risk calibration for review focus`
- `# Open questions for the user`
- `# Re-run prompt hints`

Required summary headings:

- `# Open questions for the user`
- `# Re-run prompt hints`

Also run file-risk-index schema validation.

### Phase 1c artifact checks

Required files:

- `itemdb/notes/sandbox-plan.md`
- `runs/phase-1c-summary.md`

Required summary headings:

- `# Open questions for the user`
- `# Re-run prompt hints`

Keep existing sandbox gate behavior.

## J. Update existing gates

Update `check_phase_1b` to require `threat-model.md` and validate minimum headings.

Update `check_phase_1a` and `check_phase_1c` only as needed to enforce summary sections and prevent phase leakage.

`tools/gate-check.py` should remain pre-phase readiness. It may call shared artifact validators when checking prerequisites for the next phase, but it should not become the main post-run artifact checker.

## K. Makefile updates

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
	$(PYTHON) tools/codecome.py check-phase-artifacts --phase all --allow-missing-runtime-artifacts
```

Exact flags can be adjusted during implementation.

Important: `tools/check-frontmatter.py` remains available but should no longer be the full artifact gate.

## L. Tests

Add tests:

```text
tests/test_phase_1_threat_model_templates.py
tests/test_phase_1_prompts_threat_model.py
tests/test_phase_1_gates_threat_model.py
tests/test_phase_artifacts_cli.py
```

### Template tests

Assert:

- `templates/threat-model.md` exists.
- `templates/threat-model.md` has all required headings.
- `templates/run-summary.md` has `# Open questions for the user` and `# Re-run prompt hints`.
- `templates/target-recon.md` mentions attacker model, existing controls, and assets/security objectives.

### Prompt tests

Assert:

- `prompts/phase-1b-recon.md` exists.
- old `prompts/phase-1b-codeql-recon.md` is not referenced by active code.
- `tools/codecome/phase_1.py` uses `prompts/phase-1b-recon.md`.
- Phase 1b prompt says CodeQL artifacts are optional enrichment.
- Phase 1b prompt requires `threat-model.md`.
- Phase 1b prompt references source-recon threat-model references.
- Phase 1b prompt mentions attacker capabilities, non-capabilities, existing controls, abuse-path themes, open questions, and re-run prompt hints.
- Phase 1a prompt explicitly does not produce `threat-model.md`.
- Phase 1c prompt reads `threat-model.md`.

### Gate/artifact tests

Assert:

- Phase 1b artifact checker fails when `threat-model.md` is missing.
- Phase 1b artifact checker fails when `threat-model.md` lacks required headings.
- Phase 1b artifact checker passes with minimal valid threat model plus other required artifacts.
- Phase 1b artifact checker requires run-summary open questions/re-run hint sections.
- `check-frontmatter.py` remains callable.

## M. Documentation updates

Update docs as needed:

- `docs/workflow.md` for Phase 1a/1b/1c naming.
- `AGENTS.md` phase descriptions if still stale.
- Any docs mentioning `Phase 1b: CodeQL-assisted Reconnaissance`.

## N. Lightweight attribution note

Do not add license blocks to each skill file.

Add a short note in this plan or a broader curated-skills adaptation plan:

```text
Some Phase 1 threat-modeling guidance was informed by the OpenAI curated
`security-threat-model` skill and adapted for CodeCome's phased workflow.
```

## Implementation order

1. Rename Phase 1b prompt and update references.
2. Add `templates/threat-model.md`.
3. Add source-recon reference files.
4. Update `source-recon/SKILL.md`.
5. Update Phase 1a/1b/1c prompts.
6. Update `templates/target-recon.md` and `templates/run-summary.md`.
7. Add phase artifact validator command.
8. Update `check_phase_1b` gate.
9. Update Makefile target(s).
10. Add tests.
11. Update docs.

## Acceptance criteria

- `make tests` passes.
- Phase 1b no longer appears to be CodeQL-only.
- `CODEQL=0 make phase-1` still runs Phase 1b as source-only detailed recon.
- Phase 1b requires `itemdb/notes/threat-model.md`.
- `threat-model.md` has required headings and is validated by gates/checkers.
- Phase 1 summaries include open questions and re-run prompt hints.
- `tools/codecome.py check-phase-artifacts --phase 1b` exists.
- `tools/check-frontmatter.py` remains available.
- `make frontmatter` still works.
- Makefile complete validation path uses the new phase artifact checker where appropriate.
- Future harness-level open-question rendering is tracked by issue #33.
