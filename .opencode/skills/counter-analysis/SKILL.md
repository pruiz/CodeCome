# Counter-Analysis Skill

Use this skill during CodeCome Phase 3: counter-analysis.

The goal of counter-analysis is to reduce false positives by trying to disprove, weaken, deduplicate, or reject candidate findings.

A counter-analysis pass should be skeptical.

Do not look for new findings unless they are directly related to the finding being reviewed.

## Purpose

For each finding under:

    itemdb/findings/NEEDS_VALIDATION/

determine whether it is:

- still plausible,
- overstated,
- missing assumptions,
- duplicate,
- out of scope,
- disproven by the code,
- or ready for validation.

## Inputs

Read:

- `AGENTS.md`
- `codecome.yml`
- `templates/finding.md`
- `itemdb/notes/`
- the finding being reviewed
- relevant source files under `src/`
- related findings in `itemdb/findings/`

## Outputs

Update the finding in place, or move it to the appropriate status directory.

Possible outcomes:

- keep in `NEEDS_VALIDATION/`,
- move to `REJECTED/`,
- move to `DUPLICATE/`.

Do not move a finding to `CONFIRMED/` during counter-analysis unless the prompt explicitly asks for validation and clear evidence is already available.

## Review mindset

Try to disprove the finding.

Ask:

- Is the alleged input actually attacker-controlled?
- Is the affected code path reachable?
- Is the vulnerable sink actually reached?
- Is the dangerous operation protected by validation?
- Is authorization enforced in middleware, filters, decorators, framework policy, repository layer, database policy, or another component?
- Is authentication required before the path is reachable?
- Is the reported impact realistic?
- Is the finding based only on filename, comment, documentation, benchmark label, or directory name?
- Is this a duplicate of another finding?
- Is the issue already mitigated by compiler flags, runtime protections, framework defaults, or safe wrappers?
- Is the finding too broad to validate?
- Does the validation plan actually test the claim?

## Required updates

Every reviewed finding must have an updated `# Counter-analysis` section.

The counter-analysis section should include:

- reviewer conclusion,
- evidence supporting the conclusion,
- assumptions that remain,
- confidence adjustment,
- recommended next action.

Example:

    The finding remains plausible. The handler checks authentication through
    middleware, but no ownership check was found in the controller, service, or
    repository. The repository loads the object by id only. Validation should
    attempt cross-user access using two accounts.

Example rejection:

    Rejected. The reported `fileName` input is not user-controlled. It is
    generated server-side from a UUID and never crosses a trust boundary. The
    path traversal claim is therefore not actionable.

Example duplicate:

    Duplicate of CC-0007. Both findings describe the same missing tenant check
    in `DocumentRepository.GetById`.

## Confidence adjustment

Adjust confidence when needed.

Use:

- `LOW`
- `MEDIUM`
- `HIGH`
- `CONFIRMED`

Do not use `CONFIRMED` unless evidence already exists.

Suggested mapping:

- lower to `LOW` if important assumptions remain unproven,
- keep or raise to `MEDIUM` if a credible path exists,
- raise to `HIGH` if source-to-sink or trust-boundary evidence is strong,
- reject if attacker control, reachability, or impact is absent.

## Common false positive patterns

Look for these common mistakes:

### Framework protection missed

The finding ignores protections provided by:

- authentication middleware,
- authorization filters,
- CSRF middleware,
- ORM parameterization,
- template auto-escaping,
- model validation,
- route constraints,
- safe file storage abstractions,
- request size limits,
- content type validation,
- sandboxing,
- compiler hardening.

### Wrong trust boundary

The finding assumes an attacker controls data that is actually:

- constant,
- generated server-side,
- loaded from trusted config,
- protected by admin-only access,
- created by a privileged internal service,
- unreachable from the claimed user role.

### Unreachable path

The finding ignores:

- feature flags,
- build flags,
- platform-specific compilation,
- dead code,
- tests only,
- example code,
- disabled routes,
- private functions not reachable from entrypoints.

### Non-security bug

The finding describes:

- normal error handling,
- harmless crash in local developer tooling,
- low-impact log noise,
- theoretical issue without security boundary,
- quality bug without attacker impact.

### Label leakage

The finding is based only on:

- filename,
- directory name,
- benchmark metadata,
- comments,
- known vulnerable benchmark labels.

For benchmark targets, labels may guide review but are not sufficient evidence.

### Duplicates

The same root cause may appear in multiple places.

When possible, prefer one canonical finding for the root cause, with affected variants listed inside it.

However, keep separate findings when:

- exploitation path differs,
- impact differs,
- affected component differs,
- remediation differs,
- validation strategy differs.

## Rejection format

When rejecting, update frontmatter:

    status: "REJECTED"

Move the file to:

    itemdb/findings/REJECTED/

Update `# Counter-analysis` with:

- rejection reason,
- source references,
- why the original hypothesis fails,
- whether any related issue remains.

Update `# Validation result`:

    Rejected during counter-analysis. Validation was not performed because the hypothesis was disproven statically.

## Duplicate format

When marking duplicate, update frontmatter:

    status: "DUPLICATE"

Move the file to:

    itemdb/findings/DUPLICATE/

Update `# Counter-analysis` with:

- canonical finding id,
- overlap explanation,
- whether this file adds useful evidence.

Update `# Notes` with:

    Duplicate of CC-XXXX.

## Keep-for-validation format

When keeping a finding in `NEEDS_VALIDATION`, update `# Counter-analysis` with:

- why it remains plausible,
- what evidence supports it,
- what assumptions remain,
- what validation should focus on.

Also ensure `# Validation plan` is specific enough.

## Do not over-prune

Do not reject just because validation is hard.

Do not reject just because exploitation requires authentication.

Do not reject just because impact is lower than originally claimed.

Instead:

- lower severity,
- lower confidence,
- document assumptions,
- improve validation plan.

## Completion checklist

For each finding reviewed:

- `# Counter-analysis` is no longer empty.
- status is still valid.
- confidence reflects current belief.
- duplicate checks were considered.
- rejection, if any, is explained.
- validation plan is improved if the finding remains open.
- file is in the correct status directory.
