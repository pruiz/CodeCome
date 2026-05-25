#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from findings import main as _main, STATUSES
from findings.listing import (
    filter_eligible_for_exploit,
    load_findings as _load_findings,
)

ROOT = Path(__file__).resolve().parents[1]
FINDINGS_ROOT = ROOT / "itemdb" / "findings"


def load_findings(status_filter):
    return _load_findings(status_filter, root=ROOT, findings_root=FINDINGS_ROOT, statuses=STATUSES)


if __name__ == "__main__":
    raise SystemExit(_main())
