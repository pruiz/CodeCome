# Harness Resilience: Run-Summary Gating, Resume Diagnostics, and Prompt Consistency

Date: 2026-06-05
Status: Plan
Target: `tools/` harness + agent files + phase prompts

---

## 1. Problem

`make phase-2` with `minimaxai/minimax-m2.7` failed (exit code 2) despite the model
reading all required files, understanding the target (Juliet C/C++ benchmark corpus),
and creating fresh PENDING findings.  The failure was traced to three cooperating
weaknesses:

### Symptom

```
Phase 2 reported terminal finish reason 'stop', but required durable artifacts
were not produced. Treating as incomplete.
```

The model created CC-0013 and CC-0014 in `itemdb/findings/PENDING/` but never wrote
`runs/phase-2-summary*.md`.  The harness rejected the run and its auto-resume prompt
was too generic for a weak model to self-diagnose the missing artifact.

### Root causes

1. **Gate too strict** (`tools/phases/completion.py:183`):
   `check_phase_graceful_completion` for phase 2 requires *both* a fresh PENDING
   finding AND a fresh run-summary file (`pending_fresh AND summary_fresh`).  A
   legitimate "0 new findings" outcome fails because `pending_fresh` is False.

2. **Resume prompt too generic** (`tools/phases/completion.py:289-305`):
   `build_phase_resume_prompt` says "complete remaining work" without listing
   *which* required artifacts are missing.  A weak model that already thinks it
   finished cannot self-diagnose what to fix.

3. **Agent/prompt inconsistency** (agent files vs phase prompts):
   Agent files say run-summary is "when practical" (soft).  Phase prompts say
   "Write the run summary … to `runs/phase-X-summary.md`" (firm).  In chat
   mode, where no phase prompt is loaded, the agent has no mandate to produce
   a summary at all.  A weak model reading both sources follows the weaker one.

---

## 2. Design decisions

### 2.1 Agent files are for audit methodology; prompts are for artifact requirements

Agent files currently mix behavioral rules (how to find vulnerabilities) with
output-artifact rules (what files to write).  This creates duplication and the
"when practical" vs "must" contradiction.

**Decision:** Remove the run-summary obligation from agent files.  Each agent
file gets a single delegating note instead.  Phase prompts become the single
source of truth for required output artifacts.

Rationale:
- Phase prompts are always loaded in phase mode — no loss of coverage.
- Chat mode has no harness gating — no enforcement gap to worry about.
- One place to change artifact rules, not two.
- Eliminates the hedge language that weak models latch onto.

### 2.2 All run-summary filenames include a timestamp

Current state:

| Prompt          | Path                                         | Timestamp? |
|-----------------|----------------------------------------------|------------|
| phase-1a        | `runs/phase-1a-summary.md`                  | No         |
| phase-1b        | `runs/phase-1b-summary.md`                  | No         |
| phase-1c        | `runs/phase-1c-summary.md`                  | No         |
| phase-2         | `runs/phase-2-summary.md`                   | No         |
| phase-3         | `runs/phase-3-summary-YYYY-MM-DD-HHMMSS.md` | Yes        |
| phase-4         | `runs/phase-4-FINDING-summary.md`           | No         |
| phase-5         | `runs/phase-5-FINDING-summary.md`           | No         |
| phase-6         | `runs/phase-6-summary.md`                   | No         |

**Decision:** All phases use `runs/phase-X[-FINDING]-summary-YYYY-MM-DD-HHMMSS.md`.

The glob patterns in `completion.py` already use `*` wildcards (e.g.
`phase-2-summary*.md`), so the gate won't reject the new format.  No
completion-checker change is needed for this.

Phases 4 and 5 include a finding ID (`phase-4-CC-0001-summary-TIMESTAMP.md`),
which also prevents collisions across different findings.  The timestamp
appended after the finding ID covers multiple runs of the same finding.

### 2.3 Phase-2 gate accepts "0 new findings"

A valid phase-2 outcome is "the codebase surface is already fully covered by
existing findings; no new hypotheses."  Requiring `pending_fresh` rejects this.

**Decision:** `summary_fresh` alone is sufficient for phase 2 completion.
The run summary is the durable record of what was (or was not) found.  Phase 3
(counter-analysis) can challenge coverage gaps.  `pending_fresh` is still
checked for diagnostic purposes (reported in the failure detail) but no longer
blocks.

### 2.4 Resume prompt lists exact missing artifacts

