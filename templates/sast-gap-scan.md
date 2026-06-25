# SAST Gap Scan Summary

Date: YYYY-MM-DDTHH:MM:SSZ  
Target path: `./src`  
Scanner: independent SAST-style LLM pass  
Candidate file: `itemdb/notes/sast-gap-candidates.yml`

# Goal

Identify source-backed vulnerability candidates that may be missing from active CodeCome findings without lowering the finding quality bar.

# Scope

Describe the source areas, notes, and existing finding statuses reviewed.

# Bounds Applied

- Maximum scan rounds: CODECOME_GAP_MAX_SCAN_ROUNDS
- Maximum candidates: CODECOME_GAP_MAX_CANDIDATES
- Maximum sweep files: CODECOME_GAP_MAX_SWEEP_FILES
- Maximum sweeps per audit: CODECOME_GAP_MAX_SWEEPS_PER_AUDIT

# Candidate Summary

| Decision | Count | Notes |
|---|---:|---|
| covered | 0 | Already covered by an existing finding. |
| missing_sweep | 0 | Source-backed and should be swept. |
| missing_candidate | 0 | Missing but not yet sweep-ready. |
| duplicate | 0 | Duplicates an existing candidate or finding. |
| rejected_conflict | 0 | Conflicts with a rejected/duplicate finding. |
| needs_human | 0 | Requires human review before action. |
| defer_low_signal | 0 | Too weak or generic for action. |

# Notes-Only Gaps

List candidates that appear in reconnaissance notes but have no active finding.

# Suggested Sweep Files

List files that should be passed to `make sweep FILE=...` in a later bounded sweep.

# Assumptions

List assumptions made by the gap scan.

# Limitations

List any missed coverage, inaccessible source areas, or candidate overflow beyond configured bounds.

# Next Recommended Step

State whether to run `make gap-compare`, inspect candidates manually, or defer.
