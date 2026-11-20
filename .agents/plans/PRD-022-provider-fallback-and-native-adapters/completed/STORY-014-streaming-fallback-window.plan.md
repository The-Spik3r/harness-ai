---
story: STORY-014
prd: PRD-022
slug: streaming-fallback-window
title: Real-time streamed requests through the chain — fall back before release, never after
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: Streaming fallback window

## Summary

The streamed branch of `run_conversation` (`app/services/query_pipeline.py:1367-1463`) becomes the body of a per-attempt closure `stream_attempt(candidate_route, sent, timeout)`. With a chain (`chained`) `chain.run` drives it, with `released=lambda: released` read live. Without one the same closure is called once from the existing `try` (`:1363`), so `stream_upstream` is called once with today's arguments. All per-attempt state is created inside the closure; only `completion_id`/commit, `released` and `reasoning_sent` are request-scoped. The buffered chain's `prepare`, `permitted`, `on_attempt_failed`, exhaustion handling and `_log_failed_attempt` are reused; no `log_query(` site is added.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-014-streaming-fallback-window.md` (AC text lives there)
- PRD sections: 6.6 (fallback window), 6.7, D9, D10, F5, F7, F8
- Systems affected: `query_pipeline.py` only (the router already maps `ChainExhausted` and post-commit faults: `app/routers/v1.py:315-357`, `_realtime_tail`)

## Design Decisions (binding, from the orchestrator)

1. **Shape.** `chained = len(req_chain.candidates) > 1` (drop `and not streamed_step`, `:1018`). `RequestNeeds.streaming=streamed_step` (`:1311`), so a non-streaming candidate is skipped `capability` (AC3). Pick the attempt function once: `attempt_fn = stream_attempt if streamed_step else <buffered attempt>`; the buffered one (`:1261-1278`) is untouched. Keep `relaxed = route.relaxes_input()` (`:1026`) verbatim.
2. **Fresh per-attempt state**, created at the top of the closure: `received_text`, `received_calls`, `events`, `raw_reasoning`, `content_gate`, `reasoning_gate` (today `:1150-1175`; the gate construction moves in), `gate_result`, `reasoning_text`, `stream_redaction_divergence`, `phase_now="waiting"`, `stream_request = UpstreamRequest(list(sent.messages), candidate_route.upstream_model, params, tools, candidate_route.model)`. `completion_id` is request-scoped: the `if completion_id is None:` commit block (`:1376-1384`) is kept as is, so commit fires on the first event of whichever attempt produces one, once; a later attempt neither re-commits nor resends the role chunk. At the start of an attempt after the first, call `safe.phase("waiting")` (repeating `waiting` is allowed; the initial one at `:1141` stays). `dropped_params_for(candidate_route, stream_request)`, `answer_prepared` and `attempt_route` come from the attempt (STORY-008 note); `_merge_ignored_params(..., route)` at the success row then reads the answering route.
3. **Window rule.** `released = True` only where the code already sets it: a non-empty `content()`/`reasoning()` sink call, including the end-of-stream remainders (`:1398-1410`, `:1425-1438`). Receipt never counts, an empty `TextDelta("")` never reaches the gate (`:1393`), and a gate still holding text has released nothing: that text dies with the attempt. Tool-call deltas are only accumulated into `received_calls` (`:1413-1419`) and never forwarded mid-stream (PRD-021 D6/T1); tools are released after the stream by step 7c, after `chain.run` has returned, so they cannot close the window during a stream. That is the whole of "tool release closes the window". A non-realtime streamed request (progress only) never calls `content()`, so `released` stays False and every pre-answer fault may fall back.
4. **Failure semantics, exactly one row per attempt.**

| Fault | Charge (T6) | Row written by | Next candidate |
|---|---|---|---|
| (a) `UpstreamError`, fallback-eligible, `released` False | none | `on_attempt_failed` (`:1280`): attempt n, `attempt_route` columns, NULL usage | yes |
| (b) `UpstreamError`, `released` True (or non-eligible) | closure `except`: estimate of what THIS attempt received, before the row | `on_attempt_failed` (`chain.run` calls it, then re-raises: `upstream/chain.py:200-204`) | no |
| (c) gate `PiiRedactorError` | closure `except`, same rule (`released`, not BYOK) | the closure `except`, via `_log_failed_attempt` (attempt number counted in the closure, route `candidate_route`), only when `chained`; unchained keeps the outer `except` (`:1493`) | no (`chain.run` propagates it unrecorded, `chain.py:123`) |

   Single-write rule: `on_attempt_failed` only ever sees `UpstreamError`; the closure writes only for `PiiRedactorError` and only when chained; the outer `try/except` (`:1468`) writes only on the unchained path. The chain block stays outside that `try` (as today), so neither (b) nor (c) can double-write. `prepare`'s `PiiRedactorError` row (`:1253`) is a different fault (input redaction, before any attempt) and is not touched. Move the T6 charge block (`:1474-1492`) into a helper `_charge_received(route, sent_messages, received_text, received_calls)` called from the closure's `except (OpenRouterError, PiiRedactorError)` before the re-raise; the outer `except` keeps only the row (the charge was a no-op for the buffered call, `released` is False). (d) Exhaustion: the existing `except ChainExhausted` (`:1328`) is reused unchanged: no attempt ran -> one row (`attempt=None`); before commit the router returns the JSON 502 (`translate_exhausted`, `retry-after` possible); after commit `v1._realtime_tail`/`_sse_outcome` emits the SSE `error` event.
5. **Health/charging.** `chain.run` records health and counts; the pipeline adds nothing (`test_pipeline_counts_nothing_itself`, `tests/test_query_pipeline_chain.py:520`). `charge` at 7b (`:1527`) runs once, for the answering attempt's returned `OpenRouterResult`. `timeout` from the chain is passed to `stream_upstream(timeout=)` only when not None (stubs are `(messages, model, api_key=None, **kw)`); on a loaded chain it is always set, and is the only total bound for anthropic streams (STORY-007 note). Unchained: no `timeout` kwarg, as today.

## Closure contract

- Signature `stream_attempt(candidate_route, sent, timeout) -> OpenRouterResult`; `nonlocal released, reasoning_sent, completion_id, gate_result, reasoning_text, stream_redaction_divergence, answer_prepared, attempt_route, stream_attempt_no`. Increment `stream_attempt_no` on entry (equals `chain.run`'s counter; 1 unchained). Reset `gate_result`, `reasoning_text`, `stream_redaction_divergence` on entry so a failed attempt's divergence flag never reaches the next row (`_log_failed_attempt` reads it live, `:1215`).
- Call: `stream_upstream(list(sent.messages), model=model if not chained else candidate_route.model_id, api_key=openrouter_api_key if candidate_route is primary_route else None, **extra, [timeout=])`. `primary_route` must be bound before the `if chained:` block for both paths (today only inside it, `:1242`). Keeps D15 (key reaches only the primary).
- Body: today's loop `:1373-1419`, end-of-stream gates `:1423-1447`, and `dataclasses.replace(collect(...))` `:1454-1463` using `candidate_route`/`stream_request`, `model_used=model`. The `logger.info("realtime stream committed ...")` stays in the commit block.
- Unchained call site: `openrouter_result = stream_attempt(route, prepared, None)` replaces the inline body (`:1367`). The `chain_outcome is not None` branch (`:1364`) is unchanged and now serves streamed too; lines `:1353-1361` copy route/relaxed/entities/messages from the answering attempt. `gate_result`/`reasoning_text` hold the answering attempt's values because only the last attempt can return.
- `_upstream_result` (`:1776`) and `AnsweredBy` (`:1761`) work unchanged (`chain_outcome` set). SSE carries only `model` (STORY-013 note), nothing to add.

## Skills In Use

None (`.agents/skills` holds only `frontend-design`; no UI work).

## Patterns to Follow

| Category | Source | Mirror |
|---|---|---|
| Closures/rows | `query_pipeline.py:1247-1292` (`prepare`, `attempt`, `on_attempt_failed`) | same nonlocal style; rows only through `_log_failed_attempt` (`:1194`) |
| Census | `tests/test_query_pipeline_routing.py` (11 textual `log_query(` sites) | add no `log_query(` text, not even in a comment |
| Chain tests | `tests/test_query_pipeline_chain.py:116-190` (`chained` fixture, `Upstream`, `_run`) | scripted stream stubs and `spies` as in `tests/test_query_pipeline_streaming.py:98,309` |
| Error mapping | `v1.py:315-357`, `chain.py:200-204` | no change; assert through them |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `app/services/query_pipeline.py` | UPDATE | closure, `chained`/`needs.streaming`, charge helper, comments (replace the STORY-014 pointer at `:1012-1015`) |
| `tests/test_query_pipeline_chain_stream.py` | CREATE | the cases below; registry whose candidates declare `streaming: true` (the `_REGISTRY` in the chain test file does not, so every candidate would be skipped `capability`) via `tests/_providers.py` |
| `tests/test_query_pipeline_chain.py` | UPDATE | `test_streamed_request_on_chained_model_stays_single_candidate` (`:540`) asserts the old rule (`ran == []`): rewrite or move it with a PRD-022 STORY-014 comment. If renamed or removed, register the old name in `_DELIBERATELY_SUPERSEDED_TESTS` (`tests/test_pii_redaction_integration.py`). The only pre-existing assertion expected to change: report it |

## Tasks

1. **Chained flag and needs** (`:1018`, `:1311`): drop the exclusion, `streaming=streamed_step`, update the comment. Validate: `python -c "from app.main import app"`.
2. **Charge helper** from `:1474-1492`, same formula; the outer `except` keeps the row only. Run `tests/test_query_pipeline_streaming.py` (T6 spies).
3. **Closure** per the contract; the unchained path calls it once. Bind `primary_route` early. Run the PRD-021 streaming files, unmodified.
4. **Chain wiring**: `attempt=attempt_fn`, `released=lambda: released` (buffered keeps `lambda: False`), `stream_attempt_no` for the Pii row. `on_attempt_failed` unchanged.
5. **Tests**: new file, then the `:540` test. Run the census (`test_query_pipeline_routing.py`) and `test_query_pipeline_pii_relaxation.py`.

## End-to-End Tests (new file; `_run` with a Sink stub, real `chain.run`)

- [ ] Primary `stream_upstream` raises 503 before any event -> fallback; one `committed`, success row attempt 2 + failed row attempt 1 (AC1).
- [ ] Primary yields events (role/commit, `waiting`, held gate text, nothing released), then raises -> fallback in the same response: one `committed`, one role chunk, failed row (attempt 1, NULL usage, no charge) + success row; the answer, the row `response` and the sink content contain none of the primary's text; `waiting` may repeat (AC1, AC4).
- [ ] Post-release fault: primary releases `content()`, then raises -> `stream_upstream` called once, v1 stream ends with an `error` event, one `success=0` row (attempt 1) after the `charge` spy call, estimate of what arrived (AC2).
- [ ] Gate `PiiRedactorError` (monkeypatch the final `_redact`) -> no fallback, exactly one failure row (`attempt=1`, primary columns), T6 charge iff released (case (c)).
- [ ] Candidate without `streaming` capability skipped `capability`; the success row's `skipped_providers` lists it (AC3).
- [ ] In-stream `UpstreamError(upstream_status=529, retryable=True)` pre-release falls back; a prior `TextDelta("")` does not close the window (AC4, STORY-007 note).
- [ ] Reasoning release closes the window like content; `reasoning_shown` true on the failure row.
- [ ] Every candidate fails pre-release: before commit, router JSON 502 (+`retry-after` when a candidate was open); after commit, SSE `error` event; one failure row per attempt, no exhaustion row.
- [ ] `api_key` reaches only the primary; `timeout=` reaches every stream call on a chain, absent unchained.
- [ ] No chains file: `stream_upstream` called once, no `timeout` kwarg, rows `attempt=1` (AC5).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider \
  tests/test_query_pipeline_chain_stream.py tests/test_query_pipeline_chain.py \
  tests/test_chain_runner.py tests/test_query_pipeline_streaming.py \
  tests/test_query_pipeline_audit_realtime.py tests/test_stream_upstream_seam.py \
  tests/test_v1_realtime.py tests/test_query_pipeline_routing.py \
  tests/test_query_pipeline_pii_relaxation.py tests/test_untouched_app.py
```
Add `tests/test_pii_redaction_integration.py` only if a test is renamed or removed. One pytest at a time; restart `harness-libsql-dev` if fixtures error. Full suite: GitHub CI.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test |
|---|---|---|
| AC1 fall back before release, same SSE, one commit | 1, 3, 4 | `test_query_pipeline_chain_stream.py`: open-error and events-then-fail cases |
| AC2 post-release fault: no attempt, error event, charged row | 2, 3, 4 | post-release case with spy order |
| AC3 non-streaming candidate skipped `capability` | 1 | capability case |
| AC4 fresh per-attempt state, no leak, `waiting` may repeat | 3 | held-text, empty-`TextDelta`, 529 cases |
| AC5 no chain: one `stream_upstream`, PRD-021 tests unmodified | 3 | no-chain case + `test_query_pipeline_streaming.py` |

## Risks / open points

- `route.model_id` vs `model` unchained: the plan keeps `model` unchained for byte-identical calls; simplify only if equal everywhere.
- The `:540` test contradicts the story by design (it pinned STORY-012's single-candidate rule).
- A `UpstreamError` from `collect()` after a remainder release is a post-release fault (no fallback), by the window rule.
- Local libSQL is slow: keep DB-backed cases few, share one `temp_db` setup.
