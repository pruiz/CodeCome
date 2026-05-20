# SSE Sync Recovery Plan

**Date:** 2026-05-20
**Status:** Planned
**Branch:** `migrate-to-opencode-serve-api`

## Problem Statement

The current `_sync_session_messages()` implementation causes duplicate events in CI parity tests. The sync is triggered too frequently (every 0.5s via `server.heartbeat` and `session.diff`), and the deduplication has bugs that allow duplicates through.

**Observed CI failure:**
```
--- opencode-run
+++ opencode-serve
+{"part": {"snapshot": "a249ec52d7915bc7c077ce0408a80e53fd36186f", "type": "step-start"}, "type": "step_start"}
+{"part": {"text": "Done reading.", "type": "text"}, "type": "text"}
```
Two events appear in serve path but not in run path, both with same snapshot hash.

## Research Findings

### SSE Architecture (opencode source)
- SSE uses `bus.subscribeAll()` - all bus events go to all SSE clients
- `message.part.delta` → **direct bus publish** (fire-and-forget)
- `message.part.updated` → **sync layer** (database write + bus publish)
- This means deltas are "easier" to miss than updates during stream interruptions

### SSE Reconnect Behavior (`packages/sdk/js/src/v2/gen/core/serverSentEvents.gen.ts`)
- `sseMaxRetryAttempts` defaults to `undefined` (infinite retries with 3s→30s backoff)
- When max retries exceeded: async generator **breaks silently** without throwing
- `onSseError` callback fires on each failure (including final), but loop still breaks
- After break: `Stream.runForEach` finishes, `ensuring` block fires `fail("global event stream closed")`
- `SseClient` in our code raises `SseClientError` when the stream iterator ends

### Part ID Generation (`packages/core/src/util/identifier.ts`)
- Part IDs are globally unique: `prt` prefix + 6 bytes timestamp/counter + 14 random base62 chars
- **NOT a UUID** - timestamp-based monotonic + random suffix
- Part IDs are the primary key in `PartTable` (database deduplicates on `id` alone)
- **`(type, part_id)` is sufficient for deduplication** - no need for snapshot hash

### Sync Triggering (current code - `tools/events/__init__.py:243`)
- **Immediate**: `session.idle`, `session.updated`, `todo.updated`, `session.status.type=="idle"`
- **Throttled (0.5s)**: `session.status`, `session.diff`, `server.heartbeat`
- `server.heartbeat` fires every 10s → triggers sync 20 times/minute
- `session.diff` fires on every model output delta → very frequent during active streaming

### Deduplication Bugs
1. **StateTracker line 309**: When `has_seen()` returns True, code `continue`s but does NOT mark the part as seen. So the same part gets checked and skipped on every subsequent sync.
2. **No EventLoop-level fingerprint**: Synthesized events from sync can duplicate events already emitted via SSE.

## Plan

### Approach 1: Sync Only On Reconnect (Not Periodically)

**Principle:** Only sync when we have an actual disconnect/reconnect scenario, not on a timer.

**Implementation:**
1. Add a `reconnect_callback` slot to `SseClient` that fires after successful reconnection
2. `EventLoop` registers this callback and uses it to trigger a one-time recovery sync
3. Remove `server.heartbeat`, `session.diff`, `session.status` from `_should_sync_session_messages()` triggers
4. Keep `session.idle` sync for end-of-session final catchup
5. When reconnect callback fires: set a flag that makes next `_should_sync_session_messages()` return True, then clear the flag after one sync

**Why this works:**
- If SSE was reliable (no disconnect), no unnecessary syncs
- If SSE had a brief interruption, reconnect triggers a recovery sync to catch missed events
- End-of-session (`session.idle`) catches any final events SSE might have missed

### Approach 2: Fix Deduplication at EventLoop Level

**Principle:** Even if sync produces duplicates, only one gets emitted.

**Implementation:**
1. **Fix StateTracker bug at line 309**: When skipping a part that's already seen, still call `mark_seen()` so future checks work correctly
2. **Add `_emitted_part_signatures` set in EventLoop**: Track `(part_id)` for every finalized event emitted
3. **Check before emit**: In `EventLoop.run()`, before emitting a finalized event (from `_tracker.ingest()` or sync), check if its `part.id` is in `_emitted_part_signatures`
4. **Key by `(event_type, part_id)`**: Even though `part_id` is globally unique, we key by `(event_type, part_id)` to be safe against any edge cases where same ID could appear in different event types

