import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import json
import pytest
from unittest.mock import MagicMock

from codecome.recording import EventRecorder
from codecome.transcript import Transcript
import codecome.transcript as transcript_mod


@pytest.fixture
def mock_transcript():
    return MagicMock(spec=Transcript)


def test_record_writes_transcript(mock_transcript):
    recorder = EventRecorder(mock_transcript)
    event = {"type": "text", "content": "hello"}
    recorder.record(event)
    mock_transcript.write_event.assert_called_once_with(event)


def test_debug_false_does_not_call_debug_fn(mock_transcript):
    debug_fn = MagicMock()
    recorder = EventRecorder(mock_transcript, debug=False, debug_fn=debug_fn)
    recorder.record({"type": "text"})
    debug_fn.assert_not_called()


def test_debug_true_calls_debug_fn_with_raw_json(mock_transcript):
    debug_fn = MagicMock()
    recorder = EventRecorder(mock_transcript, debug=True, debug_fn=debug_fn)
    event = {"type": "text", "content": "hello"}
    recorder.record(event)
    debug_fn.assert_called_once_with(json.dumps(event))


def test_debug_true_no_debug_fn_writes_to_stderr(mock_transcript, capsys):
    recorder = EventRecorder(mock_transcript, debug=True, debug_fn=None)
    event = {"type": "text", "content": "test"}
    recorder.record(event)
    captured = capsys.readouterr()
    assert captured.err == json.dumps(event) + "\n"


def test_record_does_not_filter_reasoning(mock_transcript):
    recorder = EventRecorder(mock_transcript, debug=False)
    reasoning_event = {"type": "reasoning", "part": {"text": "thinking..."}}
    recorder.record(reasoning_event)
    mock_transcript.write_event.assert_called_once_with(reasoning_event)


def test_record_always_forwards_all_events(mock_transcript):
    recorder = EventRecorder(mock_transcript, debug=False)
    for event_type in ("reasoning", "text", "message.updated", "tool_use"):
        mock_transcript.write_event.reset_mock()
        recorder.record({"type": event_type})
        mock_transcript.write_event.assert_called_once()


def test_phase_transcript_does_not_truncate_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(transcript_mod, "ROOT", tmp_path)
    transcript_mod._ATTEMPT_COUNTER.clear()

    existing = tmp_path / "tmp" / "last-phase-1c-no-finding-attempt-1.jsonl"
    existing.parent.mkdir(parents=True)
    existing.write_text("keep me\n", encoding="utf-8")

    transcript = Transcript.for_phase("1c", None)
    try:
        transcript.write_event({"type": "test"})
    finally:
        transcript.close()

    assert existing.read_text(encoding="utf-8") == "keep me\n"
    assert transcript.path != existing
    assert transcript.path.name.startswith("last-phase-1c-no-finding-attempt-1-")
