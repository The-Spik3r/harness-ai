---
story: STORY-011
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-011-chat-state-consumer.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: pending
status: COMPLETE
completed: 2026-11-19
---

# Implementation Report - STORY-011: Chat UI state consumes the pipeline's events

**Plan**: `.agents/plans/PRD-021-realtime-streaming/completed/STORY-011-chat-state-consumer.plan.md`
**Epic Branch**: `epic/PRD-021-realtime-streaming`
**Commit**: `pending`

## Summary

`ChatState._do_send` builds one `QueueSink` and passes it to both pipeline branches through `_run_streaming`, which starts the pipeline on the executor, folds the sink's events into seven state vars in windows of at most 100 ms (`live_batch.batches` / `fold`, one `async with self` per window in `_apply_batch`), then awaits the task inside today's `try`. `run_query` forwards a new keyword-only `sink`. The live vars are cleared in the same delta that appends the final bubble (`bubble.kind != "user"`), in the claim block and in the final `finally`.

Reflex flush verified: `.venv/Lib/site-packages/reflex/istate/proxy.py:159-178` (reflex 0.9.6.post1): the outermost `StateProxy.__aexit__` computes `_get_resolved_delta()`, calls `_clean()` and `emit_delta` before releasing the lock; one delta per `async with self`, none if nothing changed. The Risk 5 fallback is not needed.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `run_query(..., sink=None)` forwarded | `app/services/query_pipeline.py` | done |
| 2 | `END`, `batches`, `fold` | `chat_ui/chat_ui/live_batch.py` | done |
| 3 | seven vars, `_clear_live`, `_apply_batch`, `_run_streaming`, wiring | `chat_ui/chat_ui/state.py` | done |
| 4 | `sink=None` on fixed-signature fakes; `_RUN_QUERY_KWARGS` gains `sink` | 5 existing test files | done |
| 5 | new tests | `tests/test_chat_state_streaming.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| `tests/test_chat_state_streaming.py` | 13 passed |
| `tests/test_chat_state.py` | 153 passed |
| `tests/test_chat_history_send.py` + `test_chat_ui_startup_guard.py` + `test_untouched_app.py` (final run, with the new file) | 45 passed (13 + 8 + startup guard + untouched) |
| `tests/test_chat_outcomes_regression.py`, `tests/test_usage_bubble.py` (with history_send, first run) | passed (41 of 43; the 2 failures were fixed, see Deviations) |
| `tests/test_rbac.py -k chat` | 2 passed |
| `tests/test_pipeline_concurrency.py` | 4 passed, 1 skipped |
| `tests/test_query_pipeline_audit_fields.py` | 91 passed with 1 failure (fixed, see Deviations); the door and log_query guards re-run: 4 passed |
| Full suite | GitHub CI on push (user decision) |

## Files Changed

CREATE `chat_ui/chat_ui/live_batch.py`, `tests/test_chat_state_streaming.py`. UPDATE `chat_ui/chat_ui/state.py`, `app/services/query_pipeline.py`, `tests/test_chat_state.py`, `tests/test_chat_history_send.py`, `tests/test_chat_outcomes_regression.py`, `tests/test_usage_bubble.py`, `tests/test_rbac.py`.

## Deviations from Plan

- Seven vars, not six (orchestrator correction): `progress_sent_at` set in the claim block after `_clear_live()`; `_append_and_persist` clears only for non-user bubbles.
- `_run_streaming(fn, *, sink, **kwargs)` takes the pipeline function first so the PRD-013 call-site scan (`test_every_production_pipeline_call_names_its_door`) still finds both `_do_send` sites; a first draft with `sink` first failed that guard.
- `_RUN_QUERY_KWARGS` in `tests/test_chat_history_send.py` gained `"sink"` (comment cites PRD-021 D19); the two tests using it failed otherwise.
- `tests/test_chat_outcomes_regression.py` and `tests/test_usage_bubble.py` fakes also needed `sink=None` (not in the plan's list).

## Tests Written

`tests/test_chat_state_streaming.py`: phase order through both branches (a), streaming off with stage words and identical bubble (b), sink-ignoring pipeline emits no deltas, rate bound at 200 tokens/s (c), mid-stream fault with no partial text (d), success clears the vars and persists one assistant row with no reasoning (e), `progress_sent_at` survives the user bubble, `_clear_live` resets all seven, `batches` (prompt end, leftovers after END, burst grouping), `fold`.

## Acceptance Criteria

- [x] AC1 sink + 100 ms batches, one `async with self` each (a), (c), pure `batches`
- [x] AC2 bubble from `result.response`, live cleared, one row persisted, no reasoning persisted (e)
- [x] AC3 mid-stream fault gives `upstream_error`, no partial text (d)
- [x] AC4 phase order; streaming off keeps stage words and the same bubble (a), (b)
- [x] AC5 <=10 updates/s at 200 tok/s; Reflex flush verified (c) and the proxy.py citation above
