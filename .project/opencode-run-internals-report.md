# OpenCode `run` Internals: Structured Research Report

**Date:** 2026-05-16
**Target:** OpenCode CLI v1.14.50 (installed via Homebrew)
**Source:** `github.com/anomalyco/opencode` (dev branch)
**Investigator:** Automated source-code analysis

---

## 1. Executive Summary

`opencode run` (non-interactive, non-attach mode) does **not** start a traditional HTTP server or bind to a port for its own use. Instead, it creates an **in-process** SDK client whose `fetch` implementation is monkey-patched to bypass the network entirely and call `Server.Default().app.fetch(request)` directly. The server code is still loaded and executed, but requests travel through an in-memory function call rather than TCP/HTTP. For `--attach` mode, the CLI uses standard HTTP SSE to a remote server.

---

## 2. How `opencode run` Starts Its Server and Connects

### 2.1 Non-Interactive Local Mode (default)
**File:** `packages/opencode/src/cli/cmd/run.ts` (lines 275-280)

```typescript
const fetchFn = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const { Server } = await import("@/server/server")
  const request = new Request(input, init)
  return Server.Default().app.fetch(request)
}) as typeof globalThis.fetch

const sdk = createOpencodeClient({
  baseUrl: "http://opencode.internal",   // Fake URL; never hit over network
  fetch: fetchFn,
  directory,
})
```

Key observations:
- `baseUrl` is a dummy (`http://opencode.internal`). It is only used for path resolution inside the SDK.
- The real transport is `fetchFn`, which imports the server module lazily and invokes its `app.fetch()` directly.
- The server module (`packages/opencode/src/server/server.ts`) creates a Bun/Node HTTP server when `listen()` is called, but in this local mode **no port is opened** for the CLI's own consumption.
- The `InstanceRef` Effect service is provided (because `instance: (args) => !args.attach`), which boots the full opencode runtime (DB, bus, agents, etc.) inside the same process.

### 2.2 Interactive Local Mode (`--interactive` without `--attach`)
**File:** `packages/opencode/src/cli/cmd/run.ts` (lines 248-264)

Same in-process fetch pattern, but calls `runInteractiveLocalMode()` instead of `execute()`. The TUI (Ink-based React renderer) renders in the same terminal, still talking to the in-process server via the fake-fetch bridge.

### 2.3 Attach Mode (`--attach`)
**File:** `packages/opencode/src/cli/cmd/run.ts` (lines 186-193)

```typescript
const attachSDK = (dir?: string) => {
  return createOpencodeClient({
    baseUrl: args.attach!,         // e.g. http://localhost:4096
    directory: dir,
    headers: attachHeaders,         // Basic auth if provided
  })
}
```

- Standard HTTP transport (real `fetch` via the SDK).
- No local instance is booted (`instance: (args) => !args.attach`).

---

## 3. SSE Event Consumption and ND-JSON Mapping

### 3.1 Server-Side Event Production
**File:** `packages/opencode/src/server/routes/instance/httpapi/handlers/event.ts`

```typescript
function eventData(data: unknown): Sse.Event {
  return {
    _tag: "Event",
    event: "message",
    id: undefined,               // NO event ID is emitted
    data: JSON.stringify(data),
  }
}
```

The server:
- Subscribes to the global event bus (`bus.subscribeAll()`).
- Merges a heartbeat stream (every 10 seconds, type `server.heartbeat`).
- Sends an initial `server.connected` event.
- Encodes everything with `effect/unstable/encoding/Sse.encode()`.
- Response headers:
  - `Content-Type: text/event-stream`
  - `Cache-Control: no-cache, no-transform`
  - `X-Accel-Buffering: no`
  - `X-Content-Type-Options: nosniff`

### 3.2 Client-Side SSE Parsing
**File:** `packages/sdk/js/src/v2/gen/core/serverSentEvents.gen.ts`

The SDK's generated SSE client:
- Uses the standard Web Streams API (`response.body.pipeThrough(new TextDecoderStream()).getReader()`).
- Parses SSE fields (`data:`, `event:`, `id:`, `retry:`) manually.
- Joins multi-line `data:` fields with `\n`.
- Parses JSON from the joined data lines.
- Yields the parsed JSON object as the async generator's value.
- Supports **retry with exponential backoff**:
  - Default retry delay: 3000 ms
  - Max retry delay: 30000 ms
  - Retries on network/parse errors until `sseMaxRetryAttempts` is reached.
- **Event ID tracking:** reads `id:` lines into `lastEventId` and sends it back as `Last-Event-ID` header on reconnect.

### 3.3 ND-JSON Translation on Stdout
**File:** `packages/opencode/src/cli/cmd/run.ts` (lines inside `execute()` function)

The CLI's event loop (`loop()` function) consumes `events.stream` and maps events to stdout:

