# CodeCome Phase 3: Counter-Analysis and Deduplication

You are performing CodeCome Phase 3: counter-analysis and deduplication.

## Required reading

Read:

- `AGENTS.md`
- `codecome.yml`
- `templates/finding.md`
- `.opencode/agents/reviewer.md`
- `.opencode/skills/finding-format/SKILL.md`
- `.opencode/skills/counter-analysis/SKILL.md`
- all relevant files under `itemdb/notes/`
- all candidate findings under `itemdb/findings/NEEDS_VALIDATION/`
- related findings under `itemdb/findings/CONFIRMED/`, `REJECTED/`, and `DUPLICATE/`

Use additional target-specific skills only if they clearly apply.

Examples:

- `.opencode/skills/c-cpp-security/SKILL.md`
- `.opencode/skills/juliet-benchmark/SKILL.md`

## Goal

Review all findings under:

    itemdb/findings/NEEDS_VALIDATION/

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
- Is the finding a duplicate of another finding?
- Is the validation plan actionable?

## Allowed outcomes

### Keep in NEEDS_VALIDATION

Keep the finding open when it remains plausible.

Update:

- `# Counter-analysis`
- `# Validation plan` if needed
- confidence if needed
- `updated_at`

### Move to REJECTED

Move the finding to:

    itemdb/findings/REJECTED/

Use this when the hypothesis is disproven, not security-relevant, unreachable, out of scope, or based only on weak evidence.

Update:

- frontmatter `status`
- `# Counter-analysis`
- `# Validation result`
- `updated_at`

### Move to DUPLICATE

Move the finding to:

    itemdb/findings/DUPLICATE/

Use this when another finding already covers the same root cause.

Update:

- frontmatter `status`
- `# Counter-analysis`
- `# Notes`
- `updated_at`

Reference the canonical finding id.

## Counter-analysis section format

Use this structure inside each reviewed finding:

    # Counter-analysis

    Reviewer conclusion:

    Evidence reviewed:

    Disproof attempts:

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

At the end, summarize:

- findings reviewed,
- findings kept in NEEDS_VALIDATION,
- findings moved to REJECTED,
- findings moved to DUPLICATE,
- major confidence changes,
- recommended validation order,
- files modified.
