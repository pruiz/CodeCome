from __future__ import annotations

import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from codeql.install import _codeql_binary, _extract


def test_extract_strips_leading_codeql_prefix(tmp_path: Path) -> None:
    zip_path = tmp_path / "codeql-test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("codeql/", "")
        zf.writestr("codeql/codeql", "#!/bin/sh\necho codeql\n")
        zf.writestr("codeql/codeql.cmd", "@echo off\r\n")
        zf.writestr("codeql/cpp/extractor.txt", "cpp")
        zf.writestr("codeql/LICENSE.md", "license")

    dest_dir = tmp_path / "install"
    _extract(zip_path, dest_dir)

    assert (dest_dir / "codeql").is_file()
    assert (dest_dir / "codeql.cmd").is_file()
    assert (dest_dir / "cpp" / "extractor.txt").read_text(encoding="utf-8") == "cpp"
    assert (dest_dir / "LICENSE.md").read_text(encoding="utf-8") == "license"
    assert not (dest_dir / "codeql" / "codeql").exists()
    assert _codeql_binary(dest_dir) == dest_dir / "codeql"


def test_codeql_binary_supports_legacy_nested_layout(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy" / "codeql"
    legacy.mkdir(parents=True)
    binary = legacy / "codeql"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")

    assert _codeql_binary(tmp_path / "legacy") == binary
