# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
RenderSink — destination abstraction for renderer output.

Three implementations:
  - PlainSink       — writes plain strings to stdout (no Rich dependency)
  - RichConsoleSink — delegates to a rich.console.Console
  - TextualRichLogSink — delegates to a Textual RichLog or thread-safe proxy
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

__all__ = [
    "RenderSink",
    "PlainSink",
    "RichConsoleSink",
    "TextualRichLogSink",
]


@runtime_checkable
class RenderSink(Protocol):
    """Destination for rendered output.

    The sink abstracts *where* output goes but does not restrict *what*
    renderers can emit.  Rich and Textual renderers may emit any Rich
    renderable (Panel, Group, Text, Table, Syntax, Rule, Markdown, …);
    the Plain branch emits only plain strings.
    """

    mode: Literal["plain", "rich", "textual"]

    def write(self, renderable: Any, *, expand: bool = True) -> None:
        """Write a Rich renderable or plain string."""
        ...

    def write_text(self, text: str, *, end: str = "\n") -> None:
        """Write a plain string (always safe, any mode)."""
        ...


class PlainSink:
    """Writes plain strings to stdout.  No ANSI or Rich dependency."""

    mode: Literal["plain"] = "plain"

    def write(self, renderable: Any, *, expand: bool = True) -> None:
        import sys
        if isinstance(renderable, str):
            self.write_text(renderable)
        else:
            # Minimal fallback: str() the renderable.
            self.write_text(str(renderable))

    def write_text(self, text: str, *, end: str = "\n") -> None:
        import sys
        sys.stdout.write(text)
        sys.stdout.write(end)
        sys.stdout.flush()


class RichConsoleSink:
    """Delegates to a rich.console.Console."""

    mode: Literal["rich"] = "rich"

    def __init__(self, console: Any) -> None:
        self._console = console

    @property
    def console(self) -> Any:
        return self._console

    def write(self, renderable: Any, *, expand: bool = True) -> None:
        self._console.print(renderable, overflow="ignore", crop=False)

    def write_text(self, text: str, *, end: str = "\n") -> None:
        self._console.print(text, overflow="ignore", crop=False, end=end)


class TextualRichLogSink:
    """Delegates to a Textual RichLog or a thread-safe proxy.

    In chat mode, the entry point wires a ``TextualConsoleProxy`` or
    similar object that implements ``write(renderable)``.
    """

    mode: Literal["textual"] = "textual"

    def __init__(self, rich_log_or_proxy: Any) -> None:
        self._target = rich_log_or_proxy

    @property
    def target(self) -> Any:
        return self._target

    def write(self, renderable: Any, *, expand: bool = True) -> None:
        # The proxy's .write() is thread-safe (post_message in Textual).
        # Some targets (e.g. the legacy TextualConsoleProxy) do not accept
        # an expand keyword; fall back gracefully.
        try:
            self._target.write(renderable, expand=expand)  # type: ignore[call-arg]
        except TypeError:
            self._target.write(renderable)

    def write_text(self, text: str, *, end: str = "\n") -> None:
        # RichLog.write() has no end parameter; concatenate manually.
        self.write((text + end) if end else text)
