# SAST Gap Compare Summary

Date: YYYY-MM-DDTHH:MM:SSZ  
Candidate file: `itemdb/notes/sast-gap-candidates.yml`  
Findings root: `itemdb/findings/`

# Goal

Compare gap candidates against existing findings and notes to decide whether each candidate is covered, missing, duplicate, conflicting, or needs human review.

# Inputs Read

- `itemdb/notes/sast-gap-candidates.yml`
- `itemdb/findings/PENDING/`
- `itemdb/findings/CONFIRMED/`
- `itemdb/findings/EXPLOITED/`
- `itemdb/findings/REJECTED/`
- `itemdb/findings/DUPLICATE/`
- relevant `itemdb/notes/`

# Decision Summary

| Decision | Count |
|---|---:|
| covered | 0 |
| missing_sweep | 0 |
| missing_candidate | 0 |
| duplicate | 0 |
| rejected_conflict | 0 |
| needs_human | 0 |
| defer_low_signal | 0 |

# Candidate Decisions

| Candidate | Decision | Matched findings | Matched notes | Rationale |
|---|---|---|---|---|
| GAP-0001 | missing_sweep | - | `itemdb/notes/attack-surface.md:66` | Notes mention the issue but no finding covers it. |

# Recommended Actions

List candidate IDs and sweep files for the next `gap-sweep` run.

# Limitations

Document comparison uncertainty, weak matches, or candidates needing human review.
