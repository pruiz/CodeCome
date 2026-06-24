# Resume Resilience: Fast-Fail on Server Death, Exit-Code Logging, and Server Restart Recovery

Date: 2026-06-12
Status: Implemented
Follow-up issue: https://github.com/pruiz/CodeCome/issues/56
Target: `tools/codecome/runner.py`, `tools/opencode/serve.py`, `tools/codecome/phase_1.py`, `tools/codecome/harness.py`

---

## 1. Problem

During a `make phase-1` run (PID 34685, 2026-06-10), Phase 1b failed with a 120-second
`ResumeSessionNotReady` timeout. Investigation of the serve log and transcript files
confirmed the sequence:

1. Phase 1a (`ses_1515e017...`) completed cleanly — session went `idle`.
2. Phase 1b (`ses_1515a691...`) was created, ran sandbox validation (T1–T6 passed),
   and was mid-response when **the opencode server process crashed**.
3. The serve log (`tmp/opencode-serve-34685-1781046310.log`, 69 lines) ends abruptly
   with the Phase 1b session still `busy`. No `idle` transition, no error entry,
   no exit code — the process simply died.
4. The auto-resume retry called `_wait_for_resume_idle()`, which polls
   `get_session_status()` in a loop. Every call threw an HTTP exception
   (server dead), returning `None`. This was recorded as `blocked_unknown`
   (not `blocked_busy`) — 22 consecutive failures over 120 seconds.
5. The retry gave up with `ResumeSessionNotReady`. The user saw "exit code 2"
   with a transcript reference, but **no information about the server crash**.

Three cooperating weaknesses caused this wasteful 120-second failure:

### Weakness 1: `_wait_for_resume_idle` cannot distinguish "server dead" from "session busy"

`tools/codecome/runner.py:71-103` — The function polls `get_session_status()` in a loop
for up to 120s. It does not differentiate between:

| Status | Meaning | Wait makes sense? |
|--------|---------|-------------------|
| `"busy"` | Server alive, session processing | Yes |
| `None` | Server unreachable / dead | **No** — will never resolve |

Both paths get the same treatment: sleep, poll, repeat until timeout. When the server
is dead, the harness burns the full 120s doing nothing useful.

### Weakness 2: Server exit code is never recorded

`tools/opencode/serve.py` — `ServerRunner.start()` spawns opencode as a subprocess
(`start_new_session=True`), redirects stdout/stderr to a log file, but **never monitors
the child process for exit**. When the server crashes, nothing writes the exit code,
signal number, or crash reason to the log. The log just stops, leaving no diagnostic
trail.

### Weakness 3: No server restart between retry attempts

`tools/codecome/phase_1.py:408-598` (`_run_subphase` retry loop) and
`tools/codecome/harness.py:168-346` (`run_phase_mode` retry loop) — Both attempt retries
against the same server process. If the server died during the first attempt, every
retry will hit a dead server. Neither loop checks `runner.info.proc.poll()` or attempts
a server restart.

For Phase 1 (subphases 1a/1b/1c), the server is started once and reused across
all subphases. A server crash during 1b also makes 1c unreachable — the user gets
multiple opaque failures with no indication of the root cause.

---

## 2. Design

### 2.1 Fix 1 — Fast-fail on server unavailability (`runner.py`)

Add a consecutive-`None` counter to `_wait_for_resume_idle`. After N consecutive
`None` returns from `get_session_status()`, raise immediately with a diagnostic
message instead of polling for the full timeout.

```python
# Pseudocode — not to be executed
CONSECUTIVE_NONE_MAX = int(os.environ.get("CODECOME_RESUME_SERVER_UNAVAILABLE_THRESHOLD", "3"))

def _wait_for_resume_idle(...):
    consecutive_none = 0
    while True:
        status = get_session_status(...)
        if status == "idle":
            return

        if status is None:
            consecutive_none += 1
            if consecutive_none >= CONSECUTIVE_NONE_MAX:
                raise ResumeSessionNotReady(
                    f"server at {base_url} appears to be unreachable or dead "
                    f"after {consecutive_none} consecutive failed status checks; "
                    f"session {session_id} cannot be resumed"
                )
        else:
            consecutive_none = 0

        event_type = "codecome.resume.blocked_busy" if status == "busy" else "codecome.resume.blocked_unknown"
        _record_codecome_event(transcript, event_type, ...)

        if time.monotonic() >= deadline:
            raise ResumeSessionNotReady(...)
        time.sleep(max(poll_s, 0.1))
```

