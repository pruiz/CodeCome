import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import pytest
import os
import json
from pathlib import Path
from typing import Any

from rendering.tools.command.interceptors.sandbox_bootstrap import SandboxBootstrapInterceptor, _is_sandbox_bootstrap_json_call, _sandbox_payload_matches, _sandbox_glyphs
from rendering.tools.command.interceptors.rtk_read import _is_bash_shim_call, RtkReadInterceptor, _BashShim
from rendering.tools.command.interceptors.rtk_grep import _normalize_rtk_grep_output, RtkGrepInterceptor
from rendering.tools.command.interceptors.shell_listing import _strip_ls_long_format_to_filenames, _parse_find_tree, ShellListingInterceptor

# We must map "module.X" to actual functions or classes
def dict_to_shim(d):
    return _BashShim(**d) if isinstance(d, dict) else d

class MockSettings:
    sandbox_render = True
    bash_shim_render = True
    sandbox_files_cap = 50
    sandbox_validate_stderr_lines = 10
    bash_shim_ls_strip_long_format = True

class MockCache:
    def reread(self, path):
        pass

class MockContext:
    def __init__(self):
        self.settings = MockSettings()
        self.root = Path(".")
        self.sink = MockSink()
        self.cache = MockCache()

class MockSink:
    def __init__(self):
        self.items = []
        self.mode = "plain"
    def write(self, renderable, *, expand=True):
        self.items.append((renderable, expand))
    def write_text(self, text):
        self.items.append(text)

class MockRenderer:
    def __init__(self):
        self.context = MockContext()
        self.rich = False
        self.plain = True

class DummyModule:
    pass
module = DummyModule()
module._is_sandbox_bootstrap_json_call = _is_sandbox_bootstrap_json_call
module._sandbox_payload_matches = _sandbox_payload_matches
module._sandbox_glyphs = _sandbox_glyphs
module._is_bash_shim_call = lambda x: _is_bash_shim_call(x)
module._normalize_rtk_grep_output = _normalize_rtk_grep_output
module._strip_ls_long_format_to_filenames = _strip_ls_long_format_to_filenames
module._parse_find_tree = _parse_find_tree

def load_tool_module(name, path):
    return module


@pytest.mark.unit

@pytest.mark.parametrize(
    ("command", "expected"),
    [
        # Direct script invocations.
        (".venv/bin/python3 tools/sandbox-bootstrap.py --format json status", "status"),
        ("python3 tools/sandbox-bootstrap.py status --format=json", "status"),
        ("python tools/sandbox-bootstrap.py --format json validate --keep-going", "validate"),
        ("python tools/sandbox-bootstrap.py --format=json detect", "detect"),
        ("./tools/sandbox-bootstrap.py --format json list", "list"),
        # make-target wrappers with json forced via BOOTSTRAP_ARGS.
        ("make sandbox-status BOOTSTRAP_ARGS='--format json'", "status"),
        ("make sandbox-validate BOOTSTRAP_ARGS=--format=json", "validate"),
        ("make sandbox-bootstrap ID=python BOOTSTRAP_ARGS='--format json'", "apply"),
        ("BOOTSTRAP_ARGS='--format json --keep-going' make sandbox-validate", "validate"),
        ("BOOTSTRAP_ARGS=--format=json make sandbox-status", "status"),
        # Negatives.
        ("python tools/sandbox-bootstrap.py status", None),  # no --format json
        ("make sandbox-status", None),                       # text mode
        ("python tools/list-findings.py --format json", None),  # different script
        ("", None),
        ("ls -la", None),
    ],
)

def test_is_sandbox_bootstrap_json_call(command, expected):
    module = load_tool_module("run_agent_sandbox_detect", "tools/run-agent.py")
    assert module._is_sandbox_bootstrap_json_call(command) == expected



@pytest.mark.unit

def test_sandbox_payload_matches_filters_unrelated_json():
    module = load_tool_module("run_agent_sandbox_match", "tools/run-agent.py")

    # Status-shape payload matches.
    assert module._sandbox_payload_matches("status", {"sandbox_state": "missing", "capabilities": {}}) is True
    # Unrelated dict does not match status.
    assert module._sandbox_payload_matches("status", {"foo": "bar"}) is False
    # list expects a list.
    assert module._sandbox_payload_matches("list", []) is True
    assert module._sandbox_payload_matches("list", {"id": "x"}) is False
    # validate expects overall_outcome or tiers.
    assert module._sandbox_payload_matches("validate", {"overall_outcome": "passed"}) is True
    assert module._sandbox_payload_matches("validate", {"tiers": []}) is True
    assert module._sandbox_payload_matches("validate", {"unrelated": True}) is False



@pytest.mark.unit

def test_maybe_render_sandbox_bootstrap_skips_non_sandbox_bash(monkeypatch):
    module = load_tool_module("run_agent_sandbox_skip", "tools/run-agent.py")
    state = {
        "input": {"command": "ls -la", "description": "list files"},
        "output": "total 0",
        "status": "completed",
    }
    assert SandboxBootstrapInterceptor().try_render(state.get('input', {}).get('command', ''), state, MockRenderer()) is False



