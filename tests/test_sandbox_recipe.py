from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from sandbox.recipe import load_recipe, validate_recipe, dump_recipe


# -- Minimal valid recipe -------------------------------------------------------

VALID_RECIPE = {
    "schema_version": 1,
    "generated_by": "phase-1b-sandbox",
    "validation_model": "docker",
    "sandbox": {
        "path": "./sandbox",
        "managed": True,
        "compose_file": "./sandbox/docker-compose.yml",
        "default_service": "app",
        "workspace_root": "/workspace",
        "source_root": "/workspace/src",
    },
    "commands": {
        "setup": "./sandbox/scripts/setup.sh",
        "up": "./sandbox/scripts/up.sh",
        "check": "./sandbox/scripts/check.sh",
        "build": "./sandbox/scripts/build.sh",
        "test": "./sandbox/scripts/test.sh",
        "down": "./sandbox/scripts/down.sh",
    },
    "build_targets": [
        {
            "id": "root",
            "description": "Default target",
            "source_path": "./src",
            "service": "app",
            "workdir": "/workspace/src",
            "build_command": "./sandbox/scripts/build.sh",
            "test_command": "./sandbox/scripts/test.sh",
            "environment": {
                "type": "docker-compose",
                "compose_file": "./sandbox/docker-compose.yml",
                "service": "app",
            },
            "codeql": {
                "supported": True,
                "preferred_execution_mode": "docker-inside",
                "notes": [],
            },
        },
    ],
    "codeql": {
        "supported": True,
        "default_execution_mode": "docker-inside",
        "notes": [],
    },
    "limitations": [],
}


def _write_recipe(tmp_path: Path, recipe: dict) -> Path:
    path = tmp_path / "sandbox-recipe.yml"
    path.write_text(dump_recipe(recipe), encoding="utf-8")
    return path


