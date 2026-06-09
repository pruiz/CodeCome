# Plan: Track reusable open questions and re-run hints across all phases

Issue: https://github.com/pruiz/CodeCome/issues/33

## Goal

Add first-class support for durable, reusable user-context questions and re-run hints across CodeCome. The model owns explaining questions and hints in its final response and run summary. A `make hints` command lets the user review them offline.

## Design decisions

1. **Model owns questions** — appears in both its final response AND the run summary. Harness doesn't print anything.
2. **`make hints` is offline** — user runs it when they want to review accumulated questions.
3. **`codecome.py hints`** — subcommand of existing CLI, not a new standalone script.
4. **No dead code** — `display_phase_questions()` removed from harness/subphase paths. `render_questions()` removed from `RenderOutput`.
5. **Template enforces quality** — requires full-sentence questions ending in `?`, rejects noun phrases.

## Architecture

```
tools/codecome/run_summary_questions.py   # library: parse_summary(), find_latest_summary(), dataclasses
tools/codecome.py                         # CLI: "hints" subcommand → pretty-prints questions/hints
Makefile                                  # "hints" target → python3 tools/codecome.py hints
templates/run-summary.md                  # Updated sections with PROMPT_EXTRA/PROMPT_EXTRA_FILE
prompts/*.md (9 files)                    # Updated final response and run-summary req text
```

## `make hints` output format

```
Open questions & re-run hints

Phase 2  ·  runs/phase-2-summary-2026-06-09-224014.md

  Should the sandbox install librapidjson-dev to unblock deenzone?
    Why: deenzone requires rapidjson which is not in the current image.
    Affects: Whether deenzone can be built and runtime-tested inside the sandbox.

  Re-run hints:
    PROMPT_EXTRA="Add librapidjson-dev to sandbox Dockerfile" make phase-1b

Answer questions by re-running the phase with:
    PROMPT_EXTRA="your answer" make phase-<N>
    PROMPT_EXTRA_FILE=path/to/answers.txt make phase-<N>
```

Only phases with actual content shown. Empty/None sections skipped.

## Files changed

| File | Action |
|------|--------|
| `tools/codecome/run_summary_questions.py` | Remove `display_phase_questions()`. Keep parser + dataclasses. |
| `tools/codecome.py` | Add `hints` subcommand: finds all phase run summaries, parses, prints using `_colors.py` |
| `Makefile` | Add `hints: env-check` target → `$(PYTHON) tools/codecome.py hints` |
| `tools/rendering/output.py` | Revert `render_questions()` method and its imports |
| `tools/codecome/harness.py` | Revert `display_phase_questions()` call |
| `tools/codecome/phase_1.py` | Revert `display_phase_questions()` call |
| `templates/run-summary.md` | Update both sections: `PROMPT_EXTRA`/`PROMPT_EXTRA_FILE` variables, question-quality guidance |
| `prompts/phase-1a-profile.md` | Add questions/hints to final response. Update run-summary req text. |
| `prompts/phase-1b-sandbox.md` | Add questions/hints to final response. Update run-summary req text. |
| `prompts/phase-1c-recon.md` | Add questions/hints to final response. Update run-summary req text. |
| `prompts/phase-2-audit.md` | Add questions/hints to final response. Update run-summary req text. |
| `prompts/phase-3-review.md` | Add questions/hints to final response. Update run-summary req text. |
| `prompts/phase-4-validate.md` | Add questions/hints to final response. Update run-summary req text. |
| `prompts/phase-5-exploit.md` | Add questions/hints to final response. Update run-summary req text. |
| `prompts/phase-6-report.md` | Add questions/hints to final response. Update run-summary req text. |
| `prompts/sweep.md` | Add questions/hints to final response. Update run-summary req text. |
| `tests/test_run_summary_questions.py` | Remove `display_phase_questions` import. Adjust ROOT patching. |
| `tests/test_rendering_output.py` | Revert `render_questions` test classes. |
