# Plan: Styled `opencode run` Output Wrapper

## Goal

Make `make phase-*` output feel consistent end-to-end by replacing the default `opencode run` renderer with a CodeCome-owned, structured, colored, live-rendered output stream. The CodeCome banner before and after the run is not enough; the agent stream itself must be re-rendered.

## Decisions (locked)

- **Rendering fidelity**: structured. Distinct visual blocks for assistant text, tool calls, and tool results.
- **Markdown handling**: render with `rich` for assistant text and code blocks.
- **Dependency policy**: `rich` is an accepted dependency for CodeCome CLI presentation.
- **Tool I/O policy**: show full contents by default. No automatic truncation. A future toggle may add truncation, but v1 prints everything.
- **Thinking blocks**: off by default. Enable via `CODECOME_THINKING=1`.
- **Buffered stream tradeoff**: if `opencode run --format json` turns out to be buffered, accept the tradeoff and document it. The wrapper still re-renders, just not "live" in the strict sense.
- **Scope**: strictly `make phase-*` for v1. No general-purpose launcher.

## Problem

Today, colored/icon output only appears in CodeCome-owned tools such as:

- `tools/gate-check.py`
- `tools/codecome.py`
- `tools/list-findings.py`
- `tools/render-report.py`

Once `Makefile` invokes `opencode run`, stdout is controlled by OpenCode's default renderer. The visual experience drops to whatever OpenCode chooses, which is inconsistent with CodeCome's own framing.

Constraints observed in `opencode run --help`:

- `--format default|json` is available
- `--thinking` and `--print-logs` are available
- there is no `--color`, `--ansi`, or theme flag

Conclusion:

- `make` is not the rendering boundary
- `opencode run` is the rendering boundary
- to control the visual experience, CodeCome must consume `--format json` and re-render

## Recommended approach

Implement `tools/run-agent.py` as a structured, colorized, `rich`-based wrapper. Route all `make phase-*` targets through it.

Wrapper responsibilities:

- print a colored phase header
- invoke `opencode run --format json` with the chosen agent
- pass the prompt via stdin
- consume the JSON event stream
- render structured visual blocks for:
  - session/context start
  - assistant messages (markdown rendered via `rich`)
  - tool calls
  - tool results (full content, no truncation)
  - warnings/errors
- print a colored completion footer
- preserve the child exit code
- forward signals correctly

## Hard requirements (non-negotiable)

1. **Phase 0 spike** against real `opencode run --format json` output. Capture samples for at least:
   - a trivial prompt
   - a phase-1-style prompt
   - a phase-4-style prompt that invokes tools
   - a deliberately failing prompt
   Commit captured samples under `.project/spikes/opencode-json/` for reference.
2. **Schema tolerance**: unknown event types degrade to a single visible line. Never silently drop.
3. **Minimum OpenCode version**: target the version observed during the spike. Document it in the wrapper module docstring and in `README.md`.
4. **Escape hatch**: `CODECOME_USE_WRAPPER=0` makes `make phase-*` invoke `opencode run` directly, bypassing the wrapper. Required so the user is never locked out by wrapper bugs.
5. **Color control**:
   - `NO_COLOR` honored
   - `CLICOLOR_FORCE` honored
   - `--color=auto|always|never` flag exposed
   - default behavior: `auto` (TTY detection)
6. **Prompt input**: prompt content passed via stdin to `opencode run`, not as a positional argv argument. Placeholder substitution uses literal string replacement only, never regex.
7. **Signal handling**:
   - SIGINT and SIGTERM forwarded to the child
   - child exit code surfaced unchanged
   - signal exits translated to `128 + signum`
   - wrapper internal exceptions exit non-zero with a styled error block
8. **Stderr policy**:
   - child stderr passes through to the wrapper's stderr unchanged
   - wrapper does not merge stderr into stdout
   - wrapper does not style stderr
9. **Native flag passthrough**: a documented mechanism to pass extra flags to `opencode run`. Two acceptable shapes:
   - trailing `--` args on the wrapper CLI
   - `OPENCODE_ARGS` env var consumed by the wrapper
   Pick one in the spike phase. Document it clearly.
10. **Tool output policy**: full content by default. Future env override `CODECOME_TOOL_OUTPUT_LIMIT` may be introduced later but is not part of v1.
11. **Debug mode**: `--debug` mirrors raw JSON events to stderr while continuing to render styled stdout. Required for diagnosing schema drift.
12. **Validation plan** must include all of:
    - successful phase
    - failing phase
    - SIGINT mid-run
    - output piped to `tee` and to a file
    - no-TTY environment (CI-like)
    - `NO_COLOR=1`
    - `CLICOLOR_FORCE=1`
    - non-UTF-8 locale (`LANG=C`)
    - phase-4 invocation that exercises sandbox tool calls
    - large tool output (full content rendering must remain readable)
    - `CODECOME_USE_WRAPPER=0` bypass

