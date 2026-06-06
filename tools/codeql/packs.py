# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""CodeQL pack catalog loading and plan resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


class PackResolverError(RuntimeError):
    """Raised when the pack catalog or plan is invalid."""


def _require_yaml() -> None:
    if yaml is None:
        raise PackResolverError("PyYAML is required to load CodeQL pack catalogs and plans.")


def load_yaml_mapping(path: Path, *, what: str) -> dict[str, Any]:
    _require_yaml()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        raise PackResolverError(f"Failed to read {what} at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PackResolverError(f"{what} at {path} must be a YAML mapping.")
    return data


def load_pack_catalog(path: Path) -> dict[str, Any]:
    """Load and validate the CodeQL pack catalog."""
    data = load_yaml_mapping(path, what="CodeQL pack catalog")

    if data.get("schema_version") != 1:
        raise PackResolverError(f"CodeQL pack catalog at {path} must have schema_version: 1.")

    packs = data.get("packs")
    if not isinstance(packs, dict) or not packs:
        raise PackResolverError(f"CodeQL pack catalog at {path} must define a non-empty 'packs' mapping.")

    for language_id, profiles in packs.items():
        if not isinstance(language_id, str) or not language_id:
            raise PackResolverError(f"CodeQL pack catalog at {path} contains an invalid language id: {language_id!r}.")
        if not isinstance(profiles, dict) or not profiles:
            raise PackResolverError(
                f"CodeQL pack catalog at {path} must define non-empty profiles for language {language_id!r}."
            )
        for profile_name, refs in profiles.items():
            if not isinstance(profile_name, str) or not profile_name:
                raise PackResolverError(
                    f"CodeQL pack catalog at {path} contains an invalid profile name for {language_id!r}."
                )
            if not isinstance(refs, list) or not all(isinstance(ref, str) and ref for ref in refs):
                raise PackResolverError(
                    f"CodeQL pack catalog at {path} must define {language_id!r}/{profile_name!r} as a list of pack references."
                )

    candidate_policy = data.get("candidate_policy")
    if candidate_policy is not None:
        if not isinstance(candidate_policy, dict):
            raise PackResolverError(f"CodeQL pack catalog at {path} has a non-mapping 'candidate_policy' section.")
        for profile_name, policy in candidate_policy.items():
            if not isinstance(policy, dict):
                raise PackResolverError(
                    f"CodeQL pack catalog at {path} has a non-mapping candidate policy for profile {profile_name!r}."
                )
            allow_precreate = policy.get("allow_precreate")
            if not isinstance(allow_precreate, bool):
                raise PackResolverError(
                    f"CodeQL pack catalog at {path} must define candidate_policy.{profile_name}.allow_precreate as a boolean."
                )

    return data


def load_codeql_plan(path: Path) -> dict[str, Any]:
    """Load and validate a CodeQL plan file.

    Only schema v2 is supported.  Earlier versions raise an actionable
    upgrade error so the user re-runs Phase 1a.
    """
    data = load_yaml_mapping(path, what="CodeQL plan")

    version = data.get("schema_version")
    if version != 2:
        msg = (
            f"CodeQL plan at {path} has schema_version: {version!r}. "
            f"Only schema_version: 2 is supported after the CodeQL recipe "
            f"refactor.  Please delete the existing plan and re-run Phase 1a "
            f"(``make phase-1``) to regenerate a v2 plan that works with the "
            f"new sandbox-recipe integration."
        )
        raise PackResolverError(msg)

    units = data.get("analysis_units")
    if not isinstance(units, list):
        raise PackResolverError(f"CodeQL plan at {path} must define 'analysis_units' as a list.")

    for i, unit in enumerate(units):
        if not isinstance(unit, dict):
            raise PackResolverError(f"CodeQL plan at {path} has non-mapping analysis unit at index {i}.")
        unit_id = unit.get("id")
        if not isinstance(unit_id, str) or not unit_id:
            raise PackResolverError(f"CodeQL plan at {path} has analysis unit {i} without a valid 'id'.")
        unit_path = unit.get("path")
        if not isinstance(unit_path, str) or not unit_path:
            raise PackResolverError(f"CodeQL plan at {path} has analysis unit {unit_id!r} without a valid 'path'.")
        languages = unit.get("languages")
        if unit.get("recommended") is False and (languages is None or languages == []):
            continue
        if not isinstance(languages, list) or not languages:
            raise PackResolverError(f"CodeQL plan at {path} must define analysis unit {unit_id!r} languages as a non-empty list.")
        for j, entry in enumerate(languages):
            if not isinstance(entry, dict):
                raise PackResolverError(f"CodeQL plan at {path} has non-mapping language entry {j} in analysis unit {unit_id!r}.")
            language_id = entry.get("id")
            if not isinstance(language_id, str) or not language_id:
                raise PackResolverError(f"CodeQL plan at {path} has language entry {j} in analysis unit {unit_id!r} without a valid 'id'.")
            profiles = entry.get("packs")
            if not isinstance(profiles, list) or not all(isinstance(p, str) and p for p in profiles):
                raise PackResolverError(
                    f"CodeQL plan at {path} must define language {language_id!r} packs as a list of profile names."
                )

    return data


def resolve_pack_profiles(language_id: str, profiles: list[str], catalog: dict[str, Any]) -> list[str]:
    """Resolve pack profile names for one language to concrete pack references."""
    packs = catalog["packs"]
    language_profiles = packs.get(language_id)
    if not isinstance(language_profiles, dict):
        raise PackResolverError(f"Unsupported CodeQL language id: {language_id!r}.")

    resolved: list[str] = []
    seen: set[str] = set()
    for profile_name in profiles:
        refs = language_profiles.get(profile_name)
        if not isinstance(refs, list):
            raise PackResolverError(
                f"Unknown CodeQL pack profile {profile_name!r} for language {language_id!r}."
            )
        for ref in refs:
            if ref not in seen:
                resolved.append(ref)
                seen.add(ref)
    return resolved


def allow_precreate(profile_name: str, catalog: dict[str, Any]) -> bool:
    """Return whether a profile allows precreating findings by default."""
    candidate_policy = catalog.get("candidate_policy") or {}
    if not isinstance(candidate_policy, dict):
        return True
    policy = candidate_policy.get(profile_name)
    if not isinstance(policy, dict):
        return True
    value = policy.get("allow_precreate")
    return value if isinstance(value, bool) else True


def _resolve_profile_packs(language_id: str, profiles: list[str], catalog: dict[str, Any]) -> dict[str, list[str]]:
    """Resolve each profile to its own pack list (no dedup across profiles)."""
    packs = catalog["packs"]
    language_profiles = packs.get(language_id)
    if not isinstance(language_profiles, dict):
        raise PackResolverError(f"Unsupported CodeQL language id: {language_id!r}.")

    result: dict[str, list[str]] = {}
    for profile_name in profiles:
        refs = language_profiles.get(profile_name)
        if not isinstance(refs, list):
            raise PackResolverError(
                f"Unknown CodeQL pack profile {profile_name!r} for language {language_id!r}."
            )
        result[profile_name] = list(refs)
    return result


def resolve_plan_packs(plan: dict[str, Any], catalog: dict[str, Any], skip_unsupported: bool = False) -> dict[str, Any]:
    """Resolve all language entries in a CodeQL plan to concrete pack references.

    If *skip_unsupported* is True, language IDs not found in the catalog are
    skipped with a warning instead of raising PackResolverError.
    """
    units_out: list[dict[str, Any]] = []
    plan_warnings: list[str] = []

    for unit in plan.get("analysis_units", []):
        if unit.get("recommended") is False:
            plan_warnings.append(f"Skipping analysis unit '{unit['id']}' because recommended=false")
            continue

        languages_out: list[dict[str, Any]] = []
        for entry in unit.get("languages", []):
            language_id = entry["id"]
            profiles = list(entry.get("packs", []))

            if language_id not in catalog.get("packs", {}):
                if skip_unsupported:
                    plan_warnings.append(
                        f"Skipping unsupported CodeQL language '{language_id}' in analysis unit '{unit['id']}'"
                    )
                    continue
                raise PackResolverError(f"Unsupported CodeQL language id: {language_id!r}.")

            languages_out.append(
                {
                    "id": language_id,
                    "profiles": profiles,
                    "packs": resolve_pack_profiles(language_id, profiles, catalog),
                    "profile_packs": _resolve_profile_packs(language_id, profiles, catalog),
                    "candidate_policy": {
                        profile: {"allow_precreate": allow_precreate(profile, catalog)}
                        for profile in profiles
                    },
                }
            )
        units_out.append(
            {
                "id": unit["id"],
                "path": unit["path"],
                "kind": unit.get("kind"),
                "primary": unit.get("primary", False),
                "languages": languages_out,
            }
        )

    result: dict[str, Any] = {
        "schema_version": 1,
        "generated_by": "codeql-pack-resolver",
        "analysis_units": units_out,
    }
    if plan_warnings:
        result["warnings"] = plan_warnings
    return result


def dump_yaml(data: dict[str, Any]) -> str:
    """Serialize resolved pack data to YAML."""
    _require_yaml()
    return yaml.safe_dump(data, sort_keys=False)
