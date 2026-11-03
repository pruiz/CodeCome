# Confluence export

Publish CodeCome Markdown artifacts (reports, findings, notes) to Confluence
Cloud or Server/Data Center.

The exporter is project-agnostic, idempotent (create-or-update by exact page
title), and uses only the Python standard library plus `pandoc` for Markdown.

## Prerequisites

- Python 3.10+ (CodeCome virtualenv is fine).
- `pandoc` on `PATH` (Markdown only; HTML/XHTML input needs no pandoc).
- Confluence credentials via environment variables (never commit tokens).

## Configure

| Env var | Flag | Meaning |
|---|---|---|
| `CONFLUENCE_BASE` | `--base` | Base URL incl. `/wiki`, e.g. `https://org.atlassian.net/wiki` |
| `CONFLUENCE_SPACE` | `--space` | Space key, e.g. `DOCS` |
| `CONFLUENCE_EMAIL` | `--email` | Basic-auth user (Cloud) |
| `CONFLUENCE_API_TOKEN` | — | API token / PAT |
| `CONFLUENCE_PARENT` | `--parent` | Parent page id (optional) |
| `CONFLUENCE_AUTH` | `--auth` | `basic` (Cloud, default) or `bearer` (Server/DC PAT) |
| `PANDOC` | `--pandoc` | Path to pandoc if not on `PATH` |

```bash
export CONFLUENCE_BASE="https://your-org.atlassian.net/wiki"
export CONFLUENCE_EMAIL="you@org.com"
export CONFLUENCE_API_TOKEN="xxxx"
export CONFLUENCE_SPACE="DOCS"
```

Server / Data Center: set `CONFLUENCE_AUTH=bearer` and put the PAT in
`CONFLUENCE_API_TOKEN`; email is ignored.

## Make targets

Preview the default report page (no network):

```bash
make confluence-export DRY_RUN=1
```

Publish the local report (`itemdb/reports/report.md`):

```bash
make confluence-export
```

Publish confirmed/exploited findings with frontmatter-driven titles:

```bash
make confluence-export-findings
```

Override inputs or pass extra CLI flags:

```bash
make confluence-export FILES='itemdb/reports/*.md' ARGS='--label codecome --title-prefix "[Audit] "'
make confluence-export-findings FILES='itemdb/findings/PENDING/*.md' DRY_RUN=1
```

## Direct CLI

```bash
# one file — title from first "# H1"
./tools/confluence-export.py itemdb/reports/report.md

# findings — title from YAML frontmatter
./tools/confluence-export.py \
  --title-template "[{severity}|{status}] {id}: {title}" \
  itemdb/findings/CONFIRMED/*.md itemdb/findings/EXPLOITED/*.md

# preview only
./tools/confluence-export.py --dry-run itemdb/reports/report.md
```

## Behavior notes

- **Idempotent.** Looks up the page by exact title in the space. Exists →
  version-bumped UPDATE; new → CREATE. Re-running never duplicates.
- **Title is the dedup key.** Changing a title creates a new page. Prefer a
  stable `{id}` in `--title-template` for findings.
- **Leading `# H1` is dropped** from the body by default (it becomes the page
  title). Pass `--keep-h1` to keep it.
- **YAML frontmatter** is stripped from the body automatically.
- **XHTML validated** before posting (`INVALID-XHTML` instead of an opaque HTTP 400).
- Non-zero exit if any file failed — safe for CI gates.

## Library use

```python
import confluence_export as cx

cfg = cx.Config.from_env(space="DOCS", parent="123456")
cfg.validate()
html = cx.to_storage("# Hello\n\nbody")
cx.publish_page(cfg, title="My Page", html=html, labels=["codecome"])
```
