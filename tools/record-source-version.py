#!/usr/bin/env python3
# Copyright (C) 2026 CodeCome contributors
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Record the git provenance of the scanned source tree.

Reads ``project.source_path`` from ``codecome.yml``, captures the source
checkout's commit / date / branch / remote / dirty state, and writes it to
``itemdb/source-version.yml`` so every run (and the Phase 6 report) is
traceable to an exact revision.

It also warns when the source is not a clean, up-to-date git checkout — the
common cause of auditing a stale snapshot (e.g. a months-old shallow clone, or
a tree copied without its ``.git``). With ``--strict`` it exits non-zero in
that case, so it can gate a run in CI.

Usage:

    ./tools/record-source-version.py            # record + warn (never fails)
    ./tools/record-source-version.py --strict   # also fail on stale/dirty/no-git
    ./tools/record-source-version.py --quiet     # record silently
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _git(src: Path, *args: str) -> str:
    """Run a git command in *src*, returning stripped stdout ("" on error)."""
    try:
        return subprocess.check_output(
            ["git", "-C", str(src), *args],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def collect(src: Path) -> dict:
    """Collect git provenance for the source checkout at *src*."""
    info: dict = {
        "recorded": False,
        "source_path": str(src),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if _git(src, "rev-parse", "--is-inside-work-tree") != "true":
        info["reason"] = "source is not a git checkout; provenance unknown"
        return info
    commit = _git(src, "rev-parse", "HEAD")
    if not commit:
        info["reason"] = "could not read git HEAD"
        return info

    upstream = _git(src, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    ahead = behind = None
    if upstream:
        counts = _git(src, "rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        if counts and len(counts.split()) == 2:
            a, b = counts.split()
            ahead, behind = int(a), int(b)

    info.update(
        {
            "recorded": True,
            "commit": commit,
            "short": _git(src, "rev-parse", "--short", "HEAD"),
            "committed_date": _git(src, "show", "-s", "--format=%cI", "HEAD"),
            "subject": _git(src, "show", "-s", "--format=%s", "HEAD"),
            "branch": _git(src, "rev-parse", "--abbrev-ref", "HEAD"),
            "remote": _git(src, "remote", "get-url", "origin")
            or _git(src, "config", "--get", "remote.origin.url"),
            "upstream": upstream or None,
            "ahead_upstream": ahead,
            "behind_upstream": behind,
            "dirty": bool(_git(src, "status", "--porcelain")),
        }
    )
    return info


def problems_for(info: dict) -> list[str]:
    """Human-readable warnings implied by *info* (empty when all is well)."""
    if not info.get("recorded"):
        return [info.get("reason", "source provenance unknown")]
    out: list[str] = []
    if info.get("dirty"):
        out.append("source working tree is dirty (uncommitted changes)")
    if info.get("behind_upstream"):
        out.append(
            f"source is {info['behind_upstream']} commit(s) behind "
            f"{info.get('upstream')} — you may be auditing a stale snapshot; "
            f"refresh the checkout to its current branch head before scanning"
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record git provenance of the scanned source tree.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if provenance is missing, dirty, or behind upstream",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress stdout")
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / "codecome.yml").read_text(encoding="utf-8")) or {}
    source_path = config.get("project", {}).get("source_path", "./src")
    src = (ROOT / source_path).resolve()

    info = collect(src)
    out_path = ROOT / "itemdb" / "source-version.yml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(info, sort_keys=False), encoding="utf-8")

    problems = problems_for(info)
    if not args.quiet:
        if info.get("recorded"):
            print(
                f"Source version: {info['short']} "
                f"({info.get('committed_date')}) on {info.get('branch')}"
            )
        for p in problems:
            print(f"  WARNING: {p}", file=sys.stderr)
        print(f"  wrote {out_path.relative_to(ROOT)}")

    return 1 if (args.strict and problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
