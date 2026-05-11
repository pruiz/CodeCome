# Future Capabilities & Ideas

This document stores placeholder ideas and potential future features for the CodeCome workflow.

## File Risk Scoring Configuration

We might want to make the risk scoring highly configurable in `codecome.yml`:

```yaml
  file_scoring:
    enabled: true
    output: "./itemdb/notes/file-risk-index.yml"
    template: "./templates/file-risk-index.yml"
    scale_min: 1
    scale_max: 5
    scoring_dimensions:
      - "attacker_controlled_input"
      - "externally_influenced_state"
      - "trust_boundary_crossing"
      - "security_decision"
      - "dangerous_sink"
      - "parser_complexity"
      - "privilege_boundary"
      - "asset_sensitivity"
      - "historical_vulnerability_density"
      - "validation_feasibility"
```

## Advanced File Sweeps Configuration

File sweeps are currently run sequentially via `tools/run-sweep.py`. In the future, we could configure this as a formal sub-phase inside the config:

```yaml
  file_sweep:
    enabled: true
    mode: "sequential"
    prompt: "./prompts/sweep.md"
    runner: "./tools/run-sweep.py"
    index_lister: "./tools/list-risk-files.py"
    assignment: "one_file_per_run"
    default_min_score: 4
    default_limit: 5
    allow_parallel_future: true
```

## Parallelization Concepts

```yaml
future:
  parallel_validation:
    enabled: false
    intended_model:
      - "One validation worker per finding."
      - "Each worker must have isolated runtime state."
      - "Each worker writes only to its finding evidence directory and run directory."
      - "Docker Compose project names or disposable VMs may be used for isolation."
  parallel_file_sweep:
    enabled: false
    intended_model:
      - "One hypothesis-generation worker per high-risk file."
      - "Workers should use the file risk index as their assignment source."
      - "Each worker should write findings through the normal itemdb lifecycle."
      - "Semantic deduplication must run after each batch."
```
