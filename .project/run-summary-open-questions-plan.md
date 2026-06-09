# Plan: Track reusable open questions and re-run hints across all phases

Issue: https://github.com/pruiz/CodeCome/issues/33

## Goal

Add first-class harness support for extracting Open Questions and Re-run Hints from run summaries, rendering them to console at the end of each phase, and ensuring all phase prompts require these sections.

## Current State

`templates/run-summary.md` already defines both sections:

```markdown
# Open questions for the user
## Question: <short question>
- Why it matters:
- Affects:
- Suggested answer format:

# Re-run prompt hints
If useful, provide a short copy/paste prompt...
```

But:
- Only Phase 1a and 1c prompts reference these sections (and only partially)
- No harness code parses or displays them
- No tests exist for extraction or rendering

## Detailed Implementation

### Step 1: Create `tools/codecome/run_summary_questions.py`

Parser module with:

```python
@dataclass
class OpenQuestion:
    question: str          # The question text
    why_it_matters: str    # From the "Why it matters" line
    affects: str           # From the "Affects" line
    suggested_format: str  # From the "Suggested answer format" line

@dataclass
class RunSummaryQuestions:
    open_questions: list[OpenQuestion]
    rerun_hints: str | None  # None when "None." or missing

    def has_content(self) -> bool:
        ...

def find_latest_summary(phase_id: str, finding: str | None = None) -> Path | None:
    """Glob runs/phase-{phase_id}[-{finding}]-summary*.md, return newest by mtime."""
    ...

def parse_summary(path: Path) -> RunSummaryQuestions:
    """Parse a run-summary markdown file, extracting open questions and rerun hints."""
    ...
```

Parsing rules:
- Find the `# Open questions for the user` heading, extract until next `#` heading
- Within that section, look for `## Question:` subheadings and extract subsequent list items
- For `# Re-run prompt hints`, extract the full body text
- If the hints body starts with "None." (case-insensitive after trim), return `None`
- Handle cases where either section is missing

### Step 2: Add rendering to `tools/rendering/output.py`

Add `render_questions()` method to `RenderOutput`:

```python
def render_questions(self, questions: RunSummaryQuestions) -> None:
    """Render open questions and re-run hints to console."""
    if not questions.has_content():
        return
    
    self.separator(tone=T.WARNING)
    self.section("Open questions from run summary", tone=T.WARNING)
    
    for q in questions.open_questions:
        # Render each question as a panel (rich) or indented block (plain)
        ...
    
    if questions.rerun_hints:
        self.section("Re-run prompt hints", tone=T.ACCENT)
        # Render hints in a code-style block
        ...
```

Use existing primitives: `Panel`, `separator()`, `section()`, `line()`, `segments()`.

### Step 3: Integrate into harness

**`harness.py:run_phase_mode()`** — at the end, after the success/failure reporting, before `return returncode`:

```python
# Display open questions from run summary (always, even on failure)
from codecome.run_summary_questions import find_latest_summary, parse_summary
summary_path = find_latest_summary(str(args.phase), args.finding)
if summary_path:
    try:
        questions = parse_summary(summary_path)
        out.render_questions(questions)
    except Exception:
        pass  # Don't fail the whole phase for summary display issues
```

**`phase_1.py:run_phase_1()`** — after the final success message, collect subphase summaries:

```python
# Display open questions from all subphase summaries
from codecome.run_summary_questions import find_latest_summary, parse_summary
for subphase in ("1a", "1b", "1c"):
    summary_path = find_latest_summary(subphase)
    if summary_path:
        try:
            questions = parse_summary(summary_path)
            out.render_questions(questions)
        except Exception:
            pass
```

### Step 4: Update phase prompts

For each prompt file, add explicit requirement language **before or in the `## Run summary` section**:

> You MUST fill in the `# Open questions for the user` and `# Re-run prompt hints` sections of the run summary template. If there are no open questions, write "None." Do not omit either section.

Files to update:

| File | Current mentions |
|------|-----------------|
| `prompts/phase-1a-profile.md` | L111: "Non-blocking open questions should go into the run summary file" — expand |
| `prompts/phase-1b-sandbox.md` | None — add |
| `prompts/phase-1c-recon.md` | L265-266: final response mentions; L270-274: run summary section — add requirement |
| `prompts/phase-2-audit.md` | None — add |
| `prompts/phase-3-review.md` | None — add |
| `prompts/phase-4-validate.md` | None — add |
| `prompts/phase-5-exploit.md` | None — add |
| `prompts/phase-6-report.md` | None — add |
| `prompts/sweep.md` | None — add |

### Step 5: Add tests

**New file: `tests/test_run_summary_questions.py`**

Test cases:
1. `test_parse_summary_with_questions` — fixture with multiple questions and hints
2. `test_parse_summary_with_none` — fixture with "None." in both sections
3. `test_parse_summary_missing_sections` — fixture without either heading
4. `test_has_content_true` / `test_has_content_false`
5. `test_find_latest_summary` — with temp files and different mtimes
6. `test_parse_question_extracts_fields` — verify each field is correctly extracted

**Add to `tests/test_rendering_output.py`**

Test cases:
1. `test_render_questions_plain_with_content` — output contains question text
2. `test_render_questions_plain_empty` — no output when no content
3. `test_render_questions_rich_with_content` — Rich panel contains question text
4. `test_render_questions_rich_empty` — no output when no content
5. `test_render_questions_with_hints` — hints appear in output
6. `test_render_questions_textual` — calls fake sink

### Step 6: No Makefile changes needed

Phases 2-6 go through `harness.py`. Phase 1 goes through `phase_1.py`. Sweeps call `run-agent.py` via subprocess (which uses `harness.py`). CodeQL repair also goes through the harness. All paths are covered.

## Files summary

**Create:**
- `tools/codecome/run_summary_questions.py`
- `tests/test_run_summary_questions.py`

**Modify:**
- `tools/rendering/output.py`
- `tools/codecome/harness.py`
- `tools/codecome/phase_1.py`
- `prompts/phase-1a-profile.md`
- `prompts/phase-1b-sandbox.md`
- `prompts/phase-1c-recon.md`
- `prompts/phase-2-audit.md`
- `prompts/phase-3-review.md`
- `prompts/phase-4-validate.md`
- `prompts/phase-5-exploit.md`
- `prompts/phase-6-report.md`
- `prompts/sweep.md`
- `tests/test_rendering_output.py`

## Order of execution

1. Create `tools/codecome/run_summary_questions.py` (parser)
2. Add `render_questions()` to `tools/rendering/output.py`
3. Integrate into `harness.py` and `phase_1.py`
4. Create `tests/test_run_summary_questions.py` and add rendering tests
5. Run tests to confirm everything works
6. Update all prompt files
7. Run full test suite
