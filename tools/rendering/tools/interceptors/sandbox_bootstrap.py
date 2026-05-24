# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
SandboxBootstrapInterceptor — renders sandbox-bootstrap.py --format json
output as a styled Sandbox panel instead of the generic Bash panel.

Detects bash invocations of ``tools/sandbox-bootstrap.py --format json``
and renders the JSON output as a structured, colour-coded ``Sandbox``
panel. The script is CodeCome-owned, so its JSON schema is stable.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from typing import Any, Optional

from rendering.tools.base import ToolRenderer
from rendering.tools.interceptors.base import CommandExecutionInterceptor

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SANDBOX_BOOTSTRAP_SCRIPT = "tools/sandbox-bootstrap.py"
_SANDBOX_KNOWN_SUBCOMMANDS = {
    "list", "inspect", "detect", "status", "apply", "regenerate", "validate",
}
# make targets that wrap the script and where we can confidently infer the
# subcommand from the target name.
_SANDBOX_MAKE_TARGETS = {
    "sandbox-list": "list",
    "sandbox-inspect": "inspect",
    "sandbox-detect": "detect",
    "sandbox-status": "status",
    "sandbox-bootstrap": "apply",       # `make sandbox-bootstrap ID=...` -> apply
    "sandbox-regenerate": "regenerate",
    "sandbox-validate": "validate",
}
_SANDBOX_REQUIRED_CAPABILITIES = ("setup", "start", "check", "build", "test", "stop")
_SANDBOX_HELPER_CAPABILITIES = ("shell", "logs", "clean", "reset")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _console_supports_emoji(sink) -> bool:
    """Return True when the console encoding can carry common emojis."""
    from rendering.sink import RichConsoleSink
    if isinstance(sink, RichConsoleSink):
        enc = (getattr(sink._console, "encoding", "") or "").lower()
    else:
        enc = (sys.stdout.encoding or "").lower()
    return "utf" in enc


def _sandbox_glyphs(sink) -> dict[str, str]:
    """Return a name->glyph table, with emoji on utf-8 terminals and
    ASCII fallbacks elsewhere."""
    if _console_supports_emoji(sink):
        return {
            "ok": "\u2705",
            "fail": "\u274c",
            "warn": "\u26a0\ufe0f ",
            "skip": "\u23ed\ufe0f ",
            "info": "\u2139\ufe0f ",
            "box": "\U0001f4e6",
            "check": "\U0001f9ea",
            "alarm": "\U0001f6a6",
            "clock": "\u23f1",
            "bullet": "\u2022",
        }
    return {
        "ok": "[OK]",
        "fail": "[FAIL]",
        "warn": "[!]",
        "skip": "[--]",
        "info": "[i]",
        "box": "[box]",
        "check": "[chk]",
        "alarm": "[gate]",
        "clock": "t=",
        "bullet": "-",
    }


def _is_sandbox_bootstrap_json_call(command_str: str) -> Optional[str]:
    """Return the subcommand name if this bash invocation is a
    sandbox-bootstrap call configured for --format json, else None.

    Recognises both:
      - direct script invocations:
          .venv/bin/python3 tools/sandbox-bootstrap.py --format json status
          python tools/sandbox-bootstrap.py status --format=json
      - make-target wrappers when BOOTSTRAP_ARGS forces json:
          make sandbox-status BOOTSTRAP_ARGS='--format json'
          make sandbox-validate BOOTSTRAP_ARGS=--format=json
    """
    if not command_str:
        return None
    try:
        tokens = shlex.split(command_str)
    except ValueError:
        return None
    if not tokens:
        return None

    # Look for --format json or --format=json anywhere in the tokens.
    # Also recognise it when nested inside a make-style assignment such as
    # BOOTSTRAP_ARGS='--format json' (which shlex collapses into a single
    # token "BOOTSTRAP_ARGS=--format json").
    has_json_format = False
    for i, tok in enumerate(tokens):
        if tok == "--format=json":
            has_json_format = True
            break
        if tok == "--format" and i + 1 < len(tokens) and tokens[i + 1] == "json":
            has_json_format = True
            break
        # Make-style env assignments (e.g. BOOTSTRAP_ARGS=--format json,
        # BOOTSTRAP_ARGS=--format=json, OPENCODE_ARGS=...).
        if "=" in tok and ("--format json" in tok or "--format=json" in tok):
            has_json_format = True
            break

    # Direct script invocation path.
    script_idx = -1
    for i, tok in enumerate(tokens):
        if tok.endswith(_SANDBOX_BOOTSTRAP_SCRIPT) or tok.endswith("/" + _SANDBOX_BOOTSTRAP_SCRIPT):
            script_idx = i
            break
    if script_idx >= 0 and has_json_format:
        # Subcommand: first non-flag positional after the script path.
        for j in range(script_idx + 1, len(tokens)):
            t = tokens[j]
            if t.startswith("-"):
                # Skip --format json (two-token form).
                if t == "--format" and j + 1 < len(tokens):
                    continue
                continue
            # A bare token after --format json may be the value of --format.
            # Skip if previous token was --format (without =).
            if j > 0 and tokens[j - 1] == "--format":
                continue
            if t in _SANDBOX_KNOWN_SUBCOMMANDS:
                return t
        return None

    # Make-target wrapper path.
    # Accept env-prefixed forms too, e.g.:
    #   BOOTSTRAP_ARGS='--format json --keep-going' make sandbox-validate
    make_idx = -1
    for i, tok in enumerate(tokens):
        if tok == "make":
            make_idx = i
            break
    if make_idx >= 0:
        # Find the first sandbox-* target token after `make`.
        for tok in tokens[make_idx + 1:]:
            if tok in _SANDBOX_MAKE_TARGETS and has_json_format:
                return _SANDBOX_MAKE_TARGETS[tok]
    return None


