# Copyright (C) 2025-2026 Pablo Ruiz Garcia <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Sandbox recipe: load and validate sandbox-recipe.yml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

SUPPORTED_SCHEMA_VERSIONS = frozenset({1})
VALID_VALIDATION_MODELS = frozenset({"docker", "static-only", "nested-virt"})
VALID_INSTALL_STRATEGIES = frozenset({"mount-host-bundle", "copy-host-bundle", "image-preinstalled"})
VALID_EXECUTION_MODES = frozenset({"host", "docker-inside", "docker-wrapper", "unavailable"})


def _require_yaml() -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required to load sandbox recipes.")


def load_recipe(path: str | Path) -> dict[str, Any]:
    """Load a sandbox-recipe.yml file as a mapping.

    Returns the parsed dict. Does not validate (call ``validate_recipe`` separately).
    """
    _require_yaml()
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Failed to read sandbox recipe at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Sandbox recipe at {path} must be a YAML mapping")
    return data


def validate_recipe(recipe: dict[str, Any], *, root: str | Path) -> list[str]:
    """Validate a loaded sandbox-recipe dict.

    Returns a list of error strings (empty = valid).  ``root`` is the
    workspace root path used to resolve relative paths.
    """
    errors: list[str] = []

    # --- schema_version ---
    version = recipe.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        supported = ", ".join(str(v) for v in sorted(SUPPORTED_SCHEMA_VERSIONS))
        errors.append(
            f"sandbox-recipe.yml: unsupported schema_version {version!r} (supported: {supported})"
        )

    # --- validation_model ---
    validation_model = recipe.get("validation_model")
    if not isinstance(validation_model, str) or not validation_model.strip():
        errors.append("sandbox-recipe.yml: missing or empty 'validation_model'")
    elif validation_model not in VALID_VALIDATION_MODELS:
        valid = ", ".join(sorted(VALID_VALIDATION_MODELS))
        errors.append(
            f"sandbox-recipe.yml: invalid validation_model {validation_model!r} (allowed: {valid})"
        )

    # --- sandbox block ---
    sandbox = recipe.get("sandbox")
    if not isinstance(sandbox, dict):
        errors.append("sandbox-recipe.yml: missing or non-mapping 'sandbox' section")
    else:
        sandbox_path_str = sandbox.get("path")
        if not isinstance(sandbox_path_str, str) or not sandbox_path_str:
            errors.append("sandbox-recipe.yml: sandbox.path is missing or empty")
        else:
            sandbox_path = Path(root) / sandbox_path_str
            if not sandbox_path.exists():
                errors.append(
                    f"sandbox-recipe.yml: sandbox.path {sandbox_path_str!r} does not exist"
                )

    # --- commands block (optional but warn on missing known keys) ---
    commands = recipe.get("commands")
    if commands is not None and not isinstance(commands, dict):
        errors.append("sandbox-recipe.yml: 'commands' must be a mapping")

    # --- build_targets ---
    build_targets = recipe.get("build_targets")
    buildless = validation_model in ("static-only",)

    if not isinstance(build_targets, list):
        if not buildless:
            errors.append("sandbox-recipe.yml: missing or non-list 'build_targets'")
    elif len(build_targets) == 0 and not buildless:
        errors.append(
            "sandbox-recipe.yml: 'build_targets' is empty but validation_model requires at least one target"
        )
    elif isinstance(build_targets, list):
        errors.extend(_validate_build_targets(build_targets, root))

    # --- codeql block (optional) ---
    codeql = recipe.get("codeql")
    if codeql is not None:
        if not isinstance(codeql, dict):
            errors.append("sandbox-recipe.yml: 'codeql' must be a mapping")
        else:
            errors.extend(_validate_codeql_hints(codeql, prefix="codeql"))

    # --- limitations (optional) ---
    limitations = recipe.get("limitations")
    if limitations is not None and not isinstance(limitations, list):
        errors.append("sandbox-recipe.yml: 'limitations' must be a list")

    return errors


def _validate_build_targets(targets: list[Any], root: str | Path) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()

    for i, target in enumerate(targets):
        if not isinstance(target, dict):
            errors.append(
                f"sandbox-recipe.yml: build_targets[{i}] is not a mapping"
            )
            continue

        target_id = target.get("id")
        if not isinstance(target_id, str) or not target_id:
            errors.append(
                f"sandbox-recipe.yml: build_targets[{i}] missing or empty 'id'"
            )
            continue

        if target_id in seen_ids:
            errors.append(
                f"sandbox-recipe.yml: duplicate build_target id {target_id!r}"
            )
        seen_ids.add(target_id)

        # source_path
        source_path_str = target.get("source_path")
        if not isinstance(source_path_str, str) or not source_path_str:
            errors.append(
                f"sandbox-recipe.yml: build_target {target_id!r} missing or empty 'source_path'"
            )
        else:
            source_path = Path(root) / source_path_str
            if not source_path.exists():
                errors.append(
                    f"sandbox-recipe.yml: build_target {target_id!r} source_path {source_path_str!r} does not exist"
                )

        # workdir must be absolute inside the sandbox
        workdir = target.get("workdir")
        if not isinstance(workdir, str) or not workdir:
            errors.append(
                f"sandbox-recipe.yml: build_target {target_id!r} missing or empty 'workdir'"
            )
        elif not workdir.startswith("/"):
            errors.append(
                f"sandbox-recipe.yml: build_target {target_id!r} workdir {workdir!r} must be absolute (e.g. /workspace/src)"
            )

        # codeql hints
        codeql = target.get("codeql")
        if isinstance(codeql, dict):
            errors.extend(_validate_codeql_hints(codeql, prefix=f"build_targets[{i}].codeql"))

    return errors


def _validate_codeql_hints(codeql: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []

    install_strategy = codeql.get("install_strategy")
    if install_strategy is not None:
        if not isinstance(install_strategy, str) or install_strategy not in VALID_INSTALL_STRATEGIES:
            valid = ", ".join(sorted(VALID_INSTALL_STRATEGIES))
            errors.append(
                f"sandbox-recipe.yml: {prefix}.install_strategy {install_strategy!r} invalid (allowed: {valid})"
            )

    preferred_mode = codeql.get("preferred_execution_mode")
    if preferred_mode is not None:
        if not isinstance(preferred_mode, str) or preferred_mode not in VALID_EXECUTION_MODES:
            valid = ", ".join(sorted(VALID_EXECUTION_MODES))
            errors.append(
                f"sandbox-recipe.yml: {prefix}.preferred_execution_mode {preferred_mode!r} invalid (allowed: {valid})"
            )

    return errors


def dump_recipe(recipe: dict[str, Any]) -> str:
    """Serialize a recipe dict to YAML string."""
    _require_yaml()
    return yaml.safe_dump(recipe, sort_keys=False)
