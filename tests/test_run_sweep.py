"""Tests for tools/run-sweep.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from conftest import load_tool_module


def _load_run_sweep():
    return load_tool_module("run_sweep", "tools/run-sweep.py")


class TestSweepPromptTemplate:
    def test_prompt_template_path_is_phase_2_sweep(self):
        module = _load_run_sweep()
        expected = ROOT / "prompts" / "phase-2-sweep.md"
        assert module.PROMPT_TEMPLATE == expected, (
            f"Expected PROMPT_TEMPLATE to be {expected}, got {module.PROMPT_TEMPLATE}"
        )

    def test_prompt_template_exists(self):
        module = _load_run_sweep()
        assert module.PROMPT_TEMPLATE.is_file(), (
            f"Prompt template {module.PROMPT_TEMPLATE} does not exist"
        )

    def test_prompt_template_does_not_reference_old_sweep_summary(self):
        module = _load_run_sweep()
        content = module.PROMPT_TEMPLATE.read_text(encoding="utf-8")
        assert "runs/sweep-<slug>-summary-YYYY-MM-DD" not in content, (
            "Prompt template still references old sweep summary naming"
        )


class TestBuildPromptForFile:
    def test_generated_prompt_contains_target_file(self, tmp_path):
        module = _load_run_sweep()

        real_template = module.PROMPT_TEMPLATE.read_text(encoding="utf-8")
        tmp_template = tmp_path / "phase-2-sweep.md"
        tmp_template.write_text(real_template, encoding="utf-8")
        module.PROMPT_TEMPLATE = tmp_template
        orig_tmp_dir = module.TMP_DIR
        module.TMP_DIR = tmp_path / "tmp" / "file-sweep-prompts"

        try:
            prompt_path = module.build_prompt_for_file("src/app/controllers/upload.php")
            content = prompt_path.read_text(encoding="utf-8")
            assert "src/app/controllers/upload.php" in content, (
                "Generated prompt does not contain the target file path"
            )
        finally:
            module.PROMPT_TEMPLATE = ROOT / "prompts" / "phase-2-sweep.md"
            module.TMP_DIR = orig_tmp_dir

    def test_generated_prompt_contains_phase2_sweep_summary(self, tmp_path):
        module = _load_run_sweep()

        real_template = module.PROMPT_TEMPLATE.read_text(encoding="utf-8")
        tmp_template = tmp_path / "phase-2-sweep.md"
        tmp_template.write_text(real_template, encoding="utf-8")
        module.PROMPT_TEMPLATE = tmp_template
        orig_tmp_dir = module.TMP_DIR
        module.TMP_DIR = tmp_path / "tmp" / "file-sweep-prompts"

        try:
            prompt_path = module.build_prompt_for_file("src/foo/bar.c")
            content = prompt_path.read_text(encoding="utf-8")
            assert "phase-2-summary-sweep-" in content, (
                "Generated prompt does not contain phase-2-summary-sweep naming"
            )
            assert "runs/sweep-<slug>-summary-YYYY-MM-DD" not in content, (
                "Generated prompt still contains old sweep summary naming"
            )
        finally:
            module.PROMPT_TEMPLATE = ROOT / "prompts" / "phase-2-sweep.md"
            module.TMP_DIR = orig_tmp_dir

    def test_generated_prompt_uses_placeholder(self, tmp_path):
        module = _load_run_sweep()

        template = "# Sweep\nTarget: FILE_PATH_OR_ID\n"
        tmp_template = tmp_path / "test-template.md"
        tmp_template.write_text(template, encoding="utf-8")
        module.PROMPT_TEMPLATE = tmp_template
        orig_tmp_dir = module.TMP_DIR
        module.TMP_DIR = tmp_path / "tmp" / "file-sweep-prompts"

        try:
            prompt_path = module.build_prompt_for_file("test/file.py")
            content = prompt_path.read_text(encoding="utf-8")
            assert "test/file.py" in content
            assert "FILE_PATH_OR_ID" not in content
        finally:
            module.PROMPT_TEMPLATE = ROOT / "prompts" / "phase-2-sweep.md"
            module.TMP_DIR = orig_tmp_dir

    def test_missing_placeholder_raises(self, tmp_path):
        module = _load_run_sweep()

        template = "# No placeholder here"
        tmp_template = tmp_path / "bad-template.md"
        tmp_template.write_text(template, encoding="utf-8")
        module.PROMPT_TEMPLATE = tmp_template

        try:
            with pytest.raises(ValueError, match="does not contain placeholder"):
                module.build_prompt_for_file("test/file.py")
        finally:
            module.PROMPT_TEMPLATE = ROOT / "prompts" / "phase-2-sweep.md"


class TestSlugify:
    def test_slugify_sanitizes_path(self):
        module = _load_run_sweep()
        result = module.slugify("src/app/controllers/upload.php")
        assert result == "src-app-controllers-upload.php"

    def test_slugify_truncates_long_paths(self):
        module = _load_run_sweep()
        long_path = "a" * 200
        result = module.slugify(long_path)
        assert len(result) <= 120

    def test_slugify_defaults_to_target_for_empty(self):
        module = _load_run_sweep()
        result = module.slugify("---")
        assert result == "target"


class TestSweepSummaryPrompt:
    def test_summary_prompt_path_is_set(self):
        module = _load_run_sweep()
        expected = ROOT / "prompts" / "phase-2-sweep-summary.md"
        assert module.SWEEP_SUMMARY_PROMPT == expected, (
            f"Expected SWEEP_SUMMARY_PROMPT to be {expected}, got {module.SWEEP_SUMMARY_PROMPT}"
        )

    def test_summary_prompt_exists(self):
        module = _load_run_sweep()
        assert module.SWEEP_SUMMARY_PROMPT.is_file(), (
            f"Summary prompt {module.SWEEP_SUMMARY_PROMPT} does not exist"
        )

    def test_build_sweep_summary_prompt_contains_selected_files(self, tmp_path):
        module = _load_run_sweep()

        real_template = module.SWEEP_SUMMARY_PROMPT.read_text(encoding="utf-8")
        tmp_template = tmp_path / "phase-2-sweep-summary.md"
        tmp_template.write_text(real_template, encoding="utf-8")
        module.SWEEP_SUMMARY_PROMPT = tmp_template
        orig_tmp_dir = module.TMP_DIR
        module.TMP_DIR = tmp_path / "tmp" / "file-sweep-prompts"

        try:
            files = ["src/a.php", "src/b.cs"]
            prompt_path = module.build_sweep_summary_prompt(files, [])
            content = prompt_path.read_text(encoding="utf-8")
            assert "src/a.php" in content
            assert "src/b.cs" in content
            assert "## Selected files" in content
        finally:
            module.SWEEP_SUMMARY_PROMPT = ROOT / "prompts" / "phase-2-sweep-summary.md"
            module.TMP_DIR = orig_tmp_dir

    def test_build_sweep_summary_prompt_forbids_hunting(self, tmp_path):
        module = _load_run_sweep()

        real_template = module.SWEEP_SUMMARY_PROMPT.read_text(encoding="utf-8")
        tmp_template = tmp_path / "phase-2-sweep-summary.md"
        tmp_template.write_text(real_template, encoding="utf-8")
        module.SWEEP_SUMMARY_PROMPT = tmp_template
        orig_tmp_dir = module.TMP_DIR
        module.TMP_DIR = tmp_path / "tmp" / "file-sweep-prompts"

        try:
            prompt_path = module.build_sweep_summary_prompt(["src/foo.php"], [])
            content = prompt_path.read_text(encoding="utf-8")
            assert "Do NOT create new findings" in content or "not create" in content.lower()
            assert "Do NOT perform fresh vulnerability hunting" in content or "not perform" in content.lower()
        finally:
            module.SWEEP_SUMMARY_PROMPT = ROOT / "prompts" / "phase-2-sweep-summary.md"
            module.TMP_DIR = orig_tmp_dir

    def test_summary_prompt_contains_injected_per_file_summaries(self, tmp_path):
        module = _load_run_sweep()

        real_template = module.SWEEP_SUMMARY_PROMPT.read_text(encoding="utf-8")
        tmp_template = tmp_path / "phase-2-sweep-summary.md"
        tmp_template.write_text(real_template, encoding="utf-8")
        module.SWEEP_SUMMARY_PROMPT = tmp_template
        orig_tmp_dir = module.TMP_DIR
        module.TMP_DIR = tmp_path / "tmp" / "file-sweep-prompts"

        try:
            summaries = [
                "runs/phase-2-summary-sweep-src-a-2026-06-12-120000.md",
                "runs/phase-2-summary-sweep-src-b-2026-06-12-121000.md",
            ]
            prompt_path = module.build_sweep_summary_prompt(["src/a.php"], summaries)
            content = prompt_path.read_text(encoding="utf-8")
            assert "runs/sweep-summary-" in content
            assert "phase-2-summary-sweep-src-a-2026-06-12-120000.md" in content
            assert "phase-2-summary-sweep-src-b-2026-06-12-121000.md" in content
            assert "## Per-file sweep summaries" in content
        finally:
            module.SWEEP_SUMMARY_PROMPT = ROOT / "prompts" / "phase-2-sweep-summary.md"
            module.TMP_DIR = orig_tmp_dir

    def test_build_sweep_summary_prompt_raises_when_missing(self, tmp_path):
        module = _load_run_sweep()

        module.SWEEP_SUMMARY_PROMPT = tmp_path / "nonexistent.md"
        try:
            with pytest.raises(FileNotFoundError, match="missing sweep summary prompt"):
                module.build_sweep_summary_prompt(["src/foo.php"], [])
        finally:
            module.SWEEP_SUMMARY_PROMPT = ROOT / "prompts" / "phase-2-sweep-summary.md"


class TestRunSweepSummaryModelPropagation:
    """run_sweep_summary passes resolved model/variant/thinking to raw opencode run."""

    def _setup_summary_env(self, module, tmp_path, monkeypatch):
        """Configure temporary SWEEP_SUMMARY_PROMPT, TMP_DIR, and ROOT for a test.

        Returns (orig_swp, orig_tmp_dir, orig_root) for cleanup in the caller.
        """
        real_template = module.SWEEP_SUMMARY_PROMPT.read_text(encoding="utf-8")
        tmp_template = tmp_path / "phase-2-sweep-summary.md"
        tmp_template.write_text(real_template, encoding="utf-8")
        orig_swp = module.SWEEP_SUMMARY_PROMPT
        module.SWEEP_SUMMARY_PROMPT = tmp_template
        orig_tmp_dir = module.TMP_DIR
        module.TMP_DIR = tmp_path / "tmp" / "file-sweep-prompts"
        orig_root = module.ROOT
        module.ROOT = tmp_path
        return orig_swp, orig_tmp_dir, orig_root

    def _teardown_summary_env(self, module, orig_swp, orig_tmp_dir, orig_root):
        module.SWEEP_SUMMARY_PROMPT = orig_swp
        module.TMP_DIR = orig_tmp_dir
        module.ROOT = orig_root

    def test_passes_model_and_variant_flags(self, tmp_path, monkeypatch):
        """When model and variant are resolved, --model and --variant appear in the command."""
        module = _load_run_sweep()
        orig_swp, orig_tmp_dir, orig_root = self._setup_summary_env(module, tmp_path, monkeypatch)

        from codecome.config import RuntimeConfig

        fake_rc = RuntimeConfig(
            model="test-provider/test-model",
            variant="test-variant",
            model_source="env CODECOME_MODEL",
            variant_source="env CODECOME_MODEL_VARIANT",
            thinking_on=False,
            thinking_source="env",
        )
        monkeypatch.setattr(module, "resolve_runtime_config", lambda agent: fake_rc)

        captured_commands: list[list[str]] = []
        def fake_run(command, **kwargs):
            captured_commands.append(list(command))
            return module.subprocess.CompletedProcess(command, 0)

        monkeypatch.setattr(module.subprocess, "run", fake_run)

        try:
            code = module.run_sweep_summary(["src/a.php"], [])
            assert code == 0
            assert len(captured_commands) == 1
            cmd = captured_commands[0]
            assert "--model" in cmd
            model_idx = cmd.index("--model")
            assert cmd[model_idx + 1] == "test-provider/test-model"
            assert "--variant" in cmd
            variant_idx = cmd.index("--variant")
            assert cmd[variant_idx + 1] == "test-variant"
            assert "--thinking" not in cmd
            assert cmd[0] == "opencode"
            assert cmd[1] == "run"
            assert "--agent" in cmd and cmd[cmd.index("--agent") + 1] == "auditor"
        finally:
            self._teardown_summary_env(module, orig_swp, orig_tmp_dir, orig_root)

    def test_passes_thinking_flag_when_on(self, tmp_path, monkeypatch):
        """When thinking is on, --thinking appears in the command."""
        module = _load_run_sweep()
        orig_swp, orig_tmp_dir, orig_root = self._setup_summary_env(module, tmp_path, monkeypatch)

        from codecome.config import RuntimeConfig

        fake_rc = RuntimeConfig(
            model=None,
            variant=None,
            model_source="(unknown)",
            variant_source="(unknown)",
            thinking_on=True,
            thinking_source="provider-default",
        )
        monkeypatch.setattr(module, "resolve_runtime_config", lambda agent: fake_rc)

        captured_commands: list[list[str]] = []
        def fake_run(command, **kwargs):
            captured_commands.append(list(command))
            return module.subprocess.CompletedProcess(command, 0)

        monkeypatch.setattr(module.subprocess, "run", fake_run)

        try:
            code = module.run_sweep_summary(["src/b.cs"], [])
            assert code == 0
            assert len(captured_commands) == 1
            cmd = captured_commands[0]
            assert "--thinking" in cmd
            assert "--model" not in cmd
            assert "--variant" not in cmd
        finally:
            self._teardown_summary_env(module, orig_swp, orig_tmp_dir, orig_root)

    def test_no_flags_when_nothing_resolved(self, tmp_path, monkeypatch):
        """When model/variant are None and thinking is off, no extra flags are passed."""
        module = _load_run_sweep()
        orig_swp, orig_tmp_dir, orig_root = self._setup_summary_env(module, tmp_path, monkeypatch)

        from codecome.config import RuntimeConfig

        fake_rc = RuntimeConfig(
            model=None,
            variant=None,
            model_source="(unknown)",
            variant_source="(unknown)",
            thinking_on=False,
            thinking_source="env",
        )
        monkeypatch.setattr(module, "resolve_runtime_config", lambda agent: fake_rc)

        captured_commands: list[list[str]] = []
        def fake_run(command, **kwargs):
            captured_commands.append(list(command))
            return module.subprocess.CompletedProcess(command, 0)

        monkeypatch.setattr(module.subprocess, "run", fake_run)

        try:
            code = module.run_sweep_summary(["src/c.py"], [])
            assert code == 0
            assert len(captured_commands) == 1
            cmd = captured_commands[0]
            assert "--model" not in cmd
            assert "--variant" not in cmd
            assert "--thinking" not in cmd
            assert cmd[:3] == ["opencode", "run", "--agent"]
        finally:
            self._teardown_summary_env(module, orig_swp, orig_tmp_dir, orig_root)