The `blocked_unknown` event is still recorded (for transcript traceability), but the
wait cuts short once we have evidence the server is gone. The threshold is env-var
configurable so users can tune for slow/flaky networks.

**Rationale**: This is the minimum-change, highest-impact fix. It turns a guaranteed
120-second waste into a ~15-second fast-failure (3 polls × 5s HTTP timeout). The
existing timeout path (for genuinely `busy` sessions) is untouched.

### 2.2 Fix 2 — Capture server exit code in serve log (`serve.py`)

Add a daemon thread to `ServerRunner` that monitors the child process and appends
an exit record to the serve log when the process terminates.

```python
# Pseudocode — not to be executed
import threading

def _monitor_child(proc: subprocess.Popen, log_path: Path) -> None:
    exit_code = proc.wait()
    with open(log_path, "a") as f:
        if exit_code < 0:
            f.write(f"opencode serve killed by signal {-exit_code} (exit code {exit_code})\n")
        else:
            f.write(f"opencode serve exited with code {exit_code}\n")

# In ServerRunner.start(), after successful health check:
threading.Thread(
    target=_monitor_child, args=(proc, log_path),
    name=f"serve-monitor-{proc.pid}", daemon=True
).start()
```

The thread is daemon=True so it doesn't block process shutdown. It calls `proc.wait()`
which blocks until the child exits, then writes one line. The `ServerInfo` dataclass
already stores `proc` and `log_path`, so no new fields are needed.

**Rationale**: With this, future server crashes will leave a trace like
`opencode serve killed by signal 9 (exit code -9)` (OOM kill) or
`opencode serve exited with code 1` (process error). Without it, all we see is
a log that stops mid-line with no explanation.

### 2.3 Fix 3 — Detect server death and restart in retry loops

