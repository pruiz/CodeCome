from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from phases.phase_1_gates import _emit


def test_emit_plain_fallback_prints_formatted_text(capsys) -> None:
    _emit(None, "ok", "plain gate output")

    out = capsys.readouterr().out
    assert "plain gate output" in out
