# Tools Architecture Guide

This directory contains CodeCome's local tooling: phase runners, rendering, event loops, chat UI, sandbox helpers, and finding/itemdb scripts.

These rules are intended to keep the tooling modular and prevent new monoliths from forming.

## Entry points

Historical executable scripts should stay thin.

- `tools/run-agent.py` is only a compatibility entry point. It should delegate to `codecome.cli.main()` and contain no phase, rendering, event-loop, or chat logic.
- New runner logic belongs under `tools/codecome/`.
- Do not add new implementation logic to wrapper scripts unless the script is intentionally standalone and out of scope for the core runner.

## CodeCome core package

Use concrete modules rather than broad package re-exports.

- CLI parsing and top-level phase flow: `tools/codecome/cli.py`.
- Single-attempt phase execution: `tools/codecome/runner.py`.
- Rendering dispatcher and console construction: `tools/codecome/cli_render.py`.
- Configuration, prompt, model, variant, thinking, and color resolution: `tools/codecome/config.py`.
- OpenCode HTTP session/prompt helpers: `tools/codecome/session.py`.
- Phase completion and resume/repair prompts: `tools/codecome/graceful.py`.
- Transcript helpers: `tools/codecome/transcript.py`.
- Version checks: `tools/codecome/version.py`.

`tools/codecome/__init__.py` must stay lightweight. Internal code should import from the concrete module that owns the functionality.

## Rendering

Rendering code belongs under `tools/rendering/`.

- Runtime rendering state belongs in `RenderContext`.
- Rendering settings belong in `RenderSettings`.
- File snapshot/diff state belongs in `SnapshotCache`.
- Output destinations are represented by sinks (`PlainSink`, `RichConsoleSink`, `TextualRichLogSink`).
- Generic event renderers live in `tools/rendering/events.py`.
- Tool renderers live under `tools/rendering/tools/`.
- Command execution interceptors live under `tools/rendering/tools/interceptors/`.

Renderers should receive the normalized event/tool-state dictionaries emitted by the event layer. Do not introduce a second event object model unless there is a clear need.

Rich and Textual output should share renderer logic where possible. The sink decides where renderables are written; renderers may emit arbitrary Rich renderables when the sink supports them.

## Command rendering

CodeCome-specific command rendering is intentional product behavior.

Special handling for commands such as sandbox bootstrap, `rtk read`, `rtk grep`, `rg`, `ls`, `find`, or `tree` should be implemented as `CommandExecutionInterceptor` classes under `tools/rendering/tools/interceptors/` rather than hidden inside a generic bash renderer.

## Event loops

Event consumption code belongs under `tools/events/`.

- Shared SSE/session/dedup/permission/sync logic belongs in `BaseEventLoop`.
- Phase lifecycle logic belongs in `PhaseEventLoop` (`tools/events/phase_loop.py`).
- Multi-turn chat lifecycle logic belongs in `ChatEventLoop` (`tools/events/chat_loop.py`).
- `events.__init__` should only expose the public phase-loop alias and basic package exports.

Avoid adding phase-specific behavior to `BaseEventLoop` and avoid duplicating session sync or permission logic in phase/chat subclasses.

## Chat

Interactive chat code belongs under `tools/chat/`.

- Textual UI classes and the RichLog proxy live in `tools/chat/app.py`.
- Chat startup/wiring lives in `tools/chat/harness.py`.
- Chat debug helpers live in `tools/chat/debug.py`.

`chat` modules must not import `tools/run-agent.py`. Use `codecome.cli_render`, `codecome.session`, `codecome.config`, and other concrete modules instead.

`tools/chat/__init__.py` must stay lightweight and should not eagerly import Textual-adjacent modules.

## Findings and itemdb

Finding/itemdb consolidation belongs to Epic B.

When that work starts, shared finding helpers should live under `tools/findings/`, and historical scripts such as `create-finding.py`, `move-finding.py`, `list-findings.py`, `render-report.py`, and `render-index.py` should become thin wrappers.

## Testing expectations

Refactors in this directory should include focused tests for the moved component, not only broad smoke checks.

Useful test categories:

- CLI/wrapper smoke tests.
- Rendering unit tests and fixture/golden-style checks.
- Event-loop tests with fake SSE streams.
- Chat tests that import `chat.app` and `chat.harness` directly.
- Command interceptor tests.
- Snapshot/cache tests.

Do not rely on tests that patch a stale wrapper module when the implementation has moved to a concrete package module.
