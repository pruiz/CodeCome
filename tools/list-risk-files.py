#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
List high-risk files from itemdb/notes/file-risk-index.yml.

Examples:

    ./tools/list-risk-files.py
    ./tools/list-risk-files.py --min-score 4
    ./tools/list-risk-files.py --min-score 5 --limit 10 --format paths
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "itemdb" / "notes" / "file-risk-index.yml"


def load_index(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: make venv")
    if not path.exists():
        raise FileNotFoundError(
            f"file risk index not found: {path.relative_to(ROOT)}. Run Phase 1 first."
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("file risk index must be a YAML object")
    files = data.get("files")
    if not isinstance(files, list):
        raise ValueError("file risk index must contain a 'files' list")
    return data


def normalize_entry(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    path = entry.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    try:
        score = int(entry.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    normalized = dict(entry)
    normalized["path"] = path.strip()
    normalized["score"] = score
    return normalized


def select_files(entries: list[Any], min_score: int, limit: int | None) -> list[dict[str, Any]]:
    normalized = [entry for entry in (normalize_entry(e) for e in entries) if entry is not None]
    selected = [entry for entry in normalized if entry["score"] >= min_score]
    selected.sort(key=lambda item: (-int(item.get("score", 0)), str(item.get("path", ""))))
    if limit is not None:
        selected = selected[:limit]
    return selected


def format_reasons(entry: dict[str, Any]) -> str:
    reasons = entry.get("reasons")
    if not isinstance(reasons, list):
        return ""
    text = "; ".join(str(reason).strip() for reason in reasons if str(reason).strip())
    return text


def render_table(entries: list[dict[str, Any]]) -> None:
    if not entries:
        print(C.warn("No files matched the requested score threshold."))
        return

    print(C.header("High-risk files"))
    for entry in entries:
        path = entry["path"]
        score = entry["score"]
        confidence = entry.get("confidence", "")
        area = entry.get("target_area", "")
        print(f"{C.SYM_BULLET} score={score} confidence={confidence} area={area}")
        print(f"  {path}")
        reasons = format_reasons(entry)
        if reasons:
            print(f"  reasons: {reasons}")


def main() -> int:
    parser = argparse.ArgumentParser(description="List high-risk files from CodeCome file-risk-index.yml")
    parser.add_argument("--index", default=str(DEFAULT_INDEX), help="Path to file-risk-index.yml")
    parser.add_argument("--min-score", type=int, default=4, help="Minimum risk score to include")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of files to return")
    parser.add_argument("--format", choices=["table", "paths"], default="table", help="Output format")
    args = parser.parse_args()

    index_path = Path(args.index)
    if not index_path.is_absolute():
        index_path = ROOT / index_path

    try:
        data = load_index(index_path)
        entries = select_files(data["files"], args.min_score, args.limit)
    except Exception as exc:  # noqa: BLE001
        print(C.fail(str(exc)), file=sys.stderr)
        return 1

    if args.format == "paths":
        for entry in entries:
            print(entry["path"])
    else:
        render_table(entries)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
