# Phase 2 Sweep Alignment Plan

## Problem

`make sweep` is intended to run focused, file-scoped Phase 2 hypothesis generation. It is implemented as a meta-orchestrator in `tools/run-sweep.py` that selects files and invokes `tools/run-agent.py` once per file.

The current per-file invocation uses the Phase 2 harness identity:

```bash
python tools/run-agent.py \
  --phase 2 \
  --label "Deep Sweep: <file>" \
  --agent auditor \
  --prompt-file tmp/file-sweep-prompts/sweep-<slug>.md
```

The harness sees `--phase 2`, so the Phase 2 completion gate expects a fresh run summary matching:

```text
runs/phase-2-summary*.md
```

Historically, the sweep prompt told the model to write:

```text
runs/sweep-<slug>-summary-YYYY-MM-DD-HHMMSS.md
```

That naming does not satisfy the Phase 2 completion gate. A correctly completed per-file sweep can therefore fail because the artifact has the wrong name for the harness that executed it.

The first alignment change renamed the per-file summary to:

```text
runs/phase-2-summary-sweep-<slug>-YYYY-MM-DD-HHMMSS.md
```

That fixes the completion gate, but introduces a second issue: helper code that asks for the latest broad Phase 2 summary now also sees sweep summaries. This is confusing for `codecome hints` and for any tool that wants the latest normal `make phase-2` run rather than the latest per-file sweep run.

There is also a usability gap: a sweep may process many files, creating many per-file summaries. Operators need one final sweep-level summary that consolidates findings, open questions, rerun hints, limitations, and next steps.

## Important Clarification

Sweep runs do **not** process both `prompts/phase-2-audit.md` and the sweep prompt.

`--phase 2` is used by the harness for phase identity, session title, prompt-extra lookup, completion gates, retries, and transcript naming. The actual prompt body comes from `--prompt-file`.

For sweep, `tools/run-sweep.py` reads the sweep prompt template, replaces `FILE_PATH_OR_ID`, writes a generated prompt under `tmp/file-sweep-prompts/`, and passes that generated path as `--prompt-file`.

The only normal Phase 2 content a sweep may inherit is `audit.extra_prompts.hypothesis_generation` from `codecome.yml`, because `load_prompt(..., phase="2")` maps phase `2` to `hypothesis_generation`. It does not include `prompts/phase-2-audit.md`.

## Decision

Treat sweep as a specialized Phase 2 execution mode for each file, plus a separate sweep-level rollup step after all selected files complete.

The per-file sweep runs should continue to invoke `run-agent.py --phase 2`, because each per-file run creates Phase 2 candidate findings under `itemdb/findings/PENDING/` and should use existing Phase 2 readiness and completion behavior.

Per-file sweep summaries should remain Phase 2 summaries so the Phase 2 harness accepts them:

```text
runs/phase-2-summary-sweep-<slug>-YYYY-MM-DD-HHMMSS.md
```

The final aggregate sweep summary should **not** use `phase-2-summary-*`. It is not a single Phase 2 agent run and should not be treated as the latest broad Phase 2 summary. Use a distinct sweep-level name:

```text
runs/sweep-summary-YYYY-MM-DD-HHMMSS.md
```

This gives each artifact a clear meaning:

- `runs/phase-2-summary-YYYY-MM-DD-HHMMSS.md`: broad `make phase-2` hypothesis-generation summary.
- `runs/phase-2-summary-sweep-<slug>-YYYY-MM-DD-HHMMSS.md`: one file-scoped Phase 2 sweep summary, accepted by the Phase 2 completion gate.
- `runs/sweep-summary-YYYY-MM-DD-HHMMSS.md`: aggregate sweep rollup for humans and `codecome hints`.

## Non-Goals

- Do not add a separate `--phase sweep` execution mode for per-file sweep runs.
- Do not make the Phase 2 completion gate require `sweep-summary-*.md`; the per-file sweep summary remains the completion artifact for each Phase 2 harness run.
- Do not concatenate the full standard Phase 2 audit prompt into the sweep prompt.
- Do not make the aggregate sweep summary perform fresh vulnerability hunting.
- Do not create new findings during the aggregate summary step.
- Do not make `codecome hints` print every per-file sweep summary by default.

