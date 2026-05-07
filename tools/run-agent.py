#!/usr/bin/env python3
"""
Structured wrapper around `opencode run --format json` for CodeCome phase targets.

Minimum supported OpenCode version: 1.14.39
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _colors as C

try:
    from rich.console import Console, Group
    from rich.json import JSON
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.text import Text

    HAVE_RICH = True
except ImportError:  # pragma: no cover
    Console = Any  # type: ignore[assignment]
    Group = tuple  # type: ignore[assignment]
    JSON = None  # type: ignore[assignment]
    Markdown = None  # type: ignore[assignment]
    Panel = None  # type: ignore[assignment]
    Rule = None  # type: ignore[assignment]
    Text = None  # type: ignore[assignment]
    HAVE_RICH = False

ROOT = Path(__file__).resolve().parents[1]
MINIMUM_OPENCODE_VERSION = "1.14.39"


def truthy_env(name: str) -> bool:
    value = os.environ.get(name)
    return value is not None and value not in {"", "0", "false", "False", "no", "No"}


def resolve_color_mode(flag: str) -> str:
    if flag != "auto":
        return flag
    if truthy_env("CLICOLOR_FORCE"):
        return "always"
    if os.environ.get("NO_COLOR") is not None or os.environ.get("TERM") == "dumb":
        return "never"
    return "auto"


def build_console(color_mode: str) -> Console:
    if not HAVE_RICH:
        return None  # type: ignore[return-value]
    if color_mode == "always":
        return Console(force_terminal=True, soft_wrap=True, highlight=False)
    if color_mode == "never":
        return Console(force_terminal=False, no_color=True, soft_wrap=True, highlight=False)
    return Console(soft_wrap=True, highlight=False)


def load_prompt(prompt_file: Path, finding: str | None) -> str:
    prompt = prompt_file.read_text(encoding="utf-8")
    if finding is None:
        return prompt

    placeholder = "FINDING_PATH_OR_ID"
    if placeholder not in prompt:
        raise ValueError(f"Prompt placeholder {placeholder!r} not found in {prompt_file}")

    return prompt.replace(placeholder, finding)


def format_tokens(tokens: dict[str, Any]) -> str:
    if not isinstance(tokens, dict):
        return ""

    parts = []
    for key in ("input", "output", "reasoning", "total"):
        value = tokens.get(key)
        if value is not None:
            parts.append(f"{key}={value}")
    return ", ".join(parts)


def render_step_start(console: Console, phase: str, label: str, event: dict[str, Any]) -> None:
    step_type = event.get("part", {}).get("type", "step-start")
    if HAVE_RICH:
        console.print(Text(f"[{phase}] {label}: {step_type}", style="cyan"))
    else:
        print(C.info(f"[{phase}] {label}: {step_type}"))


def render_text(console: Console, event: dict[str, Any]) -> None:
    part = event.get("part", {})
    text = str(part.get("text", "")).strip()
    if not text:
        return
    if HAVE_RICH:
        console.print(Panel(Markdown(text), title="Assistant", border_style="blue", expand=True))
    else:
        print(C.header("Assistant"))
        print(text)


def render_tool_use(console: Console, event: dict[str, Any]) -> None:
    part = event.get("part", {})
    tool = str(part.get("tool", "unknown"))
    state = part.get("state", {}) if isinstance(part.get("state"), dict) else {}
    status = str(state.get("status", "unknown"))
    input_data = state.get("input")
    output_data = state.get("output")

    if HAVE_RICH:
        sections: list[Any] = []
        if input_data is not None:
            sections.append(Text("Input", style="bold cyan"))
            try:
                sections.append(JSON.from_data(input_data))
            except Exception:
                sections.append(Text(str(input_data)))

        if output_data is not None:
            if sections:
                sections.append(Text())
            sections.append(Text("Output", style="bold green"))
            if isinstance(output_data, (dict, list)):
                try:
                    sections.append(JSON.from_data(output_data))
                except Exception:
                    sections.append(Text(str(output_data)))
            else:
                sections.append(Text(str(output_data)))

        body = Group(*sections) if sections else Text("No tool payload", style="dim")
        title = f"Tool: {tool} [{status}]"
        border = "green" if status == "completed" else "yellow"
        console.print(Panel(body, title=title, border_style=border, expand=True))
    else:
        print(C.header(f"Tool: {tool} [{status}]"))
        if input_data is not None:
            print(C.info("Input"))
            print(json.dumps(input_data, indent=2) if isinstance(input_data, (dict, list)) else str(input_data))
        if output_data is not None:
            print(C.info("Output"))
            print(json.dumps(output_data, indent=2) if isinstance(output_data, (dict, list)) else str(output_data))


def render_step_finish(console: Console, event: dict[str, Any]) -> None:
    part = event.get("part", {})
    reason = str(part.get("reason", "unknown"))
    tokens = format_tokens(part.get("tokens", {}))
    suffix = f" ({tokens})" if tokens else ""
    if HAVE_RICH:
        console.print(Text(f"step finished: {reason}{suffix}", style="dim"))
    else:
        print(f"step finished: {reason}{suffix}")


def render_unknown(console: Console, event: dict[str, Any]) -> None:
    message = f"unknown event type: {event.get('type', '<missing>')}"
    if HAVE_RICH:
        console.print(Text(message, style="dim"))
    else:
        print(message)


def render_event(console: Console, phase: str, label: str, event: dict[str, Any]) -> None:
    event_type = event.get("type")
    if event_type == "step_start":
        render_step_start(console, phase, label, event)
    elif event_type == "text":
        render_text(console, event)
    elif event_type == "tool_use":
        render_tool_use(console, event)
    elif event_type == "step_finish":
        render_step_finish(console, event)
    else:
        render_unknown(console, event)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a CodeCome phase with structured output.")
    parser.add_argument("--phase", required=True, help="Phase number.")
    parser.add_argument("--label", required=True, help="Human-readable phase label.")
    parser.add_argument("--agent", required=True, help="OpenCode agent name.")
    parser.add_argument("--prompt-file", required=True, help="Prompt file path relative to repo root.")
    parser.add_argument("--finding", help="Finding id for prompt substitution.")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("--debug", action="store_true", help="Mirror raw JSON events to stderr.")
    return parser


def build_child_command(args: argparse.Namespace) -> list[str]:
    cmd = ["opencode", "run", "--format", "json", "--agent", args.agent]
    if truthy_env("CODECOME_THINKING"):
        cmd.append("--thinking")

    extra_args = shlex.split(os.environ.get("OPENCODE_ARGS", ""))
    cmd.extend(extra_args)
    return cmd


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    color_mode = resolve_color_mode(args.color)
    console = build_console(color_mode)
    prompt_file = ROOT / args.prompt_file
    prompt = load_prompt(prompt_file, args.finding)
    command = build_child_command(args)

    if HAVE_RICH:
        console.print(Rule(title=f"Phase {args.phase}: {args.label}", style="bold cyan"))
        console.print(Text(f"agent={args.agent}  prompt={args.prompt_file}", style="dim"))
        if args.finding:
            console.print(Text(f"finding={args.finding}", style="dim"))
    else:
        print(C.header(f"Phase {args.phase}: {args.label}"))
        print(C.info(f"agent={args.agent}  prompt={args.prompt_file}"))
        if args.finding:
            print(C.info(f"finding={args.finding}"))
        print(C.warn("rich is not installed; using plain structured output fallback"))

    process: subprocess.Popen[str] | None = None
    interrupted = False

    def forward_signal(signum: int, _frame: Any) -> None:
        nonlocal interrupted
        interrupted = True
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass

    previous_sigint = signal.signal(signal.SIGINT, forward_signal)
    previous_sigterm = signal.signal(signal.SIGTERM, forward_signal)

    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid,
        )

        assert process.stdin is not None
        process.stdin.write(prompt)
        process.stdin.close()

        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            if args.debug:
                sys.stderr.write(line + "\n")
                sys.stderr.flush()
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                if args.debug:
                    sys.stderr.write(f"json-parse-error: {line}\n")
                    sys.stderr.flush()
                continue
            render_event(console, args.phase, args.label, event)

        process.wait()
        returncode = process.returncode
    except Exception as exc:
        if HAVE_RICH:
            console.print(Panel(Text(str(exc), style="red"), title="Wrapper Error", border_style="red"))
        else:
            print(C.fail(str(exc)), file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)

    if returncode is None:
        returncode = 1

    if returncode < 0:
        returncode = 128 + abs(returncode)

    if interrupted and returncode == 0:
        returncode = 130

    if returncode == 0:
        if HAVE_RICH:
            console.print(Rule(style="green"))
            console.print(Text(f"{C.SYM_OK} Phase {args.phase} completed successfully", style="green"))
        else:
            print(C.ok(f"Phase {args.phase} completed successfully"))
    elif returncode == 130:
        if HAVE_RICH:
            console.print(Rule(style="yellow"))
            console.print(Text(f"{C.SYM_WARN} Phase {args.phase} interrupted", style="yellow"))
        else:
            print(C.warn(f"Phase {args.phase} interrupted"))
    else:
        if HAVE_RICH:
            console.print(Rule(style="red"))
            console.print(Text(f"{C.SYM_FAIL} Phase {args.phase} failed with exit code {returncode}", style="red"))
        else:
            print(C.fail(f"Phase {args.phase} failed with exit code {returncode}"))

    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
