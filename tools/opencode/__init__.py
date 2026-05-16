# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
Manage opencode serve lifecycle (start, stop, health check).

Usage as a module:
    from opencode.serve import ServerRunner
    runner = ServerRunner()
    info = runner.start(port=0, hostname="127.0.0.1", log_level="WARN")
    ...
    runner.stop()

Convenience CLI:
    python -m opencode.serve start --port 8080 --log-level DEBUG
    python -m opencode.serve stop --pid 12345
"""

from __future__ import annotations

from opencode.serve import ServerRunner, ServerInfo, ServerRunnerError

__all__ = ["ServerRunner", "ServerInfo", "ServerRunnerError"]
