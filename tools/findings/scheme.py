# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later
"""Finding-id scheme requested when reconnaissance starts.

Pass the first id you want (``CC-0142``, ``INT-0007``) to ``make phase-1``.
The request is stored in ``itemdb/notes/id-scheme.yml``. Later findings
continue from that sequence instead of minting another ``CC-0001``.
"""

from __future__ import annotations

import fcntl
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from findings.constants import NOTES_ROOT

STAMP_NAME = "id-scheme.yml"

_SPECIMEN_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]{0,15})-(\d{1,8})$")


class IdSchemeError(ValueError):
    """The requested scheme cannot be used."""


@dataclass(frozen=True)
class IdScheme:
    prefix: str
    width: int
    start: int
    ledger: Optional[Path] = None

    @property
    def template(self) -> str:
        return f"{self.prefix}-{{n:0{self.width}d}}"

    def format(self, number: int) -> str:
        if number < 0 or number >= 10 ** self.width:
            raise IdSchemeError(
                f"{number} does not fit in {self.prefix}-{'0' * self.width} "
                f"({self.width} digits)."
            )
        return f"{self.prefix}-{number:0{self.width}d}"

    def matches(self, finding_id: str) -> bool:
        return bool(re.fullmatch(rf"{re.escape(self.prefix)}-\d{{{self.width}}}", finding_id))

    def number_re(self) -> re.Pattern[str]:
        return re.compile(rf"\b{re.escape(self.prefix)}-(\d{{{self.width}}})\b")


def stamp_path(notes_root: Optional[Path] = None) -> Path:
    root = notes_root if notes_root is not None else NOTES_ROOT
    return root / STAMP_NAME


def parse_id_scheme(spec: str, start_override: Optional[int] = None) -> IdScheme:
    """Parse ``CC-0142`` or ``INT-0007``.

    The digits set the width and the requested start. ``--start`` replaces
    the number and keeps the width.
    """
    text = (spec or "").strip()
    match = _SPECIMEN_RE.fullmatch(text)
    if not match:
        raise IdSchemeError(
            "ID_SCHEME must be the first id you want, such as CC-0142 or "
            f"INT-0007. Got {spec!r}."
        )
    prefix, digits = match.group(1), match.group(2)
    width = len(digits)
    start = int(digits)
    if start_override is not None:
        if start_override < 0:
            raise IdSchemeError("--start must be zero or greater.")
        start = start_override
    scheme = IdScheme(prefix=prefix, width=width, start=start)
    scheme.format(start)
    return scheme


def load_id_scheme(notes_root: Optional[Path] = None) -> Optional[IdScheme]:
    path = stamp_path(notes_root)
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise IdSchemeError(f"could not read {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("specimen"), str):
        raise IdSchemeError(f"{path} must contain a specimen id.")
    start = data.get("start")
    scheme = parse_id_scheme(data["specimen"], start if isinstance(start, int) else None)
    ledger = data.get("ledger")
    if ledger:
        scheme = IdScheme(
            prefix=scheme.prefix,
            width=scheme.width,
            start=scheme.start,
            ledger=Path(str(ledger)),
        )
    return scheme


def save_id_scheme(scheme: IdScheme, notes_root: Optional[Path] = None) -> Path:
    path = stamp_path(notes_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "specimen": scheme.format(scheme.start),
        "prefix": scheme.prefix,
        "width": scheme.width,
        "start": scheme.start,
        "ledger": str(scheme.ledger) if scheme.ledger else None,
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _with_ledger(scheme: IdScheme, ledger: Optional[Path]) -> IdScheme:
    if ledger is None:
        return scheme
    return IdScheme(scheme.prefix, scheme.width, scheme.start, Path(ledger))


def preview_next_id(scheme: IdScheme, issued: list[int]) -> tuple[str, Optional[str]]:
    """Next id from numbers already on disk. Does not write a ledger."""
    local_next = max(issued, default=scheme.start - 1) + 1
    if scheme.start > local_next:
        local_next = scheme.start
    chosen = local_next
    note = None
    if scheme.ledger is not None and scheme.ledger.exists():
        slot = _slot(_read_ledger(scheme.ledger), scheme)
        if slot is not None and int(slot["next"]) > chosen:
            chosen = int(slot["next"])
            note = (
                f"requested {scheme.format(scheme.start)} is already used; "
                f"continuing at {scheme.format(chosen)}"
            )
    if issued and scheme.start > max(issued) + 1 and chosen == scheme.start and note is None:
        note = (
            f"requested start is ahead of existing findings; "
            f"the next id will be {scheme.format(chosen)}"
        )
    return scheme.format(chosen), note


def allocate_next_id(scheme: IdScheme, issued: list[int]) -> str:
    """Issue one id. A ledger, when configured, never repeats a number."""
    local_next = max(issued, default=scheme.start - 1) + 1
    if scheme.start > local_next:
        local_next = scheme.start
    if scheme.ledger is None:
        return scheme.format(local_next)

    path = scheme.ledger
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            handle.seek(0)
            raw = handle.read()
            data = json.loads(raw) if raw.strip() else {"series": {}}
            if not isinstance(data, dict) or not isinstance(data.get("series", {}), dict):
                raise IdSchemeError(f"id ledger {path} must be a JSON object with a series object.")
            data.setdefault("series", {})
            slot = _slot(data, scheme)
            if slot is None:
                slot = {"width": scheme.width, "next": local_next, "issued": []}
                data["series"][scheme.prefix] = slot
            nxt = max(int(slot["next"]), local_next)
            finding_id = scheme.format(nxt)
            issued_list = slot.setdefault("issued", [])
            if not isinstance(issued_list, list):
                raise IdSchemeError(f"id ledger series {scheme.prefix!r} has a corrupt issued list.")
            issued_list.append(finding_id)
            slot["next"] = nxt + 1
            slot["width"] = scheme.width
            handle.seek(0)
            handle.truncate()
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
    return finding_id


def _read_ledger(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise IdSchemeError(f"could not read id ledger {path}: {exc}") from exc
    if not raw.strip():
        return {"series": {}}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IdSchemeError(f"id ledger {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("series", {}), dict):
        raise IdSchemeError(f"id ledger {path} must be a JSON object with a series object.")
    data.setdefault("series", {})
    return data


def _slot(data: dict, scheme: IdScheme) -> Optional[dict]:
    slot = data.get("series", {}).get(scheme.prefix)
    if slot is None:
        return None
    if not isinstance(slot, dict) or "width" not in slot or "next" not in slot:
        raise IdSchemeError(f"id ledger series {scheme.prefix!r} is missing width/next.")
    if int(slot["width"]) != scheme.width:
        raise IdSchemeError(
            f"id ledger already numbers {scheme.prefix}- ids with width {slot['width']}, "
            f"not {scheme.width}."
        )
    return slot


def bind_ledger(scheme: IdScheme, ledger: Optional[Path]) -> IdScheme:
    return _with_ledger(scheme, ledger)
