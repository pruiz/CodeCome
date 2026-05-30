from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codeql.packs import PackResolverError, load_codeql_plan, load_pack_catalog, resolve_pack_profiles, resolve_plan_packs, _resolve_profile_packs


def _write_catalog(path: Path) -> None:
    path.write_text(
        (
            "schema_version: 1\n"
            "packs:\n"
            "  python:\n"
            "    official:\n"
            "      - codeql/python-queries\n"
            "    github-security-lab:\n"
            "      - githubsecuritylab/codeql-python-queries\n"
            "    local:\n"
            "      - ./queries/codeql/python\n"
            "  c-cpp:\n"
            "    official:\n"
            "      - codeql/cpp-queries\n"
            "    trailofbits:\n"
            "      - trailofbits/cpp-queries\n"
            "    coding-standards:\n"
            "      - codeql/coding-standards-cpp\n"
            "candidate_policy:\n"
            "  official:\n"
            "    allow_precreate: true\n"
            "  coding-standards:\n"
            "    allow_precreate: false\n"
        ),
        encoding="utf-8",
    )


def _write_plan(path: Path) -> None:
    path.write_text(
        (
            "schema_version: 1\n"
            "analysis_units:\n"
            "  - id: root\n"
            "    path: ./src\n"
            "    languages:\n"
            "      - id: python\n"
            "        packs:\n"
            "          - official\n"
            "          - github-security-lab\n"
            "      - id: c-cpp\n"
            "        packs:\n"
            "          - official\n"
            "          - coding-standards\n"
        ),
        encoding="utf-8",
    )


def test_load_pack_catalog_validates_schema(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.yml"
    _write_catalog(catalog_path)

    catalog = load_pack_catalog(catalog_path)
    assert catalog["schema_version"] == 1
    assert catalog["packs"]["python"]["official"] == ["codeql/python-queries"]


def test_resolve_pack_profiles_preserves_order_and_dedupes(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.yml"
    _write_catalog(catalog_path)
    catalog = load_pack_catalog(catalog_path)
    catalog["packs"]["python"]["dup"] = ["codeql/python-queries"]

    resolved = resolve_pack_profiles("python", ["official", "dup", "github-security-lab"], catalog)
    assert resolved == ["codeql/python-queries", "githubsecuritylab/codeql-python-queries"]


def test_resolve_pack_profiles_rejects_unknown_language(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.yml"
    _write_catalog(catalog_path)
    catalog = load_pack_catalog(catalog_path)

    try:
        resolve_pack_profiles("ruby", ["official"], catalog)
    except PackResolverError as exc:
        assert "Unsupported CodeQL language id" in str(exc)
    else:
        raise AssertionError("expected PackResolverError")


def test_resolve_pack_profiles_rejects_unknown_profile(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.yml"
    _write_catalog(catalog_path)
    catalog = load_pack_catalog(catalog_path)

    try:
        resolve_pack_profiles("python", ["trailofbits"], catalog)
    except PackResolverError as exc:
        assert "Unknown CodeQL pack profile" in str(exc)
    else:
        raise AssertionError("expected PackResolverError")


def test_resolve_plan_packs_includes_profile_packs(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.yml"
    plan_path = tmp_path / "plan.yml"
    _write_catalog(catalog_path)
    _write_plan(plan_path)

    catalog = load_pack_catalog(catalog_path)
    plan = load_codeql_plan(plan_path)
    resolved = resolve_plan_packs(plan, catalog)

    languages = resolved["analysis_units"][0]["languages"]
    assert languages[0]["packs"] == [
        "codeql/python-queries",
        "githubsecuritylab/codeql-python-queries",
    ]
    # profile_packs maps each profile to its individual packs (no dedup across profiles)
    assert languages[0]["profile_packs"] == {
        "official": ["codeql/python-queries"],
        "github-security-lab": ["githubsecuritylab/codeql-python-queries"],
    }
    assert languages[1]["candidate_policy"]["coding-standards"]["allow_precreate"] is False


def test_resolve_profile_packs_rejects_unknown_profile() -> None:
    catalog = {
        "schema_version": 1,
        "packs": {
            "python": {
                "official": ["codeql/python-queries"],
            }
        },
    }
    try:
        _resolve_profile_packs("python", ["trailofbits"], catalog)
    except PackResolverError as exc:
        assert "Unknown CodeQL pack profile" in str(exc)
    else:
        raise AssertionError("expected PackResolverError")


def test_resolve_profile_packs_rejects_unknown_language() -> None:
    catalog = {
        "schema_version": 1,
        "packs": {},
    }
    try:
        _resolve_profile_packs("ruby", ["official"], catalog)
    except PackResolverError as exc:
        assert "Unsupported CodeQL language id" in str(exc)
    else:
        raise AssertionError("expected PackResolverError")


def test_resolve_plan_packs_candidate_policy(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.yml"
    plan_path = tmp_path / "plan.yml"
    _write_catalog(catalog_path)
    _write_plan(plan_path)

    catalog = load_pack_catalog(catalog_path)
    plan = load_codeql_plan(plan_path)
    resolved = resolve_plan_packs(plan, catalog)

    languages = resolved["analysis_units"][0]["languages"]
    assert languages[0]["packs"] == [
        "codeql/python-queries",
        "githubsecuritylab/codeql-python-queries",
    ]
    assert languages[1]["candidate_policy"]["coding-standards"]["allow_precreate"] is False


def test_load_codeql_plan_rejects_invalid_language_entry(tmp_path: Path) -> None:
    plan_path = tmp_path / "bad-plan.yml"
    plan_path.write_text("analysis_units:\n  - nope\n", encoding="utf-8")

    try:
        load_codeql_plan(plan_path)
    except PackResolverError as exc:
        assert "non-mapping analysis unit" in str(exc)
    else:
        raise AssertionError("expected PackResolverError")
