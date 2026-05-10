#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Run optional file-scoped Phase 2 sweeps from itemdb/notes/file-risk-index.yml.

The runner is intentionally sequential by default so the operator can observe
what the model is doing and interrupt or steer future runs.

Examples:

    ./tools/run-file-sweep.py --file src/app/controllers/upload.php
    ./tools/run-file-sweep.py --min-score 4 --limit 5
    ./tools/run-file-sweep.py --min-score 5 --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
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
PROMPT_TEMPLATE = ROOT / "prompts" / "phase-2-file.md"
TMP_DIR = ROOT / "tmp" / "file-sweep-prompts"


def load_risk_entries(index_path: Path) -> list[dict[str, Any]]:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: make venv")
    if not index_path.exists():
        raise FileNotFoundError(
            f"file risk index not found: {index_path.relative_to(ROOT)}. Run Phase 1 first."
        )

    data = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("file risk index must be a YAML object")
    entries = data.get("files")
    if not isinstance(entries, list):
        raise ValueError("file risk index must contain a 'files' list")

    result: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            continue
        try:
            score = int(entry.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        normalized = dict(entry)
        normalized["path"] = path.strip()
        normalized["score"] = score
        result.append(normalized)

    return result


def select_from_index(index_path: Path, min_score: int, limit: int | None) -> list[str]:
    entries = load_risk_entries(index_path)
    selected = [entry for entry in entries if int(entry.get("score", 0)) >= min_score]
    selected.sort(key=lambda entry: (-int(entry.get("score", 0)), str(entry.get("path", ""))))
    if limit is not None:
        selected = selected[:limit]
    return [str(entry["path"]) for entry in selected]


def normalize_file_arg(file_path: str) -> str:
    path = Path(file_path)
    if path.is_absolute():
        try:
            return str(path.relative_to(ROOT))
        except ValueError as exc:
            raise ValueError(f"target file must be inside the workspace: {file_path}") from exc
    return str(path)


def slugify(path: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", path).strip("-")
    return value[:120] or "target"


def build_prompt_for_file(file_path: str) -> Path:
    if not PROMPT_TEMPLATE.exists():
        raise FileNotFoundError(f"missing prompt template: {PROMPT_TEMPLATE.relative_to(ROOT)}")
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    placeholder = "FILE_PATH_OR_ID"
    if placeholder not in template:
        raise ValueError(f"prompt template does not contain placeholder {placeholder!r}")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    prompt = template.replace(placeholder, file_path)
    prompt_path = TMP_DIR / f"phase-2-file-{slugify(file_path)}.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def run_gate_checks() -> None:
    subprocess.run([sys.executable, "tools/gate-check.py", "2"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "tools/sandbox-bootstrap.py", "status", "--gate"], cwd=ROOT, check=True)


def run_one_file(file_path: str, dry_run: bool) -> int:
    prompt_path = build_prompt_for_file(file_path)
    print(C.header(f"File-scoped Phase 2: {file_path}"))
    print(f"Prompt: {prompt_path.relative_to(ROOT)}")

    if dry_run:
        return 0

    if os.environ.get("CODECOME_USE_WRAPPER") == "0":
        prompt = prompt_path.read_text(encoding="utf-8")
        command = ["opencode", "run", "--agent", "auditor", prompt]
    else:
        command = [
            sys.executable,
            "tools/run-agent.py",
            "--phase",
            "2",
            "--label",
            f"File-scoped Hypothesis Generation: {file_path}",
            "--agent",
            "auditor",
            "--prompt-file",
            str(prompt_path.relative_to(ROOT)),
        ]

    result = subprocess.run(command, cwd=ROOT)
    return int(result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run sequential CodeCome file-scoped Phase 2 sweeps")
    parser.add_argument("--file", action="append", default=[], help="Specific file to sweep. May be repeated.")
    parser.add_argument("--index", default=str(DEFAULT_INDEX), help="Path to file-risk-index.yml")
    parser.add_argument("--min-score", type=int, default=4, help="Minimum risk score when selecting from the index")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of indexed files to sweep")
    parser.add_argument("--dry-run", action="store_true", help="Print selected files and generated prompts without running OpenCode")
    parser.add_argument("--skip-gates", action="store_true", help="Skip Phase 2 readiness and sandbox gates")
    args = parser.parse_args()

    index_path = Path(args.index)
    if not index_path.is_absolute():
        index_path = ROOT / index_path

    try:
        if args.file:
            files = [normalize_file_arg(path) for path in args.file]
        else:
            files = select_from_index(index_path, args.min_score, args.limit)
    except Exception as exc:  # noqa: BLE001
        print(C.fail(str(exc)), file=sys.stderr)
        return 1

    if not files:
        print(C.warn("No files selected for sweep."))
        return 0

    print(C.header("Selected files"))
    for path in files:
        print(f"{C.SYM_BULLET} {path}")

    if not args.skip_gates and not args.dry_run:
        try:
            run_gate_checks()
        except subprocess.CalledProcessError as exc:
            print(C.fail(f"Readiness gate failed with exit code {exc.returncode}"), file=sys.stderr)
            return int(exc.returncode)

    for file_path in files:
        code = run_one_file(file_path, args.dry_run)
        if code != 0:
            print(C.fail(f"Sweep failed for {file_path} with exit code {code}"), file=sys.stderr)
            return code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
