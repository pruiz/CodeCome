# Plan: Deterministic Mock-LLM Parity Testing for opencode run vs opencode serve

**Status:** Implemented ✅
**Date:** 2026-05-18  
**Author:** CodeCome Agent  
**Target:** Replace `tools/opencode-parity.py` with deterministic mock-LLM approach  
**Risk Level:** Low (new testing infrastructure, no production code changes)  

---

## 1. Problem Statement

The existing parity verification in `tools/opencode-parity.py` compares event shapes between:
- `opencode run --format json` (subprocess → ND-JSON stdout)
- `opencode serve` HTTP+SSE (SSE stream → mapped ND-JSON)

**Why it is insufficient:**
- Shape comparison alone does not validate that rendering logic (Rich/plain) handles both paths identically.
- Without a deterministic LLM backend, every run produces different tokens, making regression testing impossible.
- The mock must exercise the full pipeline: OpenCode consumes a deterministic LLM stream, produces ND-JSON/SSE events, and the client renders them.

---

## 2. Goal

Build a deterministic mock LLM **provider** (not replacing OpenCode) that:
1. Speaks standard OpenAI-compatible streaming (`POST /v1/chat/completions`).
2. Is registered as a `"test"` provider in `opencode.json`.
3. Reads a JSON script file defining the exact sequence of deltas and tool calls to emit.
4. Can be referenced as `-m test/mockmodel` in both `opencode run` and `opencode serve`.
5. Allows structural ND-JSON parity comparison between the two OpenCode paths.
6. Optionally captures rendered terminal output for human regression review.

**Key insight:** CodeCome never talks to the MockLLM directly. CodeCome talks to OpenCode. OpenCode talks to the MockLLM via the standard OpenAI chat-completions protocol. The MockLLM only needs to emit deterministic `ChatCompletionChunk` SSE deltas.

---

## 3. Architecture

```
┌─────────────────┐     OpenAI API      ┌──────────────┐     ND-JSON stdout     ┌─────────────┐
│   MockLLM       │◄──────────────────► │ opencode run │ ─────────────────────► │  CodeCome   │
│ (provider.test) │    (SSE chunks)     │              │                      │  parity     │
└─────────────────┘                     └──────────────┘                      │  checker    │
                                                                              └─────────────┘
┌─────────────────┐     OpenAI API      ┌──────────────┐     HTTP+SSE           ▲
│   MockLLM       │◄──────────────────► │opencode serve│ ──────────────────────┘
│ (provider.test) │    (SSE chunks)     │              │
└─────────────────┘                     └──────────────┘
```

### 3.1 Mock LLM Server

**Approach:** Small custom FastAPI/uvicorn server (`tools/mock_llm_server.py`).
- Reads a JSON script file at startup (e.g., `--script tools/mock_llm_scripts/basic.json`).
- Serves standard OpenAI-compatible endpoints:
  - `POST /v1/chat/completions` — streaming SSE with deterministic deltas.
  - `GET /v1/models` — returns `[{"id":"mockmodel"}]`.
- Translates the JSON script into standard `ChatCompletionChunk` SSE events.
- No control endpoints needed; behavior is entirely determined by the script file.

**Why custom instead of `mockllm`:** Minimal tokens, full control, no new dependencies (FastAPI/uvicorn already used elsewhere in the project).

### 3.2 JSON Script Format

The script file is a JSON array of LLM-side actions. The mock server translates these into standard OpenAI `ChatCompletionChunk` SSE events.

```json
[
  {"type": "text_delta", "content": "Hello "},
  {"type": "text_delta", "content": "world!"},
  {"type": "reasoning_delta", "content": "Let me think..."},
  {"type": "tool_call", "id": "call_1", "name": "read_file", "arguments": {"path": "/tmp/foo.txt"}},
  {"type": "done"}
]
```

The mock server translates `tool_call` into the OpenAI `function_call` / `tool_calls` delta format.

### 3.3 Permission Testing

To trigger a `permission` event in OpenCode, the mock LLM emits a `tool_call` for a tool that is **not** auto-approved by the existing `permissions` block in `opencode.json`.
- The CodeCome harness already accepts or rejects permissions automatically based on context + `opencode.json` rules.
- No interactive prompting is required.
- The parity test verifies that both `opencode run` and `opencode serve` emit the permission event correctly before the tool executes.

---

## 4. Provider Registration

Add to `opencode.json`:

```json
{
  "provider": {
    "test": {
      "type": "openai",
      "baseURL": "http://localhost:9999/v1",
      "apiKey": "sk-test",
      "models": ["mockmodel"]
    }
  }
}
```

This allows `-m test/mockmodel` to resolve correctly in both CLI and server contexts.

---

## 5. Test Orchestration

### 5.1 Test Script: `tools/mock_llm_parity.py`

