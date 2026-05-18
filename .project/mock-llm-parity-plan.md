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
