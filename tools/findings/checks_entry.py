# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _colors as C

from findings.constants import ROOT
from findings.checks import validate_finding, validate_file_risk_index, iter_all_finding_files


def build_parser():
    import argparse
    parser = argparse.ArgumentParser(
        description="Validate CodeCome finding frontmatter.",
    )
    return parser


def main() -> int:
    import argparse
    parser = build_parser()
    parser.parse_args()

    paths = iter_all_finding_files()

    total_errors = 0

    index_errors = validate_file_risk_index()
    if index_errors:
        total_errors += len(index_errors)
        print(C.fail("itemdb/notes/file-risk-index.yml"))
        for error in index_errors:
            print(f"  {C.SYM_BULLET} {error}")
    else:
        index_path = ROOT / "itemdb" / "notes" / "file-risk-index.yml"
        if index_path.exists():
            print(C.ok("itemdb/notes/file-risk-index.yml"))

    if not paths:
        index_path = ROOT / "itemdb" / "notes" / "file-risk-index.yml"
        if not index_path.exists():
            print(C.info("No findings or index to validate."))
        return 0 if total_errors == 0 else 1

    for path in paths:
        errors = validate_finding(path)

        if not errors:
            print(C.ok(str(path.relative_to(ROOT))))
            continue

        total_errors += len(errors)
        print(C.fail(str(path.relative_to(ROOT))))
        for error in errors:
            print(f"  {C.SYM_BULLET} {error}")

    if total_errors:
        print(f"\n{C.fail(f'Found {total_errors} frontmatter error(s).')}", file=sys.stderr)
        return 1

    print(f"\n{C.ok(f'Validated {len(paths)} finding(s).')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())