def _sandbox_payload_matches(subcommand: str, payload: Any) -> bool:
    """Cheap structural sniff so we don't render unrelated JSON as a
    Sandbox panel. Returns False on obvious schema mismatch so the bash
    renderer can take over."""
    if subcommand == "list":
        return isinstance(payload, list) and (not payload or isinstance(payload[0], dict))
    if not isinstance(payload, dict):
        return False
    if subcommand == "inspect":
        return any(k in payload for k in ("id", "display_name", "files"))
    if subcommand == "detect":
        return "candidates" in payload or "signals" in payload
    if subcommand == "status":
        return "sandbox_state" in payload or "phase2_gate_pass" in payload or "capabilities" in payload
    if subcommand in ("apply", "regenerate"):
        return any(k in payload for k in ("example", "files_to_write", "written_files", "status"))
    if subcommand == "validate":
        return "overall_outcome" in payload or "tiers" in payload
    return False


def _sandbox_outcome_style(outcome: str) -> tuple[str, str]:
    """Return (rich_style, glyph_key) for a tier outcome string."""
    if outcome == "passed":
        return "green", "ok"
    if outcome == "failed":
        return "red", "fail"
    if outcome == "skipped":
        return "dim", "skip"
    return "yellow", "warn"


def _sandbox_state_style(state_value: str) -> str:
    if state_value == "generated":
        return "green"
    if state_value == "user-managed":
        return "yellow"
    if state_value == "missing":
        return "red"
    return "dim"


def _sandbox_last_validation_style(value: Optional[str]) -> str:
    if value == "passed":
        return "green"
    if value == "mixed":
        return "yellow"
    if value == "failed":
        return "red"
    if value == "skipped":
        return "yellow"
    return "dim"


# ---------------------------------------------------------------------------
# Rich renderers (called when renderer.rich is True)
# ---------------------------------------------------------------------------

def _render_sandbox_rich(
    renderer: ToolRenderer,
    subcommand: str,
    payload: Any,
    command: str,
    description: str,
    status: str,
) -> bool:
    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text

    sink = renderer.context.sink
    glyphs = _sandbox_glyphs(sink)

    # Default border = yellow (in flight) / green (completed); per-subcommand
    # renderers may override based on payload contents (e.g. validate failed).
    border = "yellow" if status != "completed" else "green"

    title = f"{glyphs['box']} Sandbox \u00b7 {subcommand}"
    sections: list[Any] = []
    sections.append(Text(f"$ {command}", style="bold cyan"))
    if description:
        sections.append(Text(description, style="dim italic"))
    sections.append(Text())

    try:
        if subcommand == "list":
            border = _render_sandbox_list_rich(sections, payload, border)
        elif subcommand == "inspect":
            border = _render_sandbox_inspect_rich(sections, payload, border, glyphs, renderer)
        elif subcommand == "detect":
            border = _render_sandbox_detect_rich(sections, payload, border, glyphs, renderer)
        elif subcommand == "status":
            border = _render_sandbox_status_rich(sections, payload, border, glyphs)
        elif subcommand in ("apply", "regenerate"):
            border = _render_sandbox_apply_rich(sections, payload, subcommand, border, glyphs, renderer)
        elif subcommand == "validate":
            border = _render_sandbox_validate_rich(sections, payload, border, glyphs, renderer)
        else:
            return False
    except (KeyError, TypeError, AttributeError):
        return False

    sink.write(Panel(Group(*sections), title=title, border_style=border, expand=True))
    return True


