#!/usr/bin/env python3
"""
CodeCome sandbox bootstrap CLI.

Manages the curated sandbox examples under templates/sandboxes/ and the
target-specific sandbox at sandbox/.

Subcommands:
  list         List available sandbox examples.
  inspect      Print manifest and previews for one example.
  detect       Scan workspace and propose ranked sandbox candidates.
  apply        Copy an example into sandbox/ (not implemented yet).
  validate     Run validation tiers (not implemented yet).
  regenerate   Re-apply current sandbox example (not implemented yet).
  status       Print sandbox provenance and Phase 2 gate result.

Environment variables:
  CODECOME_ALLOW_NO_SANDBOX        Skip Phase 2 sandbox gate.
  CODECOME_BOOTSTRAP_MAX_RETRIES   Default agent retry budget (default 3).
  CODECOME_BOOTSTRAP_DRY_RUN       Force --dry-run on apply/regenerate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = ROOT / "templates" / "sandboxes"
SANDBOX_ROOT = ROOT / "sandbox"
NOTES_ROOT = ROOT / "itemdb" / "notes"
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
        "dotnet", "c#", "csharp", "terraform", "hcl", "shell", "bash",
    }:
        if re.search(rf"\b{re.escape(hint)}\b", text_blob):
            languages.append(hint)

    manifests: List[str] = []
    for name in _LANGUAGE_HINTS_BY_FILE:
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


def cmd_status(args: argparse.Namespace) -> int:
    provenance = read_provenance()
    has_user_content = sandbox_has_user_content()
    allow_no_sandbox = bool(os.environ.get("CODECOME_ALLOW_NO_SANDBOX"))

    if provenance is not None:
        sandbox_state = "generated"
    elif has_user_content:
        sandbox_state = "user-managed"
    else:
        sandbox_state = "missing"

    gate_pass = sandbox_state in {"generated", "user-managed"} or allow_no_sandbox

    payload: Dict[str, Any] = {
        "sandbox_state": sandbox_state,
        "sandbox_path": str(SANDBOX_ROOT.relative_to(ROOT)),
        "provenance_present": provenance is not None,
        "allow_no_sandbox": allow_no_sandbox,
        "phase2_gate_pass": gate_pass,
    }
    if provenance:
        # Strip raw text from JSON output to keep it small.
        payload["provenance"] = {k: v for k, v in provenance.items() if k != "raw"}

    if args.format == "json":
        _emit(payload, "json")
    else:
        print(C.header("Sandbox status"))
        print(f"  {C.DIM}path:{C.RESET}            {payload['sandbox_path']}")
        print(f"  {C.DIM}state:{C.RESET}           {sandbox_state}")
        print(f"  {C.DIM}provenance:{C.RESET}      {'yes' if provenance else 'no'}")
        print(f"  {C.DIM}allow override:{C.RESET}  {'yes' if allow_no_sandbox else 'no'}")
        if gate_pass:
            print(C.ok("Phase 2 sandbox gate would pass."))
        else:
            print(C.warn("Phase 2 sandbox gate would block."))
            print(C.info("Override with CODECOME_ALLOW_NO_SANDBOX=1"))

    if args.gate and not gate_pass:
        return 1
    return 0


# --- Apply / regenerate -------------------------------------------------------

import hashlib
import shutil
from datetime import datetime, timezone


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
    if args.format == "json":
        plan_payload = {
            "dry_run": dry_run,
            "example": manifest.id,
            "example_path": manifest.relative_path(),
            "sandbox_path": str(SANDBOX_ROOT.relative_to(ROOT)),
            "force": bool(args.force),
            "files_to_write": [str(p.relative_to(manifest.path)) for p in files],
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
        print(f"  {C.DIM}files to write:{C.RESET}   {len(files)}")
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
    file_hashes = {rel: digest for rel, digest in written}

    provenance_text = render_provenance(manifest, markers, file_hashes)
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
    parser = argparse.ArgumentParser(
        prog="sandbox-bootstrap",
        description="Manage CodeCome sandbox examples and bootstrap the live sandbox.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format. Defaults to text.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List available sandbox examples.")
    p_list.set_defaults(func=cmd_list)

    p_inspect = sub.add_parser(
        "inspect",
        help="Print manifest and previews for one example.",
    )
    p_inspect.add_argument("id", help="Example id (matches templates/sandboxes/<id>/).")
    p_inspect.set_defaults(func=cmd_inspect)

    p_detect = sub.add_parser(
        "detect",
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
        help="Copy an example into sandbox/ with marker substitution.",
    )
    p_apply.add_argument("id", help="Example id to apply.")
    p_apply.add_argument("--var", action="append", default=[],
                         help="Marker substitution KEY=VAL (repeatable).")
    p_apply.add_argument("--dry-run", action="store_true", help="Preview only, do not write.")
    p_apply.add_argument("--force", action="store_true",
                         help="Allow overwriting user-managed sandbox/ content.")
    p_apply.add_argument(
        "--max-retries",
        type=int,
        default=int(os.environ.get("CODECOME_BOOTSTRAP_MAX_RETRIES", DEFAULT_MAX_RETRIES)),
        help="Agent remediation retry budget (env CODECOME_BOOTSTRAP_MAX_RETRIES, default 3).",
    )
    p_apply.set_defaults(func=cmd_apply)

    p_validate = sub.add_parser(
        "validate",
        help="Run validation tiers (not implemented yet).",
    )
    p_validate.add_argument(
        "--scripts-only",
        action="store_true",
        help="Only run sandbox/scripts/* tiers.",
    )
    p_validate.add_argument(
        "--docker-only",
        action="store_true",
        help="Skip sandbox/scripts/* and call docker/docker compose directly.",
    )
    p_validate.add_argument(
        "--keep-going",
        action="store_true",
        help="Run all tiers even after a failure.",
    )
    p_validate.set_defaults(func=cmd_not_implemented)

    p_regen = sub.add_parser(
        "regenerate",
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
        "--max-retries",
        type=int,
        default=int(os.environ.get("CODECOME_BOOTSTRAP_MAX_RETRIES", DEFAULT_MAX_RETRIES)),
        help="Agent remediation retry budget.",
    )
    p_regen.set_defaults(func=cmd_regenerate)

    p_status = sub.add_parser(
        "status",
        help="Print sandbox provenance and Phase 2 gate result.",
    )
    p_status.add_argument(
        "--gate",
        action="store_true",
        help="Exit non-zero if Phase 2 should be blocked.",
    )
    p_status.set_defaults(func=cmd_status)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
