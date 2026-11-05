#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later
"""
confluence_export.py — publish Markdown (or HTML) files to Confluence Cloud / Server.

Reusable, project-agnostic. Nothing is hardcoded: every destination setting comes
from a CLI flag or an environment variable.

What it does
------------
  * Converts each Markdown file to Confluence *storage format* (XHTML) with pandoc.
    (Files that are already .html/.xhtml are posted as-is.)
  * Strips a leading YAML frontmatter block (--- ... ---) if present.
  * Idempotent: finds an existing page by exact title in the space and UPDATES it
    (version bump) instead of creating a duplicate. New titles are CREATED.
  * Validates well-formed XHTML before posting, so you never eat an opaque HTTP 400.
  * --dry-run previews titles + validation with no network calls.
  * Optional labels, optional parent page, optional per-file title templating.

Auth
----
  Cloud  (default): Basic auth = base64(email:api_token)
                    token from https://id.atlassian.com/manage-profile/security/api-tokens
  Server/DC:        Bearer personal access token  (--auth bearer)

Quick start
-----------
  export CONFLUENCE_BASE="https://your-org.atlassian.net/wiki"
  export CONFLUENCE_EMAIL="you@org.com"
  export CONFLUENCE_API_TOKEN="xxxx"
  export CONFLUENCE_SPACE="DOCS"

  # one file, title taken from its first "# H1"
  ./tools/confluence-export.py notes.md

  # findings with frontmatter-driven titles
  ./tools/confluence-export.py \\
    --title-template "[{effect}|{status}] {id}: {title}" \\
    itemdb/findings/CONFIRMED/*.md itemdb/findings/EXPLOITED/*.md

  # preview only, no posting
  ./tools/confluence-export.py --dry-run itemdb/reports/report.md

As a library
------------
  import confluence_export as cx
  cfg  = cx.Config.from_env(space="DOCS", parent="123456")
  html = cx.to_storage("# Hello\\n\\nbody")        # markdown -> storage XHTML
  cx.publish_page(cfg, title="My Page", html=html)
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

# --------------------------------------------------------------------------- config


@dataclass
class Config:
    base: str  # e.g. https://org.atlassian.net/wiki  (no trailing slash)
    space: str  # space key, e.g. "DOCS"
    email: str = ""  # Cloud basic-auth user
    token: str = ""  # API token / PAT
    parent: str = ""  # parent page id (optional)
    auth: str = "basic"  # "basic" (Cloud) | "bearer" (Server/DC PAT)

    @classmethod
    def from_env(cls, **override):
        c = cls(
            base=os.getenv("CONFLUENCE_BASE", "").rstrip("/"),
            space=os.getenv("CONFLUENCE_SPACE", ""),
            email=os.getenv("CONFLUENCE_EMAIL", ""),
            token=os.getenv("CONFLUENCE_API_TOKEN", ""),
            parent=os.getenv("CONFLUENCE_PARENT", ""),
            auth=os.getenv("CONFLUENCE_AUTH", "basic"),
        )
        for k, v in override.items():
            if v is not None:
                setattr(c, k, v)
        return c

    def auth_header(self) -> str:
        if self.auth == "bearer":
            return "Bearer " + self.token
        return "Basic " + base64.b64encode(f"{self.email}:{self.token}".encode()).decode()

    def validate(self, need_token=True):
        missing = []
        if not self.base:
            missing.append("base (CONFLUENCE_BASE / --base)")
        if not self.space:
            missing.append("space (CONFLUENCE_SPACE / --space)")
        if need_token and not self.token:
            missing.append("token (CONFLUENCE_API_TOKEN)")
        if need_token and self.auth == "basic" and not self.email:
            missing.append("email (CONFLUENCE_EMAIL / --email) for basic auth")
        if missing:
            sys.exit("Missing config: " + "; ".join(missing))


# --------------------------------------------------------------------- markdown -> xhtml

_PANDOC = os.getenv("PANDOC") or shutil.which("pandoc")
_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.S)
# validation shim: declares the ac:/ri: namespaces Confluence macros use so they
# don't trip the parser; purely for well-formedness checking, never sent.
_NS = '<root xmlns:ac="x" xmlns:ri="y">'


def strip_frontmatter(md: str) -> str:
    return _FRONTMATTER.sub("", md, count=1)


def to_storage(md_body: str, pandoc: str | None = None) -> str:
    """Convert Markdown to Confluence storage-format XHTML via pandoc."""
    exe = pandoc or _PANDOC
    if not exe:
        sys.exit(
            "pandoc not found. Install it (brew install pandoc / apt install pandoc) "
            "or set PANDOC=/path/to/pandoc."
        )
    p = subprocess.run(
        [exe, "-f", "markdown", "-t", "html", "--wrap=none"],
        input=md_body,
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"pandoc failed: {p.stderr[:300]}")
    return p.stdout


def valid_xhtml(html: str) -> bool:
    try:
        ET.fromstring(_NS + html + "</root>")
        return True
    except ET.ParseError:
        return False


def first_h1(md: str) -> str:
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def parse_frontmatter(raw: str) -> dict:
    """Minimal YAML frontmatter reader for titling.

    Captures top-level `key: value` pairs and also indented scalar keys
    (so capability fields like `effect` are available as `{effect}`).
    No external deps.
    """
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        top = re.match(r"^([A-Za-z0-9_.-]+):\s*(.*)$", line)
        if top:
            out[top.group(1)] = top.group(2).strip().strip('"').strip("'")
            continue
        nested = re.match(r"^\s+([A-Za-z0-9_.-]+):\s*(.*)$", line)
        if nested:
            key = nested.group(1)
            # Promote nested scalars (e.g. capability.effect) without
            # clobbering an already-set top-level key such as status.
            if key not in out:
                out[key] = nested.group(2).strip().strip('"').strip("'")
    return out


def body_to_html(path: str, strip_h1_title: bool, pandoc: str | None):
    """Read a file -> (h1, frontmatter_dict, storage_html).
    If the file is already HTML, it is posted verbatim."""
    raw = open(path, encoding="utf-8").read()
    if path.lower().endswith((".html", ".xhtml", ".htm")):
        return "", {}, raw
    fm = parse_frontmatter(raw)
    md = strip_frontmatter(raw)
    h1 = first_h1(md)
    if strip_h1_title and h1:
        # drop the first H1 line so it doesn't duplicate the page title
        lines = md.splitlines()
        idx = next(i for i, l in enumerate(lines) if l.startswith("# "))
        md = "\n".join(lines[:idx] + lines[idx + 1 :]).lstrip("\n")
    return h1, fm, to_storage(md, pandoc)


# ------------------------------------------------------------------------------ REST


def api(cfg: Config, method: str, path: str, body=None):
    url = f"{cfg.base}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", cfg.auth_header())
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except urllib.error.URLError as e:
        return 0, str(e)


def find_page(cfg: Config, title: str):
    q = urllib.parse.urlencode({"spaceKey": cfg.space, "title": title, "expand": "version"})
    st, d = api(cfg, "GET", f"/rest/api/content?{q}")
    if st == 200 and isinstance(d, dict) and d.get("results"):
        return d["results"][0]
    return None


def add_labels(cfg: Config, page_id: str, labels: list[str]):
    if not labels:
        return
    body = [{"prefix": "global", "name": l} for l in labels]
    api(cfg, "POST", f"/rest/api/content/{page_id}/label", body)


def publish_page(cfg: Config, title: str, html: str, labels: list[str] | None = None):
    """Create or update a page by exact title. Returns (tag, status, data)."""
    storage = {"storage": {"value": html, "representation": "storage"}}
    existing = find_page(cfg, title)
    if existing:
        pid = existing["id"]
        ver = existing["version"]["number"] + 1
        payload = {
            "id": pid,
            "type": "page",
            "title": title,
            "space": {"key": cfg.space},
            "version": {"number": ver},
        }
        if cfg.parent:
            payload["ancestors"] = [{"id": cfg.parent}]
        payload["body"] = storage
        st, d = api(cfg, "PUT", f"/rest/api/content/{pid}", payload)
        tag = "UPDATED"
    else:
        payload = {"type": "page", "title": title, "space": {"key": cfg.space}, "body": storage}
        if cfg.parent:
            payload["ancestors"] = [{"id": cfg.parent}]
        st, d = api(cfg, "POST", "/rest/api/content", payload)
        tag = "CREATED"
    if st in (200, 201) and isinstance(d, dict):
        add_labels(cfg, d["id"], labels or [])
    return tag, st, d


# ------------------------------------------------------------------------------- CLI


def derive_title(args, path, h1, fm):
    filename = os.path.splitext(os.path.basename(path))[0]
    if args.title_template:  # e.g. "[{effect}|{status}] {id}: {title}"
        fields = dict(fm)
        fields.setdefault("h1", h1)
        fields.setdefault("filename", filename)
        fields.setdefault("title", fm.get("title") or h1 or filename)
        try:
            base = args.title_template.format_map(_Default(fields))
        except Exception as e:
            sys.exit(f"--title-template error on {path}: {e}")
    elif args.title:  # explicit, single-file only
        base = args.title
    elif h1:  # from first # H1
        base = h1
    elif fm.get("title"):  # from frontmatter title:
        base = fm["title"]
    else:  # from filename
        base = re.sub(r"[-_]+", " ", filename).strip()
    return f"{args.title_prefix}{base}{args.title_suffix}"


class _Default(dict):
    """format_map helper: unknown {fields} render as empty, never KeyError."""

    def __missing__(self, k):
        return ""


def expand(patterns):
    files = []
    for p in patterns:
        hits = sorted(glob.glob(os.path.expanduser(p)))
        files.extend(hits or [p])
    return [f for f in files if os.path.isfile(f)]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Publish Markdown/HTML files to Confluence (idempotent by title)."
    )
    ap.add_argument("files", nargs="+", help="Markdown or HTML files / globs to publish.")
    ap.add_argument("--base", help="Confluence base URL incl. /wiki (env CONFLUENCE_BASE).")
    ap.add_argument("--space", help="Space key (env CONFLUENCE_SPACE).")
    ap.add_argument("--parent", help="Parent page id (env CONFLUENCE_PARENT). Optional.")
    ap.add_argument("--email", help="Basic-auth email (env CONFLUENCE_EMAIL).")
    ap.add_argument(
        "--auth",
        choices=["basic", "bearer"],
        help="Auth mode (env CONFLUENCE_AUTH, default basic).",
    )
    ap.add_argument("--title", help="Explicit page title (only valid with a single file).")
    ap.add_argument(
        "--title-template",
        help='Title from frontmatter fields, e.g. "[{effect}|{status}] {id}: {title}". '
        "Also available: {h1}, {filename}, and capability fields. Unknown fields render empty.",
    )
    ap.add_argument("--title-prefix", default="", help='Prepended to every title, e.g. "[Report] ".')
    ap.add_argument("--title-suffix", default="", help="Appended to every title.")
    ap.add_argument("--label", action="append", default=[], help="Label to add (repeatable).")
    ap.add_argument(
        "--keep-h1",
        action="store_true",
        help="Keep the first # H1 in the body (default: drop it, since it becomes the title).",
    )
    ap.add_argument("--pandoc", help="Path to pandoc (env PANDOC).")
    ap.add_argument("--dry-run", action="store_true", help="Preview titles + validation, no network.")
    args = ap.parse_args(argv)

    cfg = Config.from_env(
        base=args.base, space=args.space, parent=args.parent, email=args.email, auth=args.auth
    )
    cfg.validate(need_token=not args.dry_run)

    files = expand(args.files)
    if not files:
        sys.exit("No input files matched.")
    if args.title and len(files) > 1:
        sys.exit("--title is only valid with a single file (it would collide across files).")

    where = f"{cfg.base} space {cfg.space}" + (f" under parent {cfg.parent}" if cfg.parent else "")
    print(f"{'DRY-RUN: ' if args.dry_run else ''}{len(files)} file(s) -> {where}\n")

    created = updated = failed = invalid = 0
    for path in files:
        try:
            h1, fm, html = body_to_html(path, strip_h1_title=not args.keep_h1, pandoc=args.pandoc)
        except Exception as e:
            print(f"  ERROR reading/converting {path}: {e}")
            failed += 1
            continue
        title = derive_title(args, path, h1, fm)
        ok = valid_xhtml(html)
        if not ok:
            invalid += 1
            print(f"  INVALID-XHTML: {title[:80]}  (would 400 — check the source markup)")
            if not args.dry_run:
                failed += 1
                continue
        if args.dry_run:
            print(f"  [dry] {'OK   ' if ok else 'BAD  '}{title[:90]}")
            continue
        tag, st, d = publish_page(cfg, title, html, args.label)
        if st in (200, 201) and isinstance(d, dict):
            link = d.get("_links", {})
            print(f"  {tag}: {title[:80]}  -> {link.get('base', '')}{link.get('webui', '')}")
            created += tag == "CREATED"
            updated += tag == "UPDATED"
        else:
            print(f"  FAILED ({st}): {title[:70]}\n       {d}")
            failed += 1

    print(
        f"\nDone. created={created} updated={updated} "
        f"{'invalid=' + str(invalid) + ' ' if invalid else ''}failed={failed}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