**Why this works:**
- Part ID alone is the deduplication key (per opencode DB schema)
- `(event_type, part_id)` is a belt-and-suspenders approach
- Prevents duplicates from either SSE or sync path

### Key: Minimal Sync Surface

After implementing ideas 1 and 2, the sync should only trigger in two scenarios:
1. **On reconnect** - after SSE stream was interrupted and re-established
2. **On session.idle** - at end of session as a safety net

Both are low-frequency (reconnect should be rare; session.idle is once per session).

## Implementation Steps

### Step 1: Fix StateTracker Bug
**File:** `tools/events/state_tracker.py`
**Change:** At line 309, when skipping a part that's already seen, add to `_seen_part_ids`:
```python
if isinstance(part_id, str) and self._tracker.has_seen(part_id):
    # Already processed this part - mark as seen to avoid re-check
    self._tracker.mark_seen(part_id)  # NEW
    continue
```

Or add a `mark_seen()` method to StateTracker if it doesn't exist.

### Step 2: Add Reconnect Callback to SseClient
**File:** `tools/events/sse_client.py`
**Changes:**
- Add `on_reconnect: Callable[[], None] | None = None` parameter to `__init__`
- In `_open_stream()`, after successful reconnect (when we resume reading events after a retry), call `self.on_reconnect()` if set

### Step 3: Add Recovery Sync Flag to EventLoop
**File:** `tools/events/__init__.py`
**Changes:**
- Add `_pending_recovery_sync: bool = False` instance variable
- Add `trigger_recovery_sync()` method that sets `_pending_recovery_sync = True`
- Register this callback in `SseClient` constructor: `self._client = SseClient(..., on_reconnect=self.trigger_recovery_sync)`

### Step 4: Update Sync Trigger Logic
**File:** `tools/events/__init__.py`
**Changes:**
- Remove `server.heartbeat` and `session.diff` from throttled sync triggers (line 252)
- In `_should_sync_session_messages()`, check `_pending_recovery_sync` flag and return True if set
- Clear `_pending_recovery_sync = False` after one sync completes

### Step 5: Add EventLoop-Level Dedup
**File:** `tools/events/__init__.py`
**Changes:**
- Add `_emitted_part_signatures: set[tuple[str, str]]` instance variable
- Before emitting a finalized event (after `_tracker.ingest()` returns), compute signature `(event_type, part.get("id", ""))`
- If signature already in set, skip emit
- If not, add to set and emit

## Architecture After Changes

```
SseClient.events()
    │
    │─ on reconnect success ─→ EventLoop.trigger_recovery_sync()
    │                              └─ sets _pending_recovery_sync = True
    │
    └─ yield events ─→ EventLoop.run()
                           │
                           ├─ _tracker.ingest(event)
                           │     └─ StateTracker: dedup via _seen_part_ids (FIXED)
                           │
                           ├─ _should_sync_session_messages()
                           │     └─ returns True only if:
                           │         - _pending_recovery_sync (reconnect sync)
                           │         - session.idle (end-of-session sync)
                           │
                           ├─ _sync_session_messages() → synthesize
                           │     └─ ingest(synthesized) → dedup + emit
                           │
                           └─ emit to render_fn()
                                  │
                                  └─ check fingerprint (EventLoop level dedup)
```

## Testing Strategy

1. **Run parity tests 5 times locally** to confirm baseline passes
2. **Add a test that simulates SSE disconnect/reconnect** to verify recovery sync works
3. **Add a test for idempotency** - sync called twice with same events should not duplicate
4. **Monitor CI** for the 2 failing parity tests (script1 and script3)

## Open Questions / Follow-ups

1. **Long-term**: Investigate if SSE unreliability is a bug in opencode or expected behavior. If deltas always arrive reliably, we might not need sync at all.
2. **Metrics**: Consider adding a metric for "times sync ran" and "events emitted from sync" to understand sync frequency in production.
3. **Timeout**: What happens if reconnect never succeeds? With `max_reconnects=10` and 3s base backoff, that's ~60s total before giving up. Is that enough?

## Files to Modify

- `tools/events/state_tracker.py` - fix line 309 bug
- `tools/events/sse_client.py` - add on_reconnect callback
- `tools/events/__init__.py` - recovery sync flag, trigger, dedup fingerprint set

## Related Files (Read-Only)

- `tools/mock-llm-parity.py` - for understanding sync context
- `tools/events/emitters.py` - for understanding emit path