def _render_sandbox_list_rich(sections: list[Any], payload: Any, border: str) -> str:
    from rich.table import Table
    from rich.text import Text
    if not isinstance(payload, list):
        raise TypeError("list subcommand expects a JSON array")
    table = Table(show_header=True, header_style="bold cyan", expand=True, pad_edge=False)
    table.add_column("id", style="bold cyan", no_wrap=True)
    table.add_column("name")
    table.add_column("languages", style="dim")
    table.add_column("manifests", style="dim")
    for ex in payload:
        applies = ex.get("applies_when") or {}
        langs = ", ".join(applies.get("languages") or []) or "-"
        mans = ", ".join((applies.get("manifests") or [])[:4]) or "-"
        if applies.get("manifests") and len(applies["manifests"]) > 4:
            mans += " \u2026"
        table.add_row(str(ex.get("id", "")), str(ex.get("display_name", "")), langs, mans)
    sections.append(table)
    sections.append(Text())
    sections.append(Text(f"{len(payload)} example(s) available", style="dim"))
    return border


def _render_sandbox_inspect_rich(
    sections: list[Any], payload: dict, border: str, glyphs: dict, renderer: ToolRenderer
) -> str:
    from rich.text import Text
    sections.append(Text(f"{payload.get('display_name', '')}", style="bold cyan"))
    sections.append(Text(f"  id:    {payload.get('id', '')}", style="dim"))
    sections.append(Text(f"  path:  {payload.get('path', '')}", style="dim"))
    applies = payload.get("applies_when") or {}
    if applies:
        for k, v in applies.items():
            joined = ", ".join(v) if isinstance(v, list) else str(v)
            sections.append(Text(f"  applies_when.{k}: {joined}", style="dim"))
    if payload.get("required_tools"):
        sections.append(Text(f"  required_tools: {', '.join(payload['required_tools'])}", style="dim"))
    if payload.get("template_vars"):
        sections.append(Text(f"  template_vars:  {', '.join(payload['template_vars'])}", style="dim"))
    if payload.get("default_ports"):
        sections.append(Text(f"  default_ports:  {', '.join(str(p) for p in payload['default_ports'])}", style="dim"))
    if payload.get("build_command"):
        sections.append(Text(f"  build_command:  {payload['build_command']}", style="dim"))
    if payload.get("test_command"):
        sections.append(Text(f"  test_command:   {payload['test_command']}", style="dim"))
    if payload.get("caveats"):
        sections.append(Text())
        sections.append(Text("Caveats:", style="bold yellow"))
        for c in payload["caveats"]:
            sections.append(Text(f"  {glyphs['warn']} {c}", style="yellow"))
    files = payload.get("files") or []
    if files:
        sections.append(Text())
        cap = renderer.context.settings.sandbox_files_cap
        sections.append(Text(f"Files ({len(files)}):", style="bold cyan"))
        for f in files[:cap]:
            sections.append(Text(f"  {glyphs['bullet']} {f}"))
        if len(files) > cap:
            sections.append(Text(f"  ... and {len(files) - cap} more", style="dim"))
    return border


def _render_sandbox_detect_rich(
    sections: list[Any], payload: dict, border: str, glyphs: dict, renderer: ToolRenderer
) -> str:
    from rich.table import Table
    from rich.text import Text
    signals = payload.get("signals") or {}
    sections.append(Text("Detection signals", style="bold cyan"))
    sections.append(Text(f"  source:    {signals.get('source', '-')}", style="dim"))
    sections.append(Text(f"  languages: {', '.join(signals.get('languages') or []) or '-'}", style="dim"))
    sections.append(Text(f"  manifests: {', '.join(signals.get('manifests') or []) or '-'}", style="dim"))
    sections.append(Text())

    candidates = payload.get("candidates") or []
    sections.append(Text(f"Ranked candidates ({len(candidates)}):", style="bold cyan"))
    table = Table(show_header=True, header_style="bold cyan", expand=True, pad_edge=False)
    table.add_column("score", justify="right", no_wrap=True)
    table.add_column("id", style="bold cyan", no_wrap=True)
    table.add_column("name")
    table.add_column("path", style="dim")
    cap = renderer.context.settings.sandbox_files_cap
    for c in candidates[:cap]:
        score = c.get("score", 0)
        score_style = "green" if score >= 5 else ("yellow" if score >= 1 else "dim")
        table.add_row(
            Text(str(score), style=score_style),
            str(c.get("id", "")),
            str(c.get("display_name", "")),
            str(c.get("path", "")),
        )
    sections.append(table)
    if len(candidates) > cap:
        sections.append(Text(f"... and {len(candidates) - cap} more", style="dim"))
    return border


