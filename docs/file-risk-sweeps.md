# File risk index and file-scoped sweeps

CodeCome Phase 1 now produces a structured file risk index at:

    itemdb/notes/file-risk-index.yml

The index complements `itemdb/notes/interesting-files.md`. The Markdown file is for human reading; the YAML file is for tools and optional file-scoped Phase 2 sweeps.

## File risk scores

Scores are coarse and intentionally simple:

- `1` — low security interest.
- `2` — weak or indirect security relevance.
- `3` — moderate security interest.
- `4` — high security interest.
- `5` — very high security interest.

The recon agent should prioritize files that contain or influence attacker-controlled input, trust-boundary crossings, authentication or authorization decisions, dangerous sinks, parsers, file upload handling, crypto or secret handling, privilege boundaries, tenant isolation, network protocols, sandboxing, policy enforcement, or permission checks.

## List high-risk files

Show score 4+ files:

    python tools/list-risk-files.py --min-score 4

Show only paths for scripting:

    python tools/list-risk-files.py --min-score 4 --format paths

Limit the list:

    python tools/list-risk-files.py --min-score 5 --limit 10

## Run a file-scoped Phase 2 sweep

Run a single file:

    python tools/run-file-sweep.py --file src/path/to/file.ext

Run the top indexed files with score 4 or higher:

    python tools/run-file-sweep.py --min-score 4 --limit 5

Preview selected files and generated prompts without invoking OpenCode:

    python tools/run-file-sweep.py --min-score 4 --limit 5 --dry-run

The sweep runner is sequential by default. It invokes the normal `auditor` agent through the existing CodeCome wrapper unless `CODECOME_USE_WRAPPER=0` is set.

Generated temporary prompts are written under:

    tmp/file-sweep-prompts/

## Relationship with normal Phase 2

Normal Phase 2 remains the default broad hypothesis generation pass:

    make phase-2

File-scoped sweeps are optional follow-ups. They are useful when Phase 1 identifies many high-risk files and you want to inspect them one by one while observing the model's behavior.

## Relationship with Phase 3 deduplication

File-by-file sweeps can produce overlapping findings. Phase 3 therefore compares semantic metadata such as `sources`, `sinks`, `entry_points`, `trust_boundary`, `target_area`, and affected assets instead of relying only on titles or file paths.

When creating findings during a sweep, populate these frontmatter fields carefully. Better metadata makes later deduplication more reliable.