When the harness detects missing artifacts and auto-resumes, the resume prompt
must tell the model *exactly* what is missing so it can fix it without guessing.

**Decision:** `check_phase_graceful_completion` returns `(bool, list[str])`
instead of `bool`.  The list carries human-readable failure messages that
`build_phase_resume_prompt` injects into the resume text.

Example failure messages:

```
Missing: runs/phase-2-summary-*.md — run summary was not created or updated
Missing: itemdb/findings/PENDING/ — no .md files created or modified during this run
```

The resume prompt then reads:

```
Your previous run completed but did not produce all required artifacts.

Missing required artifacts:
- runs/phase-2-summary-*.md — run summary was not created or updated

Fix only these missing items. Do not redo completed work.

Phase 2 completion checklist:
- Create or update precise findings under itemdb/findings/PENDING/.
- …
```

---

## 3. Detailed changes

### Group A — Agent files: remove run-summary, add delegating note

**Files:**
- `.opencode/agents/auditor.md`
- `.opencode/agents/reviewer.md`
- `.opencode/agents/validator.md`
- `.opencode/agents/exploiter.md`
- `.opencode/agents/recon.md`

**Remove** lines matching:
```
- a short run summary is written when practical.
```
or (recon.md specific):
```
- a run summary is written to `runs/` using `templates/run-summary.md`.
```

Also in `auditor.md`, remove lines 43–45 in the "Required reading" section:
```
Also reference when writing run summaries:

- `templates/run-summary.md`
```

**Add** (as the first item in the "Completion checklist" section, replacing
the removed line):

```
- The phase prompt specifies required durable artifacts. Follow it precisely.
```

This line is intentionally generic — it delegates to the phase prompt for
specifics while maintaining a clear obligation.

### Group B — Phase prompts: add timestamp to all summary paths

**Files and precise changes:**

#### `prompts/phase-1a-profile.md`

Line 104:
```
OLD: - Non-blocking open questions should go into `runs/phase-1a-summary.md`.
NEW: - Non-blocking open questions should go into the run summary file.
```

Lines 124–126:
```
OLD:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-1a-summary.md

NEW:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-1a-summary-YYYY-MM-DD-HHMMSS.md
```

#### `prompts/phase-1b-recon.md`

Line 230:
```
OLD: - include unresolved questions in `runs/phase-1b-summary.md`,
NEW: - include unresolved questions in the run summary file,
```

Lines 270–272:
```
OLD:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-1b-summary.md

NEW:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-1b-summary-YYYY-MM-DD-HHMMSS.md
```

#### `prompts/phase-1c-sandbox.md`

Line 119 (optional prose reference — clean up for consistency):
```
OLD: … Record the question in `sandbox-plan.md` and `runs/phase-1c-summary.md`.
NEW: … Record the question in `sandbox-plan.md` and the run summary file.
```

Lines 133–135:
```
OLD:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-1c-summary.md

NEW:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-1c-summary-YYYY-MM-DD-HHMMSS.md
```

#### `prompts/phase-2-audit.md`

Lines 209–211:
```
OLD:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-2-summary.md

NEW:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-2-summary-YYYY-MM-DD-HHMMSS.md
```

#### `prompts/phase-4-validate.md`

Lines 198–202:
```
OLD:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-4-FINDING-summary.md

Replace `FINDING` with the validated finding id (e.g. `runs/phase-4-CC-0001-summary.md`).

NEW:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-4-FINDING-summary-YYYY-MM-DD-HHMMSS.md

Replace `FINDING` with the validated finding id
(e.g. `runs/phase-4-CC-0001-summary-2026-06-05-143022.md`).
```

#### `prompts/phase-5-exploit.md`

Lines 446–450:
```
OLD:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-5-FINDING-summary.md

Replace `FINDING` with the exploited finding id (e.g. `runs/phase-5-CC-0001-summary.md`).

NEW:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-5-FINDING-summary-YYYY-MM-DD-HHMMSS.md

Replace `FINDING` with the exploited finding id
(e.g. `runs/phase-5-CC-0001-summary-2026-06-05-143022.md`).
```

#### `prompts/phase-6-report.md`

Lines 214–216:
```
OLD:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-6-summary.md

NEW:
Write the run summary using the template at `templates/run-summary.md` to:

    runs/phase-6-summary-YYYY-MM-DD-HHMMSS.md
```

**Phase 3 (`prompts/phase-3-review.md`)** — already correct.  No change.