## Prompt Strategy

### Per-File Sweep Prompt

Rename the per-file sweep prompt:

```text
prompts/sweep.md -> prompts/phase-2-sweep.md
```

The renamed prompt should explicitly state:

- This is CodeCome Phase 2 hypothesis generation in file-scoped sweep mode.
- It complements the broad `make phase-2` pass.
- It inherits Phase 2 finding-quality and artifact expectations.
- It narrows the broad Phase 2 scope to one target file plus immediate dependencies needed for reachability and source-to-sink reasoning.
- It must write `runs/phase-2-summary-sweep-<slug>-YYYY-MM-DD-HHMMSS.md`.
- It should print a concise end-of-run summary to the screen in addition to writing the durable run summary, matching the operator experience of other phase runs.

Avoid including the full `prompts/phase-2-audit.md` text verbatim. That prompt contains broad-scope instructions such as avoiding line-by-line deep dives, which directly conflicts with sweep mode.

If shared prompt content becomes necessary later, extract common Phase 2 requirements into a reusable prompt fragment and include it from both the broad Phase 2 prompt and the sweep-mode prompt. Do not solve that extraction in this fix.

### Aggregate Sweep Summary Prompt

Add a new prompt:

```text
prompts/phase-2-sweep-summary.md
```

This prompt is for the final rollup step after `tools/run-sweep.py` has finished the selected per-file sweeps.

It should instruct the model to read and consolidate:

- The per-file sweep summaries matching `runs/phase-2-summary-sweep-*.md`.
- The relevant candidate findings under `itemdb/findings/PENDING/`, especially findings created or touched during the sweep when identifiable from summaries.
- Any sweep selection context provided in the generated rollup prompt, such as selected files and failed files if partial summary mode is later added.

It should instruct the model to write a durable summary to:

```text
runs/sweep-summary-YYYY-MM-DD-HHMMSS.md
```

It should also instruct the model to print the same concise summary to the screen. The screen output should be useful to the operator immediately after `make sweep` finishes, without requiring them to open the summary file.

The aggregate prompt should explicitly forbid fresh vulnerability hunting and new finding creation. Its job is consolidation, not another audit pass.

The aggregate summary should include:

- Files selected for the sweep.
- Per-file sweep summaries considered.
- Findings created or updated, grouped by likely theme or affected component when possible.
- Duplicate or overlapping finding candidates noticed across files.
- Open questions consolidated across per-file summaries.
- Re-run hints consolidated into concrete `PROMPT_EXTRA` or `PROMPT_EXTRA_FILE` suggestions.
- Limitations, including missing summaries, skipped files, failed per-file runs, or summaries that were too vague to consolidate.
- Recommended next step, usually Phase 3 counter-analysis once the operator is satisfied with the candidate set.

## Helper Semantics

### Broad Phase 2 Summary Lookup

`find_latest_summary("2")` should mean the latest broad Phase 2 summary by default. It should skip per-file sweep summaries.

Concretely, it should not return files matching:

```text
phase-2-summary-sweep-*.md
```

This keeps callers from accidentally treating a narrow file sweep as the latest global hypothesis-generation pass.

A minimal implementation is to add optional exclude support:

```python
def find_latest_summary(
    phase_id: str,
    finding: str | None = None,
    *,
    exclude_patterns: tuple[str, ...] = (),
) -> Path | None:
    ...
```

Then the default broad Phase 2 caller can pass `exclude_patterns=("phase-2-summary-sweep-*.md",)` or the function can special-case phase `2` if all current callers expect broad Phase 2 semantics.

The first option is more explicit and less surprising for future code.

### Sweep Summary Lookup

Add a separate helper for aggregate sweep summaries, for example:

```python
def find_latest_sweep_summary() -> Path | None:
    ...
```

It should search:

```text
runs/sweep-summary-*.md
```

This prevents aggregate sweep summaries from being mixed into Phase 2 summary lookup.

### `codecome hints`

`codecome hints` should consider both broad phase summaries and the aggregate sweep rollup.

Recommended display model:

- `Phase 1a`: latest Phase 1a summary.
- `Phase 1b`: latest Phase 1b summary.
- `Phase 1c`: latest Phase 1c summary.
- `Phase 2`: latest non-sweep `phase-2-summary*.md`.
- `Sweep`: latest `sweep-summary-*.md`, if present.
- `Phase 3`: latest Phase 3 summary.
- `Phase 4`: latest finding-scoped Phase 4 summary.
- `Phase 5`: latest finding-scoped Phase 5 summary.

Do not print every per-file `phase-2-summary-sweep-*.md` by default. Large sweeps can produce many files, and dumping all of them makes `hints` noisy. The rollup exists to consolidate those details.

If no `sweep-summary-*.md` exists, there are two acceptable behaviors:

- Preferred: print no `Sweep` block and rely on the absence of the rollup as a signal that the sweep did not complete aggregation.
- Alternative: print only the latest per-file sweep summary as `Sweep file`, but clearly label it as incomplete and avoid duplicating it as `Phase 2`.

The preferred behavior is less noisy and encourages `run-sweep.py` to produce the aggregate summary consistently.

## Implementation Steps

1. Rename the per-file sweep prompt.

   ```text
   prompts/sweep.md -> prompts/phase-2-sweep.md
   ```

2. Update `tools/run-sweep.py` to use the renamed prompt.

   Change:

   ```python
   PROMPT_TEMPLATE = ROOT / "prompts" / "sweep.md"
   ```

   to:

   ```python
   PROMPT_TEMPLATE = ROOT / "prompts" / "phase-2-sweep.md"
   ```

   Keep each per-file invocation using `--phase 2`.

3. Update the per-file prompt text.

   Replace the old run-summary instruction with:

   ```text
   runs/phase-2-summary-sweep-<slug>-YYYY-MM-DD-HHMMSS.md
   ```

   Explain that `<slug>` is the sanitized target file path.

   Instruct the model to print a concise end-of-run summary to the screen as well as writing the durable file.

4. Add the aggregate sweep summary prompt.

   Create:

   ```text
   prompts/phase-2-sweep-summary.md
   ```

   The prompt should instruct the model to consolidate `runs/phase-2-summary-sweep-*.md` into:

   ```text
   runs/sweep-summary-YYYY-MM-DD-HHMMSS.md
   ```

   It should instruct the model to print the same concise rollup to the screen.

   It should explicitly say not to create findings and not to perform fresh vulnerability hunting.

5. Add final rollup orchestration to `tools/run-sweep.py`.

   After all selected per-file sweeps succeed and when `--dry-run` is not set, run a final summary step using `prompts/phase-2-sweep-summary.md`.

   The rollup invocation should receive enough context to know which files were selected. The simplest approach is to generate a temporary prompt under `tmp/file-sweep-prompts/`, appending a selected-file list to the static rollup prompt, then run the selected agent against that generated prompt.

   Minimal acceptable behavior:

   - Run the rollup only after all per-file sweeps return success.
   - Skip the rollup during `--dry-run`.
   - Return a non-zero exit code if the rollup step fails.

   Future partial-summary behavior can be added later with a `--continue-on-error` or `--summarize-partial` flag.

6. Choose the rollup execution path.

   Prefer the smallest implementation that preserves existing rendering behavior.

   Option A: invoke `tools/run-agent.py` with a normal prompt but without pretending the rollup is Phase 2, if the runner supports a non-phase run mode.

   Option B: invoke `opencode run --agent auditor <prompt>` directly. This is simple, but bypasses the CodeCome styled wrapper and any run-agent conveniences.

   Option C: extend `tools/run-agent.py` to support a non-phase utility run. This is more invasive and should only be chosen if wrapper behavior is required.

   The current minimal preference is Option B unless inspection shows that `run-agent.py` already supports non-phase prompt execution. The aggregate summary is a convenience rollup, not a phase completion gate participant.

7. Update summary lookup helpers.

   Add explicit filtering so broad Phase 2 lookup skips `phase-2-summary-sweep-*.md`.

   Add a separate helper for `sweep-summary-*.md`.