def _render_sandbox_status_rich(
    sections: list[Any], payload: dict, border: str, glyphs: dict
) -> str:
    from rich.table import Table
    from rich.text import Text
    state_value = str(payload.get("sandbox_state", "unknown"))
    last_validation = payload.get("last_validation")
    gate_pass = bool(payload.get("phase2_gate_pass"))
    gate_reason = str(payload.get("phase2_gate_reason", ""))

    state_glyph = {"generated": glyphs["ok"], "user-managed": glyphs["warn"], "missing": glyphs["fail"]}.get(state_value, glyphs["info"])
    sections.append(Text.assemble(
        ("state: ", "bold"),
        (f"{state_glyph} {state_value}", _sandbox_state_style(state_value)),
    ))
    sections.append(Text(f"  path:           {payload.get('sandbox_path', '-')}", style="dim"))
    sections.append(Text(f"  provenance:     {'yes' if payload.get('provenance_present') else 'no'}", style="dim"))
    lv_text = last_validation if last_validation is not None else "-"
    sections.append(Text.assemble(
        ("  last validation: ", "dim"),
        (str(lv_text), _sandbox_last_validation_style(last_validation)),
    ))
    sections.append(Text(f"  allow override: {'yes' if payload.get('allow_no_sandbox') else 'no'}", style="dim"))
    sections.append(Text())

    # Gate badge.
    if gate_pass:
        sections.append(Text.assemble(
            (f"{glyphs['alarm']} ", ""),
            (f"Phase 2 gate would PASS", "bold green"),
            (f" \u2014 {gate_reason}", "dim"),
        ))
    else:
        sections.append(Text.assemble(
            (f"{glyphs['alarm']} ", ""),
            (f"Phase 2 gate would BLOCK", "bold red"),
            (f" \u2014 {gate_reason}", "dim"),
        ))
        border = "yellow"

    sections.append(Text())
    capabilities = payload.get("capabilities") or {}
    if capabilities:
        table = Table(show_header=True, header_style="bold cyan", expand=True, pad_edge=False)
        table.add_column("capability", no_wrap=True)
        table.add_column("status", no_wrap=True)
        table.add_column("path", style="dim")
        for name in (*_SANDBOX_REQUIRED_CAPABILITIES, *_SANDBOX_HELPER_CAPABILITIES):
            cap = capabilities.get(name)
            if cap is None:
                continue
            satisfied = bool(cap.get("satisfied"))
            present = bool(cap.get("present"))
            is_helper = name in _SANDBOX_HELPER_CAPABILITIES
            if satisfied:
                badge = Text(f"{glyphs['ok']} ok", style="green")
            elif is_helper and not present:
                badge = Text(f"{glyphs['skip']} optional", style="dim")
            else:
                badge = Text(f"{glyphs['fail']} missing", style="red")
            table.add_row(name, badge, str(cap.get("path", "")))
        sections.append(table)
    return border


