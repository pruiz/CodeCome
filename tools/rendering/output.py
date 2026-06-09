# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
RenderOutput — semantic console output abstraction.

Provides a small facade above the existing rendering context and sink
system so that orchestration and CLI code can express output intent
(warn, success, header, detail) without branching on Rich availability or
importing Rich/ANSI backends directly.

Semantic tone tokens (T.SUCCESS, T.WARNING, …) are the canonical style
API.  They are independently mapped to Rich styles and ANSI constants.
"""

from __future__ import annotations

from typing import Any, Literal

import _colors as C
from rendering.context import RenderContext


# ---------------------------------------------------------------------------
# Tone constants
# ---------------------------------------------------------------------------

class T:
    """Semantic tone tokens for output styling.

    Use these constants with :meth:`RenderOutput.segments`, :meth:`RenderOutput.line`,
    and as keyword arguments to methods like :meth:`RenderOutput.header`.
    """

    PLAIN = "plain"
    HEADER = "header"
    SECTION = "section"
    DETAIL = "detail"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    STRONG_ERROR = "strong_error"
    ACCENT = "accent"


Tone = Literal[
    "plain",
    "header",
    "section",
    "detail",
    "info",
    "success",
    "warning",
    "error",
    "strong_error",
    "accent",
]
"""Type alias for valid semantic tone strings."""

Segment = tuple[str, Tone]
"""A styled segment: (text, tone)."""


# ---------------------------------------------------------------------------
# Backend tone maps
# ---------------------------------------------------------------------------

_RICH_TONES: dict[str, str | None] = {
    T.PLAIN: None,
    T.HEADER: "bold cyan",
    T.SECTION: "cyan",
    T.DETAIL: "dim",
    T.INFO: "cyan",
    T.SUCCESS: "green",
    T.WARNING: "yellow",
    T.ERROR: "red",
    T.STRONG_ERROR: "bold red",
    T.ACCENT: "bold cyan",
}

_ANSI_TONES: dict[str, str] = {
    T.PLAIN: "",
    T.HEADER: C.BOLD,
    T.SECTION: C.CYAN,
    T.DETAIL: C.DIM,
    T.INFO: C.CYAN,
    T.SUCCESS: C.GREEN,
    T.WARNING: C.YELLOW,
    T.ERROR: C.RED,
    T.STRONG_ERROR: C.BOLD_RED,
    T.ACCENT: C.BOLD_CYAN,
}

_SEPARATOR_WIDTH = 62


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _rich_tone(tone: str) -> str | None:
    return _RICH_TONES.get(tone, _RICH_TONES[T.PLAIN])


def _ansi_tone(tone: str) -> str:
    return _ANSI_TONES.get(tone, _ANSI_TONES[T.PLAIN])


def _colorize(text: str, tone: str) -> str:
    return C.colorize(text, _ansi_tone(tone))


# ---------------------------------------------------------------------------
# RenderOutput
# ---------------------------------------------------------------------------

class RenderOutput:
    """Semantic console output facade.

    Wraps a :class:`~rendering.context.RenderContext` and provides
    intent-driven output methods (:meth:`header`, :meth:`warn`,
    :meth:`success`, :meth:`error`, :meth:`detail`, :meth:`segments`, …)
    that render appropriately for the current sink mode (plain, rich,
    or textual).
    """

    def __init__(self, context: RenderContext) -> None:
        self._context = context

    @property
    def context(self) -> RenderContext:
        return self._context

    @property
    def sink(self) -> Any:
        return self._context.sink

    @property
    def rich(self) -> bool:
        return self._context.sink.mode in ("rich", "textual")

    @property
    def plain(self) -> bool:
        return self._context.sink.mode == "plain"

    # -- structural output -------------------------------------------------

    def header(self, title: str, *, tone: Tone = T.HEADER) -> None:
        """Print a major section header (Rich ``Rule``, plain ``C.header``)."""
        if self.rich:
            from rich.rule import Rule

            self.sink.write(Rule(title=title, style=_rich_tone(tone)))
        elif self.plain:
            self.sink.write_text(C.header(title))

    def section(self, title: str, *, tone: Tone = T.SECTION) -> None:
        """Print a secondary heading as styled text (no rule/separator)."""
        if self.rich:
            from rich.text import Text

            self.sink.write(Text(title, style=_rich_tone(tone)))
        elif self.plain:
            self.sink.write_text(_colorize(title, tone))

    def separator(self, *, tone: Tone = T.PLAIN) -> None:
        """Print a horizontal rule (Rich) or dashed line (plain)."""
        if self.rich:
            from rich.rule import Rule

            self.sink.write(Rule(style=_rich_tone(tone)))
        elif self.plain:
            # tone is intentionally ignored in plain mode;
            # ANSI-coloured dashed lines are visually noisy.
            self.sink.write_text(C.SYM_DASH * _SEPARATOR_WIDTH)

    # -- line output -------------------------------------------------------

    def line(self, text: str, *, tone: Tone = T.PLAIN) -> None:
        """Print a single styled line without status symbols."""
        if self.rich:
            from rich.text import Text

            self.sink.write(Text(text, style=_rich_tone(tone)))
        elif self.plain:
            self.sink.write_text(_colorize(text, tone))

    def segments(self, *parts: Segment) -> None:
        """Print a line composed of independently-styled segments.

        Each *part* is a ``(text, tone)`` pair.  Empty parts or empty
        segment text is skipped.  An empty call is a no-op.
        """
        if not parts:
            return
        if self.rich:
            from rich.text import Text

            text = Text()
            for value, tone in parts:
                if not value:
                    continue
                text.append(value, style=_rich_tone(tone))
            self.sink.write(text)
        elif self.plain:
            chunks: list[str] = []
            for value, tone in parts:
                if not value:
                    continue
                chunks.append(_colorize(value, tone))
            if chunks:
                self.sink.write_text("".join(chunks))

    # -- semantic status helpers -------------------------------------------

    def detail(self, text: str) -> None:
        """Print de-emphasised metadata (dim / de-emphasised)."""
        self.line(text, tone=T.DETAIL)

    def info(self, text: str) -> None:
        """Print an informational status line."""
        if self.rich:
            self.line(text, tone=T.INFO)
        elif self.plain:
            self.sink.write_text(C.info(text))

    def warn(self, text: str, *, symbol: bool = False) -> None:
        """Print a warning status line."""
        if self.rich:
            from rich.text import Text

            if symbol:
                self.sink.write(Text(f"{C.SYM_WARN} {text}", style=_rich_tone(T.WARNING)))
            else:
                self.sink.write(Text(text, style=_rich_tone(T.WARNING)))
        elif self.plain:
            self.sink.write_text(C.warn(text))

    def success(self, text: str, *, symbol: bool = False) -> None:
        """Print a success status line."""
        if self.rich:
            from rich.text import Text

            if symbol:
                self.sink.write(Text(f"{C.SYM_OK} {text}", style=_rich_tone(T.SUCCESS)))
            else:
                self.sink.write(Text(text, style=_rich_tone(T.SUCCESS)))
        elif self.plain:
            self.sink.write_text(C.ok(text))

    def error(self, text: str, *, strong: bool = True, symbol: bool = False) -> None:
        """Print an error status line."""
        if self.rich:
            from rich.text import Text

            tone = T.STRONG_ERROR if strong else T.ERROR
            if symbol:
                self.sink.write(Text(f"{C.SYM_FAIL} {text}", style=_rich_tone(tone)))
            else:
                self.sink.write(Text(text, style=_rich_tone(tone)))
        elif self.plain:
            self.sink.write_text(C.fail(text))

    # -- panel output ------------------------------------------------------

    def render_questions(self, questions: Any) -> None:
        """Render open questions and re-run hints from a run summary.

        Expects a ``RunSummaryQuestions`` instance (from
        ``codecome.run_summary_questions``).  If the instance has no
        content this is a no-op.
        """
        if not getattr(questions, "has_content", lambda: False)():
            return

        open_qs = getattr(questions, "open_questions", [])
        rerun_hints: str | None = getattr(questions, "rerun_hints", None)

        if open_qs:
            self.separator(tone=T.WARNING)
            self.section("Open questions from run summary", tone=T.WARNING)
            for i, q in enumerate(open_qs, 1):
                q_text = getattr(q, "question", str(q))
                why = getattr(q, "why_it_matters", "")
                affects = getattr(q, "affects", "")
                suggested = getattr(q, "suggested_format", "")

                if self.rich:
                    from rich.panel import Panel
                    from rich.text import Text

                    body = Text()
                    body.append(q_text, style="bold")
                    if why:
                        body.append(f"\nWhy it matters: {why}")
                    if affects:
                        body.append(f"\nAffects: {affects}")
                    if suggested:
                        body.append(f"\nSuggested answer: {suggested}")
                    self.sink.write(
                        Panel(
                            body,
                            title=f"Question {i}",
                            border_style=_rich_tone(T.WARNING) or "yellow",
                        )
                    )
                elif self.plain:
                    self.line(f"\n  Question {i}: {q_text}", tone=T.WARNING)
                    if why:
                        self.line(f"    Why it matters: {why}", tone=T.DETAIL)
                    if affects:
                        self.line(f"    Affects: {affects}", tone=T.DETAIL)
                    if suggested:
                        self.line(f"    Suggested answer: {suggested}", tone=T.DETAIL)

        if rerun_hints:
            self.separator(tone=T.ACCENT)
            self.section("Re-run prompt hints", tone=T.ACCENT)
            if self.rich:
                from rich.panel import Panel
                from rich.text import Text

                self.sink.write(
                    Panel(
                        Text(rerun_hints),
                        title="Re-run hints",
                        border_style=_rich_tone(T.ACCENT) or "cyan",
                    )
                )
            elif self.plain:
                self.sink.write_text("")
                for line in rerun_hints.split("\n"):
                    self.sink.write_text(f"  {line}")

    def panel(self, title: str, text: str, *, tone: Tone = T.ERROR) -> None:
        """Print a bordered panel (error, warning, or info box)."""
        if self.rich:
            from rich.panel import Panel
            from rich.text import Text

            border = _rich_tone(tone) or "red"
            if border == "bold red":
                border = "red"
            self.sink.write(
                Panel(Text(text, style=_rich_tone(tone)), title=title, border_style=border)
            )
        elif self.plain:
            self.sink.write_text(C.header(title))
            self.line(text, tone=tone)


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def get_output(console: Any) -> RenderOutput:
    """Create a :class:`RenderOutput` from an OpenCode console object.

    Uses the shared rendering context so that sink mode, settings, and
    cache are consistent with event and tool renderers.
    """
    from rendering.dispatch import _get_rendering_ctx

    return RenderOutput(_get_rendering_ctx(console))
