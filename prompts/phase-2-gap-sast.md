# CodeCome Gap Scan: Independent SAST-Style Coverage Check

You are performing an optional CodeCome post-exploit **gap scan**.

This is not a normal workflow phase and it must not confirm, reject, exploit, or move findings. Its purpose is to independently look for vulnerability classes that may have been missed by the normal CodeCome Phase 2 → Phase 5 workflow, then produce durable candidate artifacts for later comparison and targeted sweeps.

## Required reading

Read the following files and directories, all relative to the workspace root:

- `AGENTS.md`
- `codecome.yml`
- `templates/finding.md`
- `.opencode/agents/auditor.md`
- `.opencode/skills/finding-format/SKILL.md`
- `.opencode/skills/source-recon/SKILL.md`
- all relevant files under `itemdb/notes/`
- existing findings under all status directories in `itemdb/findings/`

Use target-specific skills only if they clearly apply.

## Target

Analyze the target source tree under:

    ./src

Use the existing reconnaissance notes and findings to avoid duplicating already-known issues.

## Goal

Create a durable independent SAST-style gap analysis that identifies candidate issues that are either:

- already covered by existing findings,
- mentioned only in notes but missing as findings,
- not covered anywhere and worth a targeted `make sweep FILE=...`,
- too weak or generic and should be deferred,
- or require human review before any further action.

## Required outputs

Create or update these files:

1. Human-readable summary:

       itemdb/notes/sast-gap-scan.md

2. Structured candidates:

       itemdb/notes/sast-gap-candidates.yml

3. Suggested files for targeted sweeps:

       itemdb/notes/sast-gap-interesting-files.md

4. Run summary:

       runs/sast-gap-scan-YYYY-MM-DD-HHMMSS.md

Use the timestamp format already used by other CodeCome run summaries.

## Candidate schema

In `itemdb/notes/sast-gap-candidates.yml`, write a list of candidate objects with this structure:

```yaml
candidates:
  - id: GAP-0001
    title: "Short candidate title"
    category: "Information Disclosure"
    cwe: ["CWE-209"]
    severity_hint: "LOW"
    confidence: "HIGH"
    files:
      - "src/path/File.java"
    symbols:
      - "Class.method"
    entry_points:
      - "HTTP route, CLI command, parser entrypoint, or other trigger"
    sources:
      - "attacker-controlled input or externally influenced state"
    sinks:
      - "dangerous sink or security decision"
    trust_boundary: "remote user -> server response"
    evidence:
      - "short source-backed quote or precise code reference"
    impact: "realistic security impact"
    validation_idea: "actionable validation idea"
    matched_existing_findings: []
    matched_notes:
      - "itemdb/notes/attack-surface.md:66"
    decision: "missing_sweep"
    action: "sweep"
    sweep_files:
      - "src/path/File.java"
    rationale: "why this is source-backed and not just a generic bug-class guess"
```

Allowed `decision` values:

- `covered`
- `missing_sweep`
- `missing_candidate`
- `duplicate`
- `rejected_conflict`
- `needs_human`
- `defer_low_signal`

## What to look for

Focus on missed, source-backed issues including lower-severity issues that still matter. In particular, check whether Phase 1 notes mention security-relevant patterns that never became findings.

Examples of issues worth candidates when externally reachable:

- exception class names, stack traces, or internal error messages in HTTP responses,
- verbose debug/error leakage that helps attackers tune payloads,
- insecure defaults or unsafe config paths,
- missing authorization on lower-value endpoints,
- weak file/path handling that may be non-critical alone,
- hardcoded secrets in non-production-like fixtures when they are actually reachable,
- logging or response behavior that leaks sensitive implementation details.

## Quality rules

- Do not create files under `itemdb/findings/` in this gap scan.
- Do not run `make findings-create` in this gap scan.
- Do not run `make findings-move` in this gap scan.
- Do not move findings between statuses.
- Do not validate findings.
- Do not mark anything as `CONFIRMED`.
- Do not mark anything as `EXPLOITED`, `REJECTED`, or `DUPLICATE`.
- Do not re-open `REJECTED` or `DUPLICATE` findings. If a candidate conflicts with those statuses, mark it `needs_human`.
- Do not treat notes-only references as active findings.
- Do not create generic candidates without concrete files, symbols, sources, sinks, and validation ideas.
- Deduplicate against existing findings across `PENDING`, `CONFIRMED`, `EXPLOITED`, `REJECTED`, and `DUPLICATE`.
- Preserve the normal CodeCome lifecycle: targeted sweeps may later create `PENDING` findings, Phase 3 performs counter-analysis, Phase 4 validates, and Phase 5 exploits.
- Keep the gap scan limited to durable notes and run summaries under `itemdb/notes/` and `runs/`.

## Suggested output behavior

For candidates that are missing but plausible, prefer `decision: missing_sweep` and list the smallest useful set of `sweep_files`. Later automation can run `make sweep FILE=...` for those files, letting normal Phase 2 sweep logic create actual `PENDING` findings if warranted.

## Final response

At the end, summarize:

- number of candidates created,
- candidates by decision,
- candidates that are only mentioned in notes but not findings,
- suggested sweep files,
- key assumptions,
- files created or modified.

Do not claim that any candidate is a confirmed vulnerability.