def _render_sandbox_apply_rich(
    sections: list[Any], payload: dict, subcommand: str, border: str, glyphs: dict, renderer: ToolRenderer
) -> str:
    from rich.text import Text
    apply_status = str(payload.get("status", ""))
    is_dry = bool(payload.get("dry_run")) or apply_status == "dry-run"
    chip_text = "DRY RUN" if is_dry else apply_status.upper() or "(unknown)"
    chip_style = "yellow" if is_dry else ("green" if apply_status == "applied" else "dim")
    sections.append(Text.assemble(
        (f"{glyphs['box']} ", ""),
        (f"{subcommand} ", "bold cyan"),
        (f"{payload.get('example', '-')}  ", "bold cyan"),
        (f"[{chip_text}]", chip_style),
    ))
    sections.append(Text(f"  example_path: {payload.get('example_path', '-')}", style="dim"))
    sections.append(Text(f"  sandbox_path: {payload.get('sandbox_path', '-')}", style="dim"))
    sections.append(Text(f"  force:        {payload.get('force', False)}", style="dim"))
    if payload.get("backup_dir"):
        sections.append(Text(f"  backup_dir:   {payload['backup_dir']}", style="dim"))

    files_to_write = payload.get("files_to_write") or []
    written = payload.get("written_files") or []
    sections.append(Text())
    sections.append(Text(
        f"files: planned={len(files_to_write)}  written={len(written)}",
        style="bold cyan",
    ))
    markers = payload.get("markers_provided") or {}
    if markers:
        sections.append(Text(f"markers_provided ({len(markers)}):", style="bold cyan"))
        for k, v in markers.items():
            sections.append(Text(f"  {k} = {v}", style="dim"))
    unfilled = payload.get("markers_used_unfilled") or []
    if unfilled:
        sections.append(Text())
        sections.append(Text.assemble(
            (f"{glyphs['warn']} ", ""),
            (f"Declared markers used but not provided: {', '.join(unfilled)}", "yellow"),
        ))
        border = "yellow"
    undeclared = payload.get("markers_used_undeclared") or []
    if undeclared:
        sections.append(Text.assemble(
            (f"{glyphs['warn']} ", ""),
            (f"Markers used but not declared: {', '.join(undeclared)}", "yellow"),
        ))
        border = "yellow"

    show_files = files_to_write or written
    if show_files:
        sections.append(Text())
        cap = renderer.context.settings.sandbox_files_cap
        for f in show_files[:cap]:
            sections.append(Text(f"  {glyphs['bullet']} {f}"))
        if len(show_files) > cap:
            sections.append(Text(f"  ... and {len(show_files) - cap} more", style="dim"))

    if apply_status == "applied" and not is_dry:
        sections.append(Text())
        sections.append(Text.assemble(
            (f"{glyphs['ok']} ", ""),
            (f"Applied '{payload.get('example', '-')}'", "bold green"),
            (f" \u2192 {payload.get('sandbox_path', '-')}", "dim"),
        ))
        if payload.get("provenance_path"):
            sections.append(Text(f"  provenance: {payload['provenance_path']}", style="dim"))
    return border


def _render_sandbox_validate_rich(
    sections: list[Any], payload: dict, border: str, glyphs: dict, renderer: ToolRenderer
) -> str:
    from rich.table import Table
    from rich.text import Text
    overall = str(payload.get("overall_outcome", "unknown"))
    overall_style, overall_glyph_key = _sandbox_outcome_style(overall)

    sections.append(Text.assemble(
        (f"{glyphs['check']} ", ""),
        ("overall: ", "bold"),
        (f"{glyphs[overall_glyph_key]} {overall}", overall_style),
    ))

    if overall == "failed":
        border = "red"
    elif overall == "passed":
        border = "green"
    else:
        border = "yellow"

    stderr_cap = renderer.context.settings.sandbox_validate_stderr_lines

    tiers = payload.get("tiers") or []
    if tiers:
        sections.append(Text())
        table = Table(show_header=True, header_style="bold cyan", expand=True, pad_edge=False)
        table.add_column("tier", no_wrap=True)
        table.add_column("purpose")
        table.add_column("outcome", no_wrap=True)
        table.add_column("dur", justify="right", no_wrap=True)
        table.add_column("exit", justify="right", no_wrap=True)
        for t in tiers:
            t_outcome = str(t.get("outcome", "unknown"))
            o_style, o_key = _sandbox_outcome_style(t_outcome)
            badge = Text(f"{glyphs[o_key]} {t_outcome}", style=o_style)
            dur = t.get("duration_seconds")
            dur_str = f"{dur:.2f}s" if isinstance(dur, (int, float)) else "-"
            exit_code = t.get("exit_code")
            exit_str = "-" if exit_code is None else str(exit_code)
            table.add_row(
                str(t.get("tier", "")),
                str(t.get("purpose", "")),
                badge,
                dur_str,
                exit_str,
            )
        sections.append(table)

        # For each failed tier, show a capped stderr_tail under it.
        for t in tiers:
            if t.get("outcome") != "failed":
                continue
            stderr_tail = str(t.get("stderr_tail") or "").strip()
            if not stderr_tail:
                continue
            sections.append(Text())
            sections.append(Text(
                f"{glyphs['fail']} {t.get('tier', '')} {t.get('purpose', '')} stderr (tail):",
                style="bold red",
            ))
            tail_lines = stderr_tail.splitlines()
            shown = tail_lines[-stderr_cap:]
            for line in shown:
                sections.append(Text(f"  {line}", style="red"))
            if len(tail_lines) > stderr_cap:
                sections.append(Text(
                    f"  ... ({len(tail_lines) - stderr_cap} earlier lines truncated; "
                    f"see tmp/last-phase-*.jsonl for full output)",
                    style="dim",
                ))

    missing = payload.get("missing_helpers") or []
    if missing:
        sections.append(Text())
        sections.append(Text.assemble(
            (f"{glyphs['warn']} ", ""),
            (f"Helper capabilities still missing: {', '.join(missing)}", "yellow"),
        ))

    if payload.get("history_updated"):
        sections.append(Text(f"{glyphs['info']} history updated in sandbox/CODECOME-GENERATED.md", style="dim"))
    return border


