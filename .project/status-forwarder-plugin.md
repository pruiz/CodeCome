# Status Forwarder Plugin

## Problem

CodeCome uses `opencode run --format json` to run the OpenCode CLI programmatically.
When OpenCode encounters rate limits (HTTP 429), it automatically pauses and retries with an exponential backoff.
However, because it is running with `--format json`, it suppresses all interactive UI elements and also filters out the `session.status` internal pubsub events. This causes CodeCome (`run-agent.py`) to appear frozen without giving the user any feedback about the rate limit or retry attempt.

## Solution

This local OpenCode plugin (`.opencode/plugins/status-forwarder.ts`) hooks into OpenCode's internal event bus and manually forwards `session.status` events to `stdout` as JSON. 

Then, `tools/run-agent.py` catches these `session.status` events and displays a `rich` console indicator (like `[Rate limit hit: retrying attempt 1...]`) when a retry happens, and clears it when the agent recovers.
