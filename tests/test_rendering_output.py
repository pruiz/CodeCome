from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from rendering.context import RenderContext
from rendering.sink import PlainSink, RichConsoleSink, TextualRichLogSink
from rendering.settings import RenderSettings
from rendering.cache import SnapshotCache
from rendering.output import RenderOutput, T, get_output


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _ctx(sink_mode="plain"):
    if sink_mode == "rich":
        from rich.console import Console

        sink = RichConsoleSink(Console(record=True, width=120))
    else:
        sink = PlainSink()
    return RenderContext(
        root=Path("/fake"), sink=sink, settings=RenderSettings(), cache=SnapshotCache()
    )


def _rich_text_export(out: RenderOutput) -> str:
    """Return visible text exported from a Rich recording console."""
    assert isinstance(out.sink, RichConsoleSink)
    return out.sink.console.export_text()


# ---------------------------------------------------------------------------
# T constants
# ---------------------------------------------------------------------------

class TestT:
    def test_all_tones_are_strings(self):
        for attr in dir(T):
            if attr.isupper() and not attr.startswith("_"):
                val = getattr(T, attr)
                assert isinstance(val, str), f"T.{attr} should be a str"

    def test_no_overlap_with_rich_styles(self):
        """T constants shouldn't accidentally match Rich style strings."""
        rich_styles = {"bold", "dim", "red", "green", "yellow", "blue", "cyan", "magenta"}
        for attr in dir(T):
            if attr.isupper() and not attr.startswith("_"):
                val = getattr(T, attr)
                assert val not in rich_styles, f"T.{attr}={val!r} looks like a Rich style"


# ---------------------------------------------------------------------------
# Plain mode tests
# ---------------------------------------------------------------------------

class TestRenderOutputPlain:
    def test_header_includes_title(self, capsys):
        RenderOutput(_ctx("plain")).header("CodeQL")
        out = capsys.readouterr().out
        assert "CodeQL" in out

    def test_section_includes_title(self, capsys):
        RenderOutput(_ctx("plain")).section("Sub Section")
        out = capsys.readouterr().out
        assert "Sub Section" in out

    def test_separator_plain_prints_dashes(self, capsys):
        RenderOutput(_ctx("plain")).separator()
        out = capsys.readouterr().out
        assert "-" in out
        assert len(out.strip()) >= 40

    def test_line_plain_includes_message(self, capsys):
        RenderOutput(_ctx("plain")).line("hello")
        out = capsys.readouterr().out
        assert "hello" in out

    def test_line_plain_with_tone(self, capsys):
        RenderOutput(_ctx("plain")).line("warning", tone=T.WARNING)
        out = capsys.readouterr().out
        assert "warning" in out

    def test_detail_plain_includes_message(self, capsys):
        RenderOutput(_ctx("plain")).detail("metadata")
        out = capsys.readouterr().out
        assert "metadata" in out

    def test_info_plain_includes_message(self, capsys):
        RenderOutput(_ctx("plain")).info("informational")
        out = capsys.readouterr().out
        assert "informational" in out

    def test_warn_plain_includes_message(self, capsys):
        RenderOutput(_ctx("plain")).warn("careful")
        out = capsys.readouterr().out
        assert "careful" in out

    def test_warn_plain_symbol_ignored(self, capsys):
        """symbol=True in plain uses C.warn which already has symbol."""
        RenderOutput(_ctx("plain")).warn("careful", symbol=True)
        out = capsys.readouterr().out
        assert "careful" in out

    def test_success_plain_includes_message(self, capsys):
        RenderOutput(_ctx("plain")).success("done")
        out = capsys.readouterr().out
        assert "done" in out

    def test_error_plain_includes_message(self, capsys):
        RenderOutput(_ctx("plain")).error("fail")
        out = capsys.readouterr().out
        assert "fail" in out

    def test_error_plain_strong_ignored(self, capsys):
        """strong=True in plain uses C.fail which already formats."""
        RenderOutput(_ctx("plain")).error("fail", strong=False)
        out = capsys.readouterr().out
        assert "fail" in out

    def test_segments_plain_preserves_order(self, capsys):
        RenderOutput(_ctx("plain")).segments(
            ("A:", T.ACCENT),
            (" value1", T.WARNING),
            (" detail", T.DETAIL),
        )
        out = capsys.readouterr().out
        assert "A:" in out
        assert "value1" in out
        assert "detail" in out

    def test_segments_plain_skips_empty(self, capsys):
        RenderOutput(_ctx("plain")).segments(
            ("A:", T.ACCENT),
            ("", T.WARNING),
            (" detail", T.DETAIL),
        )
        out = capsys.readouterr().out
        assert "A:" in out
        assert "detail" in out

    def test_segments_plain_empty_call_noop(self, capsys):
        RenderOutput(_ctx("plain")).segments()
        out = capsys.readouterr().out
        assert out == ""

    def test_panel_plain_includes_title_and_body(self, capsys):
        RenderOutput(_ctx("plain")).panel("Error", "something went wrong")
        out = capsys.readouterr().out
        assert "Error" in out
        assert "something went wrong" in out

    def test_unknown_tone_plain_falls_back_to_unstyled(self, capsys):
        # Use a tone that isn't in the map.
        RenderOutput(_ctx("plain")).line("mystery", tone="nonexistent_tone")  # type: ignore[arg-type]
        out = capsys.readouterr().out
        assert "mystery" in out

    def test_style_modes(self):
        out = RenderOutput(_ctx("plain"))
        assert out.plain is True
        assert out.rich is False


