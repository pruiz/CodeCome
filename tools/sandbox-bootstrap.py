#!/usr/bin/env python3
# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
CodeCome sandbox bootstrap CLI.

Manages the curated sandbox examples under templates/sandboxes/ and the
target-specific sandbox at sandbox/.

Subcommands:
  list              List available sandbox examples.
  inspect           Print manifest and previews for one example.
  detect            Scan workspace and propose ranked sandbox candidates.
  apply             Copy an example into sandbox/.
  validate          Run validation tiers.
  regenerate        Re-apply current sandbox example.
  status            Print sandbox provenance and Phase 2 gate result.
  recipe-validate   Validate itemdb/notes/sandbox-recipe.yml.
  recipe-print      Print the sandbox recipe.

Environment variables:
  CODECOME_ALLOW_NO_SANDBOX        Skip Phase 2 sandbox gate.
  CODECOME_BOOTSTRAP_MAX_RETRIES   Default agent retry budget (default 3).
  CODECOME_BOOTSTRAP_DRY_RUN       Force --dry-run on apply/regenerate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

ROOT = Path(__file__).resolve().parents[1]
SANDBOX_NOTES_PATH = NOTES_ROOT = ROOT / "itemdb" / "notes"
SANDBOX_RECIPE_PATH = NOTES_ROOT / "sandbox-recipe.yml"
TEMPLATES_ROOT = ROOT / "templates" / "sandboxes"
SANDBOX_ROOT = ROOT / "sandbox"
SRC_ROOT = ROOT / "src"
PROVENANCE_FILE = SANDBOX_ROOT / "CODECOME-GENERATED.md"

DEFAULT_MAX_RETRIES = 3

NOT_IMPLEMENTED_EXIT = 64


# --- Manifest model -----------------------------------------------------------


@dataclass
class ExampleManifest:
    """Loaded view of a templates/sandboxes/<id>/manifest.yml file."""

    id: str
    display_name: str
    path: Path
    applies_when: Dict[str, List[str]] = field(default_factory=dict)
    required_tools: List[str] = field(default_factory=list)
    default_ports: List[Any] = field(default_factory=list)
    build_command: str = ""
    test_command: str = ""
    notes_md: str = "notes.md"
    caveats: List[str] = field(default_factory=list)
    template_vars: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, manifest_path: Path) -> "ExampleManifest":
        if yaml is None:
            raise RuntimeError(
                "PyYAML is not installed. Run: pip install -r requirements.txt"
            )

        with manifest_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        if not isinstance(data, dict):
            raise ValueError(f"Manifest is not a YAML object: {manifest_path}")

        example_dir = manifest_path.parent
        example_id = str(data.get("id", example_dir.name))

        applies = data.get("applies_when") or {}
        if not isinstance(applies, dict):
            applies = {}

        return cls(
            id=example_id,
            display_name=str(data.get("display_name", example_id)),
            path=example_dir,
            applies_when={k: list(v or []) for k, v in applies.items() if isinstance(v, list)},
            required_tools=list(data.get("required_tools") or []),
            default_ports=list(data.get("default_ports") or []),
            build_command=str(data.get("build_command", "")),
            test_command=str(data.get("test_command", "")),
            notes_md=str(data.get("notes_md", "notes.md")),
            caveats=list(data.get("caveats") or []),
            template_vars=list(data.get("template_vars") or []),
            raw=data,
        )

    def relative_path(self) -> str:
        return str(self.path.relative_to(ROOT))


def discover_examples() -> List[ExampleManifest]:
    """Return all example manifests under templates/sandboxes/, sorted by id."""
    if not TEMPLATES_ROOT.exists():
        return []

    examples: List[ExampleManifest] = []
    for child in sorted(TEMPLATES_ROOT.iterdir()):
        if not child.is_dir():
            continue
        manifest = child / "manifest.yml"
        if not manifest.exists():
            continue
        try:
            examples.append(ExampleManifest.load(manifest))
        except Exception as exc:  # noqa: BLE001
            print(
                C.warn(f"Skipping {child.name}: failed to load manifest ({exc})"),
                file=sys.stderr,
            )
    return examples


# --- Detection helpers --------------------------------------------------------


_LANGUAGE_HINTS_BY_FILE: Dict[str, str] = {
    "Makefile": "c-cpp",
    "CMakeLists.txt": "c-cpp",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "rebar.config": "erlang-otp",
    "rebar.lock": "erlang-otp",
    "erlang.mk": "erlang-otp",
    "mix.exs": "erlang-otp",
    ".elp.toml": "erlang-otp",
    "package.json": "node",
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "setup.py": "python",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
    "composer.json": "php",
    "Gemfile": "ruby",
    "Dockerfile": "container",
}

_LANGUAGE_HINTS_BY_SUFFIX: Dict[str, str] = {
    ".c": "c-cpp",
    ".h": "c-cpp",
    ".cpp": "c-cpp",
    ".cc": "c-cpp",
    ".cxx": "c-cpp",
    ".hpp": "c-cpp",
    ".cs": "dotnet",
    ".csproj": "dotnet",
    ".fsproj": "dotnet",
    ".vbproj": "dotnet",
    ".erl": "erlang-otp",
    ".hrl": "erlang-otp",
    ".py": "python",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".js": "node",
    ".ts": "node",
    ".jsx": "node",
    ".tsx": "node",
    ".php": "php",
    ".rb": "ruby",
    ".tf": "terraform",
    ".html": "web-static",
    ".htm": "web-static",
}

_MANIFEST_CACHE: Optional[set[str]] = None


def declared_manifests() -> set[str]:
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is not None:
        return _MANIFEST_CACHE

    names = set(_LANGUAGE_HINTS_BY_FILE)
    for example in discover_examples():
        for name in example.applies_when.get("manifests", []):
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
    _MANIFEST_CACHE = names
    return _MANIFEST_CACHE


def _scan_recon_notes() -> Dict[str, Any]:
    """Best-effort extraction of language and manifest hints from recon notes.

    Returns a dict with keys 'languages' and 'manifests'. Empty if no notes.
    """
    if not NOTES_ROOT.exists():
        return {}

    interesting = {
        "target-profile.md",
        "build-model.md",
        "execution-model.md",
        "interesting-files.md",
    }

    text_blob_parts: List[str] = []
    for name in interesting:
        path = NOTES_ROOT / name
        if path.exists():
            try:
                text_blob_parts.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue

    if not text_blob_parts:
        return {}

    text_blob = "\n".join(text_blob_parts).lower()

    languages: List[str] = []
    for hint in {
        "c", "c++", "cpp", "rust", "go", "python", "node", "javascript",
        "typescript", "java", "kotlin", "scala", "php", "ruby", ".net",
        "dotnet", "c#", "csharp", "erlang", "elixir", "otp", "rebar3",
        "common test", "dialyzer", "xref", "eqwalizer", "elp",
        "terraform", "hcl", "shell", "bash",
    }:
        if re.search(rf"\b{re.escape(hint)}\b", text_blob):
            if hint in {"erlang", "elixir", "otp", "rebar3", "common test", "dialyzer", "xref", "eqwalizer", "elp"}:
                languages.append("erlang-otp")
            else:
                languages.append(hint)

    manifests: List[str] = []
    for name in declared_manifests():
        if name.lower() in text_blob:
            manifests.append(name)

    return {
        "languages": sorted(set(languages)),
        "manifests": sorted(set(manifests)),
    }


