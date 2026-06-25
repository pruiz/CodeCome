# SAST Gap Interesting Files

Date: YYYY-MM-DDTHH:MM:SSZ  
Source candidates: `itemdb/notes/sast-gap-candidates.yml`

# Purpose

List files selected for later targeted `make sweep FILE=...` runs because an independent gap scan found source-backed missing candidates.

# Selection Rules

- Include only files tied to candidates with `decision: missing_sweep` or `needs_human` after review.
- Prefer the smallest file set that can establish reachability and source-to-sink reasoning.
- Do not include files only because they contain suspicious names or comments.
- Do not re-sweep files already swept for the same candidate unless explicitly forced.

# Files To Sweep

| Candidate | File | Priority | Rationale | Expected class |
|---|---|---:|---|---|
| GAP-0001 | `src/example/Controller.java` | 5 | Contains externally reachable error response sink. | Information Disclosure |

# Deferred Files

| Candidate | File | Reason |
|---|---|---|
| - | - | None. |

# Notes

Replace example rows with target-specific sweep planning output.