@pytest.mark.unit

def test_maybe_render_sandbox_bootstrap_falls_through_on_invalid_json(monkeypatch):
    module = load_tool_module("run_agent_sandbox_bad_json", "tools/run-agent.py")
    state = {
        "input": {"command": "tools/sandbox-bootstrap.py --format json status"},
        "output": "Loading config...\n{partial",
        "status": "completed",
    }
    assert SandboxBootstrapInterceptor().try_render(state.get('input', {}).get('command', ''), state, MockRenderer()) is False



@pytest.mark.unit

def test_maybe_render_sandbox_bootstrap_falls_through_on_schema_mismatch(monkeypatch):
    module = load_tool_module("run_agent_sandbox_schema_miss", "tools/run-agent.py")
    state = {
        "input": {"command": "tools/sandbox-bootstrap.py --format json status"},
        "output": '{"unrelated": true, "foo": [1, 2, 3]}',
        "status": "completed",
    }
    # Looks like JSON, parses as JSON, but does not have any of
    # sandbox_state / phase2_gate_pass / capabilities -> fall through.
    assert SandboxBootstrapInterceptor().try_render(state.get('input', {}).get('command', ''), state, MockRenderer()) is False



@pytest.mark.unit

@pytest.mark.parametrize(
    ("command", "expected_family", "expected_attrs"),
    [
        # rtk read family
        ("rtk read README.md", "read", {"files": ["README.md"], "rtk_filtered": False}),
        ("rtk read README.md AGENTS.md", "read",
         {"files": ["README.md", "AGENTS.md"], "rtk_filtered": False}),
        ("rtk read --level minimal README.md", "read",
         {"files": ["README.md"], "rtk_filtered": True}),
        ("rtk read --tail-lines 5 README.md", "read",
         {"files": ["README.md"], "rtk_filtered": True}),
        ("rtk read -n -m 50 README.md", "read",
         {"files": ["README.md"], "rtk_filtered": True}),
        # cat / head / tail
        ("cat README.md", "read", {"files": ["README.md"]}),
        ("cat README.md AGENTS.md", "read", {"files": ["README.md", "AGENTS.md"]}),
        ("head -n 10 README.md", "read", {"files": ["README.md"], "head_limit": 10}),
        ("head -n10 README.md", "read", {"files": ["README.md"], "head_limit": 10}),
        ("tail -n 5 README.md", "read", {"files": ["README.md"], "tail_limit": 5}),
        # grep / rg / rtk grep
        ("rg foo tools/run-agent.py", "grep", {"pattern": "foo", "path": "tools/run-agent.py"}),
        ("rg --vimgrep render_grep tools/run-agent.py", "grep",
         {"pattern": "render_grep", "path": "tools/run-agent.py"}),
        ("rtk grep render_grep tools/run-agent.py", "grep",
         {"pattern": "render_grep", "path": "tools/run-agent.py"}),
        ("rtk grep -i needle .", "grep", {"pattern": "needle", "path": "."}),
        ("grep -r foo bar/", "grep", {"pattern": "foo", "path": "bar/"}),
        # ls
        ("ls", "ls", {"path": ".", "long_format": False}),
        ("ls -la tools", "ls", {"path": "tools", "long_format": True}),
        ("rtk ls -la", "ls", {"path": ".", "long_format": True}),
        # find / tree
        ("find tools", "find", {"path": "tools"}),
        ("find tools -name '*.py'", "find", {"path": "tools"}),
        ("tree", "find", {"path": "."}),
        # leading env / sudo wrappers should be stripped
        ("LANG=C ls tools", "ls", {"path": "tools"}),
        ("sudo cat /etc/hosts", "read", {"files": ["/etc/hosts"]}),
        ("time rg foo bar/", "grep", {"pattern": "foo", "path": "bar/"}),
    ],
)

def test_is_bash_shim_call_recognises_supported_commands(command, expected_family, expected_attrs):
    module = load_tool_module("run_agent_shim_detect", "tools/run-agent.py")
    shim = module._is_bash_shim_call(command)
    assert shim is not None, f"expected shim match for {command!r}"
    assert shim.family == expected_family
    for k, v in expected_attrs.items():
        assert getattr(shim, k) == v, (
            f"attribute {k}: expected {v!r}, got {getattr(shim, k)!r} for {command!r}"
        )



@pytest.mark.unit

@pytest.mark.parametrize(
    "command",
    [
        "",
        "echo hello",
        "make phase-1",
        "git status",
        "rtk diff a b",
        "rtk smart README.md",
        # Pipelines / redirections / substitutions disqualify shim handling.
        "cat README.md | head",
        "rg foo > out.txt",
        "ls && pwd",
        "ls; pwd",
        "echo $(pwd)",
        "cat `which python`",
        # No file argument.
        "rtk read",
        "cat",
        "rg",
        # rtk subcommand we don't route.
        "rtk json '{}'",
        "rtk wc README.md",
    ],
)

