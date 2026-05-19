# Using `serve` to get the same data as `run --format json` over HTTP

## Architecture in 30 seconds

opencode has a single internal **Bus** (`packages/opencode/src/bus/index.ts`) that every component publishes events to: the model loop, tool executions, sessions, permissions, MCP servers, LSP, PTY, file changes, etc.

- **`run --format json`** subscribes to that bus, filters a small subset of events, flattens them, and writes them to stdout as NDJSON.
- **`serve`** exposes the bus more or less raw over an HTTP server-sent events stream.

So you are not switching to a different data source — you are consuming the same firehose, just less filtered and over HTTP.

## What `run --format json` actually emits

From `packages/opencode/src/cli/cmd/run.ts:592-700`, the emit envelope is:

```json
{
  "type": "tool_use | step_start | step_finish | text | reasoning | error",
  "timestamp": 1737060000000,
  "sessionID": "ses_...",
  "part": { ... }          // for non-error types
  "error": { ... }          // for "error" type
}
```

It is produced from only two bus event types:

- `message.part.updated` — emitted as `text` (when `part.type === "text"` *and* `part.time.end` is set, i.e. the text is finalized), `reasoning` (same condition, `part.type === "reasoning"`), `tool_use` (when `part.type === "tool"` and `state.status` is `completed` or `error`), `step_start`, `step_finish`.
- `session.error` — emitted as `error`.

It uses two more bus events but does *not* re-emit them to stdout:

- `session.status` with `status.type === "idle"` for that session → loop exits, process returns.
- `permission.asked` → auto-replies via the SDK (`once` if `--dangerously-skip-permissions`, otherwise `reject`).

This matters because if you replicate the behavior over HTTP, you have to do the same gating yourself.

## The HTTP equivalent: `GET /event` (SSE)

File: `packages/opencode/src/server/routes/instance/httpapi/handlers/event.ts`

Characteristics:

- `Content-Type: text/event-stream`, `Cache-Control: no-cache, no-transform`, `X-Accel-Buffering: no`
- Standard SSE framing: one event per `data: <json>\n\n` block.
- First event you will always receive: `{ "id": "...", "type": "server.connected", "properties": {} }`.
- Every 10 seconds you receive `{ "type": "server.heartbeat", "properties": {} }` — drop it.
- Stream ends when the instance is disposed (`Bus.InstanceDisposed`).
- Each business event has the shape `{ "id": "...", "type": "...", "properties": { ... } }`. The `properties` payload is the same object the bus carries internally and the same object `run` peeks at as `event.properties` / `event.properties.part`.

Notable event types you will care about (all named exactly as they appear over the wire):

| Type | When | Notable fields |
|---|---|---|
| `message.updated` | A whole assistant/user message changed | `properties.info` (role, agent, modelID, …), `properties.sessionID` |
| `message.part.updated` | A streamed part of a message changed | `properties.part` (with `type`: `text`/`reasoning`/`tool`/`step-start`/`step-finish`, `state`, `time`, `sessionID`) |
| `session.status` | Session changed state | `properties.sessionID`, `properties.status.type` (e.g. `idle`, `running`) |
| `session.error` | An error occurred during a turn | `properties.sessionID`, `properties.error` |
| `permission.asked` | A tool wants permission | `properties.sessionID`, `properties.id` (requestID), `properties.permission`, `properties.patterns` |
| `server.connected` / `server.heartbeat` / `server.disconnected` | Stream lifecycle | — |

## Recommended workflow

1. **Start the server**
   ```
   OPENCODE_SERVER_PASSWORD=changeme \
   opencode serve --port 8080 --hostname 127.0.0.1
   ```

2. **Open the SSE stream first.** Do this before sending the prompt, otherwise you lose early events (the session is created and the model starts streaming immediately).
   ```
   GET /event
   Authorization: Basic base64("opencode:changeme")
   x-opencode-directory: /absolute/path/to/your/project
   ```
   Buffer events as they arrive and dispatch them in your main loop.

3. **Create or pick a session.**
   ```
   POST /session
   ```
   Or list existing ones with `GET /session` and reuse one. Keep `sessionID`.

4. **Send the prompt.** Two flavors (from `packages/opencode/src/server/routes/instance/httpapi/groups/session.ts:73-95`):
   - `POST /session/:sessionID/message` — synchronous (HTTP response returns when the turn ends; you still get the live stream over `/event` in parallel).
   - `POST /session/:sessionID/prompt_async` — returns immediately. For an "event-driven over SSE" architecture this is usually what you want; it removes the need to keep an HTTP request open while a long turn is running.

5. **Drive your state machine off the SSE stream.** Recommended end-of-turn condition (this is exactly what `run` does, run.ts:702-708):
   ```
   event.type === "session.status"
     && event.properties.sessionID === <your sid>
     && event.properties.status.type === "idle"
   ```
   Both `session.status { status.type: "idle" }` and the deprecated
   `session.idle` event signal completion.  Prefer the `session.status`
   form because `session.idle` may be removed in future versions.

6. **Handle permissions if they happen.** On `permission.asked`, reply via:
   ```
   POST /session/:sessionID/permissions/:permissionID
   { "response": "once" | "always" | "reject" }
   ```
   If you do not reply, the turn stays blocked. `run` auto-rejects (or auto-approves with `--dangerously-skip-permissions`); decide your equivalent policy.

