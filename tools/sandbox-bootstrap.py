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


def cmd_not_implemented(args: argparse.Namespace) -> int:
    name = getattr(args, "command", "<unknown>")
    print(
        C.warn(f"Subcommand '{name}' is not implemented yet."),
        file=sys.stderr,
    )
    print(
        C.info("Tracked in .project/auto-sandbox-bootstrap-plan.md (commits 6 and 7)."),
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
        help="Copy an example into sandbox/ (not implemented yet).",
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
    p_apply.set_defaults(func=cmd_not_implemented)

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
        help="Re-apply current sandbox example (not implemented yet).",
    )
    p_regen.add_argument("--dry-run", action="store_true", help="Preview only, do not write.")
    p_regen.add_argument(
        "--max-retries",
        type=int,
        default=int(os.environ.get("CODECOME_BOOTSTRAP_MAX_RETRIES", DEFAULT_MAX_RETRIES)),
        help="Agent remediation retry budget.",
    )
    p_regen.set_defaults(func=cmd_not_implemented)

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