def test_is_bash_shim_call_rejects_unsupported(command):
    module = load_tool_module("run_agent_shim_reject", "tools/run-agent.py")
    assert module._is_bash_shim_call(command) is None



@pytest.mark.unit

def test_normalize_rtk_grep_output_converts_grouped_to_flat():
    module = load_tool_module("run_agent_shim_norm_rtk", "tools/run-agent.py")
    raw = (
        "4 matches in 3F:\n"
        "\n"
        "[file] tools/run-agent.py (2):\n"
        "  2811: return render_grep_rich(console, state)\n"
        "  2813: return render_grep_plain(state)\n"
        "\n"
        "[file] tools/x.py (1):\n"
        "    42: hit\n"
    )
    out = module._normalize_rtk_grep_output(raw)
    lines = [l for l in out.split("\n") if l.strip()]
    assert lines == [
        "tools/run-agent.py:2811:return render_grep_rich(console, state)",
        "tools/run-agent.py:2813:return render_grep_plain(state)",
        "tools/x.py:42:hit",
    ]



@pytest.mark.unit

def test_normalize_rtk_grep_output_passes_through_when_no_markers():
    module = load_tool_module("run_agent_shim_norm_passthrough", "tools/run-agent.py")
    raw = "tools/foo.py:10:hit\nanother line\n"
    assert module._normalize_rtk_grep_output(raw) == raw



@pytest.mark.unit

def test_strip_ls_long_format_to_filenames_strips_columns_and_total():
    module = load_tool_module("run_agent_shim_ls_strip", "tools/run-agent.py")
    raw = (
        "total 616\n"
        "drwxr-xr-x@ 14 pruiz  staff     448 May  8 03:02 __pycache__\n"
        "-rw-r--r--@  1 pruiz  staff    3893 May  8 00:37 _colors.py\n"
        "-rwxr-xr-x@  1 pruiz  staff    6347 May  8 00:37 check-frontmatter.py\n"
    )
    out = module._strip_ls_long_format_to_filenames(raw)
    assert out.split("\n") == ["__pycache__", "_colors.py", "check-frontmatter.py"]



@pytest.mark.unit

def test_maybe_render_bash_shim_skips_unrecognized_commands():
    module = load_tool_module("run_agent_shim_skip", "tools/run-agent.py")
    state = {
        "input": {"command": "make phase-1", "description": ""},
        "output": "Phase 1 done",
        "status": "completed",
    }
    assert RtkReadInterceptor().try_render(state.get('input', {}).get('command', ''), state, MockRenderer()) or RtkGrepInterceptor().try_render(state.get('input', {}).get('command', ''), state, MockRenderer()) or ShellListingInterceptor().try_render(state.get('input', {}).get('command', ''), state, MockRenderer()) is False



@pytest.mark.unit

def test_parse_find_tree_extracts_name_filter():
    module = load_tool_module("run_agent_find_name_1", "tools/run-agent.py")
    shim = module._parse_find_tree("find", ["itemdb/findings", "-name", "*.md"], "find itemdb/findings -name '*.md'")
    assert shim is not None
    assert shim.pattern == "*.md"
    assert shim.path == "itemdb/findings"



@pytest.mark.unit

def test_parse_find_tree_extracts_iname_filter():
    module = load_tool_module("run_agent_find_name_2", "tools/run-agent.py")
    shim = module._parse_find_tree("find", [".", "-iname", "*.PY"], "find . -iname '*.PY'")
    assert shim is not None
    assert shim.pattern == "*.PY"
    assert shim.path == "."



@pytest.mark.unit

def test_parse_find_tree_no_name_falls_back_to_verb():
    module = load_tool_module("run_agent_find_name_3", "tools/run-agent.py")
    shim = module._parse_find_tree("find", ["src/"], "find src/")
    assert shim is not None
    assert shim.pattern == "find"
    assert shim.path == "src/"



@pytest.mark.unit

def test_parse_find_tree_extracts_path_after_type_flag():
    module = load_tool_module("run_agent_find_name_4", "tools/run-agent.py")
    shim = module._parse_find_tree("find", ["itemdb", "-type", "f", "-name", "*.md"], "find itemdb -type f -name '*.md'")
    assert shim is not None
    assert shim.pattern == "*.md"
    assert shim.path == "itemdb"



@pytest.mark.unit

def test_parse_find_tree_tree_verb_no_name():
    module = load_tool_module("run_agent_find_name_5", "tools/run-agent.py")
    shim = module._parse_find_tree("tree", ["src/"], "tree src/")
    assert shim is not None
    assert shim.pattern == "tree"
    assert shim.path == "src/"


# ---------------------------------------------------------------------------
# load_prompt extra-prompt tests
# ---------------------------------------------------------------------------