def _scan_src_top_levels(max_depth: int = 2) -> Dict[str, Any]:
    """Walk src/ up to max_depth levels and collect manifest/extension hints."""
    if not SRC_ROOT.exists():
        return {"languages": [], "manifests": []}

    seen_manifests: List[str] = []
    seen_languages: List[str] = []

    for root, dirs, files in os.walk(SRC_ROOT):
        rel = Path(root).relative_to(SRC_ROOT)
        depth = 0 if str(rel) == "." else len(rel.parts)
        if depth > max_depth:
            dirs[:] = []
            continue

        # Skip noisy directories.
        dirs[:] = [
            d for d in dirs
            if d not in {".git", ".svn", ".hg", "node_modules", "vendor",
                         "build", "dist", "target", "bin", "obj", "__pycache__"}
        ]

        for filename in files:
            if filename in _LANGUAGE_HINTS_BY_FILE:
                seen_manifests.append(filename)
                seen_languages.append(_LANGUAGE_HINTS_BY_FILE[filename])
            if filename.endswith(".app.src"):
                seen_manifests.append("*.app.src")
                seen_languages.append("erlang-otp")
            suffix = Path(filename).suffix.lower()
            if suffix in _LANGUAGE_HINTS_BY_SUFFIX:
                seen_languages.append(_LANGUAGE_HINTS_BY_SUFFIX[suffix])

    return {
        "languages": sorted(set(seen_languages)),
        "manifests": sorted(set(seen_manifests)),
    }


def detect_signals(force_src_walk: bool = False) -> Dict[str, Any]:
    """Compute detection signals.

    By default, prefer recon notes. Fall back to a top-2-levels src/ walk.
    """
    if not force_src_walk:
        from_notes = _scan_recon_notes()
        if from_notes.get("languages") or from_notes.get("manifests"):
            from_notes["source"] = "notes"
            return from_notes

    walked = _scan_src_top_levels(max_depth=2)
    walked["source"] = "src-walk"
    return walked


def _example_score(manifest: ExampleManifest, signals: Dict[str, Any]) -> int:
    """Trivial ranking score: count overlap with applies_when buckets."""
    score = 0
    languages = set(signals.get("languages") or [])
    manifests = set(signals.get("manifests") or [])

    for lang in manifest.applies_when.get("languages", []):
        if lang.lower() in {l.lower() for l in languages}:
            score += 2

    for needed in manifest.applies_when.get("manifests", []):
        if needed in manifests:
            score += 3

    return score