# ---------------------------------------------------------------------------
# Plain renderers (called when renderer.rich is False)
# ---------------------------------------------------------------------------

def _render_sandbox_plain(
    renderer: ToolRenderer,
    subcommand: str,
    payload: Any,
    command: str,
    description: str,
    status: str,
) -> bool:
    import _colors as C

    sink = renderer.context.sink
    glyphs = _sandbox_glyphs(sink)
    sink.write_text(C.header(f"{glyphs['box']} Sandbox \u00b7 {subcommand}"))
    sink.write_text(f"  $ {command}")
    if description:
        sink.write_text(f"  # {description}")

    try:
        if subcommand == "list":
            _render_sandbox_list_plain(payload, glyphs, sink)
        elif subcommand == "inspect":
            _render_sandbox_inspect_plain(payload, glyphs, sink, renderer)
        elif subcommand == "detect":
            _render_sandbox_detect_plain(payload, glyphs, sink, renderer)
        elif subcommand == "status":
            _render_sandbox_status_plain(payload, glyphs, sink)
        elif subcommand in ("apply", "regenerate"):
            _render_sandbox_apply_plain(payload, subcommand, glyphs, sink, renderer)
        elif subcommand == "validate":
            _render_sandbox_validate_plain(payload, glyphs, sink, renderer)
        else:
            return False
    except (KeyError, TypeError, AttributeError):
        return False
    return True


def _render_sandbox_list_plain(payload: Any, glyphs: dict, sink) -> None:
    if not isinstance(payload, list):
        raise TypeError
    for ex in payload:
        applies = ex.get("applies_when") or {}
        langs = ", ".join(applies.get("languages") or []) or "-"
        sink.write_text(f"  {glyphs['bullet']} {ex.get('id', ''):<20} {ex.get('display_name', '')}  ({langs})")
    sink.write_text(f"  {len(payload)} example(s) available")


def _render_sandbox_inspect_plain(payload: dict, glyphs: dict, sink, renderer: ToolRenderer) -> None:
    sink.write_text(f"  id:    {payload.get('id', '')}")
    sink.write_text(f"  name:  {payload.get('display_name', '')}")
    sink.write_text(f"  path:  {payload.get('path', '')}")
    applies = payload.get("applies_when") or {}
    for k, v in applies.items():
        joined = ", ".join(v) if isinstance(v, list) else str(v)
        sink.write_text(f"  applies_when.{k}: {joined}")
    if payload.get("required_tools"):
        sink.write_text(f"  required_tools: {', '.join(payload['required_tools'])}")
    if payload.get("template_vars"):
        sink.write_text(f"  template_vars:  {', '.join(payload['template_vars'])}")
    if payload.get("default_ports"):
        sink.write_text(f"  default_ports:  {', '.join(str(p) for p in payload['default_ports'])}")
    if payload.get("build_command"):
        sink.write_text(f"  build_command:  {payload['build_command']}")
    if payload.get("test_command"):
        sink.write_text(f"  test_command:   {payload['test_command']}")
    if payload.get("caveats"):
        sink.write_text("  Caveats:")
        for c in payload["caveats"]:
            sink.write_text(f"    {glyphs['warn']} {c}")
    files = payload.get("files") or []
    if files:
        cap = renderer.context.settings.sandbox_files_cap
        sink.write_text(f"  Files ({len(files)}):")
        for f in files[:cap]:
            sink.write_text(f"    {glyphs['bullet']} {f}")
        if len(files) > cap:
            sink.write_text(f"    ... and {len(files) - cap} more")