7. **Abort if you need to**: `POST /session/:sessionID/abort`.

## Mapping `run`'s JSON envelope to API events

If your downstream consumer is already wired to the `run --format json` shape, you can keep it stable by transforming SSE events on your side. The rules:

| run NDJSON type | Trigger condition on the API event |
|---|---|
| `text` | `message.part.updated` AND `part.type === "text"` AND `part.time?.end` truthy |
| `reasoning` | `message.part.updated` AND `part.type === "reasoning"` AND `part.time?.end` truthy |
| `tool_use` | `message.part.updated` AND `part.type === "tool"` AND `state.status` in (`completed`, `error`) |
| `step_start` | `message.part.updated` AND `part.type === "step-start"` |
| `step_finish` | `message.part.updated` AND `part.type === "step-finish"` |
| `error` | `session.error` |

Always filter by `part.sessionID === <your sid>` (or `properties.sessionID` for `session.*`), because `/event` is global — you get events for *every* session in the instance.

## Authentication

File: `packages/opencode/src/server/auth.ts`

- Set `OPENCODE_SERVER_PASSWORD` and (optionally) `OPENCODE_SERVER_USERNAME` (default `opencode`).
- Send `Authorization: Basic <base64(user:pass)>` on every request, including the SSE stream.
- Alternative for environments where you cannot set a header (e.g. an `EventSource` in a browser): use the `?auth_token=<base64>` query parameter.
- If no password is set, the server still starts but logs a warning and listens unauthenticated — fine for local dev, not for anything else.

## Multi-instance / workspace routing

The server can serve multiple project directories simultaneously. Every request — *including* the SSE subscription — should carry:

```
x-opencode-directory: /absolute/path/to/the/project
```

Some routes accept it as a query parameter instead (`?directory=...`). Without it the server uses the default instance, which may or may not be the one you want. If your events look "empty" or unrelated to the work you triggered, this header is the usual culprit.

## Things that will bite you

- **Lost early events.** Open `/event` before issuing any `POST /session/...` call. SSE is not replay-able.
- **Heartbeats and connection events.** Skip `server.connected`, `server.heartbeat`, `server.disconnected` in your consumer. Use `server.heartbeat` as a liveness signal: if it stops, your connection is dead — reconnect.
- **Reconnect logic.** SSE is a long-lived TCP connection. Plan for transient drops: reconnect, but be aware that you might miss events emitted during the gap. There is no event-id replay protocol on this endpoint.
- **Idle detection is per-session.** `session.status { idle }` for *another* session is not your signal. Filter strictly on `properties.sessionID`.
- **`text` and `reasoning` parts stream incrementally.** Many `message.part.updated` events for the same `part.id` will arrive before `part.time.end` is set. If you want the streaming experience, read `part.text` on every update (it is the accumulated text so far). If you want the final flush only — like `run --format json` — wait for `part.time.end`.
- **Tools have a lifecycle.** A `tool` part goes through `pending → running → completed | error`. `run` only emits `tool_use` at the terminal state. If you want progress, watch `state.status === "running"` too.
- **The API surface is much wider.** `/event` carries PTY output, file changes, LSP diagnostics, MCP server lifecycle, sync status, etc. Most of it is irrelevant for a "consume a prompt result" use case — filter aggressively by `type` to avoid drowning your consumer.
- **There is an official SDK.** `packages/sdk` is the TypeScript client (`sdk.event.subscribe()` is literally what `run` uses). If you are writing the consumer in Node/TS, use that — you get types for every event and every payload for free. For other languages, treat the SDK source as the canonical type reference and consume `/event` directly.

## Minimal pseudocode (Node-ish)

```ts
const auth = "Basic " + Buffer.from("opencode:changeme").toString("base64")
const dir  = "/Users/pruiz/Develop/other/opencode"

// 1. open SSE first
const sse = await fetch("http://127.0.0.1:8080/event", {
  headers: { Authorization: auth, "x-opencode-directory": dir },
})

// 2. create session
const sess = await fetch("http://127.0.0.1:8080/session", {
  method: "POST",
  headers: { Authorization: auth, "x-opencode-directory": dir,
             "Content-Type": "application/json" },
  body: "{}",
}).then(r => r.json())

// 3. fire prompt asynchronously
await fetch(`http://127.0.0.1:8080/session/${sess.id}/prompt_async`, {
  method: "POST",
  headers: { Authorization: auth, "x-opencode-directory": dir,
             "Content-Type": "application/json" },
  body: JSON.stringify({ /* PromptPayload: parts, modelID, providerID, ... */ }),
})

// 4. consume SSE, translate to run-style envelope, exit on idle
for await (const evt of parseSSE(sse.body)) {
  if (evt.type === "server.heartbeat") continue
  if (evt.type === "session.status"
      && evt.properties.sessionID === sess.id
      && evt.properties.status.type === "idle") break
  // ...translate message.part.updated / session.error here...
}
```

That is genuinely all there is to it — the bulk of the integration is just deciding which bus events you care about and how strictly you want to mirror the `run --format json` envelope.