| Server SSE Event | Condition | stdout output (default) | stdout output (`--format json`) |
|---|---|---|---|
| `message.updated` | assistant role, first message | Prints header: `> agent · modelID` | `{"type":"message.updated",...}` |
| `message.part.updated` | `part.type === "text"` && `part.time?.end` | Prints plain text + newlines | `{"type":"text", "part":...}` |
| `message.part.updated` | `part.type === "reasoning"` && `part.time?.end` | Prints dim italic "Thinking: ..." | `{"type":"reasoning",...}` |
| `message.part.updated` | `part.type === "tool"` && status `running` | Inline icon + title | `{"type":"tool_use",...}` |
| `message.part.updated` | `part.type === "tool"` && status `completed` | Block with tool output | `{"type":"tool_use",...}` |
| `message.part.updated` | `part.type === "tool"` && status `error` | Error icon + title + error | `{"type":"tool_use",...}` |
| `message.part.updated` | `part.type === "step-start"` | — | `{"type":"step_start",...}` |
| `message.part.updated` | `part.type === "step-finish"` | — | `{"type":"step_finish",...}` |
| `session.error` | matching session | `UI.error(err)` | `{"type":"error", "error":...}` |
| `session.status` | `status.type === "idle"` | **Breaks loop, exits** | — |
| `permission.asked` | matching session | Prints warning + auto-rejects | `{"type":"permission.asked",...}` |

The `emit()` helper writes ND-JSON:

```typescript
process.stdout.write(
  JSON.stringify({
    type,
    timestamp: Date.now(),
    sessionID,
    ...data,
  }) + EOL,
)
```

---

## 4. Tool Permission Handling

### 4.1 Non-Interactive Mode (Default)
**File:** `packages/opencode/src/cli/cmd/run.ts` (lines 393-413)

```typescript
if (event.type === "permission.asked") {
  const permission = event.properties
  if (permission.sessionID !== sessionID) continue

  if (args["dangerously-skip-permissions"]) {
    await client.permission.reply({ requestID: permission.id, reply: "once" })
  } else {
    UI.println("... auto-rejecting")
    await client.permission.reply({ requestID: permission.id, reply: "reject" })
  }
}
```

Default behavior:
- **All permissions are auto-rejected** in non-interactive mode.
- If `--dangerously-skip-permissions` is passed, they are **auto-approved once** (`reply: "once"`).

### 4.2 Interactive Mode (TUI)
**Files:**
- `packages/opencode/src/cli/cmd/run/footer.permission.tsx` — React/Ink UI component
- `packages/opencode/src/cli/cmd/run/permission.shared.ts` — Pure state machine

Permission state machine stages:
1. **permission** → Options: `Allow once` / `Allow always` / `Reject`
2. **always** → Confirmation step: `Confirm` / `Cancel`
3. **reject** → Optional text input for rejection message

Replies sent to the server:
- `reply: "once"` — allow one time
- `reply: "always"` — allow for this pattern until restart
- `reply: "reject"` — deny (with optional message)

### 4.3 Server-Side Permission API
**File:** `packages/opencode/src/server/routes/instance/httpapi/handlers/permission.ts`

```typescript
const reply = Effect.fn("PermissionHttpApi.reply")(function* (ctx: {
  params: { requestID: PermissionID }
  payload: Permission.ReplyBody
}) {
  yield* svc.reply({
    requestID: ctx.params.requestID,
    reply: ctx.payload.reply,
    message: ctx.payload.message,
  })
  return true
})
```

Endpoint: `POST /permission/{requestID}/reply` (v2 API).

---

## 5. Tool State Reconstruction

### 5.1 Event Source
Tool state arrives via `message.part.updated` events where `part.type === "tool"`.

**File:** `packages/opencode/src/cli/cmd/run.ts` (lines 355-378)

```typescript
if (part.type === "tool" && (part.state.status === "completed" || part.state.status === "error")) {
  if (emit("tool_use", { part })) continue
  if (part.state.status === "completed") {
    await tool(part)
    continue
  }
  await toolError(part)
  UI.error(part.state.error)
}
```

### 5.2 Tool Part Structure
The `ToolPart` type (from SDK v2) contains:
- `tool`: tool name (e.g., `bash`, `write`, `edit`)
- `state`: `{ status: "running" | "completed" | "error", error?: string, ... }`
- `input`: the tool arguments
- `output`: the tool result (when completed)
- `id`: part ID
- `sessionID`: session ID

### 5.3 Display Formatting
**File:** `packages/opencode/src/cli/cmd/run/tool.ts`

Tools have custom renderers registered via a rule system:
- `toolInlineInfo(part)` → returns `{ icon, title, description, mode: "inline" | "block", body? }`
- `toolScroll(phase, ctx)` → returns scrollback text for different phases (`start`, `progress`, `final`)
- `toolPermissionInfo(name, input, meta, patterns)` → returns UI lines for the permission dialog

