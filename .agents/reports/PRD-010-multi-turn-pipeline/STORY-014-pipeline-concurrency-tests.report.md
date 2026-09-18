---
story: STORY-014
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-014-pipeline-concurrency-tests.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: 0b0a077
status: COMPLETE
completed: 2026-09-18
---

# Implementation Report — STORY-014: Concurrency: blocked upstream calls do not stall /health, /query or the chat

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-014-pipeline-concurrency-tests.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `0b0a077`

## Summary

One new test module, `tests/test_pipeline_concurrency.py` (648 lines, five tests), turns the
PRD's operator claim into an assertion. `_BlockingUpstream` is an injected `call_openrouter`
that parks its first N callers on a `threading.Event` and announces each arrival on a
`Condition`, so a test waits for "all ten are genuinely inside the upstream" as a fact rather
than as an elapsed duration — nothing in the module sleeps to let progress happen. Four CI
arms then prove: `/health` answers in < 1 s with ten `/query` calls blocked; an eleventh
`/query` returns `SUCCESS` in < 1 s and the run writes exactly eleven audit rows; the same
holds with the ten sends issued through `ChatState._do_send` on its **history** path; and,
with `PIPELINE_MAX_WORKERS=10`, the eleventh call queues without completing while `/health`
still answers — PRD Section 9.2's T6, asserted as intended behaviour. A fifth, env-gated out
of CI, runs the whole shape against a real local HTTP server delaying 60 s, reached by
monkeypatching `openrouter_client._API_URL`.

**No production file changed.** Every claim the story asked for held on the first run of the
code under test; nothing in `app/` or `chat_ui/` needed a fix.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module header, imports, `temp_db` override, `_count_audit_rows`, timeout constants | `tests/test_pipeline_concurrency.py` | ✅ |
| 2 | `_BlockingUpstream` (event + arrival `Condition`) and `_fast_upstream` | `tests/test_pipeline_concurrency.py` | ✅ |
| 3 | `pipeline_pool` fixture — sizing, and release-before-shutdown teardown | `tests/test_pipeline_concurrency.py` | ✅ |
| 4 | AC 1 — `/health` < 1 s with ten `/query` calls blocked | `tests/test_pipeline_concurrency.py` | ✅ |
| 5 | AC 2 — eleventh `/query` `SUCCESS` < 1 s; exactly one audit row each | `tests/test_pipeline_concurrency.py` | ✅ |
| 6 | AC 3 — ten blocked `ChatState._do_send`s on the history path | `tests/test_pipeline_concurrency.py` | ✅ |
| 7 | AC 4 — saturation queues and does not fail (T6) | `tests/test_pipeline_concurrency.py` | ✅ |
| 8 | AC 5 — env-gated 60 s manual smoke against a real socket | `tests/test_pipeline_concurrency.py` | ✅ |
| 9 | Confirm `ASGITransport` exercises anyio's threadpool | `tests/test_pipeline_concurrency.py` | ✅ (confirmed; no fallback needed) |
| 10 | Full suite + no-leak ordering check | N/A | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Module collects | ✅ 5 tests |
| `pytest -q tests/test_pipeline_concurrency.py` | ✅ 4 passed, 1 skipped (11.00s) |
| AC 5 manual smoke, `HARNESS_SLOW_SMOKE=1 … -s` | ✅ 1 passed (69.08s) |
| Ordering/leak check: `test_pipeline_concurrency.py` then `test_pipeline_executor.py` | ✅ 13 passed, 1 skipped |
| Neighbouring suites (`test_query_router`, `test_chat_state`, `test_chat_history_send`, `test_history_off_integration`) | ✅ 196 passed |
| Full suite `pytest -q tests/` | ✅ **2224 passed, 26 skipped, 0 failed** (179.38s) |

There is no linter or formatter in this repo; "validate" is pytest against the local libSQL
dev server.

### AC 5 — measured timings (manual smoke, not in CI)

Against `ThreadingHTTPServer` on a free port, delaying 60 s per request, with
`_API_URL` monkeypatched at it and `CHAT_HISTORY_ENABLED` on:

```
[STORY-014 AC 5 manual smoke]
  upstream delay:        60.0s
  /health while blocked: 15.0ms
  ten chat sends total:  67.73s
```

**`/health` answered in 15 ms while ten chat sends were blocked for a full minute on a real
socket** — the PRD's "< 1 s" with three orders of magnitude to spare. The ten sends
completing in 67.73 s rather than ~600 s is the other half of the claim: they ran
concurrently on the dedicated pool, not one after another.

### A note on suite flakiness during validation

