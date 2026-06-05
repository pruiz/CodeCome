# CodeCome Phase 4: Finding Validation

You are performing CodeCome Phase 4: validation.

Validate one assigned finding.

## Required input

Before running this prompt, replace:

    FINDING_PATH_OR_ID

with the finding id or path to validate.

Examples:

    CC-0001
    itemdb/findings/PENDING/CC-0001-missing-owner-check.md

## Assigned finding

    FINDING_PATH_OR_ID

## Required reading

Read the following files (all paths are relative to the project/workspace root):

- `AGENTS.md`
- `codecome.yml`
- `templates/finding.md`
- `templates/evidence-readme.md`
- `.opencode/agents/validator.md`
- `.opencode/skills/finding-format/SKILL.md`
- `.opencode/skills/exploit-validation/SKILL.md`
- `.opencode/skills/sandbox-validation/SKILL.md`
- relevant files under `itemdb/notes/`
- the assigned finding
- relevant source files under `src/`
- sandbox documentation under `sandbox/`

Use additional target-specific skills only if they clearly apply.

Examples:

- `.opencode/skills/c-cpp-security/SKILL.md`
- `.opencode/skills/juliet-benchmark/SKILL.md`

## Goal

Prove, disprove, or mark unresolved the assigned finding using the strongest practical method available inside the local sandbox.

Do not perform broad vulnerability hunting.

Do not create unrelated findings.

## Validation workflow

1. Read the assigned finding completely.
2. Extract the exact vulnerability claim.
3. Review the existing counter-analysis.
4. Identify what evidence would confirm or reject the claim.
5. Inspect relevant source files.
6. Prepare the sandbox under `sandbox/`.
7. Execute the validation plan or improve it.
8. Capture commands, inputs, outputs, logs, and observations.
9. Store evidence under `itemdb/evidence/<finding-id>/`.
10. Update the finding.
11. Move the finding to the correct status directory if needed.

## Evidence requirements

Create or update:

    itemdb/evidence/<finding-id>/README.md

Use `templates/evidence-readme.md` as the structure.

Store relevant evidence files such as:

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

## Allowed validation methods

Use one or more:

- `static_proof`
- `unit_test`
- `integration_test`
- `runtime_reproduction`
- `sanitizer_detection`
- `crash_reproduction`
- `http_exploit`
- `cli_exploit`
- `file_based_trigger`
- `config_based_trigger`
- `symbolic_or_manual_trace`
- `benchmark_oracle_comparison`

## Confirmation policy

A finding may be marked `CONFIRMED` only when clear evidence supports the vulnerability claim.

Valid confirmation examples:

- an HTTP request demonstrates unauthorized access,
- a CLI invocation triggers the claimed behavior,
- a crafted file triggers unsafe parser behavior,
- a sanitizer reports the claimed memory safety issue,
- a crash is reproducibly triggered at the claimed sink,
- a unit/integration test demonstrates a broken security property,
- a strong static proof demonstrates a reachable vulnerability.

Do not confirm based only on:

- filename,
- directory name,
- comments,
- function names,
- benchmark metadata,
- generic suspicious code,
- generic tool warning without reachability.

## Rejection policy

Reject the finding when validation or strong static analysis shows:

- input is not attacker-controlled,
- path is unreachable,
- sink is not reached,
- mitigation is effective,
- authorization or validation is enforced elsewhere,
- issue is not security-relevant,
- expected vulnerable behavior does not occur,
- finding is based only on labels or misleading names.

Move the rejected finding using the CLI tool:

    make findings-move FINDING=<id-or-path> STATUS=REJECTED

Update `# Validation result`.

## Unresolved policy

If validation cannot be completed, do not fake confirmation.

Keep the finding under:

    itemdb/findings/PENDING/

Update `# Validation result` with:

- what was attempted,
- what worked,
- what failed,
- what remains unknown,
- what is needed next.

## Confirmed policy

If confirmed, move the finding using the CLI tool:

    make findings-move FINDING=<id-or-path> STATUS=CONFIRMED

Update:

- `# Validation result`
- `# Evidence`

Reference evidence files by relative path.

## Final response

Run `make frontmatter` to ensure the finding's frontmatter is valid and fix any reported errors before finishing.

At the end, summarize:

- finding validated,
- validation method used,
- result: CONFIRMED / REJECTED / UNRESOLVED,
- evidence files created,
- finding file moved or updated,
- remaining limitations.

## Run summary

Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-4-FINDING-summary-YYYY-MM-DD-HHMMSS.md

Replace `FINDING` with the validated finding id
(e.g. `runs/phase-4-CC-0001-summary-2026-06-05-143022.md`).
