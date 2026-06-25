#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gap.sweep import run_gap_sweep


def main() -> int:
    parser = argparse.ArgumentParser(description="Run targeted sweeps for gap candidates marked missing_sweep.")
    parser.add_argument("--candidate", help="Only sweep files for one GAP-NNNN candidate.")
    parser.add_argument("--dry-run", action="store_true", help="Write the sweep summary without running make sweep.")
    parser.add_argument("--force", action="store_true", help="Allow re-sweeping candidate/file pairs already recorded in prior gap-sweep summaries.")
    args = parser.parse_args()

    run = run_gap_sweep(candidate_id=args.candidate, dry_run=args.dry_run, force=args.force)
    print(f"Selected {len(run.selected)} sweep target(s).")
    if run.created_findings:
        print("Created findings: " + ", ".join(run.created_findings))
    if run.skipped:
        print(f"Skipped {len(run.skipped)} target(s).")
    print(run.summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
