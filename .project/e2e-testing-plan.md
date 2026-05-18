# E2E Testing Plan with Docker & aimock

## 1. Provider Configuration (`opencode.json`)
Add the local Docker mock server to `opencode.json`.
```json
  "provider": {
    "aimock": {
      "type": "openai",
      "baseURL": "http://127.0.0.1:4010/v1",
      "apiKey": "mocked-key"
    }
  }
```

## 2. Makefile Fix (`CODECOME_USE_WRAPPER=0` bug)
Fix the Makefile so that `OPENCODE_ARGS` are passed down when the wrapper is bypassed.
```makefile
# Before
opencode run --agent recon "$$(cat prompts/phase-1-recon.md)";
# After
opencode run $$OPENCODE_ARGS --agent recon "$$(cat prompts/phase-1-recon.md)";
```

## 3. Makefile E2E Targets
Add targets to orchestrate the mock server and test executions:

*   `e2e-server-start`: Runs `aimock` in standard replay mode using the CopilotKit Docker image.
*   `e2e-server-stop`: Stops and removes the `aimock` container.
*   `e2e-record`: Starts `aimock` in record mode, pointing to a configurable upstream (default OpenRouter), runs the target phases forcing JSON output, and saves the baseline.
*   `test-e2e`: Resets the workspace, starts `aimock` in replay mode, and executes the Python verification script.

## 4. Verification Script (`tools/test-e2e.py`)
Creates a script that:
*   Invokes the test run via `CODECOME_USE_WRAPPER=0 OPENCODE_ARGS="--format json" CODECOME_MODEL=aimock/$(MODEL) make phase-X`.
*   Captures live stdout (JSON sequence) and compares the agent events (`agent_message`, `tool_call`, `tool_response`) with the recorded baseline.
*   Asserts file artifacts (`itemdb/notes/*.md`, `itemdb/findings/**/*.md`) match the deterministic outputs exactly.
