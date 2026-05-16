# Migration Plan: run-agent.py from subprocess to opencode serve HTTP+SSE

**Status:** ✅ Implemented
**Tests:** 29 new unit + E2E tests written in `tests/test_new_serve_stack.py` (all passing)
**Total test suite:** 216 passed, 4 skipped, 0 failed  
**Date:** 2026-05-16  
**Target:** `tools/run-agent.py`  
**Minimum OpenCode Version:** 1.14.50  
**Risk Level:** Medium (large refactor, affects all phase targets)  

---

## 1. Executive Summary

Replace the current architecture where `run-agent.py` spawns `opencode run --format json` as a subprocess and parses ND-JSON from stdout, with a direct HTTP+SSE integration against a locally-managed `opencode serve` instance.

For each `make phase-X` invocation, `run-agent.py` will:

1. Start a dedicated `opencode serve` process on an ephemeral port
2. Create a session via `POST /session`
3. Send the phase prompt via `POST /session/{id}/prompt_async`
4. Consume real-time events from `GET /event` (Server-Sent Events)
5. Map SSE events to the existing ND-JSON format consumed by `render_event()`
6. Terminate the server on exit (leaving the session in the opencode DB)

---

## 2. Motivation

| Aspect | Current (`opencode run`) | New (`opencode serve`) |
|---|---|---|
| Coupling | Spawns CLI subprocess, relies on stdout format stability | Uses official HTTP API with OpenAPI spec |
| Real-time delivery | Buffered stdout pipe | Native SSE stream |
| Multi-client support | Single process only | Server can serve other clients (IDE, web UI) |
| Tool permissions | Interactive/non-interactive baked into CLI behavior | Explicit API control |
| Model resolution | Requires probe sessions via `opencode run` + export | Read from `GET /config` or observe session events |
| Decoupling | Renders `opencode run` the bottleneck for all features | Independent HTTP surface, clearer boundaries |

---

## 3. Research Foundation

This plan is based on a deep source-code analysis of OpenCode v1.14.50, including:

- Extracting and reading the compiled Bun binary strings
- Fetching the official documentation (`https://opencode.ai/docs/server/`, `https://opencode.ai/docs/sdk`)
- Hands-on probing of all REST and SSE endpoints
- Source-code walkthrough of `packages/opencode/src/cli/cmd/run.ts`, `packages/opencode/src/server/routes/instance/httpapi/handlers/event.ts`, and SDK internals
- Identifying the exact mapping between SSE events and the ND-JSON events emitted by `opencode run --format json`

Full research report: `itemdb/notes/opencode-run-internals-report.md`

---

## 4. Target Directory Structure

```
tools/
├── run-agent.py                          # Entry point, orchestration loop
├── opencode/                             # NEW: Server lifecycle management
│   ├── __init__.py
│   └── serve.py                          # ServerRunner (start/stop/health) + convenience CLI
├── events/                               # NEW: SSE consume → map → emit
│   ├── __init__.py                       # EventLoop coordinator
│   ├── sse_client.py                     # SSE HTTP connection, reconnect, heartbeat
│   ├── state_tracker.py                  # Accumulate deltas, track part versions
│   ├── mapper.py                         # SSE → ND-JSON translation
│   └── emitters.py                       # Bridge to existing render_event()
└── _colors.py                            # Existing, unchanged
```

> Rationale: `opencode/` (containing `serve.py`) and `events/` are internal support modules, not callable CLI tools. Placing them in packages keeps the `tools/` namespace clean.

---

## 5. Execution Flow (Per Phase)

### 5.1 Server Startup

```python
from opencode.serve import ServerRunner

runner = ServerRunner()
server_info = runner.start(
    hostname="127.0.0.1",
    port=0,           # random ephemeral port
    log_level="WARN",
)
# server_info → { proc, base_url, pid, port }
```

`ServerRunner.start()` will:

1. Spawn `opencode serve --port 0 --hostname 127.0.0.1 --log-level WARN`
2. Capture stdout to discover the assigned port (e.g., `listening on http://127.0.0.1:49152`)
3. Poll `GET /global/health` until `{healthy: true}` is returned
4. Return a `ServerInfo` dataclass

If startup fails, print error details and exit non-zero. **No auto-retry.**

### 5.2 Session Creation