Two intermediate full-suite runs failed with `StorageError`-shaped fixture faults in
unrelated modules (`test_db.py`, then `test_chat_state.py` + `test_query_router.py`), each
time in *different* tests, and each failing test passed when run alone. A control run with
`--ignore=tests/test_pipeline_concurrency.py` produced two fixture errors of the same shape
in yet other modules, which rules this module out as the cause: it is the documented libSQL
dev-server degradation. Restarting `harness-libsql-dev` and re-running gave the clean
2224-passed result recorded above. Per the operational note in the plan, mass fixture errors
mean restarting the container, not bisecting the code.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_pipeline_concurrency.py` | CREATE | +648 |

No production file was touched, which is what the plan required of this story.

## Deviations from Plan

Four, all within the tasks as written:

1. **The `/health` thread spy goes on `route.dependant.call`, not on `app.main.health`.**
   Task 9 said "wrap `app.main.health` with a spy". The route captures the function object at
   import time, so patching the module attribute records nothing. FastAPI computes
   sync-vs-async once when the route is built (`get_request_handler`'s `is_coroutine`,
   verified by reading the installed source) and calls `dependant.call` per request, so a
   sync spy installed there is still dispatched through `run_in_threadpool` — which is the
   property under test. **Result: confirmed.** `/health` runs on a non-`MainThread` thread
   under `ASGITransport`, so the anyio threadpool is exercised as uvicorn exercises it and
   the subprocess fallback the plan held in reserve was not needed.
2. **AC 3 proves its branch with a raising `run_query` stub.** The plan said to set
   `CHAT_HISTORY_ENABLED` and give each state a session, and to say so in a comment. That
   makes the history path *likely* but not *proven* — both branches end in an
   `OpenRouterResult` from the same stub, so no assertion on the result could tell them
   apart. Added `monkeypatch.setattr(chat_state_mod, "run_query", _off_path_not_taken)`,
   which raises: this is `tests/test_chat_history_send.py`'s "absence is proven with a
   raising stub, never with an empty list" applied to the same question.
3. **AC 3 seeds sessions via `chat_sessions.create`** rather than by driving a first send —
   the plan offered both and asked which was used. `create` is the cheaper of the two and
   keeps the arm's upstream stub untouched before the blocking send.
4. **The manual smoke drops the `/query` probe the plan sketched.** Once `_API_URL` points at
   the 60 s server, *every* ingress hits it, so a `/query` there would measure the slow
   upstream rather than the pool's freedom, and its 60 s wait would say nothing. The `/health`
   probe is the one the story's AC 5 actually names ("ten chat sends and a `/health` probe"),
   and the in-process arms already prove `/query` stays fast. The smoke's contribution is
   that the blocking is a real socket rather than a stub. Its arrival-count wait also moved
   onto a class-level `Condition` on the handler, so even this out-of-CI arm waits on a fact
   rather than polling.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_pipeline_concurrency.py` | `test_health_answers_while_ten_query_calls_are_blocked` (AC 1 + the anyio-threadpool confirmation), `test_eleventh_query_succeeds_while_ten_are_blocked` (AC 2 + the eleven-row census), `test_health_and_query_answer_while_ten_chat_sends_are_blocked` (AC 3), `test_saturated_pool_queues_the_eleventh_call_while_health_answers` (AC 4 / T6), `test_manual_smoke_against_a_slow_local_server` (AC 5, env-gated on `HARNESS_SLOW_SMOKE`) |

## Acceptance Criteria

- [x] `PIPELINE_MAX_WORKERS=16`, an injected upstream blocking the first ten calls on a
      `threading.Event`, ten concurrent `POST /query` through
      `httpx.AsyncClient(transport=ASGITransport(app))`, waited until all ten are inside the
      stub → `GET /health` returns 200 in < 1 s
- [x] With the same ten blocked, an eleventh `POST /query` returns `SUCCESS` in < 1 s; after
      the event is set all ten complete with `SUCCESS`, and the run writes exactly eleven
      audit rows
- [x] Ten blocked sends through `ChatState._do_send` on the history path (an active session
      and `CHAT_HISTORY_ENABLED`, proven by a raising `run_query`) → `GET /health` and a
      `/query` each complete in < 1 s
- [x] Control run with `PIPELINE_MAX_WORKERS=10`: the eleventh pipeline call does not
      complete before release (and never reaches the upstream) while `/health` still answers
      — T6 documented as intended
- [x] Manual smoke against a local HTTP server delaying 60 s via a monkeypatched `_API_URL`:
      ten chat sends and a `/health` probe, timings recorded above. Not in CI
- [x] All tasks completed
- [x] No production file changed
- [x] Full suite green (2224 passed, 26 skipped, 0 failed); `tests/test_pipeline_executor.py`
      still passes when run after this module
- [x] Follows existing patterns