## Scope of changes

New:

- `tools/run-agent.py`
- `.project/spikes/opencode-json/` (sample event captures)
- `requirements.txt` updated with `rich`

Updated:

- `Makefile` (route phase targets through wrapper, support escape hatch)
- `README.md` (wrapper section, dependency note, escape hatch)
- `docs/workflow.md` (mention wrapper, env vars)
- `prompts/README.md` (note that manual `opencode run` is unchanged)
- `AGENTS.md` (only the orchestration model section, if it references command shapes)
- `Makefile` `help` target text

Out of scope for v1:

- general-purpose run launcher
- truncated tool output
- markdown re-rendering for non-assistant text
- log file persistence
- session continuation flags from the wrapper

## Design

### CLI shape

```
./tools/run-agent.py \
  --phase 1 \
  --label "Target Reconnaissance" \
  --agent recon \
  --prompt-file prompts/phase-1-recon.md \
  [--finding CC-0001] \
  [--color auto|always|never] \
  [--debug] \
  [-- <extra opencode run flags>]
```

Required flags:

- `--phase`
- `--label`
- `--agent`
- `--prompt-file`

Optional flags:

- `--finding`
- `--color`
- `--debug`
- trailing `--` args forwarded to `opencode run`

Environment variables consumed:

- `CODECOME_USE_WRAPPER` (0 disables wrapper at the Makefile layer)
- `CODECOME_THINKING` (1 enables `--thinking` on the child)
- `OPENCODE_ARGS` (optional alternate forwarding mechanism, decided in spike)
- `NO_COLOR`, `CLICOLOR_FORCE` (standard color controls)

### Prompt handling

- Read the prompt file from disk.
- If `--finding` is provided:
  - perform a single literal replacement of `FINDING_PATH_OR_ID` with the finding identifier
  - error out if the placeholder is missing but `--finding` was provided
  - do not error if the placeholder is absent and `--finding` is also absent
- Pipe the resulting prompt to `opencode run` via stdin, using `--` to separate flags from positional message arguments per `opencode run` conventions. The exact invocation shape is finalized after the spike.

### Event rendering

Rendering uses `rich` for:

- bold colored phase banner
- assistant message panels with markdown rendering
- tool call panels showing tool name, arguments, and a distinct visual style
- tool result panels with full content, monospace where appropriate
- error panels in red
- a final success/failure footer

Event categories the wrapper must understand from the JSON stream (final list confirmed during the spike):

- session start / context
- assistant text deltas or chunks
- tool call begin
- tool call result
- error / warning
- run completion

For unknown event types: render a single dim line with the event type name and skip the body. This satisfies schema tolerance.

### Signal and exit semantics

- The wrapper installs SIGINT and SIGTERM handlers that forward to the child process group.
- On normal child exit, wrapper exits with the child's exit code.
- On signal exit, wrapper exits with `128 + signum`.
- On JSON parse error, wrapper logs to stderr (only when `--debug`) and continues.
- On wrapper internal failure unrelated to the child, wrapper exits non-zero with a styled error.
- Ctrl-C during a long phase must produce a clean styled "interrupted" footer.

### Stderr handling

- Wrapper does not capture child stderr.
- Child stderr inherits the wrapper's stderr file descriptor.
- This avoids interleaving issues, preserves OpenCode's own error formatting, and respects the "do not style stderr" rule.

### Color handling

- Wrapper computes its own color decision once at startup using:
  1. `--color` flag if provided
  2. `CLICOLOR_FORCE` if set
  3. `NO_COLOR` if set
  4. `sys.stdout.isatty()` otherwise
- `rich` is configured accordingly (`force_terminal=True/False/None`).
- `tools/_colors.py` is reused for non-`rich` text where appropriate (banner, footer, simple status lines).

### Working directory

- Wrapper always invokes `opencode run` from the repository root.
- Wrapper does not pass `--dir` unless explicitly forwarded via the passthrough channel.
- This matches the current `Makefile` behavior and avoids subtle path drift.

## Makefile integration

Each `make phase-*` target uses a single integration pattern. Pseudocode shape:

```
phase-1:
	@./tools/gate-check.py 1
	@if [ "$$CODECOME_USE_WRAPPER" = "0" ]; then \
		opencode run --agent recon "$$(cat prompts/phase-1-recon.md)"; \
	else \
		./tools/run-agent.py --phase 1 --label "Target Reconnaissance" \
			--agent recon --prompt-file prompts/phase-1-recon.md; \
	fi
```

Finding-based phases (4 and 5) extend the same pattern with `--finding $(FINDING)`.

`make help` updated to mention the wrapper and the `CODECOME_USE_WRAPPER` escape hatch.

## Reuse of existing code

- `tools/_colors.py`: header, footer, simple bullet lines, status colors. Authoritative for non-`rich` styling.
- `rich`: assistant text rendering, tool panels, code blocks.
- The wrapper must not duplicate color logic that already lives in `_colors.py`.

