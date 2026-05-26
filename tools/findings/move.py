# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path
from typing import Optional

import _colors as C

from findings.constants import FRONTMATTER_RE, ROOT, STATUSES, FindingsContext
from findings.ids import find_finding
from findings.frontmatter import replace_scalar_frontmatter


def replace_validation_status(content: str, value: str) -> str:
    validation_block_re = re.compile(r"^validation:\n(?P<body>(?:  .*\n?)*)", re.MULTILINE)
    match = validation_block_re.search(content)

    if not match:
        return content

    body = match.group("body")
    status_re = re.compile(r'^  status:\s*".*"$', re.MULTILINE)

    if not status_re.search(body):
        return content

    new_body = status_re.sub(f'  status: "{value}"', body, count=1)
    return content[: match.start("body")] + new_body + content[match.end("body") :]


def update_frontmatter(content: str, status: str, validation_status: Optional[str]) -> str:
    if not FRONTMATTER_RE.match(content):
        raise RuntimeError("Finding does not start with YAML frontmatter")

    today = date.today().isoformat()

    content = replace_scalar_frontmatter(content, "status", status)
    content = replace_scalar_frontmatter(content, "updated_at", today)

    if status in ("CONFIRMED", "EXPLOITED"):
        content = replace_scalar_frontmatter(content, "confidence", "CONFIRMED")

    if validation_status:
        content = replace_validation_status(content, validation_status)

    return content


def move_finding(
    path: Path,
    status: str,
    *,
    ctx: Optional[FindingsContext] = None,
) -> Path:
    ctx = ctx if ctx is not None else FindingsContext.default()

    if status not in ctx.statuses_set:
        raise ValueError(f"Invalid status: {status}")

    content = path.read_text(encoding="utf-8")

    validation_status = None
    if status == "CONFIRMED":
        validation_status = "CONFIRMED"
    elif status == "EXPLOITED":
        validation_status = "CONFIRMED"
    elif status == "REJECTED":
        validation_status = "REJECTED"

    content = update_frontmatter(content, status, validation_status)

    target_dir = ctx.findings_root / status
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / path.name

    if target_path.exists() and target_path.resolve() != path.resolve():
        raise FileExistsError(f"Target already exists: {target_path}")

    path.write_text(content, encoding="utf-8")

    if target_path.resolve() != path.resolve():
        shutil.move(str(path), str(target_path))

    return target_path


def build_parser():
    import argparse
    parser = argparse.ArgumentParser(
        description="Move a CodeCome finding to another status directory.",
    )

    parser.add_argument("finding", help="Finding id, for example CC-0001, or path to finding file.")
    parser.add_argument("status", choices=sorted(STATUSES), help="Target status.")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        path = find_finding(args.finding)
        old_status = path.parent.name
        target_path = move_finding(path, args.status)

        print(f"{C.ok(str(target_path.relative_to(ROOT)))} {C.transition(old_status, args.status)}")
        return 0
    except FileNotFoundError as exc:
        print(C.fail(str(exc)))
        return 1
    except RuntimeError as exc:
        print(C.fail(str(exc)))
        return 1
    except ValueError as exc:
        print(C.fail(str(exc)))
        return 1
    except FileExistsError as exc:
        print(C.fail(str(exc)))
        return 1