Replaces `tools/opencode-parity.py`. Steps:

1. **Start mock server** on ephemeral port (`python tools/mock_llm_server.py --port $PORT --script $SCRIPT`).
2. **Path A — opencode run:**
   - Execute `opencode run --format json -m test/mockmodel -p "Test prompt"`.
   - Capture stdout ND-JSON to `tmp/parity-run.jsonl`.
3. **Path B — opencode serve:**
   - Execute `tools/run-agent.py` with the same model and prompt (which internally starts `opencode serve`).
   - Instruct `run-agent.py` to dump its internal mapped ND-JSON stream to `tmp/parity-serve.jsonl`.
   - Capture rendered terminal output to `tmp/parity-serve-rendered.txt` (optional).
4. **Compare:**
   - Structural ND-JSON parity: compare `tmp/parity-run.jsonl` and `tmp/parity-serve.jsonl` line-by-line, ignoring `timestamp` and `session_id` fields.
   - Rendered output parity (optional): if Rich/plain text is captured, strip ANSI sequences and compare.
5. **Report:**
   - Exit code 0 if parity passes.
   - Exit code 1 with diff if parity fails.

### 5.2 Integration with `tests/test_new_serve_stack.py`

Add a new test class `TestMockLLMParity` that:
- Auto-starts the mock server via `pytest.fixture(scope="session")`.
- Runs both paths inside the test process.
- Asserts ND-JSON parity.
- Runs in CI (non-interactive, no TTY required).

---

## 6. Acceptance Criteria

- [x] `tools/mock_llm_server.py` exists and serves deterministic OpenAI-compatible SSE streams from JSON script files.
- [x] `tools/mock_llm_scripts/` contains `basic.json`, `with_tool.json`, and `with_permission.json`.
- [x] `opencode.json` contains `provider.test` block.
- [x] `tools/mock_llm_parity.py` exists and can be invoked manually.
- [x] `tests/test_mock_llm_parity.py` exists and passes in CI.
- [x] Existing `tools/opencode-parity.py` is deleted.
- [x] Existing `tests/test_opencode_parity.py` is deleted.
- [x] `Makefile` has a `test-parity` target.
- [x] All 216+ existing tests continue to pass.

---

## 7. Rollout & Decommissioning

1. Implement mock server and provider registration.
2. Write new parity script and tests.
3. Run side-by-side with old parity script for one week.
4. Once new approach is trusted, delete `tools/opencode-parity.py` and `tests/test_opencode_parity.py`.
5. Update `.project/migrate-to-opencode-serve.md` to mark parity testing as completed.

---

## 8. Open Questions / Future Work

- **TODO:** Support multi-turn conversation scripts (for session state testing).
- **Permission event:** The mock script includes a `tool_call` that triggers a permission check under the existing `opencode.json` rules.
- **Rendered terminal output comparison:** Strip ANSI sequences before diffing; use ANSI-aware diffing if a lightweight library is available.
- **Make target:** Add `make test-parity` to the Makefile.

---

## 9. Extension: Comprehensive Multi-Turn Parity Testing

### 9.1 Problem: Current Scripts Are Too Simple

The initial scripts (`basic.json`, `with_tool.json`, `with_permission.json`) only test:
- Single text turn
- One tool per turn
- Two-turn sessions (text → tool → text)

Real CodeCome sessions (from 25 recorded fixtures) show:
- **3–5 tool calls per assistant message** (not 1)
- **No content text before pure tool turns** (content=False)
- **7–22 turns per session** (not 2)
- **Mixed tool types**: `read`, `glob`, `bash`, `write`, `edit` in same session

### 9.2 Solution: Fix Turn-Splitting Heuristic

The current `mock_llm_server.py` splits at the **first** `tool_call`. It must instead split at **turn boundaries**:

**New heuristic:**
- A **turn** = optional leading `text` + **all consecutive** `tool_call`s that follow it.
- Turn ends when the next action is `text` (after tools) or `done`.
- `done` always ends with `finish_reason: "stop"`.
- A turn with tools ends with `finish_reason: "tool_calls"`.
- A turn without tools ends with `finish_reason: "stop"`.

**Multi-turn dispatch (stateless):**
Count `role: "tool"` messages in the incoming request to determine which turn to serve:
- 0 tool messages → Turn 1
- N tool messages (where N = sum of tools in all prior turns) → Turn K

This requires no per-client tracking.

### 9.3 Comprehensive Script Design

Instead of ~10 small scripts, use **2–3 comprehensive scripts** that combine many patterns:

#### `comprehensive.json` — Full tool coverage
8 turns, exercises: `read` (multi), `glob`, `grep`, `write`, `edit`, `bash`, `todowrite`, `skill`.