## Risks (revised)

### Risk 1: JSON event stream is buffered, not streamed

Probability: medium.
Impact: live rendering becomes pseudo-live.
Mitigation: accepted by decision. Document honestly in the wrapper module docstring and in `README.md`. If the spike shows true line-buffered streaming, the wording is upgraded to "live".

### Risk 2: Schema drift across OpenCode versions

Probability: medium.
Impact: wrapper renders less detail or hits unknown event types.
Mitigation: schema-tolerant fallback, `--debug` flag, documented minimum version, escape hatch.

### Risk 3: Loss of visual richness compared to native renderer

Probability: medium.
Impact: users may prefer the native experience.
Mitigation: `rich`-based structured rendering, full tool output, escape hatch via `CODECOME_USE_WRAPPER=0`.

### Risk 4: `rich` dependency footprint

Probability: low.
Impact: heavier install, conflict with future deps.
Mitigation: `rich` is widely used and stable. Pinned in `requirements.txt`.

### Risk 5: Large tool output making sessions hard to read

Probability: medium.
Impact: full-content policy can produce wall-of-text screens.
Mitigation: accepted by decision. Add `CODECOME_TOOL_OUTPUT_LIMIT` only if it becomes a real problem.

### Risk 6: Wrapper bugs locking the user out of the workflow

Probability: low.
Impact: high.
Mitigation: `CODECOME_USE_WRAPPER=0` escape hatch wired into every phase target.

### Risk 7: Signal handling edge cases

Probability: medium.
Impact: zombie processes, hung make targets.
Mitigation: explicit SIGINT/SIGTERM forwarding, child process group handling, validated by SIGINT test.

### Risk 8: Locale and Unicode rendering issues

Probability: low.
Impact: broken glyphs in CI or constrained terminals.
Mitigation: `_colors.py` already falls back to ASCII when colors are disabled. `rich` handles locale gracefully. Validation plan covers `LANG=C`.

## Validation plan

Required tests before declaring v1 done:

1. Successful `make phase-1` produces:
   - colored banner
   - structured assistant rendering
   - colored success footer
   - exit code 0
2. `make phase-4 FINDING=...` invokes sandbox tools and renders tool calls/results as distinct panels with full content.
3. A deliberately failing prompt produces a styled failure footer and a non-zero exit code.
4. `Ctrl-C` during a phase produces a styled "interrupted" footer and exit code `130` (SIGINT).
5. `make phase-1 | tee log.txt` produces:
   - readable plain-text log file
   - stable color behavior in the terminal under default `--color=auto`
6. `NO_COLOR=1 make phase-1` produces zero ANSI escape codes.
7. `CLICOLOR_FORCE=1 make phase-1 | cat` still produces colored output.
8. `LANG=C make phase-1` does not crash; degrades glyphs gracefully.
9. `CODECOME_THINKING=1 make phase-1` shows thinking blocks via `--thinking`.
10. `CODECOME_USE_WRAPPER=0 make phase-1` invokes native `opencode run` directly.
11. `--debug` mirrors raw JSON to stderr while keeping stdout styled.
12. A phase that produces large tool output (full content) renders without truncation and without breaking layout.

## Rollout plan

### Step 0: spike

- Capture `opencode run --format json` output for representative prompts.
- Commit samples under `.project/spikes/opencode-json/`.
- Decide passthrough mechanism (`--` vs `OPENCODE_ARGS`) based on what works cleanly in shell quoting.
- Lock minimum supported OpenCode version.

### Step 1: implement wrapper

- New `tools/run-agent.py`.
- Add `rich` to `requirements.txt`.
- Implement structured rendering, signal handling, color control, debug mode.

### Step 2: wire `phase-1` and `phase-6`

- Update those two `make` targets only.
- Validate end-to-end on real runs.

### Step 3: wire remaining phases

- Update `phase-2` through `phase-5`.
- Verify finding-based prompt substitution.

### Step 4: documentation

- Update `README.md`, `docs/workflow.md`, `prompts/README.md`, `Makefile help`.
- Document env vars, escape hatch, tradeoffs, and minimum OpenCode version.

### Step 5: full validation

- Run all 12 validation cases listed above.
- Capture results in a short note under `.project/`.

## Open items deferred to v2

- Truncated tool output and `CODECOME_TOOL_OUTPUT_LIMIT`.
- General-purpose `tools/run-agent.py` usage outside `make phase-*`.
- Session continuation (`--continue`, `--session`) integration.
- Log file persistence (`--log-file`), gated behind opt-in due to sensitive content concerns.
- Provider/model selection from the wrapper CLI.

## Recommendation

Proceed with the wrapper, gated on a real Phase 0 spike. The spike output drives the final shape of:

- prompt passing
- event-to-panel mapping
- passthrough channel choice
- minimum supported OpenCode version

The plan is ready to execute once the spike produces concrete event captures.
