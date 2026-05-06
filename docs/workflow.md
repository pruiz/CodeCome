# CodeCome Workflow

CodeCome uses a phased workflow.

The workflow is intentionally simple in the initial PoC:

- one phase at a time,
- one agent at a time,
- one validation worker at a time,
- Markdown-only findings,
- file-based evidence,
- Docker-based sandbox.

## Phase overview

    Phase 1: Target reconnaissance
    Phase 2: Vulnerability hypothesis generation
    Phase 3: Counter-analysis and deduplication
    Phase 4: Finding validation
    Phase 5: Exploit development
    Phase 6: Reporting

## Phase 1: Target reconnaissance

Goal:

    Understand the target before reporting vulnerabilities.

Run:

    opencode run "$(cat prompts/phase-1-recon.md)"

Expected outputs:

    itemdb/notes/target-profile.md
    itemdb/notes/attack-surface.md
    itemdb/notes/build-model.md
    itemdb/notes/execution-model.md
    itemdb/notes/trust-boundaries.md
    itemdb/notes/data-flow.md
    itemdb/notes/validation-model.md
    itemdb/notes/interesting-files.md
    itemdb/notes/security-assumptions.md

Optional outputs:

    itemdb/notes/auth-model.md
    itemdb/notes/web-routes.md
    itemdb/notes/cli-commands.md
    itemdb/notes/public-api.md
    itemdb/notes/cwe-map.md
    itemdb/notes/benchmark-notes.md
    itemdb/notes/crypto-usage.md
    itemdb/notes/iac-resources.md

Phase 1 should not normally create findings.

## Phase 2: Vulnerability hypothesis generation

Goal:

    Create precise candidate findings.

Run:

    opencode run "$(cat prompts/phase-2-audit.md)"

Expected outputs:

    itemdb/findings/NEEDS_VALIDATION/CC-XXXX-short-title.md

Each finding must include:

- affected code,
- source-to-sink or equivalent reasoning,
- attackability,
- impact,
- validation plan,
- counter-analysis placeholder,
- evidence placeholder.

All new findings must have:

    status: "NEEDS_VALIDATION"

New findings must not have:

    confidence: "CONFIRMED"

## Phase 3: Counter-analysis and deduplication

Goal:

    Reduce false positives before validation.

Run:

    opencode run "$(cat prompts/phase-3-review.md)"

Expected actions:

- update `# Counter-analysis`,
- improve validation plans,
- lower or raise confidence,
- move disproven findings to `REJECTED`,
- move duplicate findings to `DUPLICATE`,
- leave plausible findings in `NEEDS_VALIDATION`.

Phase 3 should not normally mark findings as `CONFIRMED`.

## Phase 4: Finding validation

Goal:

    Prove or disprove one finding at a time.

Run:

    opencode run "$(sed 's#FINDING_PATH_OR_ID#CC-0001#g' prompts/phase-4-validate.md)"

Alternative:

    sed 's#FINDING_PATH_OR_ID#CC-0001#g' prompts/phase-4-validate.md | opencode run

Expected outputs:

    itemdb/evidence/CC-0001/
    itemdb/evidence/CC-0001/README.md

Useful evidence files:

    commands.txt
    output.txt
    logs.txt
    sanitizer.log
    crash.txt
    request.http
    response.txt
    exploit.py
    payload.bin
    test-output.txt
    debugger-notes.md
    static-proof.md
    limitations.md

Possible outcomes:

- move finding to `CONFIRMED`,
- move finding to `REJECTED`,
- keep finding in `NEEDS_VALIDATION` with unresolved validation notes.

## Phase 5: Exploit development

Goal:

    Demonstrate real-world impact of confirmed vulnerabilities.

Run:

    make phase-5 FINDING=CC-0001

Or manually:

    opencode run --agent exploiter "$(sed 's#FINDING_PATH_OR_ID#CC-0001#g' prompts/phase-5-exploit.md)"

Expected outputs:

    itemdb/evidence/CC-0001/exploits/
    itemdb/evidence/CC-0001/exploits/README.md
    itemdb/evidence/CC-0001/exploits/exploit.py

Useful exploitation artifacts:

    exploit.py
    exploit.sh
    payload.bin
    malicious-input.txt
    captured-output.txt
    impact-log.txt

Possible outcomes:

- move finding to `EXPLOITED` (with demonstrated impact),
- keep finding in `CONFIRMED` (exploitation not feasible).

The exploiter may adjust severity based on demonstrated impact.

## Phase 6: Reporting

Goal:

    Produce Markdown reports.

Run with an agent:

    make phase-6

Or manually:

    opencode run --agent reporter "$(cat prompts/phase-6-report.md)"

Or generate a basic local report:

    make report

Expected output:

    itemdb/reports/report.md

## Helper commands

Show available commands:

    make help

Validate workspace:

    make check

Show finding status:

    make status

Get next finding id:

    make next-id

Validate finding frontmatter:

    make frontmatter

Regenerate index:

    make index

Regenerate report:

    make report

Check sandbox:

    make sandbox-check

Open sandbox shell:

    make sandbox-shell

## Finding lifecycle

    NEEDS_VALIDATION
        ├── CONFIRMED
        │       └── EXPLOITED
        ├── REJECTED
        └── DUPLICATE

## Human review model

Findings are Markdown files so they can be reviewed like code.

Recommended human review points:

1. After Phase 1, review `itemdb/notes/`.
2. After Phase 2, review candidate findings.
3. After Phase 3, review rejected and duplicate decisions.
4. After Phase 4, review evidence before trusting confirmed findings.
5. After Phase 5, review exploit PoCs and severity adjustments.
6. Before sharing Phase 6 reports, review language and limitations.

## Validation worker model

The initial PoC uses one validation worker at a time.

Future versions may allow multiple validation workers, but each worker should have isolated runtime state.

Possible future isolation strategies:

- one Docker Compose project per finding,
- one container per finding,
- one disposable VM per finding,
- one remote sandbox per finding.

Each validation worker should write only to:

    itemdb/evidence/<finding-id>/
    runs/

## Target-specific behavior

The core workflow is target-agnostic.

Target-specific behavior belongs in:

    .opencode/skills/
    itemdb/notes/
    sandbox/scripts/
    codecome.yml target overrides

Examples:

- C/C++ review should use `.opencode/skills/c-cpp-security/`.
- Juliet/SARD review should use `.opencode/skills/juliet-benchmark/`.
- Web apps may later use `.opencode/skills/web-security/`.
- .NET apps may later use `.opencode/skills/dotnet-security/`.

## Quality gates

Before moving from Phase 1 to Phase 2:

    make check

Before reporting:

    make frontmatter
    make index
    make report

Before validation:

    make sandbox-check

## Recommended first PoC run

1. Place target source under `src/`.
2. Run:

       make check
       make sandbox-check

3. Run reconnaissance:

       make phase-1

4. Review notes under:

       itemdb/notes/

5. Run audit:

       make phase-2

6. Run counter-analysis:

       make phase-3

7. Validate one finding:

       make phase-4 FINDING=CC-0001

8. (Optional) Develop exploit for a confirmed finding:

       make phase-5 FINDING=CC-0001

9. Regenerate index and report:

       make index
       make report

   Or generate a full AI-driven report:

       make phase-6