Example tools with custom formatters: `bash`, `write`, `edit`, `task`, `WebFetch`, `Read`, etc.

---

## 6. Event ID / Cursor / Resume Mechanisms

### 6.1 Does the server support `lastEventId`?
**Partially, but it is not used.**

The server-side `eventData()` function explicitly sets `id: undefined`:

```typescript
function eventData(data: unknown): Sse.Event {
  return {
    _tag: "Event",
    event: "message",
    id: undefined,          // ← always undefined
    data: JSON.stringify(data),
  }
}
```

The SDK client **does** implement the full `lastEventId` protocol:
- Tracks `lastEventId` from SSE `id:` lines.
- Sends `Last-Event-ID` header on reconnect attempts.
- However, because the server never emits IDs, resubscription always starts from the latest real-time event; **there is no server-side replay of missed events**.

### 6.2 Is there a session-specific events endpoint?
**No.**

- The global event endpoint is `/event` (SDK: `client.subscribe()`).
- There is also `/global/event` (SDK: `client.event()`).
- There is **no** `/session/{id}/events` endpoint.
- Session filtering is done **client-side** inside the `loop()` function:
  ```typescript
  if (part.sessionID !== sessionID) continue
  if (event.properties.sessionID !== sessionID) continue
  ```

### 6.3 Session Resumption (`--continue` / `--session`)
- `--continue` looks up the last session via `sdk.session.list()` and picks the one without a `parentID`.
- `--session` fetches a specific session via `sdk.session.get({ sessionID })`.
- `--fork` creates a new forked session before continuing.
- Resumption does **not** replay historical events; it simply re-attaches to the existing session ID and starts consuming **new** events from the live bus.

---

## 7. Endpoint Reference

| Endpoint | SDK Method | Purpose |
|---|---|---|
| `GET /event` | `client.event.subscribe()` | Subscribe to global SSE stream |
| `GET /global/event` | `client.event.event()` | Subscribe to global SSE stream (legacy/alternate) |
| `POST /session` | `client.session.create()` | Create new session |
| `POST /session/{id}/prompt` | `client.session.prompt()` | Send a user message |
| `POST /session/{id}/command` | `client.session.command()` | Execute a slash command |
| `POST /permission/{requestID}/reply` | `client.permission.reply()` | Reply to a permission request |
| `GET /session/{id}` | `client.session.get()` | Get session metadata |
| `POST /session/{id}/fork` | `client.session.fork()` | Fork a session |

---

## 8. Binary Analysis Notes

- The Homebrew binary (`/opt/homebrew/bin/opencode`) is a **Mach-O 64-bit ARM64 executable** (101.6 MB).
- It is a **Bun-compiled single-file executable** with all JavaScript/TypeScript source bundled inside.
- No separate Node modules or source tree is exposed in the Cellar.
- String analysis confirms embedded module paths like `packages/opencode/src/...` and `packages/sdk/js/src/...`.
- The binary contains the full Effect framework, SQLite (via `better-sqlite3` or Bun's built-in), and React/Ink TUI runtime.

---

## 9. Security Observations

1. **In-process fetch bypass:** The local mode never validates TLS, auth tokens, or same-origin policies because requests never leave the process. This is by design, but it means `Server.Default().app.fetch()` is a direct attack surface if an attacker can inject code into the CLI process.
2. **Permission auto-rejection:** Non-interactive mode auto-rejects all tool permissions, which is a safe default. The `--dangerously-skip-permissions` flag is required to weaken this.
3. **No event replay:** Because SSE events have no IDs and there is no session-specific replay endpoint, a client that disconnects and reconnects will miss events that occurred during the disconnection. This is a reliability limitation, not a direct security issue.
4. **Basic auth in attach mode:** The `--attach` mode supports `--username` / `--password` (or env vars `OPENCODE_SERVER_USERNAME` / `OPENCODE_SERVER_PASSWORD`). Credentials are sent via Basic Auth headers.

---

## 10. Files Referenced

- `/opt/homebrew/bin/opencode` (compiled Bun binary)
- `packages/opencode/src/cli/cmd/run.ts`
- `packages/opencode/src/cli/cmd/run/permission.shared.ts`
- `packages/opencode/src/cli/cmd/run/tool.ts`
- `packages/opencode/src/server/server.ts`
- `packages/opencode/src/server/routes/instance/httpapi/handlers/event.ts`
- `packages/opencode/src/server/routes/instance/httpapi/handlers/permission.ts`
- `packages/sdk/js/src/v2/gen/core/serverSentEvents.gen.ts`
- `packages/sdk/js/src/v2/gen/sdk.gen.ts`
- `packages/sdk/js/src/v2/client.ts`

