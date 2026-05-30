# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL configuration resolution.

Priority: environment variables > codecome.yml > hard-coded defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Resolve the workspace root.  When imported from the tools/codeql/ package,
# three levels above __file__ gives the repo root.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Defaults (lowest priority)
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "fail_policy": "soft",
    "pack_catalog": "./templates/codeql-packs.yml",
    "install_managed": True,
    "install_version": "latest",
    "install_path": ".tools/codeql/current/codeql",
    "output_dir": "./itemdb/codeql",
    "database_dir": "./itemdb/codeql/databases",
    "cache_dir": "./.cache/codeql",
    "phase_1_enabled": True,
    "phase_2_enabled": True,
    "candidate_mode": "precreate",
    "max_candidates": 10,
    "sweep_enabled": True,
    "sweep_inject_context": True,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_codecome_yml() -> dict[str, Any] | None:
    """Load codecome.yml and return the configured CodeQL block."""
    if yaml is None:
        return None
    path = ROOT / "codecome.yml"
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    audit = data.get("audit")
    if not isinstance(audit, dict):
        return None
    sa = audit.get("static_analysis")
    if not isinstance(sa, dict):
        return None
    cq = sa.get("codeql")
    return cq if isinstance(cq, dict) else None


def _bool_env(name: str) -> bool | None:
    """Return a tri-state bool from an env var (0/false/no → False, 1/true/yes → True)."""
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() in ("1", "true", "yes")


def _str_env(name: str) -> str | None:
    raw = os.environ.get(name)
    return raw.strip() if raw else None


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

@dataclass
class CodeQLConfig:
    """Resolved CodeQL configuration."""

    enabled: bool = True
    fail_policy: str = "soft"

    pack_catalog: str = "./templates/codeql-packs.yml"

    install_managed: bool = True
    install_version: str = "latest"
    install_path: str = ".tools/codeql/current/codeql"

    output_dir: str = "./itemdb/codeql"
    database_dir: str = "./itemdb/codeql/databases"
    cache_dir: str = "./.cache/codeql"

    phase_1_enabled: bool = True
    phase_2_enabled: bool = True
    candidate_mode: str = "precreate"
    max_candidates: int = 10

    sweep_enabled: bool = True
    sweep_inject_context: bool = True

    # Absolute paths (resolved from ROOT)
    abs_pack_catalog: Path = field(default_factory=Path)
    abs_install_path: Path = field(default_factory=Path)
    abs_output_dir: Path = field(default_factory=Path)
    abs_database_dir: Path = field(default_factory=Path)
    abs_cache_dir: Path = field(default_factory=Path)


def resolve_config() -> CodeQLConfig:
    """Resolve the CodeQL configuration.

    Priority: env vars > codecome.yml > defaults.
    """
    yml = _load_codecome_yml() or {}

    def _get(key: str, default: Any, env: str | None = None, coerce: Any = None) -> Any:
        """Pick the highest-priority value."""
        # 1. Environment variable
        if env is not None:
            raw = os.environ.get(env)
            if raw is not None and raw.strip() != "":
                if coerce is bool:
                    return raw.strip().lower() in ("1", "true", "yes")
                if coerce is int:
                    try:
                        return int(raw)
                    except ValueError:
                        pass
                return raw.strip()

        # 2. codecome.yml
        m_key = key.replace("install_", "install.").replace("phase_1_", "phase_1.").replace("phase_2_", "phase_2.").replace("sweep_", "sweep.")
        # Try nested lookup
        parts = m_key.split(".")
        node: Any = yml
        for p in parts:
            if isinstance(node, dict) and p in node:
                node = node[p]
            else:
                node = None
                break
        if node is not None:
            return node

        # 3. Defaults
        return default

    # Top-level overrides
    enabled = _bool_env("CODEQL")
    if enabled is not None:
        # CODEQL=0 → disabled, CODEQL=1 → enabled
        pass
    else:
        enabled = _get("enabled", DEFAULTS["enabled"], coerce=bool)

    # Also check CODEQL_SKIP
    skip = _bool_env("CODEQL_SKIP")
    if skip is True:
        enabled = False

    fail_policy = _str_env("CODEQL_FAIL_POLICY") or _get("fail_policy", DEFAULTS["fail_policy"])

    # Install settings
    install_managed = _get("install_managed", DEFAULTS["install_managed"],
                           env="CODEQL_MANAGED_INSTALL", coerce=bool)
    install_version = _str_env("CODEQL_VERSION") or _get("install_version", DEFAULTS["install_version"])
    install_path = _get("install_path", DEFAULTS["install_path"])

    # Paths
    pack_catalog = _get("pack_catalog", DEFAULTS["pack_catalog"])
    output_dir = _get("output_dir", DEFAULTS["output_dir"])
    database_dir = _get("database_dir", DEFAULTS["database_dir"])
    cache_dir = _get("cache_dir", DEFAULTS["cache_dir"])

    # Phase settings
    phase_1_enabled = _get("phase_1_enabled", DEFAULTS["phase_1_enabled"],
                           env="CODEQL_PHASE_1", coerce=bool)
    phase_2_enabled = _get("phase_2_enabled", DEFAULTS["phase_2_enabled"],
                           env="CODEQL_PHASE_2", coerce=bool)
    candidate_mode = _str_env("CODEQL_CANDIDATES") or _get("candidate_mode", DEFAULTS["candidate_mode"])
    max_candidates_raw = _str_env("CODEQL_MAX_CANDIDATES")
    if max_candidates_raw is None:
        max_candidates = _safe_int(_get("max_candidates", DEFAULTS["max_candidates"]), DEFAULTS["max_candidates"])
    else:
        max_candidates = _safe_int(max_candidates_raw, DEFAULTS["max_candidates"])

    # Sweep settings
    sweep_enabled = _get("sweep_enabled", DEFAULTS["sweep_enabled"],
                         env="CODEQL_SWEEP", coerce=bool)
    sweep_inject_context = _get("sweep_inject_context", DEFAULTS["sweep_inject_context"],
                                coerce=bool)

    return CodeQLConfig(
        enabled=enabled,
        fail_policy=fail_policy,
        pack_catalog=pack_catalog,
        install_managed=install_managed,
        install_version=install_version,
        install_path=install_path,
        output_dir=output_dir,
        database_dir=database_dir,
        cache_dir=cache_dir,
        phase_1_enabled=phase_1_enabled,
        phase_2_enabled=phase_2_enabled,
        candidate_mode=candidate_mode,
        max_candidates=max_candidates,
        sweep_enabled=sweep_enabled,
        sweep_inject_context=sweep_inject_context,
        abs_pack_catalog=(ROOT / pack_catalog).resolve(),
        abs_install_path=(ROOT / install_path).resolve(),
        abs_output_dir=(ROOT / output_dir).resolve(),
        abs_database_dir=(ROOT / database_dir).resolve(),
        abs_cache_dir=(ROOT / cache_dir).resolve(),
    )
