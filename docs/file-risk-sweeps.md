# File risk index and deep-dive sweeps

CodeCome Phase 1 produces a structured file risk index at:

    itemdb/notes/file-risk-index.yml

The index complements `itemdb/notes/interesting-files.md`. The Markdown file is for human reading; the YAML file is for tools and the optional deep-dive Phase 2 `sweep` command.

## File risk scores

Scores are coarse and intentionally simple:

- `1` — low security interest.
- `2` — weak or indirect security relevance.
- `3` — moderate security interest.
- `4` — high security interest.
- `5` — very high security interest.

The recon agent will prioritize scoring files that contain or influence attacker-controlled input, trust-boundary crossings, authentication or authorization decisions, dangerous sinks, parsers, file upload handling, crypto or secret handling, privilege boundaries, tenant isolation, network protocols, sandboxing, policy enforcement, or permission checks.

## List high-risk files

Show top scored files:

    make list-risk-files

Show only score 5 files:

    python tools/list-risk-files.py --min-score 5

Show only paths for scripting:

    python tools/list-risk-files.py --format paths

## Run a Phase 2 Deep Sweep

While the global Phase 2 agent (`make phase-2`) focuses on macro-level architectural flaws and cross-component issues, you can run an optional **Deep Sweep** (Phase 2 sweep mode) to perform exhaustive, line-by-line vulnerability hunting on specific high-risk files. Each sweep run creates Phase 2 candidate findings under `itemdb/findings/PENDING/` and writes a Phase 2 run summary.

Run a sweep on specific files (supports glob patterns):

    make sweep FILE="src/path/to/file.ext"
    make sweep FILE="src/**/*.cs"

Run a sweep sequentially across the top indexed files (score 4+):

    make sweep

Preview selected files and generated prompts without invoking OpenCode:

    python tools/run-sweep.py --dry-run

The sweep runner is sequential by default. It invokes the normal `auditor` agent with a specialized prompt (`prompts/phase-2-sweep.md`) that forces the model to read related dependencies and imports to establish complete source-to-sink context.

Generated temporary prompts are written under:

    tmp/file-sweep-prompts/

Each per-file sweep run writes a Phase 2 run summary at:

    runs/phase-2-summary-sweep-<slug>-YYYY-MM-DD-HHMMSS.md

After all selected files complete, the runner invokes a final aggregate sweep summary using `prompts/phase-2-sweep-summary.md`. The aggregate step consolidates findings, open questions, and re-run hints from all per-file summaries and writes:

    runs/sweep-summary-YYYY-MM-DD-HHMMSS.md

The aggregate summary is also printed to the screen. Use `make hints` to review it later — the `Sweep` block in `codecome hints` surfaces questions from the latest aggregate sweep rollup.

## Relationship with normal Phase 2

Normal Phase 2 remains the default broad hypothesis generation pass:

    make phase-2

Deep sweeps are optional follow-ups. They are highly recommended when Phase 1 identifies many high-risk files and you want to inspect them one by one while observing the model's behavior, ensuring nothing is missed.

## Relationship with Phase 3 deduplication

File-by-file sweeps can produce overlapping findings. Phase 3 (Counter-analysis & Deduplication) compares semantic metadata such as `sources`, `sinks`, `entry_points`, `trust_boundary`, `target_area`, and affected assets instead of relying only on titles or file paths.

When creating findings during a sweep, agents are instructed to populate these frontmatter fields carefully. Better metadata makes later deduplication more reliable, gracefully merging any overlap between the global Phase 2 and your optional deep sweeps.