```python
import requests

resp = requests.post(f"{server_info.base_url}/session", json={
    "title": f"CodeCome Phase {args.phase}"
})
session = resp.json()
session_id = session["id"]
```

### 5.3 Configure Session

If `args.agent` or resolved model are explicitly pinned, set them on the session:

```python
requests.patch(f"{server_info.base_url}/session/{session_id}", json={
    "agent": args.agent,
    "model": resolved_model,   # e.g. {"providerID": "github-copilot", "modelID": "gpt-5.4"}
})
```

> Note: `POST /session` body does not accept `agent` or `model` directly; these are set via `PATCH /session/{id}`.

### 5.4 Send Prompt

```python
prompt_text = load_prompt(prompt_file, args.finding, phase=args.phase)

requests.post(
    f"{server_info.base_url}/session/{session_id}/prompt_async",
    json={
        "parts": [{"type": "text", "text": prompt_text}],
    }
)
```

The `prompt_async` endpoint returns immediately (204 No Content). The model will process the prompt asynchronously and emit events on the global SSE stream.

### 5.5 Consume SSE Events

```python
from events import EventLoop

event_loop = EventLoop(
    base_url=server_info.base_url,
    session_id=session_id,
    console=console,
    phase=args.phase,
    label=args.label,
)

result = event_loop.run()  # blocks until session idle or terminal error
# result → { finish_reason, step_finish_count, last_finish_tokens, ... }
```

`EventLoop` internals:

1. Open `GET /event` with `Accept: text/event-stream`
2. Parse SSE `data:` lines → JSON objects
3. Filter events by `session_id`
4. Distribute to `StateTracker` for accumulation
5. When `StateTracker` detects a finalized part, call `Mapper` → emit ND-JSON
6. `Emitters` forwards to existing `render_event(console, phase, label, ndjson_event)`

### 5.6 Termination & Cleanup

```python
runner.stop()
```

`ServerRunner.stop()` will:

1. Send `SIGTERM` to the serve process
2. Wait up to 5 seconds for graceful exit
3. Send `SIGKILL` if still alive
4. **Does not delete the session** — left in the opencode DB for inspection

---

## 6. SSE → ND-JSON Mapping (Critical Compatibility Layer)

All existing rendering code (~4,000 lines in `run-agent.py`) expects these exact ND-JSON shapes. The Mapper module must produce identical output.

| SSE Event from `GET /event` | Condition | Mapped ND-JSON Event |
|---|---|---|
| `message.part.updated` | `part.type == "step-start"` | `{"type": "step_start", "part": part}` |
| `message.part.updated` | `part.type == "text"` and `part.time.end` exists | `{"type": "text", "part": part}` |
| `message.part.updated` | `part.type == "reasoning"` and `part.time.end` exists | `{"type": "reasoning", "part": part}` |
| `message.part.updated` | `part.type == "tool"` | `{"type": "tool_use", "part": part}` |
| `message.part.updated` | `part.type == "step-finish"` | `{"type": "step_finish", "part": part}` |
| `session.error` | `properties.sessionID == ours` | `{"type": "error", "error": err}` |

### Text Accumulation Pattern

The server sends `message.part.delta` events with tiny text fragments:

```json
{"type":"message.part.delta","properties":{"sessionID":"...","partID":"...","field":"text","delta":"Hello"}}
```

`StateTracker` accumulates these by `partID`. When the corresponding `message.part.updated` arrives with `time.end`, the accumulated text is injected into `part.text` before mapping.

> **TODO (Future):** Factor out `StateTracker` text accumulation so we can stream text fragments in real-time without waiting for `time.end`.

---

## 7. Tool Permissions

**Behavior:** Auto-reject all permission requests, with a visible warning to the user (same as current `opencode run` non-interactive behavior).

```python
if event_type == "permission.asked" and session_id == ours:
    perm_id = event["properties"]["id"]
    requests.post(
        f"{base_url}/permission/{perm_id}/reply",
        json={"reply": "reject"}
    )
    render_permission_error_plain(error_message)
```

The `permission.asked` event appears on the SSE stream when the model requests permission to run a tool. We must respond via `POST /permission/{requestID}/reply` to unblock the session.

---

## 8. Termination Controls & Auto-Resume

The existing termination logic in `run-agent.py` (lines ~4686–4864) must be preserved exactly:

1. **Finish reason classification**
   - `stop` → OK
   - `tool-calls` → incomplete (mid-turn cutoff)
   - `error`, `length`, `max_tokens` → failure

2. **Graceful completion check** — `check_phase_graceful_completion()`
   - If the model stopped mid-turn but the required artifacts were already written, treat the phase as complete and exit 0.

3. **Auto-resume logic**
   - If finish reason is `tool-calls` (iteration limit hit), build a resume prompt and send a new `prompt_async` to the same session.
   - Budget: `CODECOME_MAX_ITERATION_RETRIES` env var (default 1).

4. **Frontmatter validation auto-correction**
   - After `session.status` → `idle`, run `tools/check-frontmatter.py`.
   - If it fails, send a repair prompt via `prompt_async` (max 2 retries).

5. **Step finish tracking**
   - Count `step_finish` events to report in resume prompts.
   - Track `last_finish_reason`, `last_finish_tokens`.

`EventLoop.run()` will return a `RunResult` object containing all signals needed by the existing termination logic.

---

## 9. Resilience & Reconnect

1. **Auto-reconnect**: If the SSE connection drops, reconnect to `/event` with exponential backoff (3s → 30s max).
2. **Heartbeat monitoring**: If no `server.heartbeat` for >15s, treat as dead and reconnect.
3. **Missed events**: The server sets `id: undefined` on all SSE events, so `Last-Event-ID` replay **does not work**. On reconnect:
   - Poll `GET /session/{session_id}/message` to get the full current message list.
   - Compare with our `StateTracker`.
   - Emit synthetic ND-JSON events for any finalized parts we missed.
4. **Server crash**: If `opencode serve` exits unexpectedly, print error and exit non-zero.

---

## 10. `make show-model` Migration

Currently, `show_model_table()` builds a dry-run command to probe the effective model. With the serve API:

1. Start a **transient** `opencode serve` on a random port.
2. Query `GET /config` and `GET /provider` for defaults.
3. Apply existing precedence logic (OPENCODE_ARGS → env `CODECOME_MODEL` → `codecome.yml` → unknown).
4. Print the resolution table.
5. Stop the transient server.

**Overhead:** ~2-3 seconds (acceptable for a diagnostic command).  
**Benefit:** Removes the need for probe sessions; keeps resolution consistent with the actual runtime path.

---

## 11. Files to Create / Modify

### New Files

| File | Lines (est.) | Description |
|---|---|---|
| `tools/opencode/__init__.py` | 5 | Package init |
| `tools/opencode/serve.py` | 200 | `ServerRunner` class: start/stop server, port discovery, health check, convenience CLI |
| `tools/events/__init__.py` | 50 | Package init, `EventLoop` coordinator class |
| `tools/events/sse_client.py` | 200 | HTTP SSE consumer: connection, parse, reconnect logic, heartbeat monitoring |
| `tools/events/state_tracker.py` | 250 | Accumulate `message.part.delta` fragments, track part versions, detect finalized parts |
| `tools/events/mapper.py` | 200 | Translate SSE events into ND-JSON compatible with existing `render_event()` |
| `tools/events/emitters.py` | 50 | Thin wrapper: calls existing `render_event(console, phase, label, event)` |

### Modified Files

| File | Lines Changed (est.) | Description |
|---|---|---|
| `tools/run-agent.py` | -500 (net reduction) | Replace `subprocess.Popen` loop with `ServerRunner` + `EventLoop`. Keep all `render_*()` functions. |
| `tests/test_run_agent.py` | +400 new/modified | Replace `FakePopen` fixtures with `FakeServer` + `FakeSSE`. Add mapper/state unit tests. |

### No Changes Required

| File | Why |
|---|---|
| `Makefile` | `make phase-X` commands stay identical from user perspective |
| `AGENTS.md` | No behavioral changes to agent contracts |
| `codecome.yml` | No config changes needed |
| `_colors.py` | Unchanged |

---

## 12. Convenience CLI

`tools/opencode/serve.py` will include a development CLI:

```bash
# Start a server manually for debugging
python tools/opencode/serve.py start --port 8080 --log-level DEBUG

# Stop a running server by PID
python tools/opencode/serve.py stop --pid 12345
```

