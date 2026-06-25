from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from gap.config import GapLimits, limits_markdown, load_gap_limits


def test_gap_limits_defaults_are_bounded():
    limits = load_gap_limits({})

    assert limits.max_scan_rounds == 1
    assert limits.max_candidates == 10
    assert limits.max_sweep_files == 5
    assert limits.max_sweeps_per_audit == 5


def test_gap_limits_read_environment_overrides():
    limits = load_gap_limits({
        "CODECOME_GAP_MAX_SCAN_ROUNDS": "2",
        "CODECOME_GAP_MAX_CANDIDATES": "7",
        "CODECOME_GAP_MAX_SWEEP_FILES": "3",
        "CODECOME_GAP_MAX_SWEEPS_PER_AUDIT": "4",
    })

    assert limits == GapLimits(max_scan_rounds=2, max_candidates=7, max_sweep_files=3, max_sweeps_per_audit=4)


def test_gap_limits_reject_non_positive_values():
    try:
        load_gap_limits({"CODECOME_GAP_MAX_CANDIDATES": "0"})
    except ValueError as exc:
        assert "CODECOME_GAP_MAX_CANDIDATES" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_gap_limits_markdown_lists_all_bounds():
    markdown = limits_markdown(GapLimits())

    assert "Maximum scan rounds: 1" in markdown
    assert "Maximum candidate gaps: 10" in markdown
    assert "Maximum sweep files: 5" in markdown
    assert "Maximum sweeps per audit: 5" in markdown
