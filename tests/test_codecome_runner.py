import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import argparse
import pytest
import threading
import json
from unittest.mock import MagicMock

from codecome import runner
from events.phase_loop import RunResult

@pytest.fixture
def mock_args():
    args = argparse.Namespace()
    args.phase = "1"
    args.label = "Recon"
    args.agent = "recon"
    args.finding = None
    args.debug = False
    return args

@pytest.fixture
def mock_console():
    return MagicMock()

def test_consume_events_renders_and_logs(mock_args, mock_console, monkeypatch):
    class FakePhaseEventLoop:
        def __init__(self, **kwargs):
            pass
        def run(self, render_and_log_fn):
            event = {"type": "text", "content": "hello"}
            render_and_log_fn(mock_console, "1", "Recon", event)
            return RunResult()
            
    monkeypatch.setattr(runner, "PhaseEventLoop", FakePhaseEventLoop)
    
    rendered_events = []
    def fake_render(console, phase, label, event):
        rendered_events.append(event)
        
    fake_transcript = MagicMock()
    
    res = runner._consume_events(
        "http://base", "session_123", mock_console, "1", "Recon", mock_args,
        fake_transcript, True, "auth", "dir", fake_render
    )
    
    assert isinstance(res, RunResult)
    assert len(rendered_events) == 1
    assert rendered_events[0]["content"] == "hello"
    fake_transcript.write.assert_called_once()
    import json
    written_data = json.loads(fake_transcript.write.call_args[0][0])
    assert written_data["content"] == "hello"

def test_run_single_attempt_success(mock_args, mock_console, monkeypatch):
    monkeypatch.setattr(runner, "create_session", lambda *a, **kw: "new_session")
    
    sent_prompts = []
    def fake_send(*a, **kw):
        sent_prompts.append(a[2]) # prompt is 3rd arg
    monkeypatch.setattr(runner, "send_prompt_to_session", fake_send)
    
    def fake_consume(*a, **kw):
        return RunResult()
    monkeypatch.setattr(runner, "_consume_events", fake_consume)
    
    monkeypatch.setattr(runner, "open_phase_transcript", lambda p, f: (Path("fake.jsonl"), MagicMock()))
    monkeypatch.setattr(runner, "close_transcript", lambda f: None)
    
    code, session_id, res, path = runner._run_single_attempt(
        mock_args, mock_console, "do work", "model", "var", True,
        "http://base", "auth", "dir", lambda *a: None
    )
    
    assert code == 0
    assert session_id == "new_session"
    assert isinstance(res, RunResult)
    assert len(sent_prompts) == 1
    assert sent_prompts[0] == "do work"

def test_run_single_attempt_consumer_exception(mock_args, mock_console, monkeypatch):
    monkeypatch.setattr(runner, "create_session", lambda *a, **kw: "new_session")
    monkeypatch.setattr(runner, "send_prompt_to_session", lambda *a, **kw: None)
    
    def fake_consume(*a, **kw):
        raise ValueError("consumer failed")
    monkeypatch.setattr(runner, "_consume_events", fake_consume)
    
    monkeypatch.setattr(runner, "open_phase_transcript", lambda p, f: (Path("fake.jsonl"), MagicMock()))
    monkeypatch.setattr(runner, "close_transcript", lambda f: None)
    
    fatal_errors = []
    def fake_fatal(console, title, msg):
        fatal_errors.append(msg)
        
    code, session_id, res, path = runner._run_single_attempt(
        mock_args, mock_console, "do work", "model", "var", True,
        "http://base", "auth", "dir", lambda *a: None,
        emit_fatal_error_fn=fake_fatal
    )
    
    assert code == 1
    assert len(fatal_errors) == 1
    assert "consumer failed" in fatal_errors[0]

def test_run_single_attempt_existing_session(mock_args, mock_console, monkeypatch):
    # Should not call create_session
    created = []
    monkeypatch.setattr(runner, "create_session", lambda *a, **kw: created.append(True))
    monkeypatch.setattr(runner, "send_prompt_to_session", lambda *a, **kw: None)
    monkeypatch.setattr(runner, "_consume_events", lambda *a, **kw: RunResult())
    monkeypatch.setattr(runner, "open_phase_transcript", lambda p, f: (Path("fake.jsonl"), MagicMock()))
    monkeypatch.setattr(runner, "close_transcript", lambda f: None)
    
    code, session_id, res, path = runner._run_single_attempt(
        mock_args, mock_console, "do work", "model", "var", True,
        "http://base", "auth", "dir", lambda *a: None,
        existing_session_id="existing_123"
    )
    
    assert code == 0
    assert session_id == "existing_123"
    assert len(created) == 0