Implemented via `if __name__ == "__main__": argparse` at the bottom of the file.

---

## 13. Backward Compatibility

| Surface | Impact |
|---|---|
| `make phase-X` | No changes. All existing env vars (`CODECOME_MODEL`, `CODECOME_THINKING`, `PROMPT_EXTRA`, etc.) respected. |
| `make show-model` | Uses transient server instead of probe sessions. Output format identical. |
| `CODECOME_USE_WRAPPER=0` | Deprecated. There is no `opencode run` fallback anymore. Warn and exit. |
| Environment variables | All `CODECOME_*` env vars continue to work as before. |
| Rendering output | Visually identical. Same panels, colors, icons, truncation, diffs. |
| Transcripts | Still written to `tmp/last-phase-{N}-{finding}-attempt-{M}.jsonl` |

**Minimum OpenCode version bump:** from `1.14.39` to `1.14.50` (required for stable SSE API surface).

---

## 14. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SSE mapping drifts from opencode source on upgrade | Medium | High | Research is documented in `itemdb/notes/opencode-run-internals-report.md`; re-sync on opencode upgrades. Pin max version in `check_opencode_version()`. |
| Server startup overhead per phase | Low | Low | ~1-2s per phase; acceptable for research workflow. |
| Localhost network issues (SSE drop) | Low | Medium | Reconnect logic + state polling fallback. |
| opencode serve API changes in future releases | Medium | High | Version gate in `check_opencode_version()`. |
| Tool permission auto-reject breaks some agent workflows | Low | High | Same as current behavior; no regression. Can be made configurable later. |
| StateTracker misses deltas due to reconnect gap | Low | Medium | Poll `GET /session/{id}/message` on reconnect to fill gaps. |

---

## 15. Testing Strategy

1. **Unit tests** (new):
   - `test_mapper.py` — verify each SSE event type maps to correct ND-JSON
   - `test_state_tracker.py` — verify delta accumulation, finalization detection
   - `test_sse_client.py` — verify reconnect, heartbeat, error handling
   - `test_server_runner.py` — verify port parsing, health check, stop logic

2. **Integration tests** (modify existing):
   - Replace `FakePopen` with `FakeServer` that yields SSE events
   - Verify `EventLoop.run()` produces identical output transcript
   - Verify auto-resume still works with new architecture
   - Verify frontmatter auto-correction still works

3. **End-to-end smoke test**:
   - Run `make show-model` with a real model configured
   - Run a minimal `make phase-1` with a small prompt
   - Verify panels render correctly (text, tool_use, step_start, step_finish)
   - Verify transcript file matches expected ND-JSON format

4. **Regression test**:
   - Compare output of old `CODECOME_USE_WRAPPER=0 make phase-X` vs new implementation on same prompt
   - Verify byte-identical rendering (modulo timestamps)

---

## 16. Implementation Order

1. Create `tools/opencode/` package with `serve.py`
2. Create `tools/events/` package with `sse_client.py`, `state_tracker.py`, `mapper.py`, `emitters.py`
3. Refactor `tools/run-agent.py` — replace subprocess loop with orchestration
4. Update `tests/test_run_agent.py` — new fixtures for server/SSE mocks
5. Run `make tests` → fix failures
6. Smoke test with real model prompt
7. Update `AGENTS.md` if any behavioral changes observed

---

## 17. Decision Log

| Question | Decision | Rationale |
|---|---|---|
| Module layout | `tools/opencode/serve.py` + `tools/events/` | Keeps `tools/` namespace clean; clearly identifies support modules |
| `make show-model` approach | Transient server | Most reliable; removes probe sessions; consistent with runtime |
| Auto-retry on server startup | No | User asked to show error and finish |
| Delete session on cleanup | No | Leave in opencode DB for inspection |
| Text streaming | Accumulate, finalize on `time.end` | Matches current behavior; TODO for future real-time streaming |
| Permission handling | Auto-reject with visible warning | Same as current `opencode run` non-interactive mode |
| Convenience CLI | Yes, in `serve.py` | Development/debugging aid |
| Minimum version bump | 1.14.39 → 1.14.50 | Required for stable SSE API |

---

*Plan written: 2026-05-16*  
*Approved by: pruiz*  
*Next step: Begin implementation (Phase 1: `tools/opencode/serve.py`)*
