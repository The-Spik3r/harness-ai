---
story: STORY-013
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-013-buffered-sse.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: 2b1773a
status: COMPLETE
completed: 2026-10-26
---

# Implementation Report — STORY-013: Buffered SSE: commit on upstream start, keep-alive, chunk sequence, include_usage, post-commit error

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-013-buffered-sse.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `2b1773a`

## Summary

`stream: true` on `POST /v1/chat/completions` is now the buffered stream that PRD Sections 6.4 and 7.6
describe, replacing the 501 placeholder.

The router's `_Upstream` wrapper doubles as the commit signal. On the pipeline thread it sets `called`
and, through `loop.call_soon_threadsafe`, an `asyncio.Event`, before it delegates to `call_openrouter`.
`chat_completions` starts the one `run_in_pipeline(run_conversation, ...)` call as a task, with
`streamed=call.stream`, and waits for the first of the task and the signal.

- **The wrapper was never called.** The request gets the same JSON response as the non-streaming path,
  with the same status. That covers every verdict and every pre-upstream fault.
- **The wrapper was called.** The request commits to a `StreamingResponse`. The new `app/services/v1_sse.py`
  writer sends `: keep-alive` every `V1_SSE_KEEPALIVE_SECONDS` until the task resolves. It then sends the
  content chunk, the finish chunk, the usage chunk (only with `include_usage`) and `[DONE]`. A post-commit
  fault is instead a single `data: {"error": ...}` event with no `[DONE]`.

The pipeline is never cancelled. `v1_sse.detach` holds every pipeline task until it finishes and retrieves
its outcome, so a client disconnect leaves no "exception was never retrieved" in the log. The row is still
written and the tokens still charged.

The outcome mapping (`_outcome`) is now shared by the JSON and SSE renderers, so a fault has the same error
object on both paths.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | SSE wire format, chunks from a `ChatCompletion`, error event | `app/services/v1_sse.py` | ✅ |
| 2 | Commit wait, `detach`, keep-alive writer | `app/services/v1_sse.py` | ✅ |
| 3 | Storage-free unit tests | `tests/test_v1_sse.py` | ✅ |
| 4 | Router: start signal, one task-wrapped pipeline call, shared outcome, commit branch | `app/routers/v1.py` | ✅ |
| 5 | Retire the 501 placeholder test | `tests/test_v1_router.py` | ✅ |
| 6 | Every verdict and pre-upstream fault, streamed and not (AC 1) | `tests/test_v1_errors.py` | ✅ |
| 7 | HTTP tests: sequence, usage, order, post-commit faults (ACs 2, 3, 4) | `tests/test_v1_sse.py` | ✅ |
| 8 | Direct-ASGI tests: keep-alive timing, disconnect on spec 2.3 and 2.4, 20 streams with `/health` (ACs 3, 5) | `tests/test_v1_sse.py` | ✅ |
| 9 | Regression sweep | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | n/a (backend only) |
| `tests/test_v1_sse.py` | ✅ 31 passed (15 without storage, 16 `db`) |
| `tests/test_v1_errors.py` | ✅ 65 passed (verdicts and pre-upstream faults now run as json and sse) |
| Targeted regression (`test_v1_*`, audit-field and PII-profile scans, outcome regression, concurrency, multiturn, PII integration) | ✅ 1046 passed, 1 skipped |
| Full suite (throwaway libSQL :8086) | ✅ 4842 passed, 27 skipped in 327 s, no flakes |
| Mutation check: `detach` removed from the router | `test_disconnect_then_upstream_failure_logs_nothing_unhandled` fails, as intended |
| E2E | ✅ 4/4, plus a post-commit 503 |

E2E setup: live uvicorn on `:8765`, a throwaway libSQL on `:8087`, and a scratchpad `ThreadingHTTPServer`
as the upstream through `OPENROUTER_BASE_URL` (3 s delay). `V1_SSE_KEEPALIVE_SECONDS=1`.

1. Keep-alives arrived at 1.09 s and 2.11 s, then the chunks and `[DONE]` at 3.11 s. The response was
   `200 text/event-stream; charset=utf-8` with `cache-control: no-cache`, `x-accel-buffering: no` and no
   `x-harness-audit-id`.