### Group C — `tools/phases/completion.py`

Three internal changes in this file.  All changes are additive/refactoring;
runtime callers in `harness.py` and `phase_1.py`, plus tests, are updated in
Groups D and E.

#### C.1: Enrich `check_phase_graceful_completion` return type

**Current signature** (line 128):
```python
def check_phase_graceful_completion(phase: str, finding: str | None,
                                    run_start_time: float) -> bool:
```

**New signature**:
```python
def check_phase_graceful_completion(phase: str, finding: str | None,
                                    run_start_time: float
                                    ) -> tuple[bool, list[str]]:
```

**Return convention**: `(True, [])` on success, `(False, failures)` on failure
where `failures` is a list of human-readable sentences describing each missing
artifact.

**Implementation** (within the function body, after the existing local variables):

- Add `failures: list[str] = []` after line 131 (`phase_is_1c = …`).
- At each `return False`, replace with `failures.append(…)` followed by a
  single `return (len(failures) == 0, failures)` at the end of each phase block.
- At each `return True`, replace with `return (True, [])`.

The `except Exception: return False` at line 237–238 becomes two distinct
returns — one for suppressed exceptions, another for unmatched phase keys:

```python
    except Exception:
        return (False, [f"Internal error during artifact check for phase '{original_phase}'"])
    # No phase_key branch matched (e.g., unknown phase like "7", or phase="4" with finding=None)
    return (False, [f"No completion gate defined for phase '{original_phase}'"])
```

The `except` path reports an internal error (genuinely unexpected).  The
fallthrough after the try/except reports that no gate logic exists for the
given phase — a distinct and more informative message that avoids misleading
implementers or users into thinking an exception was raised.

Detailed per-phase changes follow.

##### Phase 1 / 1a / 1b / 1c (lines 136–174)

Each subphase block currently returns `True` or `False`.  Convert each to
accumulate failures and return the tuple.  Example for phase 1a (lines 143–145):

```python
# OLD (line 145):
return any(_path_is_fresh(p, run_start_time) for p in paths_1a)

# NEW:
fresh_1a = any(_path_is_fresh(p, run_start_time) for p in paths_1a)
if not fresh_1a:
    failures.append("Missing: itemdb/notes/ — no phase-1a required notes "
                    "(target-profile.md, build-model.md, codeql-plan.yml) "
                    "created or updated during this run")
return (len(failures) == 0, failures)
```

Apply the same pattern to 1b (lines 149–150), 1c (lines 155–158), and the
monolith phase-1 block (lines 160–174).

##### Phase 2 / sweep (lines 175–183)

This is the key change.  The gate is relaxed from `pending_fresh AND summary_fresh`
to `summary_fresh` alone.  `pending_fresh` is still computed for diagnostics.

```python
# OLD (lines 175-183):
elif phase_key in ("2", "sweep"):
    pending_dir = finding_status_dir("PENDING")
    pending_fresh = False
    if pending_dir.exists():
        pending_fresh = any(f.name.endswith(".md") and f.name != ".gitkeep"
                            and f.stat().st_mtime >= run_start_time
                            for f in pending_dir.iterdir())
    import glob as _glob
    run_summaries = _glob.glob(str(ROOT / "runs" / "phase-2-summary*.md"))
    summary_fresh = any(Path(p).stat().st_mtime >= run_start_time
                        for p in run_summaries)
    return pending_fresh and summary_fresh

# NEW:
elif phase_key in ("2", "sweep"):
    import glob as _glob
    run_summaries = _glob.glob(str(ROOT / "runs" / "phase-2-summary*.md"))
    summary_fresh = any(Path(p).stat().st_mtime >= run_start_time
                        for p in run_summaries)
    if not summary_fresh:
        failures.append(
            "Missing: runs/phase-2-summary-*.md — run summary was not "
            "created or updated")
    pending_dir = finding_status_dir("PENDING")
    if pending_dir.exists():
        has_fresh_finding = any(
            f.name.endswith(".md") and f.name != ".gitkeep"
            and f.stat().st_mtime >= run_start_time
            for f in pending_dir.iterdir())
        if has_fresh_finding:
            pass  # diagnostic: findings created — logged below if needed
    return (len(failures) == 0, failures)
```

##### Phase 3 (lines 184–187)

