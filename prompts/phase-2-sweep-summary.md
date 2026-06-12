# CodeCome Phase 2: Sweep Summary (Aggregate Rollup)

You are performing a consolidation pass — NOT a vulnerability hunting pass.

The per-file Phase 2 sweep runs have completed. Your job is to read all per-file sweep summaries, consolidate their findings, open questions, and re-run hints into one durable aggregate summary, and also print the same concise summary to the screen.

## Required reading

Read these files (all paths are relative to the project/workspace root):

- `AGENTS.md`
- `codecome.yml`
- All per-file sweep summaries matching `runs/phase-2-summary-sweep-*.md`
- Findings under `itemdb/findings/PENDING/` that were created or touched during the sweep (identifiable from the per-file summaries)

If available in the context of this run, note which files were selected for the sweep (see the prompt body or prompt file attached to this run).

## Forbidden actions

- **Do NOT create new findings.** The per-file sweep runs already did that.
- **Do NOT perform fresh vulnerability hunting.** This is a consolidation pass.
- **Do NOT modify existing findings.** You are summarizing, not re-auditing.
- **Do NOT move findings between status directories.**

## Required output

### 1. Durable aggregate summary

Write a run summary using the template at `templates/run-summary.md` to:

    runs/sweep-summary-YYYY-MM-DD-HHMMSS.md

Use the current UTC date and time.

### 2. Screen output

Print the same concise summary to the screen before finishing. The operator should see the rollup immediately without opening the summary file. Format the screen output clearly:

- Files selected for the sweep
- Per-file sweep summaries considered
- Findings created or updated, grouped by likely theme or affected component
- Duplicate or overlapping finding candidates noticed across files
- Open questions consolidated across per-file summaries
- Re-run hints consolidated into concrete `PROMPT_EXTRA` or `PROMPT_EXTRA_FILE` suggestions
- Limitations (missing summaries, sweep failures, vague summaries that could not be consolidated)
- Recommended next step

### 3. Aggregate summary content

The durable summary must include:

- **Goal**: Explain this is a sweep consolidation rollup from per-file Phase 2 sweep runs.
- **Files processed**: List the files selected for the sweep, and which per-file summaries were found and read.
- **Findings summary**: Consolidate findings created or updated, grouped by likely theme, affected component, or security category. Flag duplicates or near-duplicates noticed across files.
- **Open questions for the user**: Deduplicate and consolidate open questions from all per-file summaries. Questions must be complete, self-contained sentences ending in `?`.
- **Re-run prompt hints**: Merge hints into concrete `PROMPT_EXTRA` or `PROMPT_EXTRA_FILE` snippets. Remove exact duplicates.
- **Limitations**: Note any missing per-file summaries, per-file runs that appear to have failed or produced low-quality output, summaries that were too vague to consolidate, and any assumptions made during consolidation.
- **Recommended next step**: Suggest the next action (e.g., run `make phase-3` for counter-analysis, re-run a specific per-file sweep with questions answered via `PROMPT_EXTRA`).

## Final response

At the end, summarize in your response:

- Number of per-file sweep summaries read
- Total findings identified across all summaries
- Key themes discovered
- Duplicates or overlaps noticed
- Files created or modified
- Open questions for the user
- Re-run prompt hints
- Recommended next step
