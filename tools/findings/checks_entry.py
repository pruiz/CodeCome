# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import sys
from pathlib import Path

import _colors as C

from findings.constants import FILE_RISK_INDEX_PATH, FILE_RISK_INDEX_REL, ROOT
from findings.checks import validate_finding, validate_file_risk_index, iter_all_finding_files


def build_parser():
    import argparse
    parser = argparse.ArgumentParser(
        description="Validate CodeCome finding frontmatter.",
    )
    return parser


def run_frontmatter_validation() -> tuple[int, str]:
    """Run frontmatter validation in-process and return (exit_code, output_text).

    This is the reusable entrypoint for code paths that need to validate
    frontmatter without shelling out to a subprocess (phase retry loops,
    gate checks, etc.).
    """
    import io

    out = io.StringIO()

    paths = iter_all_finding_files()
    total_errors = 0

    index_errors = validate_file_risk_index()
    if index_errors:
        total_errors += len(index_errors)
        out.write(C.fail(str(FILE_RISK_INDEX_REL)) + "\n")
        for error in index_errors:
            out.write(f"  {C.SYM_BULLET} {error}\n")
    else:
        if FILE_RISK_INDEX_PATH.exists():
            out.write(C.ok(str(FILE_RISK_INDEX_REL)) + "\n")

    if not paths:
        if not FILE_RISK_INDEX_PATH.exists():
            out.write(C.info("No findings or index to validate.") + "\n")
        return (0 if total_errors == 0 else 1, out.getvalue())

    for path in paths:
        errors = validate_finding(path)
        if not errors:
            out.write(C.ok(str(path.relative_to(ROOT))) + "\n")
            continue
        total_errors += len(errors)
        out.write(C.fail(str(path.relative_to(ROOT))) + "\n")
        for error in errors:
            out.write(f"  {C.SYM_BULLET} {error}\n")

    if total_errors:
        out.write(f"\n{C.fail(f'Found {total_errors} frontmatter error(s).')}\n")
    else:
        out.write(f"\n{C.ok(f'Validated {len(paths)} finding(s).')}\n")

    return (1 if total_errors else 0, out.getvalue())


def main() -> int:
    import argparse
    parser = build_parser()
    parser.parse_args()

    exit_code, output = run_frontmatter_validation()
    sys.stdout.write(output)
    if exit_code != 0:
        print(output.split("\n")[-2] if output.strip() else "", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())