```python
# OLD:
elif phase_key == "3":
    import glob as _glob
    run_summaries = _glob.glob(str(ROOT / "runs" / "phase-3-summary-*.md"))
    return any(Path(p).stat().st_mtime >= run_start_time for p in run_summaries)

# NEW:
elif phase_key == "3":
    import glob as _glob
    run_summaries = _glob.glob(str(ROOT / "runs" / "phase-3-summary-*.md"))
    summary_fresh = any(Path(p).stat().st_mtime >= run_start_time
                        for p in run_summaries)
    if not summary_fresh:
        failures.append(
            "Missing: runs/phase-3-summary-*.md — run summary was not "
            "created or updated")
    return (len(failures) == 0, failures)
```

##### Phase 4 (lines 188–196)

Add failure detail when evidence or finding is missing:

```python
# OLD (lines 196):
return evidence_fresh and finding_is_fresh

# NEW:
if not evidence_fresh:
    failures.append(
        f"Missing: itemdb/evidence/{finding}/ — no evidence files "
        "created or updated during this run")
if not finding_is_fresh:
    failures.append(
        f"Missing: itemdb/findings/*/{finding}*.md — finding file "
        "not created or updated during this run")
return (len(failures) == 0, failures)
```

##### Phase 5 (lines 197–231)

Apply the same per-condition failure detail pattern.  For each `return False`
path, append a specific message to `failures` and at the end return the tuple.
For existing `return True` paths, return `(True, [])`.

##### Phase 6 (lines 232–236)

```python
# OLD (lines 234-236):
if reports_dir.exists():
    return any(f.name.endswith(".md") and f.name != ".gitkeep"
               and f.stat().st_mtime >= run_start_time
               for f in reports_dir.iterdir())
return False

# NEW:
if reports_dir.exists():
    fresh_report = any(f.name.endswith(".md") and f.name != ".gitkeep"
                       and f.stat().st_mtime >= run_start_time
                       for f in reports_dir.iterdir())
    if fresh_report:
        return (True, [])
failures.append("Missing: itemdb/reports/ — no report files created "
                "or updated during this run")
return (False, failures)
```

#### C.2: Update `build_phase_resume_prompt` signature and body

**Current signature** (line 289):
```python
def build_phase_resume_prompt(
    phase: str,
    finding: str | None,
    reason: str,
    step_finish_count: int,
) -> str:
```

**New signature**:
```python
def build_phase_resume_prompt(
    phase: str,
    finding: str | None,
    reason: str,
    step_finish_count: int,
    failure_details: list[str] | None = None,
) -> str:
```

The new parameter defaults to `None` so existing callers that don't pass it
still work (only `harness.py` will pass it after Group D changes).

**New body logic** (replaces lines 296–305):

When `failure_details` is a non-empty list, inject the missing-artifact block
between the cutoff notice and the checklist:

```python
def build_phase_resume_prompt(
    phase: str,
    finding: str | None,
    reason: str,
    step_finish_count: int,
    failure_details: list[str] | None = None,
) -> str:
    checklist = "\n".join(f"- {line}" for line in phase_checklist_lines(phase, finding))

    lines = [
        "Your previous run completed but did not produce all required artifacts.",
        "",
        f"Observed finish reason: {reason}.",
        f"Completed loops before cutoff: {step_finish_count}.",
    ]

    if failure_details:
        lines.append("")
        lines.append("Missing required artifacts:")
        for detail in failure_details:
            lines.append(f"- {detail}")
        lines.append("")
        lines.append(
            "Fix only these missing items. Do not redo completed work."
        )
    else:
        lines.append("")
        lines.append(
            "Treat your prior work as partial. First, briefly reassess "
            "what remains unfinished for this phase. Then complete only "
            "the remaining required work. Do not restart from scratch "
            "unless necessary."
        )

    lines.append("")
    lines.append(f"Phase {phase} completion checklist:")
    lines.append(checklist)
    lines.append("")
    lines.append(
        "Before ending, verify that the required durable artifacts for "
        "this phase exist, are updated, and are internally consistent."
    )

    return "\n".join(lines)
```

#### C.3: Update `phase_checklist_lines` for phase 2

The existing checklist line (lines 254–258) mentions findings.  Add the
run-summary requirement explicitly so it's visible in both the initial prompt
and the resume:

