from __future__ import annotations

import json
from conftest import ROOT, load_tool_module


def test_sandbox_bootstrap_parser_main(monkeypatch):
    module = load_tool_module("sandbox_bootstrap", "tools/sandbox-bootstrap.py")
    
    # Mock cmd_list to just return args so we can inspect them
    def mock_cmd_list(args):
        return args
        
    monkeypatch.setattr(module, "cmd_list", mock_cmd_list)
    
    # Test format before subcommand
    args = module.main(["--format", "json", "list"])
    assert args.command == "list"
    assert args.format == "json"
    
    # Test format after subcommand
    args = module.main(["list", "--format", "json"])
    assert args.command == "list"
    assert args.format == "json"
    
    # Test default format
    args = module.main(["list"])
    assert args.command == "list"
    assert args.format == "text"


def test_sandbox_bootstrap_parser_validate_keep_going():
    module = load_tool_module("sandbox_bootstrap", "tools/sandbox-bootstrap.py")
    parser = module.build_parser()
    
    # Test keep_going is present for validate
    args = parser.parse_args(["validate"])
    assert args.command == "validate"
    assert hasattr(args, "keep_going")
    assert args.keep_going is False
    
    # Test keep_going can be set for validate
    args = parser.parse_args(["validate", "--keep-going"])
    assert args.command == "validate"
    assert args.keep_going is True


def test_render_provenance_includes_compose_project_name():
    module = load_tool_module("sandbox_bootstrap_provenance", "tools/sandbox-bootstrap.py")

    example = module.ExampleManifest(
        id="php",
        display_name="PHP project",
        path=module.TEMPLATES_ROOT / "php",
    )

    content = module.render_provenance(
        example=example,
        markers={"TARGET_NAME": "phorge"},
        file_hashes={".env": "abc123"},
        compose_project_name="phorge",
    )

    assert "## Runtime metadata" in content
    assert "`COMPOSE_PROJECT_NAME`" in content
    assert "`phorge`" in content


def test_opencode_json_allows_src_and_sandbox_env_reads():
    # Read as plain JSON because this file is expected to be strict JSON.
    with (ROOT / "opencode.json").open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    read_rules = config["permission"]["read"]

    assert read_rules["*.env"] == "deny"
    assert read_rules["*.env.*"] == "deny"
    assert read_rules["src/**/.env"] == "allow"
    assert read_rules["src/**/.env.*"] == "allow"
    assert read_rules["sandbox/.env"] == "allow"


def test_detect_signals_prefers_erlang_otp_for_rebar_targets(tmp_path, monkeypatch):
    module = load_tool_module("sandbox_bootstrap_erlang_detect", "tools/sandbox-bootstrap.py")

    src_root = tmp_path / "src"
    (src_root / "apps").mkdir(parents=True)
    (src_root / "rebar.config").write_text("{plugins, []}.\n", encoding="utf-8")
    (src_root / "apps" / "demo.erl").write_text("-module(demo).\n", encoding="utf-8")
    (src_root / "apps" / "demo.hrl").write_text("-define(DEMO, ok).\n", encoding="utf-8")
    (src_root / "apps" / "demo.app.src").write_text("{application, demo, []}.\n", encoding="utf-8")

    monkeypatch.setattr(module, "SRC_ROOT", src_root)
    module._MANIFEST_CACHE = None

    signals = module.detect_signals(force_src_walk=True)

    assert "erlang-otp" in signals["languages"]
    assert "rebar.config" in signals["manifests"]
    assert "*.app.src" in signals["manifests"]

    ranked = module.rank_examples(module.discover_examples(), signals)
    assert ranked[0]["id"] == "erlang-otp"


def test_detect_signals_reads_erlang_terms_from_recon_notes(tmp_path, monkeypatch):
    module = load_tool_module("sandbox_bootstrap_erlang_notes", "tools/sandbox-bootstrap.py")

    notes_root = tmp_path / "notes"
    notes_root.mkdir(parents=True)
    (notes_root / "target-profile.md").write_text(
        "Target uses Erlang OTP with rebar3 and Common Test.\n",
        encoding="utf-8",
    )
    (notes_root / "build-model.md").write_text(
        "Build uses rebar.config, dialyzer, xref, and ELP.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "NOTES_ROOT", notes_root)
    module._MANIFEST_CACHE = None

    signals = module.detect_signals()

    assert "erlang-otp" in signals["languages"]
    assert "rebar.config" in signals["manifests"]
