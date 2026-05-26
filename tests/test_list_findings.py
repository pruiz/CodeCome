from __future__ import annotations

from pathlib import Path

from findings import listing as listing_module
from findings.constants import FindingsContext


def test_filter_eligible_for_exploit_only_returns_supported_statuses():
    rows = [
        {"id": "CC-0001", "status": "CONFIRMED", "exploitation_status": ""},
        {"id": "CC-0002", "status": "CONFIRMED", "exploitation_status": "IN_PROGRESS"},
        {"id": "CC-0003", "status": "CONFIRMED", "exploitation_status": "DEMONSTRATED"},
        {"id": "CC-0004", "status": "PENDING", "exploitation_status": ""},
    ]

    out = listing_module.filter_eligible_for_exploit(rows)
    ids = [row["id"] for row in out]
    assert ids == ["CC-0001", "CC-0002"]


def test_load_findings_skips_invalid_yaml_frontmatter(tmp_path, monkeypatch):
    findings_root = tmp_path / "itemdb" / "findings"
    pending_dir = findings_root / "PENDING"
    confirmed_dir = findings_root / "CONFIRMED"
    pending_dir.mkdir(parents=True)
    confirmed_dir.mkdir(parents=True)

    broken = pending_dir / "CC-9998-broken.md"
    broken.write_text(
        """---
id: \"CC-9998\"
title: \"Broken\"
status: \"PENDING\"
validation:
status: \"NOT_STARTED\"
  methods: []
---

# Summary
Broken.
""",
        encoding="utf-8",
    )

    valid = confirmed_dir / "CC-9999-valid.md"
    valid.write_text(
        """---
id: \"CC-9999\"
title: \"Valid\"
status: \"CONFIRMED\"
severity: \"HIGH\"
confidence: \"MEDIUM\"
---

# Summary
Valid.
""",
        encoding="utf-8",
    )

    rows = listing_module.load_findings(
        None,
        ctx=FindingsContext(
            root=tmp_path,
            itemdb_root=tmp_path / "itemdb",
            findings_root=findings_root,
        ),
    )

    assert [row["id"] for row in rows] == ["CC-9998", "CC-9999"]
    broken_row = next(row for row in rows if row["id"] == "CC-9998")
    valid_row = next(row for row in rows if row["id"] == "CC-9999")

    assert broken_row["status"] == "PENDING"
    assert broken_row["title"] == "CC-9998-broken"
    assert valid_row["status"] == "CONFIRMED"
    assert valid_row["title"] == "Valid"