8. Update `tools/codecome.py` hints behavior.

   Remove the current per-file sweep scan from the default hints output.

   Display the latest aggregate `sweep-summary-*.md` as `Sweep` if present.

   Ensure a per-file sweep summary can never be printed once as `Phase 2` and again as `Sweep`.

9. Update docs.

   In `README.md` and `docs/file-risk-sweeps.md`, describe sweep as file-scoped Phase 2 plus a final aggregate sweep summary.

   Mention both artifact types:

   ```text
   runs/phase-2-summary-sweep-<slug>-YYYY-MM-DD-HHMMSS.md
   runs/sweep-summary-YYYY-MM-DD-HHMMSS.md
   ```

   Update the reusable prompt list to include:

   ```text
   prompts/phase-2-sweep.md
   prompts/phase-2-sweep-summary.md
   ```

   Remove or replace references to `prompts/sweep.md` in active user-facing documentation.

10. Add or update tests.

    Suggested tests:

    - `tools/run-sweep.py` uses `prompts/phase-2-sweep.md` as its per-file template.
    - `build_prompt_for_file("src/foo.php")` produces prompt content containing `src/foo.php` and `phase-2-summary-sweep-<slug>-YYYY-MM-DD-HHMMSS.md`.
    - The generated per-file sweep prompt no longer mentions `runs/sweep-<slug>-summary`.
    - The per-file sweep prompt asks the model to print a summary to the screen.
    - The Phase 2 completion gate still accepts a fresh `runs/phase-2-summary-sweep-src-foo-php-YYYY-MM-DD-HHMMSS.md` through the existing `phase-2-summary*.md` glob.
    - `find_latest_summary("2")` ignores `phase-2-summary-sweep-*.md` when looking for the broad Phase 2 summary.
    - `find_latest_sweep_summary()` returns the newest `sweep-summary-*.md`.
    - `codecome hints` displays a `Sweep` block from the latest aggregate sweep summary.
    - `codecome hints` does not duplicate the same per-file sweep summary as both `Phase 2` and `Sweep`.
    - `tools/run-sweep.py` invokes the aggregate summary step only after all per-file sweeps succeed.
    - `tools/run-sweep.py` skips the aggregate summary step during `--dry-run`.

11. Run local checks.

    ```bash
    make tests
    ```

## Expected Behavior After Fix

For a command like:

```bash
make sweep FILE="src/zabbix-7.4.10/ui/imgstore.php"
```

`tools/run-sweep.py` should:

- Generate a file-scoped prompt under `tmp/file-sweep-prompts/`.
- Invoke `tools/run-agent.py --phase 2` for the selected file.
- Create or update candidate findings under `itemdb/findings/PENDING/` when the audit identifies credible candidates.
- Require the per-file model run to write a summary such as:

```text
runs/phase-2-summary-sweep-src-zabbix-7-4-10-ui-imgstore-php-2026-06-12-164608.md
```

- Accept that per-file summary through the existing Phase 2 completion gate.
- After all selected files complete, run the aggregate summary prompt.
- Require the aggregate summary run to write:

```text
runs/sweep-summary-2026-06-12-171200.md
```

- Print the aggregate summary to the screen before exiting.

After that, `make hints` should:

- Show broad Phase 2 questions from the latest non-sweep `phase-2-summary*.md`.
- Show sweep questions from the latest `sweep-summary-*.md`.
- Avoid printing per-file sweep summaries by default.
- Avoid duplicate output.

## Future Work

Possible future improvements, intentionally outside this fix:

- Add `--continue-on-error` and final partial sweep status reporting.
- Add `--summarize-partial` to produce `sweep-summary-*.md` even when some per-file runs fail.
- Add per-file result JSON under `runs/` or `tmp/` for machine-readable sweep orchestration.
- Extract shared Phase 2 finding requirements into a prompt fragment reused by both `phase-2-audit.md` and `phase-2-sweep.md`.
- Support a separate `audit.extra_prompts.sweep` config key that is appended in addition to `audit.extra_prompts.hypothesis_generation`.
- Add a `make sweep-summary` target to regenerate only the aggregate summary from existing per-file sweep summaries.
