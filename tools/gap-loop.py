#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gap.loop import run_gap_loop


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded manual gap-scan loop.")
    parser.add_argument("--dry-run", action="store_true", help="Write a summary without executing Make targets.")
    args = parser.parse_args()

    run = run_gap_loop(dry_run=args.dry_run)
    print(f"Gap loop steps: {len(run.steps)}")
    print(run.summary_path)
    return run.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