```python
# OLD:
if str(phase) in ("2", "sweep"):
    return [
        f"Create or update precise findings under {FINDINGS_ROOT.relative_to(ROOT)}/PENDING/.",
        "Each finding must identify affected code, trust-boundary/source-to-sink reasoning, attackability, impact, validation plan, and counter-analysis placeholder.",
        "Do not stop until the new or updated findings are durable on disk.",
    ]

# NEW:
if str(phase) in ("2", "sweep"):
    return [
        f"Create or update precise findings under {FINDINGS_ROOT.relative_to(ROOT)}/PENDING/.",
        "Each finding must identify affected code, trust-boundary/source-to-sink reasoning, attackability, impact, validation plan, and counter-analysis placeholder.",
        "If no new vulnerabilities are found, document this in the run summary rather than creating placeholder findings.",
        f"Write a run summary to runs/phase-2-summary-YYYY-MM-DD-HHMMSS.md using templates/run-summary.md.",
        "Do not stop until the run summary is durable on disk.",
    ]
```

The key additions:
- Guidance for the "no new vulnerabilities" case (creates a legitimate path).
- Explicit run-summary requirement in the checklist so it appears in resume prompts.

### Group D — Runtime callers

Targeted changes to capture failure details and pipe them to the resume prompt
builder.  The return type change in Group C must be handled at every runtime
call site; otherwise non-empty tuples will be treated as truthy even when the
phase failed.

#### D.0: Update all call sites

Before editing, verify the runtime call sites with:

```bash
rg "check_phase_graceful_completion\(" tools/codecome tools/phases
```

Expected runtime callers after Group C:

- `tools/codecome/harness.py` — three call sites.
- `tools/codecome/phase_1.py` — one subphase call site.
- `tools/phases/completion.py` — function definition only.

All caller sites must unpack `(phase_ok, phase_failures)` before using the
result in a boolean condition.

#### `tools/codecome/harness.py`

Four targeted changes to capture failure details and pipe them to the resume
prompt builder.

#### D.1: Declare `phase_failures` and `phase_ok` variables (near line 135)

Insert after the existing local variable declarations (after `finish_warning`):

```python
phase_failures: list[str] = []
phase_ok: bool = False  # defensive default; assigned in D.2 or D.3 before use in D.3b
```

`phase_ok` must be declared here because D.3b references it, and we need a
safe default in case future control-flow changes skip both D.2 and D.3.

#### D.2: Lines 248–263 — capture return from `check_phase_graceful_completion` while preserving short-circuit

The original code uses a compound `and` that short-circuits: the filesystem
check in `check_phase_graceful_completion` is only invoked when
`last_finish_reason in _FINISH_MID_TURN and last_permission_error is None`.

The restructuring must preserve this short-circuit to avoid unconditional
filesystem stat calls in paths that don't need them.

```python
# OLD (lines 248-263):
if finish_warning is not None:
    if (
        last_finish_reason in _FINISH_MID_TURN
        and last_permission_error is None
        and check_phase_graceful_completion(args.phase, args.finding, RUN_START_TIME)
    ):
        msg = (...)
        out.success(msg)
        finish_warning = None
        last_finish_reason = "graceful_forgiveness"
    else:
        returncode = 2

# NEW:
if finish_warning is not None:
    if (
        last_finish_reason in _FINISH_MID_TURN
        and last_permission_error is None
    ):
        phase_ok, phase_failures = check_phase_graceful_completion(
            args.phase, args.finding, RUN_START_TIME)
        if phase_ok:
            msg = (
                f"CodeCome observed a mid-turn model/provider cutoff for Phase {args.phase} after {step_finish_count} "
                "completed loops, but expected durable artifacts were written during "
                "the run. Treating the phase as complete enough to run validation and auto-repair."
            )
            out.success(msg)
            finish_warning = None
            last_finish_reason = "graceful_forgiveness"
        else:
            returncode = 2
    else:
        returncode = 2
```

This nests the `check_phase_graceful_completion` call inside the first two
guard conditions, so it is never called when `last_finish_reason` is not
mid-turn or when a permission error is present.

#### D.3: Lines 265–267 — same treatment for terminal-OK path

```python
# OLD (lines 265-267):
if last_finish_reason in _FINISH_TERMINAL_OK:
    if not check_phase_graceful_completion(str(args.phase), args.finding,
                                           RUN_START_TIME):

# NEW:
if last_finish_reason in _FINISH_TERMINAL_OK:
    phase_ok, phase_failures = check_phase_graceful_completion(
        str(args.phase), args.finding, RUN_START_TIME)
    if not phase_ok:
```