```json
[
  {"type": "text", "content": "I'll read files."},
  {"type": "tool_call", "id": "call_1", "name": "read", "arguments": {"filePath": "README.md"}},
  {"type": "tool_call", "id": "call_2", "name": "read", "arguments": {"filePath": "AGENTS.md"}},
  {"type": "text", "content": "Let me search."},
  {"type": "tool_call", "id": "call_3", "name": "glob", "arguments": {"pattern": "src/**/*.c"}},
  {"type": "tool_call", "id": "call_4", "name": "grep", "arguments": {"pattern": "main", "path": "src"}},
  {"type": "text", "content": "Now I'll write and edit."},
  {"type": "tool_call", "id": "call_5", "name": "write", "arguments": {"filePath": "tmp/parity-test.txt", "content": "original"}},
  {"type": "tool_call", "id": "call_6", "name": "edit", "arguments": {"filePath": "tmp/parity-test.txt", "oldString": "original", "newString": "modified"}},
  {"type": "text", "content": "Running a command."},
  {"type": "tool_call", "id": "call_7", "name": "bash", "arguments": {"command": "echo hello"}},
  {"type": "text", "content": "Creating todos."},
  {"type": "tool_call", "id": "call_8", "name": "todowrite", "arguments": {"todos": [{"content":"test","status":"completed","priority":"high"}]}},
  {"type": "text", "content": "Loading skill."},
  {"type": "tool_call", "id": "call_9", "name": "skill", "arguments": {"name": "source-recon"}},
  {"type": "text", "content": "Done!"},
  {"type": "done"}
]
```

#### `with_permission_multi.json` — Permission + allowed
3 turns: reads denied `.env` file (permission rejected), then reads allowed `README.md`.

```json
[
  {"type": "text", "content": "Reading secret file."},
  {"type": "tool_call", "id": "call_1", "name": "read", "arguments": {"filePath": "secret.env"}},
  {"type": "text", "content": "Permission denied. Let me read allowed file."},
  {"type": "tool_call", "id": "call_2", "name": "read", "arguments": {"filePath": "README.md"}},
  {"type": "text", "content": "Done."},
  {"type": "done"}
]
```

#### `with_apply_patch.json` — Patch application
2–3 turns: writes a file, then applies a patch to it.

```json
[
  {"type": "text", "content": "Writing base file."},
  {"type": "tool_call", "id": "call_1", "name": "write", "arguments": {"filePath": "tmp/patch-target.txt", "content": "line1\nline2\nline3\n"}},
  {"type": "text", "content": "Applying patch."},
  {"type": "tool_call", "id": "call_2", "name": "apply_patch", "arguments": {"patchText": "*** Begin Patch\n*** Update File: tmp/patch-target.txt\n--- a/tmp/patch-target.txt\n+++ b/tmp/patch-target.txt\n@@ -1,3 +1,3 @@\n line1\n-line2\n+line2_modified\n line3\n*** End Patch"}},
  {"type": "text", "content": "Done."},
  {"type": "done"}
]
```

### 9.4 Tools NOT Covered (Recordings Missing)

| Tool | Coverage | Note |
|---|---|---|
| `task` | ❌ | Creates child session; requires subagent request detection. **TODO: add separate test once recordings available.** |

### 9.5 Mock Server Changes

1. **Fix `_build_chunks`:** Parse script into turns (group consecutive `tool_call`s under preceding `text`).
2. **Fix `do_POST`:** Count `role: "tool"` messages in request to determine turn index.
3. **Emit multi-tool chunks:** Tool calls in same turn use `index: 0, 1, 2...` in `choices[0].delta.tool_calls` array.

### 9.6 Test Changes

1. **Add scripts to `tests/test_mock_llm_parity.py`:**
   - Replace small script list with `comprehensive.json`, `with_permission_multi.json`, `with_apply_patch.json`.
2. **Add unit test for multi-tool chunks:**
   - Verify `test_chat_completions_streaming` returns `tool_calls` with correct `index` values.
3. **Estimated runtime:** 3 E2E tests × ~15s = ~45s total (vs. ~120s for 10 small scripts).

### 9.7 Acceptance Criteria (Extension)

- [ ] `mock_llm_server.py` supports multi-tool turns and stateless multi-turn dispatch.
- [ ] `comprehensive.json` covers `read`, `glob`, `grep`, `write`, `edit`, `bash`, `todowrite`, `skill`.
- [ ] `with_permission_multi.json` covers permission rejection + allowed tool in same session.
- [ ] `with_apply_patch.json` covers `write` + `apply_patch` stateful sequence.
- [ ] All 3 new scripts pass parity test (`opencode run` vs `opencode serve`).
- [ ] Unit tests verify multi-tool chunk indexing.
- [ ] Total test time < 60s for E2E parity suite.
- [ ] `task` tool documented as **TODO** with plan reference.
