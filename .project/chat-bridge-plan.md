# Chat Bridge Plan

## Problem

CodeCome currently launches OpenCode through `opencode run --format json` and renders its event stream in `tools/run-agent.py`.

The current Textual chat prototype has two blockers:

1. `opencode run --port` does not expose a usable HTTP server for the non-attach `run` path, so direct HTTP `POST /session/{id}/message` fails with `Connection refused`.
2. Falling back to launching a fresh `opencode run` for every chat message would make the chat path too slow.

There are also two UI issues:

1. The initial `Starting interactive chat harness` message appears too late because chat startup currently blocks on model-resolution and probe work before printing it.
2. `Ctrl+C` should open a confirmation modal instead of silently failing or requiring the command palette.

## Findings

Upstream `opencode` source confirms that plain `opencode run` does not start a network listener in the non-attach path.

In `packages/opencode/src/cli/cmd/run.ts`, the non-attach execution path builds an SDK client with:

- `baseUrl: "http://opencode.internal"`
- a custom in-process `fetch` that calls `Server.Default().app.fetch(request)`

This means:

- the normal `run` path talks to OpenCode in-process,
- `args.port` is not consumed there,
- the HTTP routes like `/session/{sessionID}/message` and `/tui/append-prompt` exist on the server HTTP API, but are not exposed by the plain `run` path.

The upstream plugin API exposes:

- `client`
- `serverUrl`
- hooks such as `chat.message`

The SDK client supports low-latency session prompting through `client.session.prompt(...)`.

## Solution

Implement a local plugin-backed chat bridge that keeps the existing `opencode run --format json` launch model, but gives the Textual UI a low-latency way to inject new user prompts into the active session.

### Bridge Architecture

1. Add a new local OpenCode plugin under `.opencode/plugins/`.
2. When loaded, the plugin starts a tiny localhost bridge server bound to `127.0.0.1` on a random port.
3. The plugin generates a random auth token.
4. The plugin emits a JSON line to stdout announcing readiness, for example:
   - `type: "chat.bridge.ready"`
   - `properties.port`
   - `properties.token`
5. `tools/run-agent.py` captures that event and stores the bridge connection info.
6. The Textual chat input sends messages to that bridge over localhost HTTP.
7. The plugin receives the request and calls `client.session.prompt(...)` against the active session.
8. OpenCode continues emitting its normal JSON event stream to stdout, so the existing renderer path remains the source of truth for the upper panel.

This avoids:

- switching the main launcher to `opencode serve`,
- spawning a full extra `opencode run` per chat message,
- adding polling hacks or a second event protocol.

### Session Handling

Support only one active session at a time.

The bridge should maintain a single active `sessionID`, learned from `run-agent.py` as soon as the main JSON stream exposes it.

Recommended behavior:

1. `run-agent.py` learns the current `sessionID` from streamed events.
2. `run-agent.py` sends that `sessionID` to the plugin bridge once it is known, or includes it in the first `/message` request.
3. The plugin stores it as the only accepted active session.
4. Any attempt to prompt a different session should fail fast.

This keeps the bridge state simple and matches the current Textual UI model.

### Transport

Use localhost HTTP on `127.0.0.1` with a random token.

Reasoning:

- simpler to implement than Unix sockets,
- easy for Python `urllib` or `http.client`,
- acceptable for now when bound to loopback and protected by a random token.

Suggested request:

- `POST /message`
- header: `Authorization: Bearer <token>`
- body:
  - `text`

Suggested optional request:

- `POST /session`
- header: `Authorization: Bearer <token>`
- body:
  - `sessionID`

Suggested response:

- `{"ok": true}` or structured error JSON

### Plugin Responsibilities

The plugin should:

1. Start the bridge server at initialization.
2. Emit `chat.bridge.ready` once listening.
3. Accept authenticated POST requests.
4. Track exactly one active session.
5. Call `client.session.prompt({ path: { id: sessionID }, body: { parts: [{ type: "text", text }] } })`.
6. Return success or failure quickly.
7. Close the bridge server during shutdown if possible.

If bridge submission fails, the plugin should emit a stdout event such as `chat.bridge.error` with a human-readable message so `run-agent.py` can surface it in the upper panel.

## Textual UI Changes

### Startup Feedback

Move the `Starting interactive chat harness` message to immediately after console creation and before model-resolution and runtime-probe work.

This ensures the user sees feedback instantly on `make chat`.

### Ctrl+C Confirm Modal

Override `ctrl+c` in the Textual app.

Add a `ModalScreen` with:

- message: `Are you sure you want to quit?`
- buttons:
  - `Quit`
  - `Cancel`

If confirmed:

- terminate the main `opencode` process group,
- exit the TUI cleanly.

### Layout

Keep the current fix that removes bottom docking from the chat input so the footer does not overlap it.

## `run-agent.py` Integration Plan

1. Extend chat-mode startup to wait for `chat.bridge.ready`.
2. Store:
   - `bridge_port`
   - `bridge_token`
3. Track one active `sessionID` from the main JSON stream.
4. On chat submit:
   - reject submission if bridge is not ready,
   - reject submission if active `sessionID` is not known yet,
   - POST to the local bridge with the message text,
   - do not spawn a separate `opencode run`.
5. Keep all upper-panel rendering driven exclusively by the original JSON stdout stream.
6. Render bridge failures in the upper panel until a better UX exists.
7. Add quit-confirm modal and process cleanup.

## Suggested New Files

- `.opencode/plugins/chat-bridge.ts`
- `.project/chat-bridge-plan.md`

## Validation Plan

1. Run `make chat`.
2. Confirm the startup message appears immediately.
3. Confirm the TUI opens with no footer/input overlap.
4. Confirm the plugin emits `chat.bridge.ready`.
5. Confirm the bridge learns exactly one active session.
6. Type a prompt in the lower panel.
7. Confirm:
   - no `Connection refused`,
   - no extra `opencode run` spawn,
   - low-latency model response,
   - upper panel receives standard JSON-rendered output.
8. Trigger a bridge failure and confirm it appears in the upper panel.
9. Press `Ctrl+C`.
10. Confirm the quit modal appears.
11. Confirm quitting tears down the process cleanly.

## Decisions

1. Support only one active session at a time.
2. Show bridge failures on the upper panel until a better UX exists.
3. Use localhost transport for now.
