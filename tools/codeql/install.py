# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""Managed CodeQL CLI installation.

Downloads the CodeQL CLI bundle from GitHub Releases, extracts it to a
versioned directory under ``.tools/codeql/``, and maintains a ``current``
symlink pointing to the active version.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request

from codeql.config import resolve_config, CodeQLConfig, ROOT


GITHUB_API_RELEASES = "https://api.github.com/repos/github/codeql-cli-binaries/releases"

_VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+$")


def _validate_version(version: str) -> bool:
    """Return True if *version* is a safe semver-like string (no path traversal)."""
    return bool(_VERSION_RE.match(version))


def _github_headers() -> dict[str, str]:
    """Return GitHub API headers, using a token when available."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CodeCome-CodeQL-Installer/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def _detect_platform() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin":
        return "osx64"
    if system == "linux":
        return "linux64"
    if system == "windows":
        return "win64"
    raise RuntimeError(f"Unsupported platform: system={system} machine={machine}")


def _bundle_suffix(plat: str) -> str:
    """Return the asset name suffix for a given platform."""
    return f"{plat}.zip"


# ---------------------------------------------------------------------------
# Release discovery
# ---------------------------------------------------------------------------

def _fetch_latest_version() -> str:
    """Fetch the latest CodeQL CLI version tag from the GitHub API."""
    import json

    url = f"{GITHUB_API_RELEASES}/latest"
    req = Request(url, headers=_github_headers())
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch latest CodeQL CLI release: {exc}")

    tag = data.get("tag_name", "")
    # tag_name looks like "v2.20.4" — strip leading "v"
    return tag.lstrip("v") if tag.startswith("v") else tag


def _fetch_release_assets(version: str) -> list[dict]:
    """Fetch the assets for a specific release version."""
    import json

    url = f"{GITHUB_API_RELEASES}/tags/v{version}"
    req = Request(url, headers=_github_headers())
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch CodeQL CLI release v{version}: {exc}"
        )

    return data.get("assets", [])


def _find_download_url(assets: list[dict], plat: str) -> Optional[str]:
    """Find the browser_download_url for the platform-specific bundle."""
    suffix = _bundle_suffix(plat)
    for asset in assets:
        name = asset.get("name", "")
        if name.endswith(suffix):
            return asset.get("browser_download_url")
    return None


# ---------------------------------------------------------------------------
# Download and extract
# ---------------------------------------------------------------------------

def _download(url: str, dest: Path) -> None:
    """Download a file from *url* to *dest*."""
    print(f"Downloading {url} …")
    req = Request(url, headers=_github_headers())
    try:
        with urlopen(req, timeout=300) as resp:
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
    except Exception as exc:
        if dest.exists():
            dest.unlink()
        raise RuntimeError(f"Download failed: {exc}")


def _extract(zip_path: Path, dest_dir: Path) -> None:
    """Extract a zip archive to *dest_dir*, stripping the leading ``codeql/``.

    GitHub's CodeQL bundles contain a single top-level ``codeql/`` directory.
    We strip that prefix during extraction so the launcher ends up at
    ``dest_dir/codeql`` and the rest of the bundle contents sit directly under
    the version directory.
    """
    import zipfile

    prefix = "codeql/"
    dest_root = dest_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"Extracting to {dest_dir} …")
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if not info.filename.startswith(prefix):
                raise RuntimeError(
                    f"Unexpected CodeQL bundle layout: {info.filename!r} does not start with {prefix!r}"
                )

            relative_name = info.filename[len(prefix):]
            if not relative_name:
                continue

            target = (dest_dir / relative_name).resolve()
            if target != dest_root and dest_root not in target.parents:
                raise RuntimeError(f"Refusing to extract CodeQL bundle member outside target dir: {info.filename!r}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)

            mode = (info.external_attr >> 16) & 0o777
            if mode:
                target.chmod(mode)

    launcher = dest_dir / "codeql"
    if launcher.is_file():
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def _codeql_binary(base_dir: Path) -> Path:
    """Return the path to the codeql executable inside an extracted bundle.

    New installs place the binary at ``base_dir/codeql``. Keep a temporary
    fallback for older nested local installs.
    """
    binary = base_dir / "codeql"
    if binary.is_file():
        return binary
    legacy_binary = base_dir / "codeql" / "codeql"
    if legacy_binary.is_file():
        return legacy_binary
    return binary  # fall back; will fail usefully in _verify if missing


def install(config: Optional[CodeQLConfig] = None) -> int:
    """Install (or reinstall) the managed CodeQL CLI.

    Returns 0 on success, 1 on failure.
    """
    if config is None:
        config = resolve_config()

    if not config.enabled:
        print("CodeQL is disabled (CODEQL=0 or CODEQL_SKIP=1). Skipping install.")
        return 0

    if os.environ.get("CODEQL_SKIP_INSTALL") == "1":
        print("CODEQL_SKIP_INSTALL=1 — skipping managed install.")
        return 0

    if not config.install_managed:
        print("Managed install disabled in config. Skipping.")
        return 0

    # --- Determine version ---
    version = config.install_version
    if version == "latest":
        print("Determining latest CodeQL CLI version …")
        try:
            version = _fetch_latest_version()
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(f"Latest version: {version}")

    if not _validate_version(version):
        print(f"ERROR: invalid version '{version}' — must be semver-like (e.g. 2.25.5)", file=sys.stderr)
        return 1

    # --- Determine target directories ---
    tools_dir = ROOT / ".tools" / "codeql"
    version_dir = tools_dir / version
    current_link = tools_dir / "current"
    binary_path = _codeql_binary(version_dir)

    # Check if already installed
    force = os.environ.get("CODEQL_FORCE_INSTALL") == "1"
    if not force and binary_path.is_file():
        print(f"CodeQL CLI v{version} already installed at {version_dir}")
        # Ensure the 'current' symlink points to this version
        _ensure_symlink(version_dir, current_link)
        return _verify(binary_path)

    # --- Download ---
    try:
        plat = _detect_platform()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Platform: {plat}")

    if version == "latest":
        # Re-fetch since we already resolved it above
        pass

    assets = _fetch_release_assets(version)
    url = _find_download_url(assets, plat)
    if url is None:
        print(f"ERROR: No CodeQL CLI bundle found for platform '{plat}' in release v{version}",
              file=sys.stderr)
        print("Available assets:", file=sys.stderr)
        for a in assets:
            print(f"  - {a.get('name', '?')}", file=sys.stderr)
        return 1

    # --- Download and extract ---
    tmp_root = ROOT / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="codecome-codeql-", dir=tmp_root))
    try:
        zip_path = tmp_dir / f"codeql-{version}-{plat}.zip"
        _download(url, zip_path)

        # Replace stale partial installs before extracting a fresh bundle.
        if version_dir.exists():
            shutil.rmtree(version_dir)

        _extract(zip_path, version_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Recompute the binary path after extraction — a legacy nested install
    # may have been replaced with the new flat layout during this run.
    binary_path = _codeql_binary(version_dir)

    # --- Create current symlink ---
    _ensure_symlink(version_dir, current_link)

    # --- Verify ---
    return _verify(binary_path)


def _ensure_symlink(target: Path, link: Path) -> None:
    """Create or update ``link -> target``."""
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.is_file():
        link.unlink()
    elif link.is_dir():
        shutil.rmtree(link)
    link.symlink_to(target.name, target_is_directory=True)


def _verify(binary_path: Path) -> int:
    """Verify the CodeQL binary works."""
    if not binary_path.is_file():
        print(f"ERROR: CodeQL binary not found at {binary_path}", file=sys.stderr)
        return 1

    try:
        result = subprocess.run(
            [str(binary_path), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"ERROR: codeql --version failed: {result.stderr}", file=sys.stderr)
            return 1
        version_line = result.stdout.strip().split("\n")[0]
        print(f"CodeQL CLI ready: {version_line}")
        return 0
    except FileNotFoundError:
        print(f"ERROR: CodeQL binary not found at {binary_path}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
