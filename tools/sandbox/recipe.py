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

        if validation_model == "docker":
            compose_file = sandbox.get("compose_file")
            if not isinstance(compose_file, str) or not compose_file:
                errors.append("sandbox-recipe.yml: sandbox.compose_file is missing or empty (required for docker)")
            else:
                compose_path = Path(root) / compose_file
                if not compose_path.exists():
                    errors.append(
                        f"sandbox-recipe.yml: sandbox.compose_file {compose_file!r} does not exist"
                    )

            default_service = sandbox.get("default_service")
            if not isinstance(default_service, str) or not default_service:
                errors.append("sandbox-recipe.yml: sandbox.default_service is missing or empty (required for docker)")

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
        errors.extend(_validate_build_targets(build_targets, root, validation_model))

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


def _command_looks_path_like(command: str) -> bool:
    """Return True when *command* appears to be a filesystem path.

    Shell commands like ``make -C src`` or ``mvn test`` should NOT be
    validated as paths.  Only the first token is inspected.
    """
    if not command.strip():
        return False
    try:
        first = command.strip().split()[0]
    except IndexError:
        return False
    return first.startswith(("./", "/"))


def _validate_build_targets(
    targets: list[Any], root: str | Path, validation_model: str
) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    is_docker = validation_model == "docker"

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

        # service required for docker targets
        if is_docker:
            service = target.get("service")
            if not isinstance(service, str) or not service:
                errors.append(
                    f"sandbox-recipe.yml: build_target {target_id!r} missing or empty 'service' (required for docker validation_model)"
                )

        # environment block
        environment = target.get("environment")
        if isinstance(environment, dict):
            errors.extend(_validate_target_environment(environment, target_id, root))
        elif is_docker:
            if environment is None:
                errors.append(
                    f"sandbox-recipe.yml: build_target {target_id!r} missing 'environment' block"
                )
            else:
                errors.append(
                    f"sandbox-recipe.yml: build_target {target_id!r} 'environment' must be a mapping"
                )

        # build_command
        build_command = target.get("build_command")
        if isinstance(build_command, str) and build_command.strip():
            if _command_looks_path_like(build_command):
                build_path = Path(root) / build_command
                if not build_path.exists():
                    errors.append(
                        f"sandbox-recipe.yml: build_target {target_id!r} build_command path {build_command!r} does not exist"
                    )

        # codeql hints
        codeql = target.get("codeql")
        if isinstance(codeql, dict):
            errors.extend(_validate_codeql_hints(codeql, prefix=f"build_targets[{i}].codeql"))
            if "supported" in codeql and not isinstance(codeql["supported"], bool):
                errors.append(
                    f"sandbox-recipe.yml: build_targets[{i}].codeql.supported must be boolean"
                )

    return errors


def _validate_target_environment(
    environment: dict[str, Any], target_id: str, root: str | Path
) -> list[str]:
    errors: list[str] = []
    env_type = environment.get("type")
    if isinstance(env_type, str) and env_type not in ("docker-compose", "container", "native", "static-only"):
        errors.append(
            f"sandbox-recipe.yml: build_target {target_id!r} environment.type {env_type!r} invalid "
            f"(expected docker-compose, container, native, or static-only)"
        )

    if env_type in ("docker-compose",):
        compose_file = environment.get("compose_file")
        if isinstance(compose_file, str) and compose_file.strip():
            compose_path = Path(root) / (compose_file if not Path(compose_file).is_absolute() else compose_file)
            if not compose_path.exists():
                errors.append(
                    f"sandbox-recipe.yml: build_target {target_id!r} environment.compose_file "
                    f"{compose_file!r} does not exist"
                )
        else:
            errors.append(
                f"sandbox-recipe.yml: build_target {target_id!r} missing or empty environment.compose_file"
            )

    service = environment.get("service")
    if not isinstance(service, str) or not service:
        if env_type in ("docker-compose",):
            errors.append(
                f"sandbox-recipe.yml: build_target {target_id!r} missing or empty environment.service"
            )

    return errors


def _validate_codeql_hints(codeql: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []

    if "preferred_execution_mode" in codeql:
        mode = codeql.get("preferred_execution_mode")
        if mode is not None:
            if not isinstance(mode, str) or mode not in VALID_EXECUTION_MODES:
                valid = ", ".join(sorted(VALID_EXECUTION_MODES))
                errors.append(
                    f"sandbox-recipe.yml: {prefix}.preferred_execution_mode {mode!r} invalid (allowed: {valid})"
                )

    if "default_execution_mode" in codeql:
        mode = codeql.get("default_execution_mode")
        if mode is not None:
            if not isinstance(mode, str) or mode not in VALID_EXECUTION_MODES:
                valid = ", ".join(sorted(VALID_EXECUTION_MODES))
                errors.append(
                    f"sandbox-recipe.yml: {prefix}.default_execution_mode {mode!r} invalid (allowed: {valid})"
                )

    return errors


def dump_recipe(recipe: dict[str, Any]) -> str:
    """Serialize a recipe dict to YAML string."""
    _require_yaml()
    return yaml.safe_dump(recipe, sort_keys=False)