class TestLoadRecipe:
    def test_load_valid_recipe(self, tmp_path: Path) -> None:
        path = _write_recipe(tmp_path, VALID_RECIPE)
        data = load_recipe(path)
        assert data["schema_version"] == 1
        assert data["validation_model"] == "docker"

    def test_load_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.yml"
        try:
            load_recipe(path)
            raise AssertionError("Expected ValueError")
        except ValueError as exc:
            assert "Failed to read" in str(exc)

    def test_load_not_a_mapping(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yml"
        path.write_text("- list\n- not\n- a mapping\n", encoding="utf-8")
        try:
            load_recipe(path)
            raise AssertionError("Expected ValueError")
        except ValueError as exc:
            assert "YAML mapping" in str(exc)


class TestValidateRecipe:
    def test_valid_recipe_passes(self, tmp_path: Path) -> None:
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(VALID_RECIPE, root=str(tmp_path))
        assert errors == [], f"Unexpected errors: {errors}"

    def test_unsupported_schema_version(self, tmp_path: Path) -> None:
        recipe = dict(VALID_RECIPE, schema_version=99)
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("unsupported schema_version" in e for e in errors)

    def test_missing_validation_model(self, tmp_path: Path) -> None:
        recipe = dict(VALID_RECIPE)
        del recipe["validation_model"]
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("missing or empty 'validation_model'" in e for e in errors)

    def test_invalid_validation_model(self, tmp_path: Path) -> None:
        recipe = dict(VALID_RECIPE, validation_model="bogus")
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("invalid validation_model" in e for e in errors)

    def test_missing_sandbox_section(self, tmp_path: Path) -> None:
        recipe = dict(VALID_RECIPE)
        del recipe["sandbox"]
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("non-mapping 'sandbox'" in e for e in errors)

    def test_sandbox_path_does_not_exist(self, tmp_path: Path) -> None:
        recipe = dict(VALID_RECIPE)
        recipe["sandbox"] = dict(recipe["sandbox"], path="./missing-dir")
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("does not exist" in e for e in errors)

    def test_empty_build_targets_for_docker_model(self, tmp_path: Path) -> None:
        recipe = dict(VALID_RECIPE, build_targets=[])
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("requires at least one target" in e for e in errors)

    def test_empty_build_targets_ok_for_static_only(self, tmp_path: Path) -> None:
        recipe = dict(VALID_RECIPE, validation_model="static-only", build_targets=[])
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert errors == []

    def test_duplicate_build_target_id(self, tmp_path: Path) -> None:
        target = VALID_RECIPE["build_targets"][0]
        recipe = dict(VALID_RECIPE, build_targets=[target, target])
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("duplicate build_target id" in e for e in errors)

    def test_build_target_missing_id(self, tmp_path: Path) -> None:
        recipe = dict(VALID_RECIPE, build_targets=[{"not_id": "root"}])
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("missing or empty 'id'" in e for e in errors)

    def test_build_target_missing_source_path(self, tmp_path: Path) -> None:
        target = dict(VALID_RECIPE["build_targets"][0])
        del target["source_path"]
        recipe = dict(VALID_RECIPE, build_targets=[target])
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("missing or empty 'source_path'" in e for e in errors)

    def test_build_target_source_path_does_not_exist(self, tmp_path: Path) -> None:
        target = dict(VALID_RECIPE["build_targets"][0], source_path="./does-not-exist")
        recipe = dict(VALID_RECIPE, build_targets=[target])
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("does not exist" in e for e in errors)

    def test_workdir_not_absolute(self, tmp_path: Path) -> None:
        target = dict(VALID_RECIPE["build_targets"][0], workdir="src")
        recipe = dict(VALID_RECIPE, build_targets=[target])
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("must be absolute" in e for e in errors)


    def test_invalid_preferred_execution_mode(self, tmp_path: Path) -> None:
        target = dict(VALID_RECIPE["build_targets"][0])
        target["codeql"] = dict(target["codeql"], preferred_execution_mode="quantum")
        recipe = dict(VALID_RECIPE, build_targets=[target])
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("preferred_execution_mode" in e and "invalid" in e for e in errors)

    def test_non_list_build_targets(self, tmp_path: Path) -> None:
        recipe = dict(VALID_RECIPE, build_targets={"not": "a list"})
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("non-list 'build_targets'" in e for e in errors)

    def test_non_mapping_build_target_entry(self, tmp_path: Path) -> None:
        recipe = dict(VALID_RECIPE, build_targets=["not a mapping"])
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("is not a mapping" in e for e in errors)

    def test_bad_commands_section(self, tmp_path: Path) -> None:
        recipe = dict(VALID_RECIPE, commands="not-a-mapping")
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("must be a mapping" in e for e in errors)

    def test_bad_limitations_section(self, tmp_path: Path) -> None:
        recipe = dict(VALID_RECIPE, limitations="not-a-list")
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("must be a list" in e for e in errors)

    def test_missing_workdir(self, tmp_path: Path) -> None:
        target = dict(VALID_RECIPE["build_targets"][0])
        del target["workdir"]
        recipe = dict(VALID_RECIPE, build_targets=[target])
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert any("missing or empty 'workdir'" in e for e in errors)

    def test_valid_recipe_with_multiple_targets(self, tmp_path: Path) -> None:
        target2 = {
            "id": "cli",
            "description": "CLI build target",
            "source_path": "./src",
            "service": "app",
            "workdir": "/workspace/src/cli",
            "build_command": "./sandbox/scripts/build-cli.sh",
            "test_command": "./sandbox/scripts/test-cli.sh",
            "environment": {
                "type": "docker-compose",
                "compose_file": "./sandbox/docker-compose.yml",
                "service": "app",
            },
            "codeql": {
                "supported": True,
                "preferred_execution_mode": "docker-inside",
                "notes": [],
            },
        }
        recipe = dict(VALID_RECIPE, build_targets=[VALID_RECIPE["build_targets"][0], target2])
        _setup_fake_paths(tmp_path)
        errors = validate_recipe(recipe, root=str(tmp_path))
        assert errors == [], f"Unexpected errors: {errors}"


def _setup_fake_paths(tmp_path: Path) -> None:
    (tmp_path / "sandbox").mkdir(exist_ok=True)
    (tmp_path / "sandbox" / "scripts").mkdir(exist_ok=True)
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "sandbox" / "docker-compose.yml").write_text("")
    (tmp_path / "sandbox" / "scripts" / "build.sh").write_text("")
    (tmp_path / "sandbox" / "scripts" / "build-cli.sh").write_text("")