#### D.3b: Lines 310–315 — use the captured terminal-OK result in auto-resume predicate

The retry predicate currently calls `check_phase_graceful_completion` inline as
a bool.  After Group C, `not (False, failures)` is always `False`, so terminal
OK runs with missing artifacts would skip auto-resume.

```python
# OLD (lines 310-315):
if returncode == 2 and (
    last_finish_reason in _FINISH_MID_TURN
    or (
        last_finish_reason in _FINISH_TERMINAL_OK
        and not check_phase_graceful_completion(str(args.phase), args.finding, RUN_START_TIME)
    )
):

# NEW:
if returncode == 2 and (
    last_finish_reason in _FINISH_MID_TURN
    or (last_finish_reason in _FINISH_TERMINAL_OK and not phase_ok)
):
```

`phase_ok` is assigned in D.3 before this block for terminal-OK paths.  Keep
`phase_failures` from D.3 so the resume prompt receives the missing-artifact
details in D.4.

#### D.4: Line 326 — pass failures to resume prompt builder

```python
# OLD (line 326):
prompt = build_phase_resume_prompt(
    args.phase, args.finding, last_finish_reason, step_finish_count
)

# NEW:
prompt = build_phase_resume_prompt(
    args.phase, args.finding, last_finish_reason, step_finish_count,
    failure_details=phase_failures if phase_failures else None,
)
```

Note: pass `None` when the list is empty so the resume prompt uses the
existing generic wording.  When the list is non-empty, the targeted
"Missing required artifacts:" block is rendered instead.

#### `tools/codecome/phase_1.py`

##### D.5: Line 630 — unpack the subphase completion check (preserving short-circuit)

Phase 1 subphase mode also consumes `check_phase_graceful_completion` in a
boolean `and` condition.  Without this update, `(False, failures)` is truthy
and mid-turn forgiveness would be granted even when required subphase artifacts
are missing.

The same short-circuit preservation from D.2 applies here: nest the call inside
the preceding guard conditions.

```python
# OLD (lines 626-641):
if finish_warning is not None:
    if (
        (not any_step_finish_seen or last_finish_reason in _FINISH_MID_TURN)
        and last_permission_error is None
        and check_phase_graceful_completion(phase_id, finding, subphase_start_time)
    ):
        msg = (...)
        out.success(msg)
        finish_warning = None
        last_finish_reason = "graceful_forgiveness"
    else:
        returncode = 2

# NEW:
if finish_warning is not None:
    if (
        (not any_step_finish_seen or last_finish_reason in _FINISH_MID_TURN)
        and last_permission_error is None
    ):
        phase_ok, phase_failures = check_phase_graceful_completion(
            phase_id, finding, subphase_start_time)
        if phase_ok:
            msg = (
                f"CodeCome observed an incomplete model/provider completion signal for Phase {phase_id} after "
                f"{step_finish_count} completed loops, but expected durable artifacts were written during "
                "the run. Treating the subphase as complete enough to run validation and auto-repair."
            )
            out.success(msg)
            finish_warning = None
            last_finish_reason = "graceful_forgiveness"
        else:
            returncode = 2
    else:
        returncode = 2
```

##### D.5b: Line 764 — wire `phase_failures` into the resume prompt

The resume prompt call at line 764 must pass `failure_details` so that
subphase auto-resumes get targeted "Missing required artifacts:" messaging
rather than the generic wording.

```python
# OLD (line 764):
prompt = build_phase_resume_prompt(
    phase_id, finding, last_finish_reason, step_finish_count,
)

# NEW:
prompt = build_phase_resume_prompt(
    phase_id, finding, last_finish_reason, step_finish_count,
    failure_details=phase_failures if phase_failures else None,
)
```

##### D.5c: Asymmetry with `harness.py` — intentional, documented

Unlike `harness.py` (D.3/D.3b), `phase_1.py`'s retry block at line 753 only
triggers auto-resume for `_FINISH_MID_TURN`.  It does NOT auto-resume on
terminal-OK with missing artifacts.

