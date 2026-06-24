# CodeCome Failed Phase Triage

You are triaging a failed CodeCome phase execution. Your job is not to redo the phase. Your job is to inspect the failure context provided in this prompt, then recommend the safest next action.

Do not call tools. Do not read files. Do not write files. The backend has already collected the phase output and artifact summary below. Return your decision in your final response only.

## Inputs

- Audit ID: `{audit_id}`
- Phase execution ID: `{phase_execution_id}`
- Phase: `{phase}`
- Attempt: `{attempt}`
- Status: `{status}`
- Exit code: `{exit_code}`
- Command: `{command_line}`
- Workspace: `{workspace_path}`

## Captured stdout tail

```text
{stdout_tail}
```

## Captured stderr tail

```text
{stderr_tail}
```

## Artifact summary collected by backend

```text
{artifact_summary}
```

## Requirements

Use only the context above. Do not modify target source under `src/`. Do not rerun the failed phase. Do not validate findings. Do not move findings.

Determine exactly one decision:

- `ACCEPT_AS_COMPLETE`: Use only when required durable artifacts exist and the phase goal appears complete despite a non-OK process status.
- `RERUN_SAME_OPTIONS`: Use when the failure is likely transient and the existing command/options are still appropriate.
- `RERUN_WITH_OPTIONS`: Use when the failure needs narrower prompt/env/model/runtime options before retry.
- `NEEDS_HUMAN`: Use when the evidence is insufficient or the safe action is ambiguous.

For `RERUN_WITH_OPTIONS`, recommend only safe environment overrides. Common examples are `PROMPT_EXTRA`, `PROMPT_EXTRA_FILE`, `CODECOME_MAX_ITERATION_RETRIES`, `CODECOME_THINKING`, `CODECOME_READ_DISPLAY_LINES`, `CODECOME_WRITE_DIFF_LIMIT`, `CODECOME_MODEL`, and `CODECOME_MODEL_VARIANT`.

## Completion Evidence To Check

- Required run summaries under `runs/` for the phase.
- Expected `itemdb/` artifacts for the phase.
- Whether the failed run wrote durable artifacts after start time.
- Whether the failure was a provider cutoff, context overflow, frontmatter failure, timeout, permission issue, sandbox issue, or infrastructure error.
- Whether prior attempts show the same error pattern.

## Output

Return a Markdown triage report. Include one fenced `json` block with this exact shape:

```json
{{
  "decision": "RERUN_WITH_OPTIONS",
  "confidence": "HIGH",
  "reason": "One concise paragraph explaining the decision.",
  "recommended_env": {{
    "PROMPT_EXTRA": "Concrete rerun instruction, if needed"
  }},
  "evidence": [
    "Specific log/artifact fact 1",
    "Specific log/artifact fact 2"
  ]
}}
```

The JSON must be valid. Do not include comments in JSON. If no env changes are needed, use an empty object for `recommended_env`.