def rank_examples(
    examples: Iterable[ExampleManifest],
    signals: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Return ranked candidates as plain dicts."""
    ranked: List[Dict[str, Any]] = []
    for manifest in examples:
        ranked.append(
            {
                "id": manifest.id,
                "display_name": manifest.display_name,
                "score": _example_score(manifest, signals),
                "applies_when": manifest.applies_when,
                "path": manifest.relative_path(),
            }
        )
    ranked.sort(key=lambda row: (-row["score"], row["id"]))
    return ranked


# --- Provenance ---------------------------------------------------------------


def read_provenance() -> Optional[Dict[str, Any]]:
    """Parse the trivial key:value frontmatter of CODECOME-GENERATED.md."""
    if not PROVENANCE_FILE.exists():
        return None

    text = PROVENANCE_FILE.read_text(encoding="utf-8", errors="replace")
    info: Dict[str, Any] = {"raw": text}

    # We accept either YAML frontmatter (--- ... ---) or a simple
    # "Key: value" block at the top of the file.
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if fm_match and yaml is not None:
        try:
            data = yaml.safe_load(fm_match.group(1))
            if isinstance(data, dict):
                info.update(data)
        except Exception:  # noqa: BLE001
            pass
        return info

    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z][A-Za-z0-9_ -]*?):\s*(.+)$", line.strip())
        if m:
            info[m.group(1).strip().lower().replace(" ", "_")] = m.group(2).strip()

    return info


def sandbox_has_user_content() -> bool:
    """Return True if sandbox/ has tracked content other than .gitkeep."""
    if not SANDBOX_ROOT.exists():
        return False
    for child in SANDBOX_ROOT.iterdir():
        if child.name in {".gitkeep", "CODECOME-GENERATED.md"}:
            continue
        if child.name.startswith(".backup-"):
            continue
        return True
    return False


def phase_1c_bootstrap_recorded() -> bool:
    """Return True once Phase 1c has documented a sandbox bootstrap attempt."""
    return (NOTES_ROOT / "sandbox-plan.md").is_file()


def classify_sandbox_state() -> str:
    """Classify sandbox state using both filesystem and workflow progress."""
    provenance = read_provenance()
    if provenance is not None:
        return "generated"
    if sandbox_has_user_content():
        return "user-managed"
    if phase_1c_bootstrap_recorded():
        return "missing"
    return "pending"


# --- Output helpers -----------------------------------------------------------


def _emit(payload: Any, fmt: str) -> None:
    if fmt == "json":
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        # text mode caller is expected to print directly; this is reserved
        # for callers passing structured data.
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        sys.stdout.write("\n")


def _print_text_examples(examples: List[ExampleManifest]) -> None:
    if not examples:
        print(C.warn("No sandbox examples found under templates/sandboxes/."))
        return

    print(C.header("Available sandbox examples:"))
    print()
    for ex in examples:
        langs = ", ".join(ex.applies_when.get("languages", [])) or "-"
        manifests = ", ".join(ex.applies_when.get("manifests", [])) or "-"
        print(f"  {C.BOLD}{ex.id:<24}{C.RESET} {ex.display_name}")
        print(f"    {C.DIM}languages:{C.RESET} {langs}")
        print(f"    {C.DIM}manifests:{C.RESET} {manifests}")
        print(f"    {C.DIM}path:{C.RESET}      {ex.relative_path()}")
        print()


# --- Subcommands --------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    examples = discover_examples()
    if args.format == "json":
        _emit(
            [
                {
                    "id": ex.id,
                    "display_name": ex.display_name,
                    "path": ex.relative_path(),
                    "applies_when": ex.applies_when,
                    "required_tools": ex.required_tools,
                    "template_vars": ex.template_vars,
                }
                for ex in examples
            ],
            "json",
        )
    else:
        _print_text_examples(examples)
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    examples = {ex.id: ex for ex in discover_examples()}
    manifest = examples.get(args.id)
    if manifest is None:
        print(C.fail(f"Unknown example: {args.id}"), file=sys.stderr)
        print(C.info("Run: tools/sandbox-bootstrap.py list"), file=sys.stderr)
        return 1

    if args.format == "json":
        _emit(
            {
                "id": manifest.id,
                "display_name": manifest.display_name,
                "path": manifest.relative_path(),
                "applies_when": manifest.applies_when,
                "required_tools": manifest.required_tools,
                "default_ports": manifest.default_ports,
                "build_command": manifest.build_command,
                "test_command": manifest.test_command,
                "caveats": manifest.caveats,
                "template_vars": manifest.template_vars,
                "files": [
                    str(p.relative_to(manifest.path))
                    for p in sorted(manifest.path.rglob("*"))
                    if p.is_file()
                ],
            },
            "json",
        )
        return 0

    print(C.header(f"{manifest.id} - {manifest.display_name}"))
    print(f"  {C.DIM}path:{C.RESET} {manifest.relative_path()}")
    if manifest.applies_when:
        print(f"  {C.DIM}applies_when:{C.RESET}")
        for k, v in manifest.applies_when.items():
            print(f"    {k}: {', '.join(v) or '-'}")
    if manifest.required_tools:
        print(f"  {C.DIM}required_tools:{C.RESET} {', '.join(manifest.required_tools)}")
    if manifest.default_ports:
        ports = ", ".join(str(p) for p in manifest.default_ports)
        print(f"  {C.DIM}default_ports:{C.RESET} {ports}")
    if manifest.template_vars:
        print(f"  {C.DIM}template_vars:{C.RESET} {', '.join(manifest.template_vars)}")
    if manifest.build_command:
        print(f"  {C.DIM}build_command:{C.RESET} {manifest.build_command}")
    if manifest.test_command:
        print(f"  {C.DIM}test_command:{C.RESET} {manifest.test_command}")
    if manifest.caveats:
        print(f"  {C.DIM}caveats:{C.RESET}")
        for caveat in manifest.caveats:
            print(f"    {C.SYM_BULLET} {caveat}")

    print()
    print(C.header("Files in this example:"))
    for p in sorted(manifest.path.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(manifest.path)}")

    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    signals = detect_signals(force_src_walk=args.force_src_walk)
    examples = discover_examples()
    ranked = rank_examples(examples, signals)

    payload = {
        "signals": signals,
        "candidates": ranked,
    }

    if args.format == "json":
        _emit(payload, "json")
        return 0

    print(C.header("Detection signals"))
    print(f"  {C.DIM}source:{C.RESET}    {signals.get('source', 'unknown')}")
    print(f"  {C.DIM}languages:{C.RESET} {', '.join(signals.get('languages') or []) or '-'}")
    print(f"  {C.DIM}manifests:{C.RESET} {', '.join(signals.get('manifests') or []) or '-'}")
    print()
    print(C.header("Ranked candidates"))
    if not ranked:
        print(C.warn("No candidates available. Add examples under templates/sandboxes/."))
        return 0

    for row in ranked:
        marker = C.GREEN if row["score"] > 0 else C.DIM
        print(
            f"  {marker}score={row['score']:>2}{C.RESET}  "
            f"{C.BOLD}{row['id']:<24}{C.RESET} {row['display_name']}"
        )

    return 0


_VALIDATION_RUN_HEADER_RE = re.compile(r"^## Validation run ", re.MULTILINE)
_VALIDATION_TABLE_ROW_RE = re.compile(
    r"^\|\s*(T\d)\s*\|\s*[^|]+\|\s*(passed|failed|skipped)\s*\|",
    re.MULTILINE | re.IGNORECASE,
)


def _last_validation_outcome() -> Optional[str]:
    """Inspect CODECOME-GENERATED.md for the most recent validation outcome.

    Returns 'passed', 'failed', 'mixed', 'skipped', or None if no run found.
    """
    if not PROVENANCE_FILE.exists():
        return None

    text = PROVENANCE_FILE.read_text(encoding="utf-8", errors="replace")
    headers = list(_VALIDATION_RUN_HEADER_RE.finditer(text))
    if not headers:
        return None

    last_block_start = headers[-1].start()
    block = text[last_block_start:]

    outcomes = [m.group(2).lower() for m in _VALIDATION_TABLE_ROW_RE.finditer(block)]
    if not outcomes:
        return None

    if any(o == "failed" for o in outcomes):
        return "failed"
    if all(o == "skipped" for o in outcomes):
        return "skipped"
    if any(o == "passed" for o in outcomes):
        return "mixed" if any(o == "skipped" for o in outcomes) else "passed"
    return None


def cmd_status(args: argparse.Namespace) -> int:
    provenance = read_provenance()
    allow_no_sandbox = bool(os.environ.get("CODECOME_ALLOW_NO_SANDBOX"))
    capability_status = _capability_status()
    sandbox_state = classify_sandbox_state()

    last_validation = _last_validation_outcome()

    # Gate logic:
    # - pending             -> block (override wins), but Phase 1c has not run yet
    # - missing             -> block (override wins), because Phase 1c should have created it
    # - generated + failed  -> block (override wins)
    # - generated + passed  -> pass
    # - generated + mixed   -> pass with warning (some tiers skipped)
    # - generated + None    -> pass with warning (no validation run yet)
    # - generated + skipped -> block (no real validation evidence)
    # - user-managed        -> pass with warning (user owns it)
    if allow_no_sandbox:
        gate_pass = True
        gate_reason = "override (CODECOME_ALLOW_NO_SANDBOX=1)"
    elif sandbox_state == "pending":
        gate_pass = False
        gate_reason = "sandbox bootstrap pending; run make phase-1"
    elif sandbox_state == "missing":
        gate_pass = False
        gate_reason = "sandbox is missing"
    elif sandbox_state == "generated" and last_validation == "failed":
        gate_pass = False
        gate_reason = "last validation failed"
    elif sandbox_state == "generated" and last_validation == "skipped":
        gate_pass = False
        gate_reason = "last validation has no real outcomes (all tiers skipped)"
    else:
        gate_pass = True
        if sandbox_state == "user-managed":
            gate_reason = "sandbox is user-managed (validation not enforced)"
        elif last_validation is None:
            gate_reason = "no validation run on record"
        elif last_validation == "passed":
            gate_reason = "last validation passed"
        elif last_validation == "mixed":
            gate_reason = "last validation passed (some tiers skipped)"
        else:
            gate_reason = f"last validation: {last_validation}"

    payload: Dict[str, Any] = {
        "sandbox_state": sandbox_state,
        "sandbox_path": str(SANDBOX_ROOT.relative_to(ROOT)),
        "provenance_present": provenance is not None,
        "allow_no_sandbox": allow_no_sandbox,
        "last_validation": last_validation,
        "phase2_gate_pass": gate_pass,
        "phase2_gate_reason": gate_reason,
        "capabilities": capability_status,
    }
    if provenance:
        # Strip raw text from JSON output to keep it small.
        payload["provenance"] = {k: v for k, v in provenance.items() if k != "raw"}

    if args.format == "json":
        _emit(payload, "json")
    else:
        print(C.header("Sandbox status"))
        print(f"  {C.DIM}path:{C.RESET}             {payload['sandbox_path']}")
        print(f"  {C.DIM}state:{C.RESET}            {sandbox_state}")
        print(f"  {C.DIM}provenance:{C.RESET}       {'yes' if provenance else 'no'}")
        print(f"  {C.DIM}last validation:{C.RESET}  {last_validation or '-'}")
        print(f"  {C.DIM}allow override:{C.RESET}   {'yes' if allow_no_sandbox else 'no'}")
        print(f"  {C.DIM}capabilities:{C.RESET}")
        for name in ("setup", "start", "check", "build", "test", "stop", "shell", "logs", "clean", "reset"):
            status = capability_status[name]
            state = "ok" if status.get("satisfied") else "pending" if sandbox_state == "pending" else "missing"
            print(f"    {name:<6} {state:<7} {status['path']}")
        if gate_pass:
            print(C.ok(f"Phase 2 sandbox gate would pass ({gate_reason})."))
        else:
            print(C.warn(f"Phase 2 sandbox gate would block: {gate_reason}."))
            print(C.info("Override with CODECOME_ALLOW_NO_SANDBOX=1"))

    if args.gate and not gate_pass:
        return 1
    return 0


# --- Apply / regenerate -------------------------------------------------------

_MARKER_RE = re.compile(r"__([A-Z][A-Z0-9_]+)__")


def parse_var_args(var_args: List[str]) -> Dict[str, str]:
    """Parse repeated --var KEY=VAL into a dict."""
    parsed: Dict[str, str] = {}
    for raw in var_args or []:
        if "=" not in raw:
            raise ValueError(f"Invalid --var {raw!r} (expected KEY=VAL).")
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"Invalid --var {raw!r} (empty key).")
        parsed[key] = value
    return parsed


def find_used_markers(content: str) -> List[str]:
    """Return the set of __VARNAME__ markers used in content."""
    return sorted(set(_MARKER_RE.findall(content)))


def substitute_markers(content: str, values: Dict[str, str]) -> str:
    """Replace __VARNAME__ tokens using values. Unknown markers stay intact."""
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in values:
            return values[key]
        return match.group(0)

    return _MARKER_RE.sub(replace, content)


def is_text_file(path: Path) -> bool:
    """Best-effort detection of text vs binary files."""
    try:
        with path.open("rb") as fh:
            chunk = fh.read(8192)
    except OSError:
        return False
    if b"\x00" in chunk:
        return False
    try:
        chunk.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def list_example_files(manifest: ExampleManifest) -> List[Path]:
    """All files inside the example, excluding manifest.yml itself."""
    files: List[Path] = []
    for child in sorted(manifest.path.rglob("*")):
        if not child.is_file():
            continue
        rel = child.relative_to(manifest.path)
        if str(rel) == "manifest.yml":
            continue
        files.append(child)
    return files


def sandbox_user_managed_paths() -> List[Path]:
    """Files under sandbox/ that look user-managed (not bookkeeping)."""
    if not SANDBOX_ROOT.exists():
        return []
    out: List[Path] = []
    for child in sorted(SANDBOX_ROOT.rglob("*")):
        if not child.is_file():
            continue
        name = child.name
        rel = child.relative_to(SANDBOX_ROOT)
        rel_str = str(rel)
        if name in {".gitkeep", "CODECOME-GENERATED.md"}:
            continue
        if rel_str.startswith(".backup-"):
            continue
        out.append(child)
    return out


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def render_provenance(
    example: ExampleManifest,
    markers: Dict[str, str],
    file_hashes: Dict[str, str],
    compose_project_name: str,
) -> str:
    """Build CODECOME-GENERATED.md content."""
    lines: List[str] = ["---"]
    lines.append(f'generated_at: "{_iso_now()}"')
    lines.append(f'source_example: "{example.id}"')
    lines.append(f'source_example_path: "{example.relative_path()}"')
    if markers:
        lines.append("markers:")
        for key in sorted(markers):
            value = str(markers[key]).replace('"', '\\"')
            lines.append(f'  {key}: "{value}"')
    else:
        lines.append("markers: {}")
    if file_hashes:
        lines.append("baseline_files:")
        for rel_path in sorted(file_hashes):
            lines.append(f'  "{rel_path}": "{file_hashes[rel_path]}"')
    else:
        lines.append("baseline_files: {}")
    lines.append("validation: []")
    lines.append("---")
    lines.append("")
    lines.append("# CodeCome sandbox provenance")
    lines.append("")
    lines.append(
        "This file is generated by `tools/sandbox-bootstrap.py`. Its presence "
        "marks `sandbox/` as bootstrap-managed."
    )
    lines.append("")
    lines.append("## Manifest summary")
    lines.append("")
    lines.append(f"- id: `{example.id}`")
    lines.append(f"- display_name: {example.display_name}")
    lines.append(f"- source path: `{example.relative_path()}`")
    if example.template_vars:
        lines.append(
            f"- declared template_vars: {', '.join(example.template_vars)}"
        )
    if example.caveats:
        lines.append("- caveats:")
        for caveat in example.caveats:
            lines.append(f"  - {caveat}")
    lines.append("")
    lines.append("## Provided marker values")
    lines.append("")
    if markers:
        lines.append("| Marker | Value |")
        lines.append("|---|---|")
        for key in sorted(markers):
            lines.append(f"| `{key}` | `{markers[key]}` |")
    else:
        lines.append("(none)")
    lines.append("")
    lines.append("## Runtime metadata")
    lines.append("")
    lines.append("| Key | Value |")
    lines.append("|---|---|")
    lines.append(f"| `COMPOSE_PROJECT_NAME` | `{compose_project_name}` |")
    lines.append("")
    lines.append("## Manual edits since generation")
    lines.append("")
    lines.append(
        "Compare hashes in `baseline_files` against the current files to "
        "detect manual edits. Re-running `apply` or `regenerate` will refresh "
        "this provenance after backing up the previous content."
    )
    lines.append("")
    lines.append("## Validation history")
    lines.append("")
    lines.append("Filled in by `tools/sandbox-bootstrap.py validate` (pending).")
    lines.append("")
    return "\n".join(lines)


def _ensure_example_known(example_id: str) -> ExampleManifest:
    examples = {ex.id: ex for ex in discover_examples()}
    manifest = examples.get(example_id)
    if manifest is None:
        raise SystemExit(
            f"Unknown example: {example_id}. "
            f"Available: {', '.join(sorted(examples)) or '(none)'}"
        )
    return manifest


def _confirm_unknown_markers(
    files: List[Path],
    declared: List[str],
    provided: Dict[str, str],
) -> tuple[List[str], List[str]]:
    """Inspect example text files for markers and return (unfilled, undeclared).

    unfilled: declared markers used in files but not provided in `provided`.
    undeclared: markers found in files but not present in declared list.
    """
    used: set[str] = set()
    for path in files:
        if not is_text_file(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        used.update(find_used_markers(text))

    declared_set = set(declared or [])
    provided_set = set(provided.keys())

    unfilled = sorted((declared_set & used) - provided_set)
    undeclared = sorted(used - declared_set)
    return unfilled, undeclared


def _copy_with_markers(
    src_root: Path,
    src_files: List[Path],
    dst_root: Path,
    markers: Dict[str, str],
    dry_run: bool,
) -> List[tuple[str, str]]:
    """Copy each file from src_root to dst_root, substituting markers in text files.

    Returns a list of (relative_path, sha256) tuples for the written files.
    For dry-run, sha256 is computed against the substituted content but
    nothing is written to disk.
    """
    written: List[tuple[str, str]] = []
    for src_path in src_files:
        rel = src_path.relative_to(src_root)
        dst_path = dst_root / rel

        if is_text_file(src_path):
            text = src_path.read_text(encoding="utf-8")
            new_text = substitute_markers(text, markers)
            data = new_text.encode("utf-8")
            digest = hashlib.sha256(data).hexdigest()
            if not dry_run:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                dst_path.write_bytes(data)
                # Preserve executable bit.
                if os.access(src_path, os.X_OK):
                    dst_path.chmod(dst_path.stat().st_mode | 0o111)
        else:
            data = src_path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if not dry_run:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                dst_path.write_bytes(data)
                if os.access(src_path, os.X_OK):
                    dst_path.chmod(dst_path.stat().st_mode | 0o111)

        written.append((str(rel), digest))
    return written


def _docker_compose_project_name() -> str:
    """Read the project name from codecome.yml and sanitize it for docker compose."""
    try:
        from codecome import load_config
        config = load_config()
        raw_name = str(config.get("project", {}).get("name", "codecome-sandbox"))
    except Exception:
        raw_name = "codecome-sandbox"

    # Docker Compose allows lowercase alphanumeric, hyphens, and underscores.
    # Must start with a letter or number.
    sanitized = re.sub(r'[^a-z0-9_-]', '-', raw_name.lower())
    sanitized = re.sub(r'-+', '-', sanitized)
    sanitized = sanitized.strip('-')

    if not sanitized or not sanitized[0].isalnum():
        sanitized = "cc-" + sanitized.lstrip('-_')

    if not sanitized:
        sanitized = "codecome-sandbox"

    return sanitized


def cmd_apply(args: argparse.Namespace) -> int:
    dry_run = bool(args.dry_run) or bool(os.environ.get("CODECOME_BOOTSTRAP_DRY_RUN"))

    try:
        manifest = _ensure_example_known(args.id)
    except SystemExit as exc:
        print(C.fail(str(exc)), file=sys.stderr)
        return 1

    try:
        markers = parse_var_args(args.var)
    except ValueError as exc:
        print(C.fail(str(exc)), file=sys.stderr)
        return 2

    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    provenance_present = PROVENANCE_FILE.exists()
    user_files = sandbox_user_managed_paths()

    # Idempotency rule: never silently overwrite a user-managed sandbox.
    if user_files and not provenance_present and not args.force:
        print(C.fail("sandbox/ has user-managed content without CODECOME-GENERATED.md."), file=sys.stderr)
        print(C.info("Re-run with --force to back up and overwrite."), file=sys.stderr)
        for path in user_files[:10]:
            print(f"  {C.SYM_BULLET} {path.relative_to(ROOT)}", file=sys.stderr)
        if len(user_files) > 10:
            print(f"  {C.SYM_BULLET} ... and {len(user_files) - 10} more", file=sys.stderr)
        return 3

    files = list_example_files(manifest)
    unfilled, undeclared = _confirm_unknown_markers(
        files, manifest.template_vars, markers
    )

    will_backup = bool(user_files) or provenance_present
    backup_target = SANDBOX_ROOT / f".backup-{_timestamp()}" if will_backup else None

    # Plan summary.
    # We always inject a .env file to isolate docker compose projects.
    compose_project_name = _docker_compose_project_name()
    env_content = f"COMPOSE_PROJECT_NAME={compose_project_name}\n"
    if args.format == "json":
        plan_payload = {
            "dry_run": dry_run,
            "example": manifest.id,
            "example_path": manifest.relative_path(),
            "sandbox_path": str(SANDBOX_ROOT.relative_to(ROOT)),
            "force": bool(args.force),
            "files_to_write": [str(p.relative_to(manifest.path)) for p in files] + [".env"],
            "markers_provided": markers,
            "markers_used_unfilled": unfilled,
            "markers_used_undeclared": undeclared,
            "backup_dir": str(backup_target.relative_to(ROOT)) if backup_target else None,
            "provenance_present_before": provenance_present,
        }
    else:
        plan_payload = None
        print(C.header(f"Apply plan for example '{manifest.id}'"))
        print(f"  {C.DIM}target:{C.RESET}            {SANDBOX_ROOT.relative_to(ROOT)}")
        print(f"  {C.DIM}example path:{C.RESET}      {manifest.relative_path()}")
        print(f"  {C.DIM}dry-run:{C.RESET}           {'yes' if dry_run else 'no'}")
        print(f"  {C.DIM}force:{C.RESET}             {'yes' if args.force else 'no'}")
        print(f"  {C.DIM}prov. present:{C.RESET}    {'yes' if provenance_present else 'no'}")
        if backup_target:
            print(f"  {C.DIM}backup target:{C.RESET}    {backup_target.relative_to(ROOT)}")
        print(f"  {C.DIM}files to write:{C.RESET}   {len(files) + 1}")
        if markers:
            print(f"  {C.DIM}marker values:{C.RESET}")
            for k in sorted(markers):
                print(f"    {k} = {markers[k]}")
        if unfilled:
            print(C.warn(f"Declared markers used but not provided: {', '.join(unfilled)}"))
            print(C.info("They will remain as __MARKER__ tokens in the generated files."))
        if undeclared:
            print(C.warn(f"Markers used in example but not declared in manifest: {', '.join(undeclared)}"))

    if dry_run:
        if args.format == "json":
            assert plan_payload is not None
            plan_payload["status"] = "dry-run"
            _emit(plan_payload, "json")
        else:
            print()
            print(C.info("Dry-run only; no files written."))
        return 0

    # Backup user-managed and previous provenance content.
    if backup_target is not None:
        if args.format != "json":
            print(C.info(f"Backing up existing sandbox content to {backup_target.relative_to(ROOT)}"))
        backup_target.mkdir(parents=True, exist_ok=False)
        for path in user_files:
            rel = path.relative_to(SANDBOX_ROOT)
            dst = backup_target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(dst))
        if provenance_present:
            shutil.move(str(PROVENANCE_FILE), str(backup_target / "CODECOME-GENERATED.md"))
        # Drop empty leftover dirs (excluding .backup-*).
        for child in sorted(SANDBOX_ROOT.glob("*"), key=lambda p: -len(p.parts)):
            if child.is_dir() and not any(child.iterdir()) and not child.name.startswith(".backup-"):
                child.rmdir()

    written = _copy_with_markers(manifest.path, files, SANDBOX_ROOT, markers, dry_run=False)
    
    # Inject isolated compose project name.
    env_file = SANDBOX_ROOT / ".env"
    env_file.write_text(env_content, encoding="utf-8")
    written.append((".env", file_sha256(env_file)))
    
    file_hashes = {rel: digest for rel, digest in written}

    provenance_text = render_provenance(
        manifest,
        markers,
        file_hashes,
        compose_project_name,
    )
    PROVENANCE_FILE.write_text(provenance_text, encoding="utf-8")

    if args.format == "json":
        assert plan_payload is not None
        plan_payload["status"] = "applied"
        plan_payload["written_files"] = [rel for rel, _ in written]
        plan_payload["provenance_path"] = str(PROVENANCE_FILE.relative_to(ROOT))
        _emit(plan_payload, "json")
    else:
        print()
        print(C.ok(f"Applied example '{manifest.id}' to {SANDBOX_ROOT.relative_to(ROOT)}"))
        print(C.info(f"Wrote provenance: {PROVENANCE_FILE.relative_to(ROOT)}"))
        if unfilled:
            print(C.warn(
                "Some declared markers were not provided. Edit the generated "
                "files or re-run with the missing --var values."
            ))
    return 0


def cmd_regenerate(args: argparse.Namespace) -> int:
    dry_run = bool(args.dry_run) or bool(os.environ.get("CODECOME_BOOTSTRAP_DRY_RUN"))

    provenance = read_provenance()
    if provenance is None:
        print(
            C.fail(
                "No sandbox/CODECOME-GENERATED.md found. "
                "Use 'apply <id>' to bootstrap a fresh sandbox first."
            ),
            file=sys.stderr,
        )
        return 1

    example_id = str(provenance.get("source_example", "")).strip()
    if not example_id:
        print(C.fail("Provenance file does not record source_example."), file=sys.stderr)
        return 1

    # Reuse markers from provenance unless the caller overrides via --var.
    base_markers: Dict[str, str] = {}
    if isinstance(provenance.get("markers"), dict):
        for k, v in provenance["markers"].items():
            base_markers[str(k)] = str(v)

    try:
        cli_markers = parse_var_args(args.var)
    except ValueError as exc:
        print(C.fail(str(exc)), file=sys.stderr)
        return 2

    # CLI overrides win.
    merged_markers = {**base_markers, **cli_markers}

    # Build a synthetic args namespace and call cmd_apply.
    apply_args = argparse.Namespace(
        id=example_id,
        var=[f"{k}={v}" for k, v in merged_markers.items()],
        dry_run=dry_run,
        force=True,  # regenerate implies overwrite
        max_retries=getattr(args, "max_retries", DEFAULT_MAX_RETRIES),
        format=args.format,
    )

    if args.format != "json":
        print(C.header(f"Regenerating sandbox from example '{example_id}'"))
        if cli_markers:
            print(C.info(f"Marker overrides: {', '.join(sorted(cli_markers))}"))

    return cmd_apply(apply_args)


# --- Validate ----------------------------------------------------------------


@dataclass
class TierResult:
    tier: str
    purpose: str
    command: str
    started_at: str
    duration_seconds: float
    exit_code: Optional[int]
    outcome: str  # passed | failed | skipped
    stderr_tail: str
    stdout_tail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier,
            "purpose": self.purpose,
            "command": self.command,
            "started_at": self.started_at,
            "duration_seconds": round(self.duration_seconds, 3),
            "exit_code": self.exit_code,
            "outcome": self.outcome,
            "stderr_tail": self.stderr_tail,
            "stdout_tail": self.stdout_tail,
        }


_VALIDATE_STDERR_TAIL_LINES = int(os.environ.get("CODECOME_VALIDATE_TAIL_LINES", "50"))


def _tail_lines(text: str, max_lines: int = _VALIDATE_STDERR_TAIL_LINES) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text.rstrip()
    return "\n".join(lines[-max_lines:])


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _docker_compose_available() -> bool:
    if not _docker_available():
        return False
    # `docker compose version` returns 0 when the plugin is available.
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _run_command(command: List[str], cwd: Path) -> TierResult:
    """Run a command, capture stdout/stderr, return a TierResult-shaped dict."""
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        duration = time.monotonic() - t0
        return TierResult(
            tier="",
            purpose="",
            command=" ".join(shlex.quote(c) for c in command),
            started_at=started,
            duration_seconds=duration,
            exit_code=result.returncode,
            outcome="passed" if result.returncode == 0 else "failed",
            stderr_tail=_tail_lines(result.stderr or ""),
            stdout_tail=_tail_lines(result.stdout or ""),
        )
    except FileNotFoundError as exc:
        duration = time.monotonic() - t0
        return TierResult(
            tier="",
            purpose="",
            command=" ".join(shlex.quote(c) for c in command),
            started_at=started,
            duration_seconds=duration,
            exit_code=None,
            outcome="failed",
            stderr_tail=str(exc),
            stdout_tail="",
        )


def _has_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _resolve_tier1_command(scripts_only: bool, docker_only: bool) -> tuple[str, List[str], str]:
    """T1 sandbox setup capability.

    Returns (kind, command, expected_path).
    kind: 'script' | 'docker' | 'missing'
    expected_path: relative path of the preferred helper that was
                   sought (or empty string when not script-bound).
    """
    setup_script = SANDBOX_ROOT / "scripts" / "setup.sh"
    compose_file = SANDBOX_ROOT / "docker-compose.yml"
    if not docker_only and _has_executable(setup_script):
        return (
            "script",
            [str(setup_script.relative_to(ROOT))],
            str(setup_script.relative_to(ROOT)),
        )
    if not scripts_only and compose_file.exists():
        return (
            "docker",
            ["docker", "compose", "-f", str(compose_file.relative_to(ROOT)), "build"],
            "",
        )
    return ("missing", [], str(setup_script.relative_to(ROOT)))


def _resolve_tier2_command(scripts_only: bool, docker_only: bool) -> tuple[str, List[str], str]:
    up_script = SANDBOX_ROOT / "scripts" / "up.sh"
    if not docker_only and _has_executable(up_script):
        return ("script", [str(up_script.relative_to(ROOT))], str(up_script.relative_to(ROOT)))
    return ("missing", [], str(up_script.relative_to(ROOT)))


def _resolve_tier3_command(scripts_only: bool, docker_only: bool) -> tuple[str, List[str], str]:
    check_script = SANDBOX_ROOT / "scripts" / "check.sh"
    if not docker_only and _has_executable(check_script):
        return ("script", [str(check_script.relative_to(ROOT))], str(check_script.relative_to(ROOT)))
    return ("missing", [], str(check_script.relative_to(ROOT)))


def _resolve_tier4_command(scripts_only: bool, docker_only: bool) -> tuple[str, List[str], str]:
    build_script = SANDBOX_ROOT / "scripts" / "build.sh"
    if not docker_only and _has_executable(build_script):
        return ("script", [str(build_script.relative_to(ROOT))], str(build_script.relative_to(ROOT)))
    return ("missing", [], str(build_script.relative_to(ROOT)))


def _resolve_tier5_command(scripts_only: bool, docker_only: bool) -> tuple[str, List[str], str]:
    test_script = SANDBOX_ROOT / "scripts" / "test.sh"
    if not docker_only and _has_executable(test_script):
        return ("script", [str(test_script.relative_to(ROOT))], str(test_script.relative_to(ROOT)))
    return ("missing", [], str(test_script.relative_to(ROOT)))


def _resolve_tier6_command(scripts_only: bool, docker_only: bool) -> tuple[str, List[str], str]:
    down_script = SANDBOX_ROOT / "scripts" / "down.sh"
    if not docker_only and _has_executable(down_script):
        return ("script", [str(down_script.relative_to(ROOT))], str(down_script.relative_to(ROOT)))
    return ("missing", [], str(down_script.relative_to(ROOT)))


def _capability_helpers() -> Dict[str, tuple[Path, str]]:
    return {
        "setup": (SANDBOX_ROOT / "scripts" / "setup.sh", "set up the sandbox environment in a repeatable way"),
        "check": (SANDBOX_ROOT / "scripts" / "check.sh", "run sandbox sanity checks"),
        "build": (SANDBOX_ROOT / "scripts" / "build.sh", "build the target"),
        "test": (SANDBOX_ROOT / "scripts" / "test.sh", "test the target"),
        "start": (SANDBOX_ROOT / "scripts" / "up.sh", "bring the environment up"),
        "stop": (SANDBOX_ROOT / "scripts" / "down.sh", "stop the environment"),
        "shell": (SANDBOX_ROOT / "scripts" / "shell.sh", "open a shell in the environment"),
        "logs": (SANDBOX_ROOT / "scripts" / "logs.sh", "inspect environment logs"),
        "clean": (SANDBOX_ROOT / "scripts" / "clean.sh", "clean runtime artifacts"),
        "reset": (SANDBOX_ROOT / "scripts" / "reset.sh", "reset the environment to a known state"),
    }


def _capability_status() -> Dict[str, Dict[str, str | bool]]:
    compose_file = SANDBOX_ROOT / "docker-compose.yml"
    statuses: Dict[str, Dict[str, str | bool]] = {}
    for name, (path, purpose) in _capability_helpers().items():
        present = _has_executable(path)
        statuses[name] = {
            "present": present,
            "path": str(path.relative_to(ROOT)),
            "purpose": purpose,
        }

    # Image build may be satisfied by docker compose even when there is no
    # helper script yet. Starting the environment remains a separate helper.
    setup_status = statuses["setup"]
    setup_status["satisfied"] = bool(setup_status["present"] or compose_file.exists())
    for key, status in statuses.items():
        if key != "setup":
            status["satisfied"] = bool(status["present"])
    return statuses


def _format_outcome(outcome: str) -> str:
    if outcome == "passed":
        return f"{C.GREEN}{outcome}{C.RESET}"
    if outcome == "failed":
        return f"{C.RED}{outcome}{C.RESET}"
    return f"{C.DIM}{outcome}{C.RESET}"


def _append_validation_history(entries: List[Dict[str, Any]]) -> bool:
    """Append a validation history block to sandbox/CODECOME-GENERATED.md.

    Returns True if updated, False if no provenance file exists.
    """
    if not PROVENANCE_FILE.exists():
        return False

    text = PROVENANCE_FILE.read_text(encoding="utf-8")
    block_lines = ["", f"## Validation run {_iso_now()}", ""]
    block_lines.append("| Tier | Purpose | Outcome | Exit | Duration | Command |")
    block_lines.append("|---|---|---|---|---|---|")
    for entry in entries:
        block_lines.append(
            f"| {entry['tier']} "
            f"| {entry['purpose']} "
            f"| {entry['outcome']} "
            f"| {entry.get('exit_code', '-')} "
            f"| {entry['duration_seconds']}s "
            f"| `{entry['command']}` |"
        )
    block_lines.append("")
    text = text.rstrip() + "\n" + "\n".join(block_lines) + "\n"
    PROVENANCE_FILE.write_text(text, encoding="utf-8")
    return True


def cmd_validate(args: argparse.Namespace) -> int:
    if args.scripts_only and args.docker_only:
        print(C.fail("--scripts-only and --docker-only are mutually exclusive."), file=sys.stderr)
        return 2

    if not SANDBOX_ROOT.exists():
        print(C.fail("sandbox/ does not exist. Run 'apply' first."), file=sys.stderr)
        return 1

    if not _docker_compose_available() and not args.scripts_only:
        # Allow scripts-only invocations to proceed; but warn early.
        # We still proceed since some tiers (T2 check.sh, T3, T4) may
        # not need docker compose directly. The script themselves call docker.
        if args.format != "json":
            print(C.warn("Docker / 'docker compose' not detected on host."))
            print(C.info("Validation will likely fail unless your sandbox can run without Docker."))

    tier_specs = [
        ("T1", "Sandbox setup", _resolve_tier1_command),
        ("T2", "Environment start", _resolve_tier2_command),
        ("T3", "Sandbox sanity", _resolve_tier3_command),
        ("T4", "Target build", _resolve_tier4_command),
        ("T5", "Target test", _resolve_tier5_command),
        ("T6", "Environment stop", _resolve_tier6_command),
    ]

    results: List[Dict[str, Any]] = []
    overall_outcome = "passed"

    for tier_id, purpose, resolver in tier_specs:
        kind, command, expected_path = resolver(args.scripts_only, args.docker_only)
        if kind == "missing":
            reason = (
                f"required sandbox capability is missing: {expected_path}. "
                "Templates are seeds; Phase 1b must leave behind a working way to "
                "set up the sandbox, start it, sanity-check it, build the target, test the target, and stop the environment. "
                "See .opencode/skills/sandbox-bootstrap/SKILL.md."
            )
            entry = TierResult(
                tier=tier_id,
                purpose=purpose,
                command=f"(missing: {expected_path})",
                started_at=_iso_now(),
                duration_seconds=0.0,
                exit_code=None,
                outcome="failed",
                stderr_tail=reason,
                stdout_tail="",
            ).to_dict()
            results.append(entry)
            overall_outcome = "failed"
            if args.format != "json":
                print(
                    f"  {tier_id:<3} {purpose:<18} {_format_outcome('failed')}  "
                    f"{C.DIM}reason: missing {expected_path}{C.RESET}"
                )
                print(f"    {C.DIM}Templates are seeds; implement the missing sandbox capability during Phase 1b.{C.RESET}")
            if not args.keep_going:
                # Mark remaining tiers as skipped because we stopped early.
                for skip_id, skip_purpose, _r in tier_specs[len(results):]:
                    skipped = TierResult(
                        tier=skip_id,
                        purpose=skip_purpose,
                        command="(skipped: prior tier failed)",
                        started_at=_iso_now(),
                        duration_seconds=0.0,
                        exit_code=None,
                        outcome="skipped",
                        stderr_tail="",
                        stdout_tail="",
                    ).to_dict()
                    results.append(skipped)
                    if args.format != "json":
                        print(f"  {skip_id:<3} {skip_purpose:<18} {_format_outcome('skipped')}  (prior tier failed)")
                break
            continue

        if args.format != "json":
            print(f"  {tier_id:<3} {purpose:<18} running {C.DIM}{' '.join(command)}{C.RESET}")

        result = _run_command(command, cwd=ROOT)
        result.tier = tier_id
        result.purpose = purpose
        entry = result.to_dict()
        results.append(entry)

        if args.format != "json":
            outcome_str = _format_outcome(result.outcome)
            exit_str = "-" if result.exit_code is None else str(result.exit_code)
            print(
                f"  {tier_id:<3} {purpose:<18} {outcome_str}  "
                f"{C.DIM}exit={exit_str}  duration={result.duration_seconds:.2f}s{C.RESET}"
            )
            if result.outcome == "failed" and result.stderr_tail:
                print(f"    {C.DIM}--- stderr (last lines) ---{C.RESET}")
                for line in result.stderr_tail.splitlines()[-15:]:
                    print(f"    {line}")

        if result.outcome == "failed":
            overall_outcome = "failed"
            if not args.keep_going:
                # Mark remaining as skipped.
                for skip_id, skip_purpose, _ in tier_specs[len(results):]:
                    skipped = TierResult(
                        tier=skip_id,
                        purpose=skip_purpose,
                        command="(skipped: prior tier failed)",
                        started_at=_iso_now(),
                        duration_seconds=0.0,
                        exit_code=None,
                        outcome="skipped",
                        stderr_tail="",
                        stdout_tail="",
                    ).to_dict()
                    results.append(skipped)
                    if args.format != "json":
                        print(f"  {skip_id:<3} {skip_purpose:<18} {_format_outcome('skipped')}  (prior tier failed)")
                break

    helper_status = _capability_status()
    missing_helpers = [
        name for name in ("shell", "logs", "clean", "reset")
        if not bool(helper_status[name].get("satisfied"))
    ]

    history_updated = _append_validation_history(results)

    payload = {
        "overall_outcome": overall_outcome,
        "history_updated": history_updated,
        "tiers": results,
        "capabilities": helper_status,
        "missing_helpers": missing_helpers,
    }

    if args.format == "json":
        _emit(payload, "json")
    else:
        print()
        print(f"  {C.BOLD}overall:{C.RESET}  {_format_outcome(overall_outcome)}")
        if missing_helpers:
            print(C.warn(
                "Helper capabilities still missing: " + ", ".join(missing_helpers)
            ))
            print(C.info(
                "Phase 2 enforces setup/start/check/build/test/stop. Document missing helper capabilities in sandbox-plan.md."
            ))
        if history_updated:
            print(C.info(f"Validation history appended to {PROVENANCE_FILE.relative_to(ROOT)}"))
        else:
            print(C.warn("No CODECOME-GENERATED.md present; validation history not persisted."))

    return 0 if overall_outcome == "passed" else 1


def cmd_recipe_validate(args: argparse.Namespace) -> int:
    path = Path(args.path) if hasattr(args, "path") and args.path else SANDBOX_RECIPE_PATH
    if not path.is_file():
        print(C.fail(f"Sandbox recipe not found at {path}"), file=sys.stderr)
        return 1

    try:
        from sandbox.recipe import load_recipe, validate_recipe
        recipe = load_recipe(path)
    except Exception as exc:
        print(C.fail(f"Failed to load recipe: {exc}"), file=sys.stderr)
        return 1

    errors = validate_recipe(recipe, root=str(ROOT))
    if errors:
        print(C.fail(f"Sandbox recipe at {path} has {len(errors)} validation error(s):"), file=sys.stderr)
        for err in errors:
            print(f"  {C.SYM_BULLET} {err}")
        return 1

    print(C.ok(f"Sandbox recipe at {path} is valid."))
    return 0


def cmd_recipe_print(args: argparse.Namespace) -> int:
    path = Path(args.path) if hasattr(args, "path") and args.path else SANDBOX_RECIPE_PATH
    if not path.is_file():
        print(C.fail(f"Sandbox recipe not found at {path}"), file=sys.stderr)
        return 1

    try:
        from sandbox.recipe import load_recipe
        recipe = load_recipe(path)
    except Exception as exc:
        print(C.fail(f"Failed to load recipe: {exc}"), file=sys.stderr)
        return 1

    if args.format == "json":
        _emit(recipe, "json")
    else:
        from sandbox.recipe import dump_recipe
        print(dump_recipe(recipe).rstrip())

    return 0


def cmd_not_implemented(args: argparse.Namespace) -> int:
    name = getattr(args, "command", "<unknown>")
    print(
        C.warn(f"Subcommand '{name}' is not implemented yet."),
        file=sys.stderr,
    )
    print(
        C.info("Tracked in .project/auto-sandbox-bootstrap-plan.md."),
        file=sys.stderr,
    )
    return NOT_IMPLEMENTED_EXIT


# --- Argument parser ----------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--format",
        choices=["text", "json"],
        default=argparse.SUPPRESS,
        help="Output format. Defaults to text.",
    )

    parser = argparse.ArgumentParser(
        prog="sandbox-bootstrap",
        description="Manage CodeCome sandbox examples and bootstrap the live sandbox.",
    )
    # Support --format before the subcommand as well
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help=argparse.SUPPRESS,
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", parents=[common], help="List available sandbox examples.")
    p_list.set_defaults(func=cmd_list)

    p_inspect = sub.add_parser(
        "inspect",
        parents=[common],
        help="Print manifest and previews for one example.",
    )
    p_inspect.add_argument("id", help="Example id (matches templates/sandboxes/<id>/).")
    p_inspect.set_defaults(func=cmd_inspect)

    p_detect = sub.add_parser(
        "detect",
        parents=[common],
        help="Scan workspace and propose ranked sandbox candidates.",
    )
    p_detect.add_argument(
        "--force-src-walk",
        action="store_true",
        help="Ignore recon notes and always walk src/ for hints.",
    )
    p_detect.set_defaults(func=cmd_detect)

    p_apply = sub.add_parser(
        "apply",
        parents=[common],
        help="Copy an example into sandbox/ with marker substitution.",
    )
    p_apply.add_argument("id", help="Example id to apply.")
    p_apply.add_argument("--var", action="append", default=[],
                         help="Marker substitution KEY=VAL (repeatable).")
    p_apply.add_argument("--dry-run", action="store_true", help="Preview only, do not write.")
    p_apply.add_argument("--force", action="store_true",
                         help="Allow overwriting user-managed sandbox/ content.")
    p_apply.add_argument(
        "--no-gate",
        action="store_true",
        help="Skip recording provenance and evaluating validation gate.",
    )
    p_apply.set_defaults(func=cmd_apply)

    p_validate = sub.add_parser(
        "validate",
        parents=[common],
        help="Run sandbox validation tiers and capture results.",
    )
    p_validate.add_argument(
        "--scripts-only",
        action="store_true",
        help="Only run sandbox/scripts/* tiers; never call docker compose directly.",
    )
    p_validate.add_argument(
        "--docker-only",
        action="store_true",
        help="Only run docker compose tiers; skip sandbox/scripts/*.",
    )
    p_validate.add_argument(
        "--no-record",
        action="store_true",
        help="Do not record the result in state.json (dry run evaluation).",
    )
    p_validate.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue running subsequent tiers even if one fails.",
    )
    p_validate.set_defaults(func=cmd_validate)

    p_regen = sub.add_parser(
        "regenerate",
        parents=[common],
        help="Re-apply the recorded sandbox example with backup.",
    )
    p_regen.add_argument(
        "--var",
        action="append",
        default=[],
        help="Marker override KEY=VAL (repeatable). Wins over recorded markers.",
    )
    p_regen.add_argument("--dry-run", action="store_true", help="Preview only, do not write.")
    p_regen.add_argument(
        "--no-gate",
        action="store_true",
        help="Skip recording provenance and evaluating validation gate.",
    )
    p_regen.set_defaults(func=cmd_regenerate)

    p_status = sub.add_parser(
        "status",
        parents=[common],
        help="Print sandbox provenance and Phase 2 gate result.",
    )
    p_status.add_argument(
        "--gate",
        action="store_true",
        help="Exit non-zero if Phase 2 should be blocked.",
    )
    p_status.set_defaults(func=cmd_status)

    p_recipe_validate = sub.add_parser(
        "recipe-validate",
        parents=[common],
        help="Validate itemdb/notes/sandbox-recipe.yml.",
    )
    p_recipe_validate.add_argument(
        "path",
        nargs="?",
        default=str(SANDBOX_RECIPE_PATH),
        help=f"Path to the recipe file. Defaults to {SANDBOX_RECIPE_PATH}.",
    )
    p_recipe_validate.set_defaults(func=cmd_recipe_validate)

    p_recipe_print = sub.add_parser(
        "recipe-print",
        parents=[common],
        help="Print the sandbox recipe.",
    )
    p_recipe_print.add_argument(
        "path",
        nargs="?",
        default=str(SANDBOX_RECIPE_PATH),
        help=f"Path to the recipe file. Defaults to {SANDBOX_RECIPE_PATH}.",
    )
    p_recipe_print.set_defaults(func=cmd_recipe_print)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
