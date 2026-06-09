# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Parse run-summary Markdown files for open questions and re-run hints.

Used by the phase harness to extract user-facing questions from run
summaries and render them at the end of each phase.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from codecome.config import ROOT

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

_SECTION_HEADING_RE = re.compile(r"^#\s")


@dataclass
class OpenQuestion:
    question: str
    why_it_matters: str = ""
    affects: str = ""
    suggested_format: str = ""


@dataclass
class RunSummaryQuestions:
    open_questions: list[OpenQuestion] = field(default_factory=list)
    rerun_hints: str | None = None

    def has_content(self) -> bool:
        return bool(self.open_questions) or bool(self.rerun_hints)


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------

_SECTION_HEADING_RE = re.compile(r"^#\s")
_FENCE_RE = re.compile(r"^(```+|~~~+)")


def _extract_section(text: str, heading: str) -> str | None:
    """Extract the body of a named top-level section.

    Returns everything from the heading line (exclusive) until the next
    ``#`` heading at the same level (outside fenced code blocks), or end
    of text.
    """
    heading_line = f"# {heading}"
    heading_pattern = re.compile(
        r"^" + re.escape(heading_line) + r"\s*$", re.MULTILINE
    )
    m = heading_pattern.search(text)
    if not m:
        return None
    start = m.end()

    lines = text[start:].split("\n")
    in_fence = False
    fence_delim: str = ""

    end_idx = 0
    for line in lines:
        stripped = line.strip()
        fm = _FENCE_RE.match(stripped)
        if fm:
            delim = fm.group(1)
            if not in_fence:
                in_fence = True
                fence_delim = delim
            elif delim.startswith(fence_delim) and len(delim) >= len(fence_delim):
                in_fence = False
        elif not in_fence and _SECTION_HEADING_RE.match(line):
            break
        end_idx += len(line) + 1

    body = text[start : start + end_idx].rstrip("\n")
    return body if body else None


def _is_none_content(body: str) -> bool:
    """Check whether the extracted section body represents no content."""
    stripped = body.strip()
    if not stripped:
        return True
    first_line = stripped.split("\n", 1)[0].strip().lower()
    return first_line in (
        "none",
        "none.",
        "none —",
        "n/a",
    ) or first_line.startswith("none ")


# ---------------------------------------------------------------------------
# Question parsing
# ---------------------------------------------------------------------------

_QUESTION_HEADING_RE = re.compile(r"^##\s+Question:\s*(.*)", re.MULTILINE)
_LIST_ITEM_RE = re.compile(
    r"^[-*]\s+(Why it matters|Affects|Suggested answer format):\s*(.*)",
    re.MULTILINE,
)


def _parse_questions(body: str) -> list[OpenQuestion]:
    """Parse OpenQuestion entries from the open-questions section body."""
    questions: list[OpenQuestion] = []

    # Split the body at each "## Question:" heading
    parts = re.split(r"^(?=##\s+Question:)", body, flags=re.MULTILINE)

    for part in parts:
        heading_match = _QUESTION_HEADING_RE.search(part)
        if not heading_match:
            continue

        question_text = heading_match.group(1).strip() or ""

        # Ignore question blocks where the heading text is effectively empty
        # or a none marker (e.g. "## Question: <none ...>")
        if not question_text or _is_none_content(question_text):
            continue
        # Skip placeholder-like questions: "<none", "None", "N/A"
        if question_text.strip().lower() in ("none", "<none", "n/a", "none."):
            continue
        if question_text.strip().lower().startswith(("<none", "none ")):
            continue

        q = OpenQuestion(question=question_text)

        for m in _LIST_ITEM_RE.finditer(part):
            field_name = m.group(1)
            value = m.group(2).strip()
            if field_name == "Why it matters":
                q.why_it_matters = value
            elif field_name == "Affects":
                q.affects = value
            elif field_name == "Suggested answer format":
                q.suggested_format = value

        questions.append(q)

    return questions


# ---------------------------------------------------------------------------
# Hints parsing
# ---------------------------------------------------------------------------

def _parse_hints(body: str) -> str | None:
    """Parse re-run hints from the section body."""
    stripped = body.strip()
    if not stripped or _is_none_content(stripped):
        return None
    return stripped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_summary(path: Path) -> RunSummaryQuestions:
    """Parse a run-summary Markdown file.

    Returns a :class:`RunSummaryQuestions` with any extracted open
    questions and re-run hints.
    """
    text = path.read_text(encoding="utf-8")

    questions_body = _extract_section(text, "Open questions for the user")
    hints_body = _extract_section(text, "Re-run prompt hints")

    open_questions: list[OpenQuestion] = []
    if questions_body is not None:
        open_questions = _parse_questions(questions_body)
        # Only treat as empty if there are no parsed questions AND the body
        # is effectively "none" content (avoids false negatives when intro
        # text starts with "None" but still has real questions after it).
        if not open_questions and _is_none_content(questions_body):
            open_questions = []

    rerun_hints: str | None = None
    if hints_body is not None:
        rerun_hints = _parse_hints(hints_body)

    return RunSummaryQuestions(
        open_questions=open_questions,
        rerun_hints=rerun_hints,
    )


def display_phase_questions(
    phase_id: str, finding: str | None = None
) -> None:
    """Find the latest run summary for *phase_id*, parse it, and render
    open questions and re-run hints to console.

    This is a no-op when no summary is found or when parsing fails.
    Intended to be called at the end of each phase.
    """
    from rendering.output import get_output

    summary_path = find_latest_summary(phase_id, finding)
    if not summary_path:
        return
    try:
        questions = parse_summary(summary_path)
    except Exception:
        return

    out = get_output(None)
    out.render_questions(questions)


def find_latest_summary(
    phase_id: str, finding: str | None = None
) -> Path | None:
    """Find the newest run-summary file for a phase.

    Globs ``runs/phase-{phase_id}[-{finding}]-summary*.md`` and returns
    the one with the highest modification time.
    """
    runs_dir = ROOT / "runs"

    # Build glob pattern:
    #   phase-2-summary*.md
    #   phase-4-CC-0001-summary*.md   (when finding is provided)
    if finding:
        pattern = f"phase-{phase_id}-{finding}-summary*.md"
    else:
        pattern = f"phase-{phase_id}-summary*.md"

    candidates = sorted(
        runs_dir.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None