This is intentional: phase-1 subphases have simpler gates (often just "any
file in this list was freshened") and the orchestrator `run_phase_1()` handles
subphase failure by stopping progression rather than retrying.  If a terminal-OK
run fails the gate in a subphase, the overall phase-1 exits with error and the
user re-runs.

No code change is needed here, but this asymmetry should be understood during
implementation to avoid mistakenly "fixing" the retry predicate.

### Group E — Tests

Update tests that assert the old boolean return value from
`check_phase_graceful_completion`.

Affected tests:

- `tests/test_phases_completion.py` lines 114–117, 147, and 155.
- `tests/test_phase_graceful_completion_subphases.py` lines 30–151.

Change success assertions from:

```python
result = check_phase_graceful_completion(...)
assert result is True
```

to:

```python
ok, failures = check_phase_graceful_completion(...)
assert ok is True
assert failures == []
```

Change failure assertions from:

```python
result = check_phase_graceful_completion(...)
assert result is False
```

to:

```python
ok, failures = check_phase_graceful_completion(...)
assert ok is False
assert failures
```

Where practical, assert that `failures` contains the expected artifact family
or path fragment, such as `runs/phase-2-summary`, `sandbox-plan.md`,
`itemdb/notes/`, or `itemdb/evidence/<finding-id>/`.

---

## 4. Verification checklist

After implementation, confirm:

| # | Test | Expected result |
|---|------|-----------------|
| 1 | `make phase-2` — model creates 0 findings but writes run-summary | Passes (previously failed) |
| 2 | `make phase-2` — model creates findings but forgets run-summary | Fails with exit 2; auto-resume prompt reads "Missing: runs/phase-2-summary-*" |
| 3 | `make phase-2` — model creates no findings and no summary | Fails; auto-resume lists the missing summary |
| 4 | `make phase-3` — unchanged behavior, gate unchanged | Still passes (phase 3 was already ok) |
| 5 | `make phase-4 FINDING=CC-0001` — no evidence created | Fails; auto-resume lists missing evidence dir |
| 6 | All `make phase-X` runs — summary files use timestamped names | No overwrite on rerun of same phase |
| 7 | Chat mode with auditor agent (`make chat AGENT=auditor`) | Agent file no longer contains "when practical" hedge |
| 8 | `make frontmatter` | Frontmatter auto-correction path is unchanged (uses its own retry block at harness line 279) |
| 9 | `pytest tests/test_phases_completion.py tests/test_phase_graceful_completion_subphases.py` | Tuple-return tests pass |
| 10 | `make tests` | Full local quality gate passes |

---

## 5. Files touched

| File | Group | Summary |
|------|-------|---------|
| `.opencode/agents/auditor.md`         | A | Remove run-summary; add delegating note |
| `.opencode/agents/reviewer.md`        | A | Remove run-summary; add delegating note |
| `.opencode/agents/validator.md`       | A | Remove run-summary; add delegating note |
| `.opencode/agents/exploiter.md`       | A | Remove run-summary; add delegating note |
| `.opencode/agents/recon.md`           | A | Remove run-summary; add delegating note |
| `prompts/phase-1a-profile.md`         | B | Timestamp in summary path |
| `prompts/phase-1b-recon.md`           | B | Timestamp in summary path |
| `prompts/phase-1c-sandbox.md`         | B | Timestamp in summary path |
| `prompts/phase-2-audit.md`            | B | Timestamp in summary path |
| `prompts/phase-4-validate.md`         | B | Timestamp in summary path |
| `prompts/phase-5-exploit.md`          | B | Timestamp in summary path |
| `prompts/phase-6-report.md`           | B | Timestamp in summary path |
| `tools/phases/completion.py`          | C | Enriched return; relaxed gate; updated resume prompt; updated checklist |
| `tools/codecome/harness.py`           | D | Capture failure details; pass to resume prompt |
| `tools/codecome/phase_1.py`           | D | Unpack tuple return in subphase graceful-completion check |
| `tests/test_phases_completion.py`     | E | Update graceful-completion assertions for tuple return |
| `tests/test_phase_graceful_completion_subphases.py` | E | Update subphase graceful-completion assertions for tuple return |

---

## 6. Non-goals

- Chat mode gating — chat mode has no harness gating and does not require a
  run summary.  If run-summary support for chat mode is desired later, add a
  "## Run summary" section to `prompts/chat-initial.md`.

- Phase 1 multi-subphase gating — phase 1 already has subphase-specific
  artifact sets (1a, 1b, 1c).  Those are preserved as-is; only the failure
  reporting format is enriched.

- Models that hallucinate findings — a model that invents vulnerabilities
  from thin air is a model quality issue, not a harness issue.

- Integration tests for the new harness behavior — the existing test suite
  (`make tests`) exercises harness paths; specific resume-prompt tests
  should be added but are tracked separately.

---

## 7. Rollback / risk

All changes are additive or backward-compatible:

- `check_phase_graceful_completion` return type changes from `bool` to
  `tuple[bool, list[str]]`.  Runtime callers in `harness.py` and `phase_1.py`,
  plus tests, are updated in Groups D and E.  No known external callers remain.

- The phase-2 gate relaxes from `pending_fresh AND summary_fresh` to
  `summary_fresh` alone.  This cannot cause false passes because the run
  summary must still exist.  Phase 3 (counter-analysis) provides a second
  review gate.

- Timestamped paths in phase prompts are guidance to the model.  The glob
  patterns in `completion.py` already accept wildcards, so old non-timestamped
  files still match.

- Agent file changes are cosmetic (remove one line, add one line).  No
  behavioral change for phase mode since the phase prompt already contains
  the requirements.

---

## 8. Follow-up: source-of-truth alignment (review feedback)

After the initial implementation, the owner review (and a Copilot pass)
flagged that the "phase prompt is the source of truth" rule was not
fully enforced by the completion gates.  The original plan explicitly
deferred subphase summary gating as a non-goal and did not gate
phases 4/5/6 on summary either; the review pushed back on that decision.

This follow-up closes the gap:

- Subphase gates (1a, 1b, 1c) now also check for a fresh
  `runs/phase-X-summary*.md` via the new helper
  `_append_run_summary_check` in `tools/phases/completion.py`.
- Phase 4 and 5 gates now also check for a fresh
  `runs/phase-{4|5}-<finding>-summary*.md`.
- Phase 6 gate now also checks for a fresh `runs/phase-6-summary*.md`.
- Phase 3 resume checklist now includes a run-summary line in
  `phase_checklist_lines`, matching the already-enforced gate check.
- The phase-2 diagnostic message and glob now use the same pattern
  (no mandatory hyphen after `summary`).  Both are
  `runs/phase-2-summary*.md`.
- The `build_phase_resume_prompt` opening line is no longer a
  universal "Your previous run completed".  A private helper
  `_resume_opener_for_reason` classifies the recorded reason
  (`"infrastructure_error"`, mid-turn cutoffs, finish failures,
  `graceful_forgiveness`, terminal-OK with missing artifacts, or
  unknown) and renders a context-specific opener.
- `tools/codecome/phase_1.py` defensively initializes
  `phase_failures: list[str] = []` and `phase_ok: bool = False` at
  the top of `_run_subphase`, mirroring the pattern already
  established in `tools/codecome/harness.py:137-138`.  This eliminates
  the `UnboundLocalError` risk on the path that builds the resume
  prompt when the run was set to `returncode = 2` without ever
  entering the graceful-completion branch.

The expansion is deliberately conservative: summary checks were
already implied by the prompts; the gates simply now enforce them.
The behavior change for subphases (1a/1b/1c) is the only
user-visible addition — those subphases now fail the auto-resume if
no summary is written.  This matches the contract documented in each
subphase prompt.

### Files affected

- `tools/phases/completion.py` — added `_run_summary_is_fresh` and
  `_append_run_summary_check` helpers, expanded 1a/1b/1c/4/5/6 gates,
  added phase-3 checklist summary lines, fixed phase-2 diagnostic
  string, added `_resume_opener_for_reason` helper, replaced the
  hardcoded opener in `build_phase_resume_prompt`.
- `tools/codecome/phase_1.py` — defensive init of `phase_failures`
  and `phase_ok`.
- `tests/test_phases_completion.py` — new tests:
  `TestPhase2GlobStringMatchesDiagnostic`,
  `TestResumePromptOpenerDistinguishesReasons`,
  `TestSubphaseGatesRequireRunSummary`,
  `TestPhase45And6GatesRequireRunSummary`,
  `TestPhase3ChecklistMentionsRunSummary`.  Existing test fixture
  for the phase-2 resume prompt updated to use the unhyphenated
  glob.
- `tests/test_phase_graceful_completion_subphases.py` — positive
  tests now create a fresh `runs/phase-1{a,b,c}-summary.md` to keep
  passing under the stricter gate; negative tests additionally
  assert the new summary failure fragment.

### Verification

`make tests`: 676 → 691 tests pass (15 new).  The pre-existing
`itemdb/notes/threat-model.md` heading-set warning from
`check-phase-artifacts` is unrelated to this change (verified by
re-running the check with the changes stashed).