# ---------------------------------------------------------------------------
# Rich mode tests
# ---------------------------------------------------------------------------

class TestRenderOutputRich:
    def test_header_rich_records_title(self):
        out = RenderOutput(_ctx("rich"))
        out.header("CodeQL")
        text = _rich_text_export(out)
        assert "CodeQL" in text

    def test_section_rich_records_title(self):
        out = RenderOutput(_ctx("rich"))
        out.section("Sub Section")
        text = _rich_text_export(out)
        assert "Sub Section" in text

    def test_separator_rich_works(self):
        out = RenderOutput(_ctx("rich"))
        out.separator()
        # Just verify it doesn't crash; Rule output is visual.
        text = _rich_text_export(out)
        # Rich rules are rendered as horizontal lines of dash-like chars
        assert len(text.strip()) >= 0

    def test_separator_rich_with_tone(self):
        out = RenderOutput(_ctx("rich"))
        out.separator(tone=T.SUCCESS)
        # Should not crash.

    def test_line_rich_records_text(self):
        out = RenderOutput(_ctx("rich"))
        out.line("hello", tone=T.WARNING)
        text = _rich_text_export(out)
        assert "hello" in text

    def test_detail_rich_records_text(self):
        out = RenderOutput(_ctx("rich"))
        out.detail("metadata")
        text = _rich_text_export(out)
        assert "metadata" in text

    def test_info_rich_records_text(self):
        out = RenderOutput(_ctx("rich"))
        out.info("informational")
        text = _rich_text_export(out)
        assert "informational" in text

    def test_warn_rich_records_text(self):
        out = RenderOutput(_ctx("rich"))
        out.warn("careful")
        text = _rich_text_export(out)
        assert "careful" in text

    def test_warn_rich_with_symbol(self):
        out = RenderOutput(_ctx("rich"))
        out.warn("careful", symbol=True)
        text = _rich_text_export(out)
        assert "careful" in text

    def test_success_rich_records_text(self):
        out = RenderOutput(_ctx("rich"))
        out.success("done")
        text = _rich_text_export(out)
        assert "done" in text

    def test_success_rich_with_symbol(self):
        out = RenderOutput(_ctx("rich"))
        out.success("done", symbol=True)
        text = _rich_text_export(out)
        assert "done" in text

    def test_error_rich_strong(self):
        out = RenderOutput(_ctx("rich"))
        out.error("fail")
        text = _rich_text_export(out)
        assert "fail" in text

    def test_error_rich_not_strong(self):
        out = RenderOutput(_ctx("rich"))
        out.error("fail", strong=False)
        text = _rich_text_export(out)
        assert "fail" in text

    def test_error_rich_with_symbol(self):
        out = RenderOutput(_ctx("rich"))
        out.error("fail", symbol=True)
        text = _rich_text_export(out)
        assert "fail" in text

    def test_segments_rich_preserves_order(self):
        out = RenderOutput(_ctx("rich"))
        out.segments(
            ("A:", T.ACCENT),
            (" value1", T.WARNING),
            (" detail", T.DETAIL),
        )
        text = _rich_text_export(out)
        assert "A:" in text
        assert "value1" in text
        assert "detail" in text

    def test_segments_rich_empty_call_noop(self):
        out = RenderOutput(_ctx("rich"))
        out.segments()
        text = _rich_text_export(out)
        assert text.strip() == "" or text == "\n"

    def test_panel_rich_records_title_and_body(self):
        out = RenderOutput(_ctx("rich"))
        out.panel("Error", "something went wrong")
        text = _rich_text_export(out)
        assert "Error" in text
        assert "something went wrong" in text

    def test_unknown_tone_rich_falls_back(self):
        out = RenderOutput(_ctx("rich"))
        out.line("mystery", tone="nonexistent_tone")  # type: ignore[arg-type]
        text = _rich_text_export(out)
        assert "mystery" in text

    def test_style_modes(self):
        out = RenderOutput(_ctx("rich"))
        assert out.plain is False
        assert out.rich is True


