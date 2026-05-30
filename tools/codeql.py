#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL CLI wrapper for CodeCome.

Usage::

    tools/codeql.py install
    tools/codeql.py check
    tools/codeql.py resolve-packs
    tools/codeql.py run
    tools/codeql.py import-risk
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codeql.config import ROOT, resolve_config
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


def _cmd_run() -> int:
    """Run CodeQL analysis: create databases, analyze, normalize SARIF."""
    config = resolve_config()

    if not config.enabled:
        print("CodeQL is disabled (CODEQL=0 or CODEQL_SKIP=1). Skipping run.")
        return 0

    binary_path = config.abs_install_path
    if not binary_path.is_file():
        print(f"FAIL: CodeQL binary not found at {binary_path}")
        print("Run 'tools/codeql.py install' to install the managed CodeQL CLI.")
        return 1

    from codeql.runner import run_codeql, write_manifest
    from codeql.normalize import normalize_all
    from codeql.packs import _load_yaml_mapping

    manifest = run_codeql(config)
    output_dir = config.abs_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(manifest, output_dir)

    status = manifest["status"]
    print(f"CodeQL run: {status}")

    if manifest.get("warnings"):
        for w in manifest["warnings"]:
            print(f"  WARN: {w}")
    if manifest.get("failures"):
        for f in manifest["failures"]:
            print(f"  FAIL: {f}")

    normalized_dir = output_dir / "normalized"
    resolved_path = output_dir / "selected-query-packs.yml"

    if status == "completed" and resolved_path.is_file():
        sarif_dir = output_dir / "sarif"
        if list(sarif_dir.glob("*.sarif")):
            try:
                resolved = _load_yaml_mapping(resolved_path, what="resolved packs")
                alerts_path, file_signals_path = normalize_all(
                    sarif_dir, normalized_dir, resolved,
                    manifest.get("codeql_version", "unknown"), ROOT,
                )
                print(f"Normalized alerts: {alerts_path.relative_to(ROOT) if alerts_path.is_relative_to(ROOT) else alerts_path}")
                print(f"File signals:    {file_signals_path.relative_to(ROOT) if file_signals_path.is_relative_to(ROOT) else file_signals_path}")
            except Exception as exc:
                print(f"WARN: SARIF normalization failed: {exc}")

    summary_path = _write_summary(manifest, normalized_dir, output_dir)
    print(f"Summary: {summary_path.relative_to(ROOT) if summary_path.is_relative_to(ROOT) else summary_path}")

    if status == "failed":
        return 1
    return 0


def _cmd_import_risk() -> int:
    """Import CodeQL file signals into file-risk-index.yml."""
    config = resolve_config()
    if not config.enabled:
        print("CodeQL is disabled — skipping risk import.")
        return 0

    from codeql.import_risk import import_risk

    signals_path = config.abs_output_dir / "normalized" / "file-signals.yml"
    risk_path = ROOT / "itemdb/notes/file-risk-index.yml"

    status, warnings = import_risk(signals_path, risk_path)
    for w in warnings:
        print(f"WARN: {w}")
    if status == "skipped":
        print("Risk import skipped — no risk index to enrich.")
        return 0

    print(f"File risk index enriched from {signals_path.relative_to(ROOT) if signals_path.is_relative_to(ROOT) else signals_path}")
    return 0


def _write_summary(manifest: dict, normalized_dir: Path, output_dir: Path) -> Path:
    """Write codeql-summary.md."""
    status = manifest.get("status", "unknown")
    version = manifest.get("codeql_version", "unknown")
    languages = manifest.get("languages", [])
    warnings = manifest.get("warnings", [])
    failures = manifest.get("failures", [])
    fail_policy = manifest.get("fail_policy", "soft")

    lines = [
        "# CodeQL Analysis Summary",
        "",
        f"- **Status**: {status}",
        f"- **CodeQL version**: {version}",
        f"- **Fail policy**: {fail_policy}",
        f"- **Started**: {manifest.get('started_at', '')}",
        f"- **Finished**: {manifest.get('finished_at', '')}",
        "",
    ]

    if languages:
        lines.append(f"- **Languages**: {', '.join(languages)}")
        lines.append("")

    alerts_path = normalized_dir / "alerts.yml"
    signals_path = normalized_dir / "file-signals.yml"

    if alerts_path.is_file():
        from codeql.packs import _load_yaml_mapping
        try:
            data = _load_yaml_mapping(alerts_path, what="alerts")
            total_alerts = len(data.get("alerts", []))
            lines.append(f"- **Total alerts**: {total_alerts}")
            lines.append("")
        except Exception:
            pass

    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    if failures:
        lines.append("## Failures")
        lines.append("")
        for f in failures:
            lines.append(f"- {f}")
        lines.append("")

    path = output_dir / "codeql-summary.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CodeQL CLI wrapper for CodeCome.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("install", help="Install the managed CodeQL CLI.")
    sub.add_parser("check", help="Verify the CodeQL CLI is installed and working.")
    sub.add_parser("run", help="Run CodeQL analysis (create DBs, analyze, normalize SARIF).")
    sub.add_parser("import-risk", help="Import CodeQL file signals into file-risk-index.yml.")
    resolve = sub.add_parser("resolve-packs", help="Resolve plan pack profiles to concrete pack references.")
    resolve.add_argument("--plan", default="itemdb/notes/codeql-plan.yml", help="Path to codeql-plan.yml")
    resolve.add_argument(
        "--output",
        default="itemdb/codeql/selected-query-packs.yml",
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
    elif args.command == "run":
        return _cmd_run()
    elif args.command == "import-risk":
        return _cmd_import_risk()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
