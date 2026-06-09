# CodeCome Phase 3: Counter-Analysis and Deduplication

You are performing CodeCome Phase 3: counter-analysis and deduplication.

## Required reading

Read the following files (all paths are relative to the project/workspace root):

- `AGENTS.md`
- `codecome.yml`
- `templates/finding.md`
- `.opencode/agents/reviewer.md`
- `.opencode/skills/finding-format/SKILL.md`
- `.opencode/skills/counter-analysis/SKILL.md`
- all relevant files under `itemdb/notes/`
- `itemdb/notes/threat-model.md` — operational threat model from Phase 1b: assets, attacker model, trust-boundary summary, existing controls, abuse-path themes, risk calibration, and open assumptions.
- all candidate findings under `itemdb/findings/PENDING/`
- related findings under `itemdb/findings/CONFIRMED/`, `REJECTED/`, and `DUPLICATE/`

Use additional target-specific skills only if they clearly apply.

Examples:

- `.opencode/skills/c-cpp-security/SKILL.md`
- `.opencode/skills/juliet-benchmark/SKILL.md`

## Goal

Review all findings under:

    itemdb/findings/PENDING/

Try to disprove, weaken, deduplicate, or improve each finding.

Do not perform full runtime validation in this phase unless explicitly instructed.

Do not mark a finding as confirmed unless clear validation evidence already exists.

## Review questions

For each finding, ask:

- Is the input actually attacker-controlled or externally influenced?
- Is the affected code path reachable?
- Is the dangerous sink actually reached?
- Is there a real trust boundary?
- Is the impact security-relevant?
- Are there existing mitigations?
- Is validation performed upstream?
- Is authorization enforced elsewhere?
- Is the finding based mostly on labels, filenames, comments, or assumptions?
- Does the finding align with the attacker capabilities and non-capabilities documented in `threat-model.md`?
- Does the claimed impact map to an asset and security objective from `threat-model.md`?
- Do existing controls documented in `threat-model.md` weaken, block, or narrow the finding?
- Is the finding based on an abuse-path theme from Phase 1b, and if so, has it been grounded into a concrete vulnerable path?
- Is the finding a duplicate of another finding?
- Is the validation plan actionable?

## Semantic deduplication

Do not deduplicate only by title or by exact file path.

Two findings are likely duplicates when they describe the same root cause, security property, source, sink, trust boundary, and remediation pattern, even if they were discovered from different files during a file-scoped sweep.

For each candidate finding, compare these frontmatter fields against all other findings:

- `category`
- `target_area`
- `files`
- `symbols`
- `entry_points`
- `sources`
- `sinks`
- `trust_boundary`
- `assets_at_risk`

Also compare these body sections:

- `# Source-to-sink reasoning`
- `# Attackability / trigger conditions`
- `# Impact`
- `# Root cause analysis`
- `# Remediation idea`

Prefer a single canonical finding when multiple findings share the same bug pattern and validation path. Keep separate findings when any of these differ materially:

- affected security property,
- attacker capability,
- affected tenant/account/resource boundary,
- dangerous sink,
- exploit primitive,
- impact,
- remediation,
- validation method.

When marking a duplicate, update `# Counter-analysis` and `# Notes` to reference the canonical finding id and explain why the root cause is the same.

When keeping similar-but-not-duplicate findings, update `# Notes` to explain the distinction so later reviewers do not collapse them incorrectly.

If frontmatter metadata is too vague to compare findings, improve it before deciding.

## Allowed outcomes

### Keep in PENDING

Keep the finding open when it remains plausible.

Update:

- `# Counter-analysis`
- `# Validation plan` if needed
- confidence if needed
- semantic metadata if needed (`files`, `symbols`, `entry_points`, `sources`, `sinks`, `trust_boundary`, `assets_at_risk`, `category`, `target_area`)
- `updated_at`

### Move to REJECTED

Move the finding using the CLI tool:

    make findings-move FINDING=<id-or-path> STATUS=REJECTED

Use this when the hypothesis is disproven, not security-relevant, unreachable, out of scope, or based only on weak evidence.

Update:

- `# Counter-analysis`
- `# Validation result`

### Move to DUPLICATE

Move the finding using the CLI tool:

    make findings-move FINDING=<id-or-path> STATUS=DUPLICATE

Use this when another finding already covers the same root cause.

Update:

- `# Counter-analysis`
- `# Notes`

Reference the canonical finding id.

## Counter-analysis section format

Use this structure inside each reviewed finding:

    # Counter-analysis

    Reviewer conclusion:

    Evidence reviewed:

    Disproof attempts:

    Semantic deduplication:

    Remaining assumptions:

    Confidence adjustment:

    Recommended next action:

## Validation plan improvement

If a finding remains open, ensure its validation plan explains:

- what to build or run,
- exact input/request/command to try,
- expected vulnerable behavior,
- expected safe behavior,
- evidence to capture,
- what would reject the finding.

## Do not over-prune

Do not reject a finding only because:

- exploitation requires authentication,
- validation is hard,
- impact is lower than originally claimed,
- runtime confirmation is still pending,
- the target is a benchmark or test corpus and that corpus is in scope.

Instead:

- lower confidence,
- lower severity,
- document assumptions,
- improve validation plan.

## Final response

Run `make frontmatter` to ensure all modified findings have valid frontmatter and fix any reported errors before finishing.

At the end, summarize:

- findings reviewed,
- findings kept in PENDING,
- findings moved to REJECTED,
- findings moved to DUPLICATE,
- findings weakened or rejected due to attacker non-capabilities or existing controls from `threat-model.md`,
- findings kept because they cross a documented trust boundary or affect a documented asset,
- threat-model assumptions that affected counter-analysis,
- semantic duplicate groups identified,
- major confidence changes,
- recommended validation order,
- files modified.

## Run summary

Write the run summary to:

    runs/phase-3-summary-YYYY-MM-DD-HHMMSS.md

Use the current timestamp (year-month-day-hour-minute-second). Use the structure from `templates/run-summary.md`.

You MUST fill in the `# Open questions for the user` and `# Re-run prompt hints` sections. If there are no useful open questions or hints, write "None." Do not omit either section.
