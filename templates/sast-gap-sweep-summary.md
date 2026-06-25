# SAST Gap Sweep Summary

Date: YYYY-MM-DDTHH:MM:SSZ  
Candidate source: `itemdb/notes/sast-gap-candidates.yml`

# Goal

Record targeted sweeps launched from missing gap candidates and the resulting findings, if any.

# Sweep Bounds

- Maximum sweep files: CODECOME_GAP_MAX_SWEEP_FILES
- Maximum sweeps per audit: CODECOME_GAP_MAX_SWEEPS_PER_AUDIT

# Files Swept

| Candidate | File | Command | Result |
|---|---|---|---|
| GAP-0001 | `src/example/Controller.java` | `make sweep FILE=src/example/Controller.java` | Pending. |

# Findings Created

| Candidate | Finding ID | Title | Path |
|---|---|---|---|
| - | - | None. | - |

# Candidates Deferred

| Candidate | Reason |
|---|---|
| - | None. |

# Notes

Do not mark findings as confirmed from this summary. Normal Phase 3/4/5 must handle counter-analysis, validation, and exploitation.
