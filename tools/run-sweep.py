#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Run optional deep-dive sweeps on specific files or from itemdb/notes/file-risk-index.yml.

The runner is intentionally sequential by default so the operator can observe
what the model is doing and interrupt or steer future runs.

Examples:

    ./tools/run-sweep.py --file src/app/controllers/upload.php
    ./tools/run-sweep.py --file "src/**/*.cs"
    ./tools/run-sweep.py --min-score 4 --limit 5
    ./tools/run-sweep.py --min-score 5 --dry-run
"""

from __future__ import annotations

import argparse
import glob
import re
import subprocess
import sys
import time
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
PROMPT_TEMPLATE = ROOT / "prompts" / "phase-2-sweep.md"
SWEEP_SUMMARY_PROMPT = ROOT / "prompts" / "phase-2-sweep-summary.md"
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


def expand_file_args(file_args: list[str]) -> list[str]:
    resolved_paths = []
    for arg in file_args:
        # Handle wildcards if any
        matches = glob.glob(arg, root_dir=str(ROOT), recursive=True) if "*" in arg else [arg]
        if not matches:
            raise FileNotFoundError(f"No files matched: {arg}")
        
        for match in matches:
            path = Path(ROOT) / match
            if not path.is_file():
                continue
                
            try:
                resolved_paths.append(str(path.relative_to(ROOT)))
            except ValueError as exc:
                raise ValueError(f"Target file must be inside the workspace: {path}") from exc
                
    if not resolved_paths:
        raise FileNotFoundError(f"No valid files found for the given arguments: {file_args}")
        
    # Remove duplicates but preserve order
    return list(dict.fromkeys(resolved_paths))


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
    prompt_path = TMP_DIR / f"sweep-{slugify(file_path)}.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def run_gate_checks() -> None:
    subprocess.run([sys.executable, "tools/gate-check.py", "2"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "tools/sandbox-bootstrap.py", "status", "--gate"], cwd=ROOT, check=True)


def run_one_file(file_path: str, dry_run: bool) -> int:
    prompt_path = build_prompt_for_file(file_path)
    print(C.header(f"Deep Sweep: {file_path}"))
    print(f"Prompt: {prompt_path.relative_to(ROOT)}")

    if dry_run:
        return 0

    command = [
        sys.executable,
        "tools/run-agent.py",
        "--phase",
        "2",
        "--label",
        f"Deep Sweep: {file_path}",
        "--agent",
        "auditor",
        "--prompt-file",
        str(prompt_path.relative_to(ROOT)),
    ]

    result = subprocess.run(command, cwd=ROOT)
    return int(result.returncode)


def build_sweep_summary_prompt(
    selected_files: list[str],
    per_file_summaries: list[str],
) -> Path:
    if not SWEEP_SUMMARY_PROMPT.exists():
        try:
            rel = SWEEP_SUMMARY_PROMPT.relative_to(ROOT)
        except ValueError:
            rel = SWEEP_SUMMARY_PROMPT
        raise FileNotFoundError(f"missing sweep summary prompt: {rel}")
    template = SWEEP_SUMMARY_PROMPT.read_text(encoding="utf-8")

    files_header = "## Selected files\n\nThe per-file sweep runs were executed on these files:\n\n"
    files_list = "\n".join(f"    {f}" for f in selected_files)
    files_block = f"{files_header}{files_list}\n"

    summaries_block = ""
    if per_file_summaries:
        summaries_header = "## Per-file sweep summaries\n\nRead ONLY these per-file summaries (do not read unrelated historical sweep summaries):\n\n"
        summaries_list = "\n".join(f"    {s}" for s in per_file_summaries)
        summaries_block = f"{summaries_header}{summaries_list}\n"

    prompt = template + "\n" + files_block + summaries_block
    prompt_path = TMP_DIR / f"sweep-summary-{time.strftime('%Y%m%d-%H%M%S')}.md"
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def run_sweep_summary(files: list[str], per_file_summaries: list[str]) -> int:
    """Run the aggregate sweep rollup after all per-file sweeps complete.

    Uses raw ``opencode run`` directly because the aggregate rollup is
    not a phase-mode run — it does not participate in the Phase 2
    completion gate and ``run-agent.py`` does not currently support
    non-phase utility prompts.
    """
    prompt_path = build_sweep_summary_prompt(files, per_file_summaries)
    print(C.header("Sweep Summary (Aggregate Rollup)"))
    print(f"Prompt: {prompt_path.relative_to(ROOT)}")

    prompt = prompt_path.read_text(encoding="utf-8")
    command = ["opencode", "run", "--agent", "auditor", prompt]
    result = subprocess.run(command, cwd=ROOT)
    return int(result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run sequential CodeCome file-scoped sweeps")
    parser.add_argument("--file", action="append", default=[], help="Specific file or glob to sweep. May be repeated.")
    parser.add_argument("--index", default=str(DEFAULT_INDEX), help="Path to file-risk-index.yml")
    parser.add_argument("--min-score", type=int, default=4, help="Minimum risk score when selecting from the index")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of indexed files to sweep")
    parser.add_argument("--dry-run", action="store_true", help="Print selected files and generated prompts without running OpenCode")
    parser.add_argument("--skip-gates", action="store_true", help="Skip readiness and sandbox gates")
    args = parser.parse_args()

    index_path = Path(args.index)
    if not index_path.is_absolute():
        index_path = ROOT / index_path

    try:
        if args.file:
            files = expand_file_args(args.file)
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

    sweep_start_time = time.time()
    for file_path in files:
        code = run_one_file(file_path, args.dry_run)
        if code != 0:
            print(C.fail(f"Sweep failed for {file_path} with exit code {code}"), file=sys.stderr)
            return code

    if not args.dry_run:
        fresh_summaries = [
            str(s.relative_to(ROOT))
            for f in files
            for s in sorted(
                (ROOT / "runs").glob(f"phase-2-summary-sweep-{slugify(f)}-*.md"),
                key=lambda p: p.stat().st_mtime,
            )
            if s.stat().st_mtime >= sweep_start_time
        ]
        code = run_sweep_summary(files, fresh_summaries)
        if code != 0:
            print(C.fail(f"Sweep aggregate summary failed with exit code {code}"), file=sys.stderr)
            return code

    return 0


if __name__ == "__main__":
    raise SystemExit(main())