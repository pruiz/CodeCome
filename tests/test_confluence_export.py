from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import confluence_export as cx


def test_parse_frontmatter_reads_top_level_pairs():
    raw = (
        "---\n"
        'id: "CC-0001"\n'
        "severity: CRITICAL\n"
        "status: EXPLOITED\n"
        'title: "Missing authorization on admin API"\n'
        "validation:\n"
        "  status: DONE\n"
        "---\n"
        "# Summary\n"
        "\n"
        "body\n"
    )
    fm = cx.parse_frontmatter(raw)
    assert fm["id"] == "CC-0001"
    assert fm["severity"] == "CRITICAL"
    assert fm["status"] == "EXPLOITED"
    assert fm["title"] == "Missing authorization on admin API"
    # nested keys are ignored by the minimal parser
    assert "status" in fm
    assert "validation" not in fm or fm.get("validation") == ""


def test_strip_frontmatter_removes_block():
    raw = "---\nid: CC-0001\n---\n# Title\n\nbody\n"
    assert cx.strip_frontmatter(raw).startswith("# Title")


def test_first_h1():
    assert cx.first_h1("# Hello\n\nbody") == "Hello"
    assert cx.first_h1("no heading\n") == ""


def test_valid_xhtml():
    assert cx.valid_xhtml("<p>ok</p>") is True
    assert cx.valid_xhtml("<p>broken") is False
    assert cx.valid_xhtml('<ac:structured-macro ac:name="code"></ac:structured-macro>') is True


def test_derive_title_from_template(tmp_path: Path):
    path = tmp_path / "CC-0001-missing-auth.md"
    path.write_text("x", encoding="utf-8")
    args = Namespace(
        title_template="[{severity}|{status}] {id}: {title}",
        title=None,
        title_prefix="",
        title_suffix="",
    )
    fm = {
        "id": "CC-0001",
        "severity": "CRITICAL",
        "status": "EXPLOITED",
        "title": "Missing authorization on admin API",
    }
    title = cx.derive_title(args, str(path), h1="Summary", fm=fm)
    assert title == "[CRITICAL|EXPLOITED] CC-0001: Missing authorization on admin API"


def test_derive_title_unknown_fields_are_empty(tmp_path: Path):
    path = tmp_path / "note.md"
    path.write_text("x", encoding="utf-8")
    args = Namespace(
        title_template="{missing}-{h1}-{filename}",
        title=None,
        title_prefix="[",
        title_suffix="]",
    )
    title = cx.derive_title(args, str(path), h1="Hello", fm={})
    assert title == "[-Hello-note]"


def test_derive_title_falls_back_to_h1(tmp_path: Path):
    path = tmp_path / "report.md"
    path.write_text("x", encoding="utf-8")
    args = Namespace(
        title_template=None,
        title=None,
        title_prefix="",
        title_suffix="",
    )
    assert cx.derive_title(args, str(path), h1="Audit Report", fm={}) == "Audit Report"


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_BASE", "https://org.atlassian.net/wiki/")
    monkeypatch.setenv("CONFLUENCE_SPACE", "DOCS")
    monkeypatch.setenv("CONFLUENCE_EMAIL", "a@b.com")
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "tok")
    monkeypatch.setenv("CONFLUENCE_PARENT", "99")
    monkeypatch.setenv("CONFLUENCE_AUTH", "basic")
    cfg = cx.Config.from_env()
    assert cfg.base == "https://org.atlassian.net/wiki"
    assert cfg.space == "DOCS"
    assert cfg.parent == "99"
    assert cfg.auth_header().startswith("Basic ")


def test_config_bearer_auth(monkeypatch):
    monkeypatch.delenv("CONFLUENCE_EMAIL", raising=False)
    cfg = cx.Config(
        base="https://confluence.example",
        space="SEC",
        token="pat-token",
        auth="bearer",
    )
    assert cfg.auth_header() == "Bearer pat-token"


def test_expand_globs(tmp_path: Path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("a", encoding="utf-8")
    b.write_text("b", encoding="utf-8")
    files = cx.expand([str(tmp_path / "*.md")])
    assert files == [str(a), str(b)]


def test_cli_dry_run_with_html(tmp_path: Path, monkeypatch, capsys):
    html = tmp_path / "page.html"
    html.write_text("<p>hello</p>", encoding="utf-8")
    monkeypatch.setenv("CONFLUENCE_BASE", "https://org.atlassian.net/wiki")
    monkeypatch.setenv("CONFLUENCE_SPACE", "DOCS")
    rc = cx.main(["--dry-run", "--title", "Hello Page", str(html)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "Hello Page" in out
