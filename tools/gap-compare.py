#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gap.compare import compare_gap_candidates


def main() -> int:
    results, summary_path = compare_gap_candidates()
    print(f"Compared {len(results)} gap candidate(s).")
    print(summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
