# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

try:
    import yaml
except ImportError:
    yaml = None

from findings.constants import FRONTMATTER_RE, SECTION_RE


def load_frontmatter(path: Path) -> Dict[str, object]:
    """Returns {} on missing or invalid frontmatter. Used by listing, report, index."""
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: pip install -r requirements.txt")

    content = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)

    if not match:
        return {}

    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}

    return data if isinstance(data, dict) else {}


def load_frontmatter_strict(path: Path) -> Dict[str, object]:
    """Raises ValueError on missing or invalid frontmatter. Used by checks."""
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Run: pip install -r requirements.txt")

    content = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)

    if not match:
        raise ValueError("missing YAML frontmatter")

    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a YAML object")

    return data


def replace_scalar_frontmatter(content: str, key: str, value: str) -> str:
    """Replace a quoted scalar value in YAML frontmatter only (not in body)."""
    pattern = re.compile(rf'^{re.escape(key)}:\s*".*"$', re.MULTILINE)
    replacement = f'{key}: "{value}"'
    fm_match = FRONTMATTER_RE.match(content)
    if fm_match:
        fm_block = content[: fm_match.end()]
        body = content[fm_match.end() :]
        if pattern.search(fm_block):
            fm_block = pattern.sub(replacement, fm_block, count=1)
            return fm_block + body
        return content
    if pattern.search(content):
        return pattern.sub(replacement, content, count=1)
    return content


def replace_nested_value(content: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^  {re.escape(key)}:\s*.*$", re.MULTILINE)
    replacement = f'  {key}: "{value}"'
    return pattern.sub(replacement, content, count=1)


def extract_sections(path: Path) -> Dict[str, str]:
    content = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)
    body = content[match.end() :] if match else content
    sections: Dict[str, str] = {}

    for section_match in SECTION_RE.finditer(body):
        title = section_match.group("title").strip()
        section_body = section_match.group("body").strip()
        sections[title] = section_body or "Pending."

    return sections