Modify `_run_single_attempt` to accept an optional `ServerRunner` reference and
return a distinct finish reason when the server is unreachable (not just when the
session isn't ready). Then modify the calling retry loops to restart the server
and create a fresh session.

**Step 3a — Return distinct reason for server death** (`runner.py`)

Currently, `ResumeSessionNotReady` maps to `resume_not_ready` indiscriminately.
Introduce a new synthetic finish reason `server_unreachable` for the fast-fail
path from Fix 1 (when consecutive `None` threshold is hit). The existing timeout
path (session stays busy for 120s) keeps `resume_not_ready`.

**Step 3b — Server-death propagation from `run_phase_1`** (`phase_1.py`)

`_run_subphase` does NOT restart the server. When it detects `server_unreachable`,
it returns `RunStatus.SERVER_UNREACHABLE`. `run_phase_1()` converts this into a
`Phase1Outcome(status=RunStatus.SERVER_UNREACHABLE, failed_subphase="1a"|"1b"|"1c")`.

`run_phase_1()` does **not** start, stop, or restart `opencode serve`. It only
reports which subphase failed so the harness can restart and re-enter at the
same subphase.

Resume status polling distinguishes two cases.

**Authoritative liveness signal: the child process handle, not HTTP probes.**

A later incident (PID 57813, 2026-06-12, port `:61694`) proved that HTTP probes
are an unreliable death signal. During a long busy turn, opencode 1.17.4's HTTP
control plane — including `/session/status` AND `/global/health` — blocks and
times out while the process is perfectly alive and the session is still `busy`.
Three failed polls (~32s, dominated by 5s socket timeouts) wrongly declared the
server dead; the harness then SIGTERM'd a live, busy server and exhausted the
restart budget.

Fix:

- `_wait_for_resume_idle()` accepts an optional `liveness_check: Callable[[], bool]`.
- Phase callers build it via `make_liveness_check(runner)` in `opencode/serve.py`,
  which consults `ServerInfo.proc.poll()` (the OS child handle).
- When `/session/status` returns `None`:
  - `liveness_check()` is `True` (process alive): record
    `codecome.resume.status_unavailable_process_alive`, do not count toward death,
    keep waiting until the idle timeout (then `resume_not_ready`).
  - `liveness_check()` is `False` (process exited): raise
    `ResumeSessionServerUnreachable` immediately (`processExited=True`).
  - No `liveness_check` provided (e.g. tests, non-phase callers): fall back to the
    `/global/health` probe + `CODECOME_RESUME_SERVER_UNAVAILABLE_THRESHOLD`.
- Resume probe socket timeouts were lowered to `CODECOME_RESUME_PROBE_TIMEOUT`
  (default 2s) so a poll cycle approximates `CODECOME_RESUME_IDLE_POLL` instead of
  ~11s, letting the 120s idle window cover many polls.
- Chat mode is unaffected: it never calls `_run_single_attempt`/`_wait_for_resume_idle`.

**Step 3c — Server restart in `run_phase_mode`** (`harness.py`)

The harness owns the `ServerRunner` for all phases. For Phase 1 it calls
`run_phase_1(..., start_at="1a")`. If the outcome is `SERVER_UNREACHABLE`, the
harness restarts the server with `runner.restart(...)`, then re-enters
`run_phase_1(..., start_at=outcome.failed_subphase)`. This avoids rerunning
completed subphases.

For phases 2-6, the existing harness retry loop also handles `server_unreachable`
with `runner.restart(...)`.

**Rationale**: Without server restart, a crash during any subphase/phase means
the entire run fails irrecoverably. With restart, the harness can self-heal and
give the user a completed phase rather than a cryptic exit code 2.

### 2.4 Design principle: `_run_subphase` never touches the server

`_run_subphase` receives a `runner: ServerRunner` and `base_url: str` from its
caller so it can use the current server password and endpoint. It does **not**
own the server lifecycle. When it detects that the server died
(`server_unreachable`), it returns `RunStatus.SERVER_UNREACHABLE`.

`run_phase_1()` also does not own server lifecycle. It returns a structured
`Phase1Outcome` to the harness. Only the harness calls `runner.restart(...)`.

### 2.5 `ServerRunner.restart()` method

Added to `tools/opencode/serve.py` — a single method that encapsulates the
stop/start sequence, so callers don't duplicate the launch logic:

```python
def restart(self, **kwargs: Any) -> ServerInfo:
    self.stop()
    return self.start(**kwargs)
```

### 2.6 Scope / non-goals

- **Not fixing** why the opencode server crashed — that's an opencode bug
  (likely OOM, segfault, or provider disconnect handling). This plan focuses
  on resilience.
- **Not adding** a general-purpose server health-check heartbeat — the existing
  health URL is sufficient; we just need to use it.
- **Not backporting** to `ServerRunner._kill` or the signal handling — those
  are working correctly for normal shutdown.

---

## 3. Implementation order

| Step | File | Complexity | Description |
|------|------|-----------|-------------|
| Fix 1 — fast-fail | `runner.py:71-103` | Low | Consecutive-`None` counter in `_wait_for_resume_idle` |
| Fix 2 — exit-code logging | `serve.py:126-218` | Low | Daemon monitor thread, `_start_exit_monitor` |
| `restart()` method | `serve.py:239-247` | Low | Single stop/start encapsulation on `ServerRunner` |
| Fix 3a — `server_unreachable` reason | `runner.py:26-28, 215-226` | Low | `ResumeSessionServerUnreachable` subclass + distinct finish reason |
| Fix 3a.1 — health-confirm server death | `session.py`, `runner.py` | Low | Status probe failures only consume restart budget when `/global/health` also fails |
| Status enum | `status.py` | Low | Explicit `RunStatus` values replace magic return code 3 |
| Fix 3 — Phase 1 propagation | `phase_1.py` | Medium | `Phase1Outcome(status, failed_subphase)`; no server lifecycle in phase code |
| Fix 3 — server restart in harness | `harness.py` | Medium | `runner.restart()` called from harness retry loop; Phase 1 re-enters at failed subphase |
| Resume opener for `server_unreachable` | `completion.py:429-475` | Low | Context-specific resume prompt opener |

Recommended order: 1 → 2 → 3a → 3b → 3c.

Fixes 1 and 2 can be done independently. Fix 3a is a prerequisite for 3b/3c.

---

## 4. Testing

### 4.1 Unit tests for Fix 1

- Mock `get_session_status` to return `None` repeatedly → assert
  `ResumeSessionNotReady` raised after `CONSECUTIVE_NONE_MAX` polls.
- Mock to return `"busy"` for 120s → assert timeout path still works.
- Mock to return alternating `None`/`"busy"` → assert counter resets on non-`None`.

### 4.2 Integration test for Fix 3

- Kill the opencode server mid-phase (SIGKILL) → assert harness detects
  `server_unreachable`, restarts server, and retries with a fresh session.

### 4.3 Regression test for Fix 2

- Start server, verify normal exit produces `exited with code 0` in serve log.
- Start server, kill with SIGTERM, verify `killed by signal 15` in serve log.

---

## 5. Open questions

1. For Fix 1, is `CONSECUTIVE_NONE_MAX=3` a reasonable default? Each poll involves
   a 5-second HTTP timeout on the status endpoint, so 3 consecutive failures ≈ 15s
   before fast-failing. Could be 5 for flaky networks.
2. For Fix 3, should the server-restart budget be capped (e.g., 2 restarts)?
   Without a cap, a persistently-crashing server could loop forever.

---

## 6. Fix 4 — Do not abandon a still-busy turn (the real root cause)

Date: 2026-06-15
Status: Implemented
Verified against: opencode v1.17.7 (issue reproduced identically on 1.17.7).

### 6.1 What actually happened

Across PIDs 57813, 73953, and 11183, the failure was **never** a dead server.
The serve logs show the Phase 1b session staying `busy` continuously until the
harness itself SIGTERM'd it. The sequence:

1. A long model turn runs. opencode emits `session.status:{type:"busy"}` on the
   SSE `/event` stream throughout.
2. The first attempt's `PhaseEventLoop` stops **before** the terminal
   `session.status:{type:"idle"}` — the SSE stream dropped and the
   `SseClient` reconnect budget (`max_reconnects=10`) / heartbeat timeout
   exhausted while the turn was still genuinely running.
3. The loop returned a non-terminal `RunResult` with `last_finish_reason="tool-calls"`
   (a `_FINISH_MID_TURN` reason — really just a step boundary), so CodeCome
   misread a still-running turn as a "mid-turn cutoff" and triggered auto-resume.
4. The resume pre-flight (`_wait_for_resume_idle`) then polled the REST
   `GET /session/status` endpoint, which is workspace-`forward`ed and unreliable
   while the target session is in a long busy turn — returning nothing for the
   full 120s → `ResumeSessionNotReady` (exit code 2).

### 6.2 Source confirmation (opencode v1.17.7)

- `packages/opencode/src/server/routes/.../handlers/session.ts`: `status` handler
  returns `Object.fromEntries(statusSvc.list())`.
- `packages/opencode/src/session/status.ts`: on `idle`, the session is
  **deleted** from the status map (`data.delete(sessionID)`); `busy`/`retry` are
  stored. So idle = absent, busy = `{type:"busy"}`.
- `packages/opencode/src/server/shared/workspace-routing.ts`: `/session/status`
  is `action:"forward"`. The REST status call is therefore subject to
  forwarding/blocking under load — which is why our polls returned nothing while
  the SSE stream still reported `busy`.

Conclusion: **the SSE `/event` stream is the authoritative busy/idle source.**
The REST `/session/status` poll in the resume pre-flight is redundant and flaky.

### 6.3 The fix

`SseClient` gains an optional `should_continue: Callable[[], bool]`.
`PhaseEventLoop` supplies `_should_keep_consuming()`, which is True while:

- the last SSE-observed `session.status` for the session is `busy`, AND
- the server process is alive (`liveness_check`, built from
  `ServerInfo.proc.poll()` via `make_liveness_check`).

When `should_continue()` is True, `SseClient` keeps reconnecting past
`max_reconnects` (resetting the counter to keep backoff bounded) instead of
raising `SSE reconnect budget exhausted`. A long model turn is therefore never
abandoned: the loop keeps consuming until it observes the genuine terminal
`idle` (or the process dies / true terminal finish reason).

Consequence: a still-busy turn is no longer misclassified as a mid-turn cutoff,
so the auto-resume + `_wait_for_resume_idle` path fires only on genuine
terminal-but-incomplete states. The flaky REST status poll is no longer on the
hot path for long turns.

Wiring: `liveness_check` is threaded
`harness/phase_1 → _run_single_attempt → _consume_events → PhaseEventLoop →
SseClient.should_continue`. Chat mode is unaffected (it never calls
`_run_single_attempt`/`PhaseEventLoop` with these hooks).

### 6.4 Tests

`tests/test_sse_busy_resilience.py`:
- `SseClient` honors the budget without `should_continue`.
- `SseClient` keeps consuming past the budget while `should_continue` is True,
  and stops when it flips to False (or raises).
- `PhaseEventLoop._should_keep_consuming()` truth table: not-busy → False;
  busy+alive → True; busy+dead → False; busy+no-liveness → True; idle clears
  busy; `session.idle` event clears busy.

---

## 7. Fix 5 — Bounded busy-wait (stall watchdog) + restart/retry

Date: 2026-06-15
Status: Implemented
Verified against: opencode v1.17.7 (live hang reproduced, PID 58436).

### 7.1 What happened

Fix 4 (keep consuming while busy+alive) removed false server kills but
introduced an **unbounded** wait: a genuinely hung model turn (provider stalled
mid-generation) keeps the session `busy` with the process alive forever, so the
SSE loop never returns.

Live evidence (PID 58436): the model ran two bash validation tool calls that
completed, the step ended with finish reason `tool-calls` (a step boundary, not
a turn end), it began the next assistant message, and then the provider produced
no further tokens. CodeCome's transcript froze; the serve log kept emitting
`busy` for ~11 min, then went silent entirely while the process stayed alive.

### 7.2 The fix

A no-progress watchdog in `PhaseEventLoop`:

- `_note_progress(event)` updates `_last_progress_at` on **every** SSE event
  except `server.heartbeat` and `server.connected` (pure connection lifecycle).
- `_stalled()` is True once `now - _last_progress_at >= CODECOME_BUSY_STALL_TIMEOUT`
  (default **180s**; `0` disables).
- `_should_keep_consuming()` returns False (and sets `_session_stalled`) once
  stalled, even while busy+alive — so the SSE client stops at the next
  reconnect/heartbeat checkpoint instead of waiting forever.
- The stalled run surfaces `RunResult.session_stalled=True` and
  `last_finish_reason="session_stalled"`.

Propagation and recovery:

- `runner.py` records `codecome.session.stalled` and returns the stalled result.
- `phase_1._run_subphase` maps it to new status `RunStatus.SESSION_STALLED`;
  `run_phase_1` returns `Phase1Outcome(SESSION_STALLED, failed_subphase)`.
- `phases/completion.py` adds a `session_stalled` resume opener (no PROMPT_EXTRA).
- `harness.py` treats `session_stalled` exactly like `server_unreachable`:
  restart the server and retry, **sharing the same `CODECOME_MAX_SERVER_RESTARTS`
  budget** (default 2), with a clear `[Auto-Recovery] ... stalled ...` message.

### 7.3 De-duplication

The restart+retry logic was duplicated across the Phase 1 branch and the two
Phase 2-6 recovery blocks. Consolidated:

- `_RECOVERABLE_RESTART_REASONS` maps `server_unreachable` / `session_stalled`
  to their user-facing wording.
- `_restart_server(runner, *, log_level)` centralizes the single
  `runner.restart(...)` invocation.
- Phases 2-6 now use one recovery block driven by `_recovery_reason`; Phase 1
  uses the shared map + helper.

### 7.4 Tests

- `tests/test_sse_busy_resilience.py`: stall stops consuming even when busy+alive;
  non-heartbeat events reset the timer; heartbeat/connected do not; timeout=0
  disables; `RunResult.session_stalled` default.
- `tests/test_runner_resume_health.py`: `_run_subphase` maps a stalled run to
  `SESSION_STALLED`.
- `tests/test_harness_recovery_restart.py`: both reasons restart+retry then
  succeed; shared budget exhaustion yields a non-zero terminal status.

---

## 8. Fix 6 — Reachable stall watchdog on a silent-but-open SSE stream

Date: 2026-06-15
Status: Implemented
Verified against: opencode v1.17.7 (live hang reproduced, PID 74577).

### 8.1 Root cause (confirmed in opencode v1.17.7 source)

`packages/opencode/src/server/routes/instance/httpapi/handlers/event.ts` builds
the `/event` SSE response by merging the event output with
`Stream.tick("10 seconds")` heartbeats, scheduled on the Effect runtime.
`global.ts` does the same for `/global/health`. When a model turn (or a wedged
`@explore` subagent) hangs synchronously, the Effect runtime scheduler blocks and
**no heartbeats fire on either stream**. The live hang (PID 74577) had **0
`server.heartbeat` events** in the serve log; the HTTP connection stayed open
(`X-Accel-Buffering: no`, no FIN) but silent.

CodeCome's stall watchdog (Fix 5) was logically correct but **unreachable** here:
- `_should_keep_consuming()` (which holds the 180s no-progress check) is only
  evaluated at SSE reconnect/budget checkpoints.
- The heartbeat-timeout check lived in `_on_event`, which only runs when an event
  arrives.
- The blocking line read (`for byte_line in resp`) did not surface a wall-clock
  timeout on a silent-but-open socket, so neither check ever ran.

### 8.2 The fix (read tick; no background threads → chat-safe)

`SseClient._open_stream` now:
- Sets an explicit per-read socket timeout via `_set_stream_timeout(resp, tick)`
  with `tick = CODECOME_SSE_READ_TICK` (default 10s).
- Reads with manual `resp.readline()` and converts `socket.timeout`/`TimeoutError`
  into an inactivity **tick** (`yield None`) instead of blocking forever; EOF
  becomes `SSE stream closed by server`.

`SseClient.events()` handles a `None` tick by evaluating `should_continue()`
(when provided): if it returns False (e.g. stall watchdog tripped), it stops the
stream cleanly. With `should_continue=None` (chat mode) ticks are ignored and the
loop keeps reading — chat behavior is unchanged, and chat consumers never see a
`None` (ticks are absorbed inside `events()`).

This makes Fix 5's 180s no-progress watchdog reachable on a silent-but-open
stream: a stall is detected within ~one tick (~10s) of crossing 180s (worst case
~190s).

### 8.3 Heartbeat-loss as a secondary (faster) signal

Heartbeat detection is now **independent of heartbeat arrival** and no longer
false-positives when a server emits none:
- `_on_event` records heartbeat arrival but does not raise on stale heartbeats;
  a late non-heartbeat event is valid progress and must not be discarded.
- `SseClient.seconds_since_heartbeat()` exposes the gap (or None if never seen).
- `PhaseEventLoop._stalled()` keeps an optional secondary trigger: if heartbeats
  were seen and then stopped for `CODECOME_HEARTBEAT_STALL_TIMEOUT` while busy,
  flag a stall early. This is disabled by default because live Phase 1a runs
  showed opencode can pause heartbeats during valid long turns.

### 8.4 New env knobs

- `CODECOME_SSE_READ_TICK` (default 10s) — inactivity read tick / socket timeout.
- `CODECOME_HEARTBEAT_STALL_TIMEOUT` (default 0s / disabled) — optional
  secondary heartbeat-gap stall.
- (existing) `CODECOME_BUSY_STALL_TIMEOUT` (default 180s) — primary no-progress.

### 8.5 Tests

`tests/test_sse_busy_resilience.py`:
- `None` tick + `should_continue()==False` stops the stream; `==True` keeps
  reading; `should_continue=None` (chat) ignores ticks and still delivers events.
- Heartbeat-loss triggers a stall; never-seen heartbeats do not trigger via the
- Heartbeat-loss can trigger a stall only when explicitly enabled; never-seen
  heartbeats do not trigger via the heartbeat path; a recent heartbeat does not
  trigger.
- `_on_event` does not discard late events after a heartbeat gap;
  `seconds_since_heartbeat()` reflects the gap after a heartbeat.

---

## 9. Fix 7 — Avoid false stalls when SSE misses terminal idle

Date: 2026-06-16
Status: Implemented
Verified against: opencode v1.17.7 (Phase 1a restart-budget exhaustion).

### 9.1 What happened

Live Phase 1a attempts produced valid model/tool progress and then CodeCome
classified the turn as `session_stalled` after exhausting the restart budget.
The transcript ended near a pending write/tool boundary plus heartbeat/reconnect
events, but the matching serve log later showed the main Phase 1a session reached
`idle` before CodeCome killed the server.

### 9.2 Root cause

Two independent false-positive paths combined:

- `SseClient._on_event()` treated a stale heartbeat as fatal on any subsequent
  non-heartbeat event, so a valid late event (including a terminal idle) could be
  dropped instead of delivered to `PhaseEventLoop`.
- `PhaseEventLoop` cached `_session_busy=True` from the last SSE status and did
  not verify `/session/status` before turning the no-progress timeout into a
  hard `session_stalled` result. opencode's status endpoint only returns busy
  sessions; absence from that map means idle.

### 9.3 The fix

- `SseClient._on_event()` no longer raises on stale heartbeats; heartbeat gaps
  are telemetry, while silence is handled by read ticks plus the phase watchdog.
- `CODECOME_HEARTBEAT_STALL_TIMEOUT` defaults to `0` (disabled) and is documented
  as optional/diagnostic.
- Before marking a busy turn stalled, `PhaseEventLoop` probes `/session/status`
  with the existing short probe timeout. If the target session is idle, it clears
  `_session_busy`, records `_session_idle_via_status`, and exits without setting
  `session_stalled`.
- When idle is observed via status probe, `PhaseEventLoop` performs a final
  `_sync_session_messages()` before returning so a missed terminal `step_finish`
  can still be recovered from persisted session messages.
- `runner.py` now records `codecome.session.stalled` on the normal result path;
  the previous marker was unreachable after an unconditional return.

### 9.4 Tests

`tests/test_sse_busy_resilience.py` now covers:

- stale heartbeat followed by a valid late event does not raise;
- status-probe idle prevents a false stall;
- status-probe busy still yields a true stall;
- heartbeat-gap stalls are disabled by default;
- final sync after status-idle recovery can recover a terminal `step_finish`.

---

## 10. Fix 8 — Treat control-plane timeouts as recoverable server unresponsiveness

Date: 2026-06-16
Status: Implemented
Verified against: opencode v1.17.7 (Phase 1c `POST /session` timeout after CodeQL).

### 10.1 What happened

After Phase 1b completed and CodeQL ran successfully, Phase 1c failed before it
could create a session:

- transcript contained only `codecome.attempt.started` and
  `codecome.attempt.failed` with `TimeoutError: timed out`;
- there was no `codecome.session.ready`, so failure happened inside
  `create_session()` (`POST /session`, hard-coded 10s timeout);
- the matching serve log showed the previous Phase 1b session reached `idle`
  around the same moment, so the server process was alive but the HTTP control
  plane was temporarily unresponsive/backpressured.

### 10.2 Root cause

`create_session()` did not retry transient failures and `_run_single_attempt()`
treated a `POST /session` timeout as a generic fatal `RunStatus.ERROR`. That
bypassed the Phase 1 harness recovery path, which only restarts/retries on
structured `server_unreachable` or `session_stalled` outcomes.

Prompt submission had a related gap: `send_prompt_to_session()` retried transient
failures, but if retries were exhausted it raised a generic `RuntimeError`, also
classified as fatal instead of recoverable infrastructure unresponsiveness.

### 10.3 The fix

- `codecome.session.OpenCodeRequestError` now carries `retriable` and `operation`
  metadata for opencode HTTP failures.
- `create_session()` retries transient failures (`TimeoutError`, `URLError`,
  `OSError`, HTTP 5xx, HTTP 429) with the existing backoff schedule.
- Exhausted transient `create_session()` and `send_prompt_to_session()` failures
  are mapped by `_run_single_attempt()` to `RunStatus.INCOMPLETE` with
  `RunResult.last_finish_reason="server_unreachable"`.
- Phase 1 and phase harness wording now says the server is unreachable or
  unresponsive, not only dead.
- Non-retriable failures (for example empty session IDs or HTTP 4xx) remain fatal.

### 10.4 Tests

- `tests/test_session.py`: create-session timeouts retry and eventually succeed;
  exhausted create-session and prompt-send timeouts raise retriable
  `OpenCodeRequestError`.
- `tests/test_codecome_runner.py`: retriable prompt-send and create-session
  failures return a recoverable `server_unreachable` result rather than invoking
  the fatal-error path.
