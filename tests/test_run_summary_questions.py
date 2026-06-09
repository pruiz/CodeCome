from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codecome.run_summary_questions import (
    OpenQuestion,
    RunSummaryQuestions,
    find_latest_summary,
    parse_summary,
    _extract_section,
    _is_none_content,
    _parse_questions,
    _parse_hints,
)


# ---------------------------------------------------------------------------
# Helper: create a summary file
# ---------------------------------------------------------------------------

def _write_summary(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixture content
# ---------------------------------------------------------------------------

_SUMMARY_WITH_QUESTIONS = """\
# CodeCome Run Summary

Date: 2026-06-09
Phase: reconnaissance

# Goal

Test run.

# Open questions for the user

None that block the phase. The following are optional follow-ups:

## Question: Should we enable feature X?

- Why it matters: Feature X changes the scope significantly.
- Affects: Phase 2 and Phase 4.
- Suggested answer format: A yes/no with rationale.

## Question: Which target should get priority?

- Why it matters: Resource allocation.
- Affects: Phase 2 findings.
- Suggested answer format: A list of target names.

# Re-run prompt hints

```
PROMPT_EXTRA="Focus on auth modules"
```

# Limitations

None.
"""

_SUMMARY_WITH_NONE_SECTIONS = """\
# CodeCome Run Summary

# Open questions for the user

None.

# Re-run prompt hints

None.

# Limitations

None.
"""

_SUMMARY_NO_QUESTIONS_SECTION = """\
# CodeCome Run Summary

# Goal

Test run.

# Limitations

None.
"""

_SUMMARY_QUESTIONS_ONLY = """\
# CodeCome Run Summary

# Open questions for the user

## Question: Test question

- Why it matters: Testing.
- Affects: Tests.
- Suggested answer format: Text.

# Limitations

None.
"""

_SUMMARY_HINTS_ONLY = """\
# CodeCome Run Summary

# Re-run prompt hints

Run with PROMPT_EXTRA="focus on foo"

# Limitations

None.
"""

_SUMMARY_WITH_NONE_PLACEHOLDER_QUESTION = """\
# CodeCome Run Summary

# Open questions for the user

None that block completion.

## Question: <none — Phase 1b is unblocked>

- Why it matters: Not applicable.
- Affects: Nothing.
- Suggested answer format: N/A.

# Re-run prompt hints

None.
"""

_SUMMARY_VARIED_FORMATS = """\
# CodeCome Run Summary

# Open questions for the user

Intro text here.

## Question: First real question

* Why it matters: Important stuff.
* Affects: Everything.
* Suggested answer format: Free text.

## Question: None

- Why it matters: xxx
- Affects: yyy

## Question: second

- Why it matters: Also important.
- Affects: Phase 3.

# Re-run prompt hints

Use PROMPT_EXTRA for re-runs.

# Limitations

None.
"""

_SUMMARY_WITH_CODE_BLOCK_HINTS = """\
# CodeCome Run Summary

# Open questions for the user

None.

# Re-run prompt hints

```
# Run again with:
CODECOME_THINKING=1 make phase-2
```
"""


# ---------------------------------------------------------------------------
# _extract_section tests
# ---------------------------------------------------------------------------

class TestExtractSection:
    def test_extract_existing_section(self):
        body = _extract_section(_SUMMARY_WITH_QUESTIONS, "Open questions for the user")
        assert body is not None
        assert "## Question: Should we enable feature X?" in body

    def test_extract_missing_section(self):
        body = _extract_section(_SUMMARY_NO_QUESTIONS_SECTION, "Open questions for the user")
        assert body is None

    def test_extract_section_stops_at_next_heading(self):
        body = _extract_section(_SUMMARY_WITH_QUESTIONS, "Open questions for the user")
        assert body is not None
        assert "# Limitations" not in body

    def test_extract_re_run_hints(self):
        body = _extract_section(_SUMMARY_WITH_QUESTIONS, "Re-run prompt hints")
        assert body is not None
        assert "PROMPT_EXTRA" in body

    def test_extract_hints_missing(self):
        body = _extract_section(_SUMMARY_NO_QUESTIONS_SECTION, "Re-run prompt hints")
        assert body is None


# ---------------------------------------------------------------------------
# _is_none_content tests
# ---------------------------------------------------------------------------

class TestIsNoneContent:
    def test_none(self):
        assert _is_none_content("None") is True

    def test_none_dot(self):
        assert _is_none_content("None.") is True

    def test_none_with_dash(self):
        assert _is_none_content("None — Phase 1b completed.") is True

    def test_none_with_text(self):
        assert _is_none_content("None that block the phase.") is True

    def test_na(self):
        assert _is_none_content("N/A") is True

    def test_empty(self):
        assert _is_none_content("") is True

    def test_whitespace(self):
        assert _is_none_content("   \n  ") is True

    def test_not_none(self):
        assert _is_none_content("Some questions here.") is False

    def test_question_none(self):
        assert _is_none_content("None") is True


# ---------------------------------------------------------------------------
# _parse_questions tests
# ---------------------------------------------------------------------------

class TestParseQuestions:
    def test_parses_multiple_questions(self):
        body = _extract_section(_SUMMARY_WITH_QUESTIONS, "Open questions for the user")
        assert body is not None
        questions = _parse_questions(body)
        assert len(questions) == 2

        assert questions[0].question == "Should we enable feature X?"
        assert questions[0].why_it_matters == "Feature X changes the scope significantly."
        assert questions[0].affects == "Phase 2 and Phase 4."
        assert questions[0].suggested_format == "A yes/no with rationale."

        assert questions[1].question == "Which target should get priority?"
        assert questions[1].why_it_matters == "Resource allocation."

    def test_skips_none_placeholder_question(self):
        body = _extract_section(
            _SUMMARY_WITH_NONE_PLACEHOLDER_QUESTION, "Open questions for the user"
        )
        assert body is not None
        questions = _parse_questions(body)
        assert len(questions) == 0

    def test_skips_plain_none_question(self):
        body = _extract_section(_SUMMARY_VARIED_FORMATS, "Open questions for the user")
        assert body is not None
        questions = _parse_questions(body)
        assert len(questions) == 2
        assert questions[0].question == "First real question"
        assert questions[1].question == "second"

    def test_handles_asterisk_bullets(self):
        body = _extract_section(_SUMMARY_VARIED_FORMATS, "Open questions for the user")
        assert body is not None
        questions = _parse_questions(body)
        assert questions[0].why_it_matters == "Important stuff."

    def test_empty_section_returns_empty(self):
        questions = _parse_questions("")
        assert questions == []

    def test_no_questions_in_section(self):
        questions = _parse_questions("Just some intro text, no questions.")
        assert questions == []


# ---------------------------------------------------------------------------
# _parse_hints tests
# ---------------------------------------------------------------------------

class TestParseHints:
    def test_parses_hints(self):
        body = _extract_section(_SUMMARY_WITH_QUESTIONS, "Re-run prompt hints")
        assert body is not None
        hints = _parse_hints(body)
        assert hints is not None
        assert "PROMPT_EXTRA" in hints

    def test_none_hints_returns_none(self):
        body = _extract_section(_SUMMARY_WITH_NONE_SECTIONS, "Re-run prompt hints")
        assert body is not None
        hints = _parse_hints(body)
        assert hints is None

    def test_empty_body_returns_none(self):
        hints = _parse_hints("")
        assert hints is None

    def test_none_text_returns_none(self):
        hints = _parse_hints("None.")
        assert hints is None


# ---------------------------------------------------------------------------
# parse_summary tests
# ---------------------------------------------------------------------------

class TestParseSummary:
    def test_parse_with_questions_and_hints(self, tmp_path):
        p = tmp_path / "summary.md"
        _write_summary(p, _SUMMARY_WITH_QUESTIONS)
        result = parse_summary(p)
        assert result.has_content()
        assert len(result.open_questions) == 2
        assert result.rerun_hints is not None
        assert "PROMPT_EXTRA" in result.rerun_hints

    def test_parse_with_none_sections(self, tmp_path):
        p = tmp_path / "summary.md"
        _write_summary(p, _SUMMARY_WITH_NONE_SECTIONS)
        result = parse_summary(p)
        assert not result.has_content()
        assert result.open_questions == []
        assert result.rerun_hints is None

    def test_parse_missing_sections(self, tmp_path):
        p = tmp_path / "summary.md"
        _write_summary(p, _SUMMARY_NO_QUESTIONS_SECTION)
        result = parse_summary(p)
        assert not result.has_content()

    def test_parse_questions_only(self, tmp_path):
        p = tmp_path / "summary.md"
        _write_summary(p, _SUMMARY_QUESTIONS_ONLY)
        result = parse_summary(p)
        assert result.has_content()
        assert len(result.open_questions) == 1
        assert result.rerun_hints is None

    def test_parse_hints_only(self, tmp_path):
        p = tmp_path / "summary.md"
        _write_summary(p, _SUMMARY_HINTS_ONLY)
        result = parse_summary(p)
        assert result.has_content()
        assert result.open_questions == []
        assert result.rerun_hints is not None

    def test_parse_with_code_block_hints(self, tmp_path):
        p = tmp_path / "summary.md"
        _write_summary(p, _SUMMARY_WITH_CODE_BLOCK_HINTS)
        result = parse_summary(p)
        assert result.has_content()
        assert result.rerun_hints is not None
        assert "CODECOME_THINKING=1" in result.rerun_hints


# ---------------------------------------------------------------------------
# RunSummaryQuestions.has_content tests
# ---------------------------------------------------------------------------

class TestHasContent:
    def test_has_content_true(self):
        r = RunSummaryQuestions(
            open_questions=[OpenQuestion(question="test")],
        )
        assert r.has_content()

    def test_has_content_true_hints_only(self):
        r = RunSummaryQuestions(rerun_hints="Run again")
        assert r.has_content()

    def test_has_content_false_empty(self):
        r = RunSummaryQuestions()
        assert not r.has_content()

    def test_has_content_false_empty_lists(self):
        r = RunSummaryQuestions(open_questions=[], rerun_hints=None)
        assert not r.has_content()


# ---------------------------------------------------------------------------
# find_latest_summary tests
# ---------------------------------------------------------------------------

class TestFindLatestSummary:
    def test_finds_summary_without_finding(self, tmp_path, monkeypatch):
        import codecome.run_summary_questions as rsm
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        monkeypatch.setattr(rsm, "ROOT", tmp_path)

        p1 = runs_dir / "phase-2-summary-older.md"
        p2 = runs_dir / "phase-2-summary-newer.md"
        p1.write_text("old")
        p2.write_text("new")
        time.sleep(0.01)
        p2.write_text("newer")

        result = find_latest_summary("2")
        assert result is not None
        assert result.name == "phase-2-summary-newer.md"

    def test_finds_summary_with_finding(self, tmp_path, monkeypatch):
        import codecome.run_summary_questions as rsm
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        monkeypatch.setattr(rsm, "ROOT", tmp_path)

        p = runs_dir / "phase-4-CC-0001-summary-test.md"
        p.write_text("content")

        result = find_latest_summary("4", "CC-0001")
        assert result is not None
        assert result.name == "phase-4-CC-0001-summary-test.md"

    def test_returns_none_when_no_match(self, tmp_path, monkeypatch):
        import codecome.run_summary_questions as rsm
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        monkeypatch.setattr(rsm, "ROOT", tmp_path)

        result = find_latest_summary("9")
        assert result is None

    def test_returns_none_when_dir_missing(self, tmp_path, monkeypatch):
        import codecome.run_summary_questions as rsm
        monkeypatch.setattr(rsm, "ROOT", tmp_path)
        result = find_latest_summary("2")
        assert result is None
