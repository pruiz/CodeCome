#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gap.config import limits_markdown, load_gap_limits


def main() -> int:
    parser = argparse.ArgumentParser(description="Print or validate CodeCome gap-scan bounds.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    try:
        limits = load_gap_limits()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(limits.as_env(), indent=2, sort_keys=True))
    else:
        print(limits_markdown(limits), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
