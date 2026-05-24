from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from rendering.sink import PlainSink, RichConsoleSink, TextualRichLogSink, RenderSink


class TestPlainSink:
    def test_mode(self):
        sink = PlainSink()
        assert sink.mode == "plain"

    def test_write_text(self, capsys):
        sink = PlainSink()
        sink.write_text("hello")
        out = capsys.readouterr().out
        assert out == "hello\n"

    def test_write_text_with_custom_end(self, capsys):
        sink = PlainSink()
        sink.write_text("hello", end="")
        sink.write_text("world", end="\n")
        out = capsys.readouterr().out
        assert out == "helloworld\n"

    def test_write_string(self, capsys):
        sink = PlainSink()
        sink.write("hello")
        out = capsys.readouterr().out
        assert out == "hello\n"

    def test_isinstance_checks(self):
        sink = PlainSink()
        assert isinstance(sink, RenderSink)


class TestRichConsoleSink:
    def test_mode(self):
        from rich.console import Console
        sink = RichConsoleSink(Console())
        assert sink.mode == "rich"

    def test_write_delegates_to_console(self):
        from rich.console import Console
        console = Console(record=True)
        sink = RichConsoleSink(console)
        from rich.text import Text
        sink.write(Text("hi"))
        exported = console.export_text()
        assert "hi" in exported

    def test_console_property(self):
        from rich.console import Console
        console = Console()
        sink = RichConsoleSink(console)
        assert sink.console is console

    def test_isinstance_checks(self):
        from rich.console import Console
        sink = RichConsoleSink(Console())
        assert isinstance(sink, RenderSink)


class TestTextualRichLogSink:
    def test_mode(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        assert sink.mode == "textual"

    def test_write_delegates_to_target(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        sink.write("hello", expand=True)
        proxy.write.assert_called_once()

    def test_write_with_expand_not_supported_falls_back(self):
        proxy = MagicMock()
        proxy.write.side_effect = [TypeError("unexpected keyword"), None]
        sink = TextualRichLogSink(proxy)
        sink.write("hello", expand=True)
        assert proxy.write.call_count == 2
        proxy.write.assert_called_with("hello")

    def test_write_text_delegates(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        sink.write_text("hello")
        proxy.write.assert_called_once()

    def test_target_property(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        assert sink.target is proxy

    def test_isinstance_checks(self):
        sink = TextualRichLogSink(MagicMock())
        assert isinstance(sink, RenderSink)


class TestRichConsoleSink:
    def test_mode(self):
        from rich.console import Console
        sink = RichConsoleSink(Console())
        assert sink.mode == "rich"

    def test_write_delegates_to_console(self):
        from rich.console import Console
        console = Console(record=True)
        sink = RichConsoleSink(console)
        from rich.text import Text
        sink.write(Text("hi"))
        exported = console.export_text()
        assert "hi" in exported

    def test_console_property(self):
        from rich.console import Console
        console = Console()
        sink = RichConsoleSink(console)
        assert sink.console is console

    def test_isinstance_checks(self):
        from rich.console import Console
        sink = RichConsoleSink(Console())
        assert isinstance(sink, RenderSink)


class TestTextualRichLogSink:
    def test_mode(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        assert sink.mode == "textual"

    def test_write_delegates_to_target(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        sink.write("hello", expand=True)
        proxy.write.assert_called_once()

    def test_write_with_expand_not_supported_falls_back(self):
        proxy = MagicMock()
        proxy.write.side_effect = [TypeError("unexpected keyword"), None]
        sink = TextualRichLogSink(proxy)
        sink.write("hello", expand=True)
        assert proxy.write.call_count == 2
        proxy.write.assert_called_with("hello")

    def test_write_text_delegates(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        sink.write_text("hello")
        proxy.write.assert_called_once()

    def test_target_property(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        assert sink.target is proxy

    def test_isinstance_checks(self):
        sink = TextualRichLogSink(MagicMock())
        assert isinstance(sink, RenderSink)


class TestRichConsoleSink:
    def test_mode(self):
        from rich.console import Console
        sink = RichConsoleSink(Console())
        assert sink.mode == "rich"

    def test_write_delegates_to_console(self):
        from rich.console import Console
        console = Console(record=True)
        sink = RichConsoleSink(console)
        from rich.text import Text
        sink.write(Text("hi"))
        exported = console.export_text()
        assert "hi" in exported

    def test_console_property(self):
        from rich.console import Console
        console = Console()
        sink = RichConsoleSink(console)
        assert sink.console is console

    def test_isinstance_checks(self):
        from rich.console import Console
        sink = RichConsoleSink(Console())
        assert isinstance(sink, RenderSink)


class TestTextualRichLogSink:
    def test_mode(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        assert sink.mode == "textual"

    def test_write_delegates_to_target(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        sink.write("hello", expand=True)
        proxy.write.assert_called_once()

    def test_write_with_expand_not_supported_falls_back(self):
        proxy = MagicMock()
        proxy.write.side_effect = [TypeError("unexpected keyword"), None]
        sink = TextualRichLogSink(proxy)
        sink.write("hello", expand=True)
        assert proxy.write.call_count == 2
        proxy.write.assert_called_with("hello")

    def test_write_text_delegates(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        sink.write_text("hello")
        proxy.write.assert_called_once()

    def test_target_property(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        assert sink.target is proxy

    def test_isinstance_checks(self):
        sink = TextualRichLogSink(MagicMock())
        assert isinstance(sink, RenderSink)


class TestRichConsoleSink:
    def test_mode(self):
        from rich.console import Console
        sink = RichConsoleSink(Console())
        assert sink.mode == "rich"

    def test_write_delegates_to_console(self):
        from rich.console import Console
        console = Console(record=True)
        sink = RichConsoleSink(console)
        from rich.text import Text
        sink.write(Text("hi"))
        exported = console.export_text()
        assert "hi" in exported

    def test_console_property(self):
        from rich.console import Console
        console = Console()
        sink = RichConsoleSink(console)
        assert sink.console is console

    def test_isinstance_checks(self):
        from rich.console import Console
        sink = RichConsoleSink(Console())
        assert isinstance(sink, RenderSink)


class TestTextualRichLogSink:
    def test_mode(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        assert sink.mode == "textual"

    def test_write_delegates_to_target(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        sink.write("hello", expand=True)
        proxy.write.assert_called_once()

    def test_write_with_expand_not_supported_falls_back(self):
        proxy = MagicMock()
        proxy.write.side_effect = [TypeError("unexpected keyword"), None]
        sink = TextualRichLogSink(proxy)
        sink.write("hello", expand=True)
        assert proxy.write.call_count == 2
        proxy.write.assert_called_with("hello")

    def test_write_text_delegates(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        sink.write_text("hello")
        proxy.write.assert_called_once()

    def test_target_property(self):
        proxy = MagicMock()
        sink = TextualRichLogSink(proxy)
        assert sink.target is proxy

    def test_isinstance_checks(self):
        sink = TextualRichLogSink(MagicMock())
        assert isinstance(sink, RenderSink)
