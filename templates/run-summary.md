# CodeCome Run Summary

Date: YYYY-MM-DD  
Phase: reconnaissance / hypothesis_generation / counter_analysis / validation / exploit_development / reporting  
Agent: recon / auditor / reviewer / validator / exploiter / reporter / generic  
Target path: `./src`

# Goal

Describe the goal of this run.

# Prompt

Summarize the prompt or task that was executed.

# Files read

List important files read during the run.

Examples:

- `AGENTS.md`
- `codecome.yml`
- `itemdb/notes/target-profile.md`
- `src/...`

# Files created

List files created during the run.

# Files modified

List files modified during the run.

# Findings created

| ID | Title | Path |
|---|---|---|
| - | None. | - |

# Findings moved

| ID | From | To | Reason |
|---|---|---|---|
| - | - | - | None. |

# Findings updated

| ID | Update summary |
|---|---|
| - | None. |

# Evidence created

List evidence directories or files created.

Examples:

- `itemdb/evidence/CC-0001/README.md`
- `itemdb/evidence/CC-0001/sanitizer.log`

# Important observations

Summarize useful observations from the run.

# Assumptions

List assumptions made during the run.

Mark each assumption as:

- confirmed
- likely
- unknown
- risky

# Open questions for the user

List questions that would materially improve a later re-run.

Each question must be a complete, specific sentence ending in `?`.
Someone seeing only the question line should understand what's being asked
without reading the rest of the run summary.

Good: "Should the sandbox install librapidjson-dev to unblock deenzone?"
Bad:  "Validation model for C challenges"

Answer these by re-running the phase with:

    PROMPT_EXTRA="your answer" make phase-<N>
    PROMPT_EXTRA_FILE=path/to/answers.txt make phase-<N>

If there are no useful questions, write: None.

## Question: <full-sentence question ending in ?>

- Why it matters: What changes if this is answered.
- Affects: Which phases, findings, or decisions depend on the answer.
- Suggested answer format: A `PROMPT_EXTRA` snippet or concrete format.

# Re-run prompt hints

Copy/paste snippets the user can pass via `PROMPT_EXTRA` or
`PROMPT_EXTRA_FILE` on re-run. These are the actual mechanisms — do not
invent fictional environment variables. Example:

    PROMPT_EXTRA="Focus on auth modules; assume production deployment" make phase-2

If there are no useful hints, write: None.

# Limitations

List anything that could not be completed.

# Recommended next step

State the most useful next action.
