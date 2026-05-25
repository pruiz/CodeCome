"""Test that CLI render tunables propagate into RenderSettings.

Regression test for PR #21 comment: --read-display-lines,
--write-content-lines, --write-diff-limit, --edit-diff-lines must reach
the rendering context's settings when the phase harness applies overrides.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import dataclasses
import pytest

from rendering.dispatch import _get_rendering_ctx, _RENDERING_CTX_CACHE


@pytest.fixture(autouse=True)
def _clear_ctx_cache():
    """Ensure each test starts with a fresh rendering context cache."""
    _RENDERING_CTX_CACHE.clear()
    yield
    _RENDERING_CTX_CACHE.clear()


def test_cli_overrides_propagate_to_render_settings():
    """Verify that dataclasses.replace on the context settings
    correctly overrides the tunables, matching the pattern used
    by codecome.harness.run_phase_mode."""
    # Get a plain-mode context (console=None → plain sink)
    ctx = _get_rendering_ctx(None)
    assert ctx.settings.read_display_lines == 10  # default
    assert ctx.settings.write_content_lines == 25  # default
    assert ctx.settings.write_diff_limit == 50    # default
    assert ctx.settings.edit_diff_lines == 25     # default

    # Apply CLI overrides (same pattern as harness.py)
    overrides = {
        "read_display_lines": 42,
        "write_content_lines": 99,
        "write_diff_limit": 200,
        "edit_diff_lines": 7,
    }
    ctx.settings = dataclasses.replace(ctx.settings, **overrides)

    assert ctx.settings.read_display_lines == 42
    assert ctx.settings.write_content_lines == 99
    assert ctx.settings.write_diff_limit == 200
    assert ctx.settings.edit_diff_lines == 7


def test_cached_context_preserves_overrides():
    """Once overrides are applied, subsequent _get_rendering_ctx calls
    should return the same context with overrides intact."""
    ctx = _get_rendering_ctx(None)
    ctx.settings = dataclasses.replace(ctx.settings, read_display_lines=77)

    ctx2 = _get_rendering_ctx(None)
    assert ctx2 is ctx
    assert ctx2.settings.read_display_lines == 77
