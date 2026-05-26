# Copyright (C) 2025-2026 Pablo Ruiz García <pablo.ruiz@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later OR AGPL-3.0-or-later

"""
CodeCome configuration resolution: env, codecome.yml, prompt, model, variant, thinking,
color/output mode, and render settings.

This module is intentionally transversal (it reads from many configuration
sources) but must NOT contain execution logic (server start/stop, session
creation, prompt submission, phase loops, retry/resume).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]

import _colors as C  # noqa: E402  — tools/ is on sys.path at runtime

from common.env import truthy_env  # noqa: E402


# ---------------------------------------------------------------------------
# Color / output mode
# ---------------------------------------------------------------------------

def resolve_color_mode(flag: str) -> str:
    if flag != "auto":
        return flag
    if truthy_env("CLICOLOR_FORCE"):
        return "always"
    if os.environ.get("NO_COLOR") is not None or os.environ.get("TERM") == "dumb":
        return "never"
    return "auto"


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

_PHASE_NAMES = {
    "1": "reconnaissance",
    "2": "hypothesis_generation",
    "3": "counter_analysis",
    "4": "validation",
    "5": "exploit_development",
    "6": "reporting",
}


def load_prompt(prompt_file: Path, finding: str | None, phase: str | None = None) -> str:
    prompt = prompt_file.read_text(encoding="utf-8")
    if finding is not None:
        placeholder = "FINDING_PATH_OR_ID"
        if placeholder not in prompt:
            raise ValueError(f"Prompt placeholder {placeholder!r} not found in {prompt_file}")
        prompt = prompt.replace(placeholder, finding)

    extra_sections: list[tuple[str, str]] = []

    # Source 1: codecome.yml  audit.extra_prompts.<phase_name>
    if phase is not None:
        phase_name = _PHASE_NAMES.get(str(phase))
        if phase_name:
            try:
                import yaml  # type: ignore

                config_path = ROOT / "codecome.yml"
                if config_path.exists():
                    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                    ep = cfg.get("audit", {}).get("extra_prompts", {})
                    yml_extra = ep.get(phase_name, "").strip() if isinstance(ep, dict) else ""
                    if yml_extra:
                        extra_sections.append(("From codecome.yml", yml_extra))
            except Exception:
                pass

    # Source 2: PROMPT_EXTRA_FILE env var
    extra_file = os.environ.get("PROMPT_EXTRA_FILE", "").strip()
    if extra_file:
        extra_path = Path(extra_file)
        if not extra_path.is_absolute():
            extra_path = ROOT / extra_path
        if extra_path.is_file():
            file_text = extra_path.read_text(encoding="utf-8").strip()
            if file_text:
                extra_sections.append((f"From {extra_file}", file_text))

    # Source 3: PROMPT_EXTRA env var
    extra_inline = os.environ.get("PROMPT_EXTRA", "").strip()
    if extra_inline:
        extra_sections.append(("Additional instructions", extra_inline))

    if extra_sections:
        prompt += "\n\n## Additional instructions\n"
        for heading, body in extra_sections:
            prompt += f"\n### {heading}\n\n{body}\n"

    return prompt


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------

_MODEL_FLAG_NAMES = ("--model", "-m")
_VARIANT_FLAG_NAMES = ("--variant",)
_MODEL_BEARING_KEYS = ("modelID", "providerID", "model")
_DISCOVERY_TIMEOUT_S = float(os.environ.get("CODECOME_MODEL_DISCOVERY_TIMEOUT", "1.0"))
_MODEL_PROBE_TIMEOUT_S = float(os.environ.get("CODECOME_MODEL_PROBE_TIMEOUT", "20.0"))


def _extract_flag_value(tokens: list[str], flag_names: tuple[str, ...]) -> Optional[str]:
    for i, tok in enumerate(tokens):
        for flag in flag_names:
            if tok == flag and i + 1 < len(tokens):
                return tokens[i + 1]
            prefix = flag + "="
            if tok.startswith(prefix):
                return tok[len(prefix):]
    return None


def _scan_event_for_model(payload: Any) -> Optional[str]:
    """Recursively walk an event payload looking for a model identity."""
    if isinstance(payload, dict):
        pid = payload.get("providerID")
        model_field = payload.get("model")
        mid = payload.get("modelID") or (model_field if isinstance(model_field, str) else None)
        if isinstance(model_field, dict):
            inner_pid = model_field.get("providerID")
            inner_id = model_field.get("id") or model_field.get("modelID")
            if inner_pid and inner_id:
                return f"{inner_pid}/{inner_id}"
            if inner_id:
                return str(inner_id)
        if pid and mid and isinstance(mid, str):
            return f"{pid}/{mid}"
        if isinstance(mid, str) and mid:
            return mid

        for v in payload.values():
            found = _scan_event_for_model(v)
            if found:
                return found
        return None
    if isinstance(payload, list):
        for item in payload:
            found = _scan_event_for_model(item)
            if found:
                return found
    return None


def _discover_opencode_default_model() -> Optional[str]:
    """Best-effort: return the model used in the most recent opencode session."""
    worktree = str(ROOT)

    queries = [
        (
            "SELECT s.model FROM session s "
            "JOIN project p ON s.project_id = p.id "
            f"WHERE p.worktree = '{worktree}' AND s.model IS NOT NULL "
            "ORDER BY s.time_updated DESC LIMIT 1"
        ),
        (
            "SELECT s.model FROM session s "
            "WHERE s.model IS NOT NULL "
            "ORDER BY s.time_updated DESC LIMIT 1"
        ),
    ]

    for query in queries:
        try:
            result = subprocess.run(
                ["opencode", "db", query, "--format", "tsv"],
                capture_output=True,
                text=True,
                timeout=_DISCOVERY_TIMEOUT_S,
            )
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            return None
        if result.returncode != 0:
            continue

        lines = [ln for ln in (result.stdout or "").splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        raw = lines[-1]
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return raw if raw and raw != "model" else None

        if isinstance(obj, dict):
            mid = obj.get("id") or obj.get("modelID")
            pid = obj.get("providerID")
            if pid and mid:
                return f"{pid}/{mid}"
            if mid:
                return str(mid)

    return None


def _extract_model_from_export(export_text: str) -> Optional[str]:
    try:
        payload = json.loads(export_text)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        found = _scan_event_for_model(payload)
        if found:
            return found
    return None


def _strip_probe_unsafe_flags(command: list[str]) -> list[str]:
    stripped: list[str] = []
    skip_next = False
    value_flags = {"--session", "-s", "--title", "--attach", "--port", "-p"}
    standalone_flags = {"--continue", "-c", "--fork", "--share"}

    for token in command:
        if skip_next:
            skip_next = False
            continue
        name = token.split("=", 1)[0]
        if name in standalone_flags:
            continue
        if name in value_flags:
            if "=" not in token:
                skip_next = True
            continue
        stripped.append(token)

    return stripped


@lru_cache(maxsize=32)
def _probe_effective_model(probe_key: tuple[str, ...]) -> Optional[str]:
    command = list(probe_key)
    session_id: str | None = None
    try:
        result = subprocess.run(
            command + ["Reply with exactly OK."],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=_MODEL_PROBE_TIMEOUT_S,
        )
        if result.returncode != 0:
            return None

        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            return None

        first = json.loads(lines[0])
        if not isinstance(first, dict):
            return None
        session_id = first.get("sessionID")
        if not isinstance(session_id, str) or not session_id:
            return None

        exported = subprocess.run(
            ["opencode", "export", session_id],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=_MODEL_PROBE_TIMEOUT_S,
        )
        if exported.returncode != 0:
            return None
        return _extract_model_from_export(exported.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    finally:
        if session_id:
            try:
                subprocess.run(
                    ["opencode", "session", "delete", session_id],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except (OSError, subprocess.SubprocessError):
                pass


def _read_codecome_yml_agent(agent_name: str) -> tuple[Optional[str], Optional[str]]:
    config_path = ROOT / "codecome.yml"
    if not config_path.exists():
        return None, None
    try:
        import yaml  # type: ignore
    except ImportError:
        return None, None
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return None, None
    if not isinstance(data, dict):
        return None, None
    agents = data.get("agents")
    if not isinstance(agents, dict):
        return None, None
    entry = agents.get(agent_name)
    if not isinstance(entry, dict):
        return None, None
    model = entry.get("model")
    variant = entry.get("variant")
    return (str(model) if model else None, str(variant) if variant else None)


def resolve_model_and_variant(
    agent_name: str,
    opencode_args_tokens: list[str],
    *,
    discover_default: bool = True,
) -> tuple[Optional[str], Optional[str], str, str]:
    model_from_args = _extract_flag_value(opencode_args_tokens, _MODEL_FLAG_NAMES)
    variant_from_args = _extract_flag_value(opencode_args_tokens, _VARIANT_FLAG_NAMES)

    env_model = (os.environ.get("CODECOME_MODEL") or "").strip() or None
    env_variant = (os.environ.get("CODECOME_MODEL_VARIANT") or "").strip() or None

    yaml_model, yaml_variant = _read_codecome_yml_agent(agent_name)

    if model_from_args:
        model, model_source = model_from_args, "OPENCODE_ARGS"
    elif env_model:
        model, model_source = env_model, "env CODECOME_MODEL"
    elif yaml_model:
        model, model_source = yaml_model, "codecome.yml"
    else:
        discovered = _discover_opencode_default_model() if discover_default else None
        if discovered:
            model, model_source = discovered, "opencode session history"
        else:
            model, model_source = None, "(unknown)"

    if variant_from_args:
        variant, variant_source = variant_from_args, "OPENCODE_ARGS"
    elif env_variant:
        variant, variant_source = env_variant, "env CODECOME_MODEL_VARIANT"
    elif yaml_variant:
        variant, variant_source = yaml_variant, "codecome.yml"
    else:
        variant, variant_source = None, "(unknown)"

    return model, variant, model_source, variant_source


def resolve_runtime_model_for_banner(
    args_model: Optional[str],
    args_variant: Optional[str],
    model_source: str,
    variant_source: str,
    probe_command: list[str],
) -> tuple[Optional[str], Optional[str], str, str]:
    """Prefer the actual runtime model over a historical guess.

    Env/YAML/CLI-pinned values remain authoritative.  Falls back to a
    throwaway probe session when the source is historical or unknown.

    Args:
        args_model: Model string from CLI args (e.g. "openai/gpt-5").
        args_variant: Variant string from CLI args.
        model_source: Where ``args_model`` came from (e.g. "OPENCODE_ARGS").
        variant_source: Where ``args_variant`` came from.
        probe_command: The full ``sys.argv``-like token list that will be
            executed for the probe.  Unsafe flags such as ``--session``,
            ``--continue``, ``--title``, ``--port`` are stripped internally
            before the probe is run.

    Returns:
        A 4-tuple of (model, variant, model_source, variant_source).  When a
        probe succeeds the model_source becomes "runtime probe".
    """
    if model_source in {"OPENCODE_ARGS", "env CODECOME_MODEL", "codecome.yml"}:
        return args_model, args_variant, model_source, variant_source

    probe_command_clean = _strip_probe_unsafe_flags(probe_command)
    probed = _probe_effective_model(tuple(probe_command_clean))
    if probed:
        return probed, args_variant, "runtime probe", variant_source

    return args_model, args_variant, model_source, variant_source


# ---------------------------------------------------------------------------
# Thinking mode resolution
# ---------------------------------------------------------------------------

def _thinking_default_for_provider(provider_id: Optional[str]) -> bool:
    if not provider_id:
        return True
    pid = provider_id.lower()
    if pid.startswith("anthropic"):
        return False
    return True


def resolve_thinking_decision(
    model: Optional[str],
    extra_args: list[str],
) -> tuple[bool, str]:
    if "--thinking" in extra_args:
        return True, "user-args"

    raw = os.environ.get("CODECOME_THINKING")
    if raw is not None:
        if raw.strip() in ("0", "false", "False", "no", ""):
            return False, "env"
        return True, "env"

    provider_id = None
    if model and "/" in model:
        provider_id = model.split("/", 1)[0]
    enabled = _thinking_default_for_provider(provider_id)
    return enabled, "provider-default"


# ---------------------------------------------------------------------------
# Unified runtime config resolution
# ---------------------------------------------------------------------------

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    """Resolved runtime configuration shared by phase and chat modes."""
    model: Optional[str]
    variant: Optional[str]
    model_source: str
    variant_source: str
    thinking_on: bool
    thinking_source: str


def resolve_runtime_config(agent: str) -> RuntimeConfig:
    """Resolve model, variant, and thinking from agent + env in one call.

    Both phase and chat paths should call this instead of separately
    calling resolve_model_and_variant + resolve_thinking_decision.
    """
    import shlex

    extra_args = shlex.split(os.environ.get("OPENCODE_ARGS", ""))
    model, variant, model_source, variant_source = resolve_model_and_variant(
        agent, extra_args
    )
    thinking_on, thinking_source = resolve_thinking_decision(model, extra_args)
    return RuntimeConfig(
        model=model,
        variant=variant,
        model_source=model_source,
        variant_source=variant_source,
        thinking_on=thinking_on,
        thinking_source=thinking_source,
    )


# ---------------------------------------------------------------------------
# Model resolution display (--show-model)
# ---------------------------------------------------------------------------

def show_model_table(agent_name: str) -> int:
    """Print the model-resolution table for an agent and exit."""
    import shlex

    extra_args = shlex.split(os.environ.get("OPENCODE_ARGS", ""))

    args_model = _extract_flag_value(extra_args, _MODEL_FLAG_NAMES)
    args_variant = _extract_flag_value(extra_args, _VARIANT_FLAG_NAMES)
    env_model = (os.environ.get("CODECOME_MODEL") or "").strip() or None
    env_variant = (os.environ.get("CODECOME_MODEL_VARIANT") or "").strip() or None
    yaml_model, yaml_variant = _read_codecome_yml_agent(agent_name)
    discovered = _discover_opencode_default_model()

    model, variant, model_source, variant_source = resolve_model_and_variant(
        agent_name, extra_args
    )

    def fmt(v: Optional[str]) -> str:
        return v if v else "(not set)"

    print(C.header(f"Model resolution for agent {agent_name}:"))
    print()
    print(f"  {C.DIM}OPENCODE_ARGS{C.RESET}                 model={fmt(args_model)}  variant={fmt(args_variant)}")
    print(f"  {C.DIM}env CODECOME_MODEL{C.RESET}            model={fmt(env_model)}")
    print(f"  {C.DIM}env CODECOME_MODEL_VARIANT{C.RESET}    variant={fmt(env_variant)}")
    print(f"  {C.DIM}codecome.yml{C.RESET}                  model={fmt(yaml_model)}  variant={fmt(yaml_variant)}")
    print(f"  {C.DIM}opencode session history{C.RESET}      model={fmt(discovered)}")
    print(f"  {C.DIM}runtime probe{C.RESET}                 not run by show-model")
    print()
    effective_model = model or "(unknown)"
    effective_variant = variant or "(unknown)"
    thinking_on, thinking_source = resolve_thinking_decision(model, extra_args)
    print(f"  {C.BOLD}effective{C.RESET}                     "
          f"model={effective_model}  variant={effective_variant}  "
          f"thinking={'on' if thinking_on else 'off'}")
    print(f"  {C.DIM}sources{C.RESET}                       "
          f"model: {model_source}  variant: {variant_source}  "
          f"thinking: {thinking_source}")
    return 0