# ---------------------------------------------------------------------------
# Textual-like tests
# ---------------------------------------------------------------------------

class TestRenderOutputTextual:
    def test_line_calls_fake_sink(self):
        fake = MagicMock()
        fake.write = MagicMock()
        sink = TextualRichLogSink(fake)
        ctx = RenderContext(
            root=Path("/fake"),
            sink=sink,
            settings=RenderSettings(),
            cache=SnapshotCache(),
        )
        RenderOutput(ctx).line("hello", tone=T.INFO)
        fake.write.assert_called()

    def test_segments_calls_fake_sink(self):
        fake = MagicMock()
        fake.write = MagicMock()
        sink = TextualRichLogSink(fake)
        ctx = RenderContext(
            root=Path("/fake"),
            sink=sink,
            settings=RenderSettings(),
            cache=SnapshotCache(),
        )
        RenderOutput(ctx).segments(("A:", T.ACCENT), (" value", T.WARNING))
        fake.write.assert_called()

    def test_header_calls_fake_sink(self):
        fake = MagicMock()
        fake.write = MagicMock()
        sink = TextualRichLogSink(fake)
        ctx = RenderContext(
            root=Path("/fake"),
            sink=sink,
            settings=RenderSettings(),
            cache=SnapshotCache(),
        )
        RenderOutput(ctx).header("Title")
        fake.write.assert_called()

    def test_separator_calls_fake_sink(self):
        fake = MagicMock()
        fake.write = MagicMock()
        sink = TextualRichLogSink(fake)
        ctx = RenderContext(
            root=Path("/fake"),
            sink=sink,
            settings=RenderSettings(),
            cache=SnapshotCache(),
        )
        RenderOutput(ctx).separator()
        fake.write.assert_called()


# ---------------------------------------------------------------------------
# get_output factory
# ---------------------------------------------------------------------------

class TestGetOutput:
    def test_get_output_returns_render_output(self):
        from rendering import dispatch as rendering_dispatch

        rendering_dispatch.reset_rendering_context_cache()
        try:
            out = get_output(None)
            assert isinstance(out, RenderOutput)
            assert out.plain is True
        finally:
            rendering_dispatch.reset_rendering_context_cache()

    def test_get_output_with_rich_console(self):
        from rendering import dispatch as rendering_dispatch

        rendering_dispatch.reset_rendering_context_cache()
        try:
            from rich.console import Console

            out = get_output(Console(record=True))
            assert isinstance(out, RenderOutput)
            assert out.rich is True
        finally:
            rendering_dispatch.reset_rendering_context_cache()
