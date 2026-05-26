#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Tests for tools/findings/package.py"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

import findings.package as pkg_module


@pytest.mark.unit
def test_validate_finding_id_accepts_valid_ids():
    assert pkg_module.validate_finding_id("CC-0001") == "CC-0001"
    assert pkg_module.validate_finding_id("  CC-1234  ") == "CC-1234"


@pytest.mark.unit
def test_validate_finding_id_rejects_invalid_ids():
    for invalid in ("abc", "cc-0001", "CC-001", "CC-00001", "C-0001", "CC-0001-extra"):
        try:
            pkg_module.validate_finding_id(invalid)
            pytest.fail(f"Expected SystemExit for {invalid!r}")
        except SystemExit as e:
            assert e.code == 2


@pytest.mark.unit
def test_discover_files_includes_matching_and_excludes_zip(tmp_path):
    itemdb = tmp_path / "itemdb"
    (itemdb / "findings" / "PENDING").mkdir(parents=True)
    (itemdb / "evidence" / "CC-0001").mkdir(parents=True)

    f1 = itemdb / "findings" / "PENDING" / "CC-0001-off-by-one.md"
    f1.write_text("finding content")
    f2 = itemdb / "evidence" / "CC-0001" / "README.md"
    f2.write_text("evidence content")
    f3 = itemdb / "evidence" / "CC-0001.zip"
    f3.write_text("should be excluded")
    f4 = itemdb / "evidence" / "CC-0002" / "other.md"
    f4.parent.mkdir(parents=True)
    f4.write_text("other finding")

    files = pkg_module.discover_files("CC-0001", itemdb=itemdb, evidence_root=itemdb / "evidence")
    names = [f.name for f in files]

    assert "CC-0001-off-by-one.md" in names
    assert "README.md" in names
    assert "CC-0001.zip" not in names
    assert "other.md" not in names


@pytest.mark.unit
def test_discover_files_returns_empty_when_no_itemdb(tmp_path):
    nonexistent = tmp_path / "no_itemdb"
    assert pkg_module.discover_files("CC-0001", itemdb=nonexistent) == []


@pytest.mark.unit
def test_create_bundle_makes_zip_with_relative_paths(tmp_path):
    itemdb = tmp_path / "itemdb"
    evidence = itemdb / "evidence"
    evidence.mkdir(parents=True)

    f1 = itemdb / "findings" / "PENDING" / "CC-0001.md"
    f1.parent.mkdir(parents=True)
    f1.write_text("finding")

    f2 = evidence / "CC-0001" / "log.txt"
    f2.parent.mkdir(parents=True)
    f2.write_text("log")

    zip_path = pkg_module.create_bundle(
        "CC-0001", [f1, f2],
        evidence_root=evidence,
        root=tmp_path,
    )

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()
        assert any("CC-0001.md" in n for n in namelist)
        assert any("log.txt" in n for n in namelist)
        # Should use repo-relative paths, not absolute
        assert not any(n.startswith("/") for n in namelist)


@pytest.mark.unit
def test_create_bundle_overwrites_existing_zip(tmp_path):
    itemdb = tmp_path / "itemdb"
    evidence = itemdb / "evidence"
    evidence.mkdir(parents=True)

    old_zip = evidence / "CC-0001.zip"
    old_zip.write_text("old content")

    f1 = itemdb / "notes" / "CC-0001-note.md"
    f1.parent.mkdir(parents=True)
    f1.write_text("note")

    zip_path = pkg_module.create_bundle(
        "CC-0001", [f1],
        evidence_root=evidence,
        root=tmp_path,
    )

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path, "r") as zf:
        assert zf.namelist()
    # Old content should be gone (zip overwritten, not appended)


@pytest.mark.unit
def test_main_exits_zero_on_success(capsys, tmp_path, monkeypatch):
    itemdb = tmp_path / "itemdb"
    evidence = itemdb / "evidence"
    evidence.mkdir(parents=True)

    f1 = itemdb / "findings" / "CONFIRMED" / "CC-0001.md"
    f1.parent.mkdir(parents=True)
    f1.write_text("confirmed finding")

    monkeypatch.setattr(pkg_module, "ROOT", tmp_path)
    monkeypatch.setattr(pkg_module, "EVIDENCE_ROOT", evidence)

    code = pkg_module.main(["CC-0001"])
    assert code == 0

    out = capsys.readouterr().out
    assert "Bundling 1 file(s)" in out
    assert "Created" in out

    zip_file = evidence / "CC-0001.zip"
    assert zip_file.exists()


@pytest.mark.unit
def test_main_exits_one_when_no_files(capsys, tmp_path, monkeypatch):
    itemdb = tmp_path / "itemdb"
    evidence = itemdb / "evidence"
    evidence.mkdir(parents=True)

    monkeypatch.setattr(pkg_module, "ROOT", tmp_path)
    monkeypatch.setattr(pkg_module, "EVIDENCE_ROOT", evidence)

    code = pkg_module.main(["CC-0001"])
    assert code == 1

    err = capsys.readouterr().err
    assert "No files found" in err


@pytest.mark.unit
def test_main_dry_run_prints_without_creating_zip(capsys, tmp_path, monkeypatch):
    itemdb = tmp_path / "itemdb"
    evidence = itemdb / "evidence"
    evidence.mkdir(parents=True)

    f1 = itemdb / "findings" / "PENDING" / "CC-0001.md"
    f1.parent.mkdir(parents=True)
    f1.write_text("finding")

    monkeypatch.setattr(pkg_module, "ROOT", tmp_path)
    monkeypatch.setattr(pkg_module, "EVIDENCE_ROOT", evidence)

    code = pkg_module.main(["--dry-run", "CC-0001"])
    assert code == 0

    out = capsys.readouterr().out
    assert "Would create" in out

    zip_file = evidence / "CC-0001.zip"
    assert not zip_file.exists()
