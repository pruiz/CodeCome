import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import pytest
import json
from unittest.mock import MagicMock
import threading

import chat.app as app

def test_textual_console_proxy_write_main_thread(monkeypatch):
    monkeypatch.setattr(threading, "current_thread", threading.main_thread)
    
    mock_log = MagicMock()
    mock_app = MagicMock()
    
    proxy = app.TextualConsoleProxy(mock_log, mock_app)
    proxy.print("hello")
    
    mock_log.write.assert_called_once()
    mock_app.post_message.assert_not_called()

def test_textual_console_proxy_write_bg_thread(monkeypatch):
    class DummyThread(threading.Thread):
        pass
    dummy = DummyThread()
    monkeypatch.setattr(threading, "current_thread", lambda: dummy)
    
    mock_log = MagicMock()
    mock_app = MagicMock()
    
    proxy = app.TextualConsoleProxy(mock_log, mock_app)
    proxy.print("hello", "world")
    
    mock_log.write.assert_not_called()
    mock_app.post_message.assert_called_once()

def test_chat_render_and_log(monkeypatch):
    mock_transcript = MagicMock()
    mock_args = MagicMock()
    mock_args.debug = True
    
    class FakeSelf:
        transcript = mock_transcript
        args = mock_args
        thinking_on = True
        _modeline_info = ""
        
    fake_self = FakeSelf()
    
    rendered = []
    def fake_render(console, phase, label, event):
        rendered.append(event)
        
    monkeypatch.setattr(app, "render_event", fake_render)
    
    event = {"type": "message.updated", "info": {"role": "assistant", "modelID": "gpt-5"}}
    
    app._chat_render_and_log(fake_self, None, "1", "label", event)
    
    assert len(rendered) == 1
    assert "gpt-5" in fake_self._modeline_info
    mock_transcript.write_event.assert_called()

def test_chat_update_modeline_info():
    class FakeSelf:
        _modeline_info = ""
        
    fake_self = FakeSelf()
    
    # Missing info
    app._chat_update_modeline_info(fake_self, {})
    assert fake_self._modeline_info == ""
    
    # With role assistant and model
    event = {
        "type": "message.updated",
        "info": {
            "role": "assistant",
            "modelID": "claude",
            "providerID": "anthropic",
            "tokens": {"input": 10, "output": 20},
            "cost": 0.05
        }
    }
    app._chat_update_modeline_info(fake_self, event)
    
    assert "anthropic/claude" in fake_self._modeline_info
    assert "↑10" in fake_self._modeline_info
    assert "↓20" in fake_self._modeline_info
    assert "$0.05" in fake_self._modeline_info
