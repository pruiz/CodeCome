# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional

from findings.constants import FINDINGS_ROOT, FINDING_ID_RE, FINDING_ID_STRICT_RE, ROOT, STATUSES


def extract_id_from_path(path: Path) -> str:
    """Extract CC-XXXX from a finding path stem like CC-0001-off-by-one."""
    return "-".join(path.stem.split("-", 2)[:2])


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value[:80] or "finding"


def iter_finding_files(
    *,
    findings_root: Optional[Path] = None,
) -> List[Path]:
    """Recursive CC-*.md glob, sorted. Used by create (next_id), checks."""
    findings_root = findings_root if findings_root is not None else FINDINGS_ROOT
    files: List[Path] = []

    if not findings_root.exists():
        return files

    for path in findings_root.rglob("CC-*.md"):
        if path.is_file():
            files.append(path)

    return sorted(files)


def iter_findings(
    status_filter: Optional[str] = None,
    *,
    findings_root: Optional[Path] = None,
    statuses: Optional[List[str]] = None,
) -> Iterable[Path]:
    """Iterate by status dir (CC-*.md glob per dir). Used by listing, report, index."""
    findings_root = findings_root if findings_root is not None else FINDINGS_ROOT
    statuses = statuses if statuses is not None else STATUSES
    status_list = [status_filter] if status_filter else statuses

    for status in status_list:
        status_dir = findings_root / status
        if not status_dir.exists():
            continue

        yield from sorted(status_dir.glob("CC-*.md"))


def next_finding_id(
    *,
    findings_root: Optional[Path] = None,
) -> str:
    ids: List[int] = []

    for path in iter_finding_files(findings_root=findings_root):
        match = FINDING_ID_RE.search(path.name)
        if match:
            ids.append(int(match.group(1)))

    next_id = max(ids, default=0) + 1
    return f"CC-{next_id:04d}"


def find_finding(
    identifier: str,
    *,
    findings_root: Optional[Path] = None,
    root: Optional[Path] = None,
) -> Path:
    findings_root = findings_root if findings_root is not None else FINDINGS_ROOT
    root = root if root is not None else ROOT
    candidate = Path(identifier)

    if candidate.exists():
        return candidate.resolve()

    if not FINDING_ID_STRICT_RE.fullmatch(identifier):
        raise FileNotFoundError(f"Invalid finding id or path: {identifier}")

    matches = sorted(findings_root.rglob(f"{identifier}-*.md"))

    if not matches:
        raise FileNotFoundError(f"Finding not found: {identifier}")

    if len(matches) > 1:
        paths = "\n".join(str(path.relative_to(root)) for path in matches)
        raise RuntimeError(f"Multiple findings matched {identifier}:\n{paths}")

    return matches[0]