2. With `include_usage`, the usage chunk (`choices: []`, 11/5/16) came before `[DONE]`.
3. An injection prompt with `stream: true` returned `400 application/json` with `suspicious_pattern`.
4. `openai` 3.36.1 with `stream=True` and `include_usage` reassembled "Hello from the stub." and read the
   usage. A post-commit 503 raised `openai.APIError`, and a block raised `BadRequestError`. That block was
   `duplicate_request`, because the injection prompt had already been sent once in step 3.
5. Every one of the 8 rows had `ingress='v1'`, `profile='code'` and `streamed=1`. `usage_daily` showed the
   4 answered requests charged (44 input / 20 output tokens).

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/v1_sse.py` | CREATE | +127 |
| `app/routers/v1.py` | UPDATE | +150/-58 |
| `tests/test_v1_sse.py` | CREATE | +887 |
| `tests/test_v1_errors.py` | UPDATE | +59/-36 |
| `tests/test_v1_router.py` | UPDATE | +5/-16 |

## Deviations from Plan

- **Every pipeline is detached, not only streamed ones.** A non-streamed request whose handler is cancelled
  would otherwise leave the task's outcome unretrieved.
- **The plain JSON path waits with `asyncio.wait({pipeline})`** and maps the outcome in `_outcome`. That
  matches the plan's code sketch. The plan's prose named `ChatCompletion` plus the audit id as the success
  return, but the audit id is already `completion.harness.audit_id`, so `_outcome` returns the
  `ChatCompletion` alone.
- **The HTTP tests use `TestClient`, as the rest of the `/v1` suites do, rather than `AsyncClient`.** Both
  collect the whole body. `AsyncClient` over `ASGITransport` is used where concurrency needs it (20 streams
  plus `/health`).
- **The disconnect tests run on ASGI spec `2.3` (uvicorn's value) and `2.4`, not `2.0` and `2.4`.**
  Starlette takes the same cancel path for every spec below 2.4.
- **Charging is verified from `usage_daily` rather than with a spy.** The real `charge` ran and its counters
  were read back.
- **The full suite ran without the keep-awake wrapper.** The PowerShell `-ExecutionPolicy Bypass` launch was
  refused in this session.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_v1_sse.py` | No storage: the chunk sequence with and without usage; finish_reason passthrough; the error event; keep-alives until the outcome; no keep-alive once done; `aclose` and cancel leave the pipeline running; `detach` silences the never-retrieved log (with a control case); `detach` holds until done; `wait_for_commit` on the signal and on completion; `_sse_events` for a success, an unexpected exception and a verdict after commit. Over HTTP: the answered sequence and headers; the usage chunk; `include_usage` without `stream`; streamed content equal to non-streamed; keep-alive order (3.5 s, 1 s); four post-commit faults matching the JSON error object, with rows; an immediate upstream failure still commits; an unexpected post-commit exception becomes `internal_error`. Direct ASGI: keep-alive arrival times; disconnect writes the row and charges (spec 2.3 and 2.4); disconnect followed by an upstream failure logs nothing; `/health` under 200 ms with 20 streams waiting |
| `tests/test_v1_errors.py` | The `stream` fixture (json/sse) on all 9 verdict tests and the storage and input-redaction fault tests; JSON content-type asserted; `streamed` asserted on the rows |

## Acceptance Criteria

- [x] With `stream: true`, a request blocked or faulted before the upstream call gets the same JSON error and status as without `stream`, never `text/event-stream`; its row has `streamed=1`.
- [x] An answered streamed request is `200 text/event-stream` with `Cache-Control: no-cache` and `X-Accel-Buffering: no`. Its events are exactly content, finish, usage (only with `include_usage`) and `[DONE]`, and every `id` is `chatcmpl-harness-{audit_id}`.
- [x] With a 3.5 s upstream and a 1 s interval, at least three `: keep-alive` lines arrive before the first `data:` line and none after it.
- [x] A post-commit upstream or output-redaction failure ends with one `error` event (the STORY-011 object) and no `[DONE]`; its rows match the non-streaming case.
- [x] After a client disconnect, the success row is written and the tokens charged, and the loop logs no unhandled exception. With 20 concurrent streams, `/health` answers within 200 ms.
