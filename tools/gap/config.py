from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import os


DEFAULT_MAX_SCAN_ROUNDS = 1
DEFAULT_MAX_CANDIDATES = 10
DEFAULT_MAX_SWEEP_FILES = 5
DEFAULT_MAX_SWEEPS_PER_AUDIT = 5


@dataclass(frozen=True)
class GapLimits:
    max_scan_rounds: int = DEFAULT_MAX_SCAN_ROUNDS
    max_candidates: int = DEFAULT_MAX_CANDIDATES
    max_sweep_files: int = DEFAULT_MAX_SWEEP_FILES
    max_sweeps_per_audit: int = DEFAULT_MAX_SWEEPS_PER_AUDIT

    def as_env(self) -> dict[str, str]:
        return {
            "CODECOME_GAP_MAX_SCAN_ROUNDS": str(self.max_scan_rounds),
            "CODECOME_GAP_MAX_CANDIDATES": str(self.max_candidates),
            "CODECOME_GAP_MAX_SWEEP_FILES": str(self.max_sweep_files),
            "CODECOME_GAP_MAX_SWEEPS_PER_AUDIT": str(self.max_sweeps_per_audit),
        }


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    value = env.get(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if parsed < 1:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def load_gap_limits(env: Mapping[str, str] | None = None) -> GapLimits:
    source = env if env is not None else os.environ
    return GapLimits(
        max_scan_rounds=_positive_int(source, "CODECOME_GAP_MAX_SCAN_ROUNDS", DEFAULT_MAX_SCAN_ROUNDS),
        max_candidates=_positive_int(source, "CODECOME_GAP_MAX_CANDIDATES", DEFAULT_MAX_CANDIDATES),
        max_sweep_files=_positive_int(source, "CODECOME_GAP_MAX_SWEEP_FILES", DEFAULT_MAX_SWEEP_FILES),
        max_sweeps_per_audit=_positive_int(source, "CODECOME_GAP_MAX_SWEEPS_PER_AUDIT", DEFAULT_MAX_SWEEPS_PER_AUDIT),
    )


def limits_markdown(limits: GapLimits) -> str:
    return "\n".join([
        "# Gap Scan Bounds",
        "",
        f"- Maximum scan rounds: {limits.max_scan_rounds}",
        f"- Maximum candidate gaps: {limits.max_candidates}",
        f"- Maximum sweep files: {limits.max_sweep_files}",
        f"- Maximum sweeps per audit: {limits.max_sweeps_per_audit}",
        "",
    ])
