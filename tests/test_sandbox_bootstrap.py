from __future__ import annotations

import sys
from conftest import load_tool_module


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