def _render_sandbox_detect_plain(payload: dict, glyphs: dict, sink, renderer: ToolRenderer) -> None:
    signals = payload.get("signals") or {}
    sink.write_text("  signals:")
    sink.write_text(f"    source:    {signals.get('source', '-')}")
    sink.write_text(f"    languages: {', '.join(signals.get('languages') or []) or '-'}")
    sink.write_text(f"    manifests: {', '.join(signals.get('manifests') or []) or '-'}")
    candidates = payload.get("candidates") or []
    sink.write_text(f"  candidates ({len(candidates)}):")
    cap = renderer.context.settings.sandbox_files_cap
    for c in candidates[:cap]:
        sink.write_text(f"    score={c.get('score', 0):>2}  {c.get('id', ''):<20} {c.get('display_name', '')}")
    if len(candidates) > cap:
        sink.write_text(f"    ... and {len(candidates) - cap} more")


def _render_sandbox_status_plain(payload: dict, glyphs: dict, sink) -> None:
    import _colors as C

    state_value = str(payload.get("sandbox_state", "unknown"))
    last_validation = payload.get("last_validation")
    gate_pass = bool(payload.get("phase2_gate_pass"))
    gate_reason = str(payload.get("phase2_gate_reason", ""))

    sink.write_text(f"  state:           {state_value}")
    sink.write_text(f"  path:            {payload.get('sandbox_path', '-')}")
    sink.write_text(f"  provenance:      {'yes' if payload.get('provenance_present') else 'no'}")
    sink.write_text(f"  last validation: {last_validation if last_validation is not None else '-'}")
    sink.write_text(f"  allow override:  {'yes' if payload.get('allow_no_sandbox') else 'no'}")
    if gate_pass:
        sink.write_text(C.ok(f"  {glyphs['alarm']} Phase 2 gate would PASS \u2014 {gate_reason}"))
    else:
        sink.write_text(C.warn(f"  {glyphs['alarm']} Phase 2 gate would BLOCK \u2014 {gate_reason}"))

    capabilities = payload.get("capabilities") or {}
    if capabilities:
        sink.write_text("  capabilities:")
        for name in (*_SANDBOX_REQUIRED_CAPABILITIES, *_SANDBOX_HELPER_CAPABILITIES):
            cap = capabilities.get(name)
            if cap is None:
                continue
            satisfied = bool(cap.get("satisfied"))
            present = bool(cap.get("present"))
            is_helper = name in _SANDBOX_HELPER_CAPABILITIES
            if satisfied:
                marker = f"{glyphs['ok']} ok"
            elif is_helper and not present:
                marker = f"{glyphs['skip']} optional"
            else:
                marker = f"{glyphs['fail']} missing"
            sink.write_text(f"    {name:<14} {marker:<14} {cap.get('path', '')}")


def _render_sandbox_apply_plain(payload: dict, subcommand: str, glyphs: dict, sink, renderer: ToolRenderer) -> None:
    import _colors as C

    apply_status = str(payload.get("status", ""))
    is_dry = bool(payload.get("dry_run")) or apply_status == "dry-run"
    chip_text = "DRY RUN" if is_dry else apply_status.upper() or "(unknown)"
    sink.write_text(f"  {glyphs['box']} {subcommand} {payload.get('example', '-')}  [{chip_text}]")
    sink.write_text(f"    example_path: {payload.get('example_path', '-')}")
    sink.write_text(f"    sandbox_path: {payload.get('sandbox_path', '-')}")
    sink.write_text(f"    force:        {payload.get('force', False)}")
    if payload.get("backup_dir"):
        sink.write_text(f"    backup_dir:   {payload['backup_dir']}")
    files_to_write = payload.get("files_to_write") or []
    written = payload.get("written_files") or []
    sink.write_text(f"    files: planned={len(files_to_write)} written={len(written)}")
    markers = payload.get("markers_provided") or {}
    if markers:
        sink.write_text(f"    markers_provided ({len(markers)}):")
        for k, v in markers.items():
            sink.write_text(f"      {k} = {v}")
    unfilled = payload.get("markers_used_unfilled") or []
    if unfilled:
        sink.write_text(C.warn(f"    {glyphs['warn']} Declared markers used but not provided: {', '.join(unfilled)}"))
    undeclared = payload.get("markers_used_undeclared") or []
    if undeclared:
        sink.write_text(C.warn(f"    {glyphs['warn']} Markers used but not declared: {', '.join(undeclared)}"))
    show_files = files_to_write or written
    if show_files:
        cap = renderer.context.settings.sandbox_files_cap
        for f in show_files[:cap]:
            sink.write_text(f"    {glyphs['bullet']} {f}")
        if len(show_files) > cap:
            sink.write_text(f"    ... and {len(show_files) - cap} more")
    if apply_status == "applied" and not is_dry:
        sink.write_text(C.ok(f"    {glyphs['ok']} Applied '{payload.get('example', '-')}'"))
        if payload.get("provenance_path"):
            sink.write_text(f"      provenance: {payload['provenance_path']}")


