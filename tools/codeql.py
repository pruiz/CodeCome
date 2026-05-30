#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL CLI wrapper for CodeCome.

Usage::

    tools/codeql.py install
    tools/codeql.py check
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codeql.config import resolve_config
from codeql.install import ROOT
from codeql.packs import PackResolverError, dump_yaml, load_codeql_plan, load_pack_catalog, resolve_plan_packs


def _cmd_install() -> int:
    """Install the managed CodeQL CLI."""
    from codeql.install import install
    return install()


def _cmd_check() -> int:
    """Check that CodeQL CLI is available and working."""
    config = resolve_config()

    if not config.enabled:
        print("CodeQL is disabled (CODEQL=0 or CODEQL_SKIP=1).")
        return 0

    binary_path = config.abs_install_path

    # 1. Binary check
    if not binary_path.is_file():
        print(f"FAIL: CodeQL binary not found at {binary_path}")
        print("Run 'tools/codeql.py install' to install the managed CodeQL CLI.")
        return 1

    try:
        result = subprocess.run(
            [str(binary_path), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"FAIL: codeql --version failed: {result.stderr}")
            return 1
        version_line = result.stdout.strip().split("\n")[0]
        print(f"CodeQL CLI: {version_line}")
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    # 2. Pack resolve check
    print("Checking pack resolution …")
    try:
        result = subprocess.run(
            [str(binary_path), "resolve", "qlpacks"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"WARN: codeql resolve qlpacks failed: {result.stderr}")
            # Soft-fail: the binary works, packs might need downloading later
        else:
            print("Pack resolution OK.")
    except Exception as exc:
        print(f"WARN: pack resolution check failed: {exc}")

    print("CodeQL CLI check passed.")
    return 0


def _cmd_resolve_packs(args: argparse.Namespace) -> int:
    """Resolve CodeQL plan pack profiles to concrete pack references."""
    config = resolve_config()

    plan_path = ROOT / args.plan if not Path(args.plan).is_absolute() else Path(args.plan)
    catalog_path = config.abs_pack_catalog
    output_path = ROOT / args.output if not Path(args.output).is_absolute() else Path(args.output)

    try:
        catalog = load_pack_catalog(catalog_path)
        plan = load_codeql_plan(plan_path)
        resolved = resolve_plan_packs(plan, catalog)
    except PackResolverError as exc:
        print(f"FAIL: {exc}")
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dump_yaml(resolved), encoding="utf-8")

    if args.format == "json":
        print(json.dumps(resolved, indent=2))
    else:
        print(f"Resolved CodeQL packs written to {output_path.relative_to(ROOT) if output_path.is_relative_to(ROOT) else output_path}")
        for language in resolved["languages"]:
            print(f"- {language['id']}: {', '.join(language['profiles'])}")
            for pack in language["packs"]:
                print(f"    {pack}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CodeQL CLI wrapper for CodeCome.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("install", help="Install the managed CodeQL CLI.")
    sub.add_parser("check", help="Verify the CodeQL CLI is installed and working.")
    resolve = sub.add_parser("resolve-packs", help="Resolve plan pack profiles to concrete pack references.")
    resolve.add_argument("--plan", default="itemdb/notes/codeql-plan.yml", help="Path to codeql-plan.yml")
    resolve.add_argument(
        "--output",
        default="itemdb/evidence/codeql/selected-query-packs.yml",
        help="Path to write resolved pack selections",
    )
    resolve.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "install":
        return _cmd_install()
    elif args.command == "check":
        return _cmd_check()
    elif args.command == "resolve-packs":
        return _cmd_resolve_packs(args)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