def _render_sandbox_validate_plain(payload: dict, glyphs: dict, sink, renderer: ToolRenderer) -> None:
    import _colors as C

    overall = str(payload.get("overall_outcome", "unknown"))
    overall_glyph = glyphs["ok"] if overall == "passed" else glyphs["fail"] if overall == "failed" else glyphs["warn"]
    sink.write_text(f"  {glyphs['check']} overall: {overall_glyph} {overall}")

    stderr_cap = renderer.context.settings.sandbox_validate_stderr_lines

    tiers = payload.get("tiers") or []
    for t in tiers:
        t_outcome = str(t.get("outcome", "unknown"))
        o_glyph = glyphs["ok"] if t_outcome == "passed" else glyphs["fail"] if t_outcome == "failed" else glyphs["skip"]
        dur = t.get("duration_seconds")
        dur_str = f"{dur:.2f}s" if isinstance(dur, (int, float)) else "-"
        exit_code = t.get("exit_code")
        exit_str = "-" if exit_code is None else str(exit_code)
        sink.write_text(f"    {t.get('tier', ''):<3} {str(t.get('purpose', '')):<20} "
                        f"{o_glyph} {t_outcome:<8} dur={dur_str:<7} exit={exit_str}")
        if t_outcome == "failed":
            stderr_tail = str(t.get("stderr_tail") or "").strip()
            if stderr_tail:
                tail_lines = stderr_tail.splitlines()
                shown = tail_lines[-stderr_cap:]
                for line in shown:
                    sink.write_text(f"      | {line}")
                if len(tail_lines) > stderr_cap:
                    sink.write_text(f"      | ... ({len(tail_lines) - stderr_cap} earlier lines truncated)")
    missing = payload.get("missing_helpers") or []
    if missing:
        sink.write_text(C.warn(f"  {glyphs['warn']} Helper capabilities still missing: {', '.join(missing)}"))
    if payload.get("history_updated"):
        sink.write_text(f"  {glyphs['info']} history updated in sandbox/CODECOME-GENERATED.md")


# ---------------------------------------------------------------------------
# Interceptor class
# ---------------------------------------------------------------------------

class SandboxBootstrapInterceptor:
    """Interceptor that renders sandbox-bootstrap.py --format json output
    as a structured Sandbox panel."""

    name = "sandbox_bootstrap"

    def try_render(
        self,
        command: str,
        state: dict[str, Any],
        renderer: ToolRenderer,
    ) -> bool:
        if not renderer.context.settings.sandbox_render:
            return False

        inp = state.get("input")
        output = state.get("output")
        if not isinstance(inp, dict):
            return False

        subcommand = _is_sandbox_bootstrap_json_call(command)
        if subcommand is None:
            return False

        output_str = str(output) if output is not None else ""
        stripped = output_str.strip()
        if not stripped:
            return False

        # Only proceed when output parses as a single JSON document.
        # make commands often echo the invocation line, so try to find
        # the first JSON-like delimiter if a strict parse fails.
        try:
            payload = json.loads(stripped)
        except (ValueError, TypeError):
            first_brace = stripped.find("{")
            first_bracket = stripped.find("[")
            idxs = [i for i in (first_brace, first_bracket) if i >= 0]
            if not idxs:
                return False
            start_idx = min(idxs)
            try:
                payload = json.loads(stripped[start_idx:])
            except (ValueError, TypeError):
                return False

        if not _sandbox_payload_matches(subcommand, payload):
            return False

        description = str(inp.get("description", "")).strip()
        status = str(state.get("status", ""))

        if renderer.rich:
            return _render_sandbox_rich(
                renderer, subcommand, payload, command, description, status
            )
        return _render_sandbox_plain(
            renderer, subcommand, payload, command, description, status
        )
