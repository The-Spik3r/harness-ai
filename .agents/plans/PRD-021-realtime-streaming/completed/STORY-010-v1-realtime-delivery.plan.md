---
story: STORY-010
prd: PRD-021
slug: v1-realtime-delivery
title: /v1 real-time SSE and reasoning_content
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-18
---

# Plan: /v1 real-time SSE and reasoning_content

## Summary

The `/v1` router computes `Visibility` once (the pipeline's own classmethod) and, when the switch is on and `visibility.upstream_streamed`, passes a `_CommitSink(QueueSink)` to `run_conversation`. With `stream: true` and `visibility.realtime`, the response is `v1_sse.realtime_events(...)` (PRD 6.6); every other request keeps today's code path. `reasoning_content` is added to `ChunkDelta`/`AssistantMessage` (key absent when None) and filled from `QuerySuccessResponse.reasoning` for buffered bodies.

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-010-v1-realtime-delivery.md`
- PRD: 6.3, 6.6, F8, T1, T5, T13, D9, D15, D16, D21, D22, 10 (reasoning_content)
- Systems: `v1.py`, `v1_sse.py`, `v1_schemas.py`, `v1_translate.py`, `delivery.py`, `query_pipeline.py` (2 small seams, see Design), `schemas.py`, `config.py` (comment only)

## Design Decisions

**D-A. One rule for "real time", in `Visibility.compute` (`delivery.py:117-142`).** Add `streamed: bool = True`; after computing, `if ingress == "v1" and not streamed: realtime = False` (and `upstream_streamed` follows from the new `realtime`). Pipeline step 2d (`query_pipeline.py:680-686`) passes `streamed=streamed`. Reason: `stream:false` with `stream:realtime` must stay today's (PRD 6.4: `/v1 stream:false` column), and the pipeline recomputes visibility from grants, so the router cannot override it from outside. Default `True` keeps every other caller and `tests/test_delivery.py` unchanged. The router calls `Visibility.compute(..., ingress="v1", streamed=call.stream)` with `caps` from `authz.authorize_route(identity, model).capabilities` (`PermissionDenied` -> no sink; the pipeline's single denial applies, T3) and `holds()` (T8). It computes nothing when `settings.STREAMING_ENABLED` is False (D22). No second copy of the rule.

**D-B. Sink iff `visibility.upstream_streamed`** (realtime OR reasoning). Needed because reasoning is only collected by the pipeline when it streams upstream (`query_pipeline.py:1093-1102`), so rows 3/4 of PRD 6.4 (reasoning without real time, stream or not) require a sink too. Realtime AND `call.stream` -> `realtime_events`. Otherwise the sink's queue is never read and the existing JSON / `stream()` paths render (with `reasoning_content` from `result.reasoning`). **Orchestrator correction (3.2):** in that non-realtime case the `_CommitSink` must not accumulate an unread queue: construct it with `forward=False` (or equivalent) so `stage/phase/content/reasoning` puts are dropped and only `committed()` (the commit signal) acts. Test it: a non-realtime reasoning stream leaves the queue empty. Pass `sink=` to `run_in_pipeline` only when not None (`**kwargs`), so test stubs of `run_conversation` are untouched.

**D-C. The sink path never calls `_Upstream`** (the pipeline uses `stream_upstream`, `query_pipeline.py:1062`), so `upstream.result` is empty. Add a private `_upstream_result` + `upstream_result` property on `QuerySuccessResponse` (`schemas.py:100-114` pattern, never serialized), set at `query_pipeline.py:~1442` when `streamed_step`. `_outcome` (`v1.py:251`) uses `upstream.result or result.upstream_result` (replaces the assert at `:~308`). Orchestrator note: pydantic `__eq__` compares private attrs; run the streaming/chat pipeline tests; if one breaks, narrow to `ingress == "v1"` instead of editing tests.

**D-D. Commit.** `_CommitSink(QueueSink)` in `v1.py`: attrs `called` (set on the pipeline thread) and `started` (`asyncio.Event`, set via `call_soon_threadsafe`), `committed()` sets both then `super().committed()`. `wait_for_commit(pipeline, sink.started)`; commit iff `call.stream and (upstream.called or sink.called)` (`v1.py:419`). A pre-stream fault or verdict means no `committed`, so JSON with the real status as today.

**D-E. `realtime_events(queue, pipeline, *, created, model, tail, interval, coalesce_s, on_close) -> AsyncIterator[str]`** in `v1_sse.py` (reads no settings; router passes the values). `tail(pipeline)` returns `Union[Tail, List[str]]`; `Tail` is a frozen dataclass `(completion: ChatCompletion, notes: Tuple[str, ...])` defined in `v1_sse.py`. Order: role chunk `ChunkDelta(role="assistant", content="")` on `CommittedEvent` (id = its `completion_id`, kept for every later chunk; `created`/`model` fixed by the router so all chunks agree); `ReasoningEvent` -> `delta.reasoning_content`; `ContentEvent` -> `delta.content`; `StageEvent`/`PhaseEvent` dropped (T5). Loop = one persistent `queue.get()` task raced with `pipeline` in `asyncio.wait(..., timeout=...)`, never cancelled mid-wait (as `stream()` at `v1_sse.py:121-141`); timeout = min(time to coalesce flush, time to next keep-alive measured from the last yielded bytes).
- **Coalescing (D21):** pending buffer `(kind, parts, since)`. A delta of the other kind flushes first; a window of `coalesce_s` is measured from the first pending delta (flush on timeout); `coalesce_s == 0` flushes every delta; flush again before the tail. Applies to gated and ungated text alike. Concatenated text must not change.
- **Drain guarantee:** the pipeline thread's `call_soon_threadsafe(put_nowait)` calls precede the executor future's own `call_soon_threadsafe` completion, the loop's ready queue is FIFO, and `pipeline` is a task awaiting that future (one more iteration), so every put has run once `pipeline.done()`. After done: `await asyncio.sleep(0)`, then `get_nowait()` until `QueueEmpty`, feeding the same handler, then flush, then the tail. A test puts 2000 events from a worker thread and returns at once.
- **Tail (only from `Tail`, never from events, T1):** one chunk per `completion.choices[0].message.tool_calls` (`ChunkToolCall(index, id, function)`, as `completion_events` `v1_sse.py:73-78`); then one content delta per note: `note` if no content was sent yet, else `"\n\n" + note` (so the concatenation equals `tool_release.content_with_notes(redacted, notes)`, `tool_release.py:121`); then the finish chunk (`completion.choices[0].finish_reason`, which `translate_result` took from `tool_release` or the upstream); the usage chunk (`completion.usage`, `choices=[]`) only when `include_usage` (router passes `tail` closed over it); then `DONE`. A `list[str]` tail (error) is yielded as is, no `[DONE]` (D16).
- **`finally:`** `on_close(completed)`; the router's callback calls `sink.close()` and, when `completed` is False, logs one INFO `v1 realtime stream disconnected: user_id=%s completion_id=%s` (never content). `detach(pipeline)` already runs at `v1.py:409`, so the pipeline finishes and writes `success=1` (D15). `_SafeSink` is not touched.

**D-F. Faults / T13.** Extract the body of `_sse_events` (`v1.py:316`) into `_sse_outcome(pipeline, upstream, identity) -> Union[ChatCompletion, List[str]]` (the existing try/except, the `internal_error` log, the verdict WARNING, the `error_event` list). `_sse_events` becomes a two-line wrapper with an identical result (`completion_events` for a `ChatCompletion`); the realtime `tail` calls `_sse_outcome` and wraps a `ChatCompletion` plus `result.tool_outcome.release.notes` into `Tail`. So the code mapping (`_fault_code`, `PiiRedactorError` -> `redaction_failed`) and the T13 warning are the same code. `completion_events` is not edited for realtime.

**D-G. `reasoning_content` (D9, O5: never `reasoning`).** `ChunkDelta` gets `reasoning_content: Optional[str] = None`; its serializer already keeps only set fields (`v1_schemas.py:229-246`), and additionally drops `reasoning_content` when None. `AssistantMessage` (`:134`) gets the field and its serializer pops it when None (`content: null` and `tool_calls: null` keep their existing rules; field order role, content, tool_calls, reasoning_content). `translate_result` (`v1_translate.py:621,637`) passes `reasoning_content=result.reasoning` on both message constructions (a pure attribute read, no import). `completion_events` (`v1_sse.py:66-69`) adds `reasoning_content=choice.message.reasoning_content` to the role chunk only when it is not None (identical output otherwise): this is the buffered `stream:true`-with-`reasoning:view` case and the one necessary edit to that function; orchestrator to confirm.

## Skills In Use

None apply (`.agents/skills/frontend-design` is UI-only; no `chat_ui/` change).

## Patterns to Follow

| Category | Source | Mirror |
|----------|--------|--------|
| Async generator that never cancels the pipeline | `v1_sse.py:121-141` | `asyncio.wait` + timeout, keep-alive |
| Private result attribute | `schemas.py:100-114` | `_upstream_result` |
| Set-ness serializers | `v1_schemas.py:134-152,229-246` | key absent when unset |
| Error events | `v1.py:316-357` | `_sse_events` reuse |
| Disconnect log | `v1.py:272` (`user_id=`, never content) | INFO with `completion_id` |
| Direct-ASGI streaming tests (live chunks) | `tests/test_v1_sse.py` `_drive` (header comment :17-24), disconnect test `:817` | timing + disconnect |
| File-mode registry + grants | `tests/test_query_pipeline_streaming.py:47-155` (`provider_file`, `_YAML`, `ROLE_PERMISSIONS` patch) | all realtime tests |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/delivery.py` | UPDATE | `Visibility.compute(streamed=)` (D-A) |
| `app/services/query_pipeline.py` | UPDATE | pass `streamed=` at step 2d; set `success._upstream_result` (D-C) |
| `app/models/schemas.py` | UPDATE | private `_upstream_result` + property |
| `app/models/v1_schemas.py` | UPDATE | `reasoning_content` on `ChunkDelta`, `AssistantMessage` |
| `app/services/v1_translate.py` | UPDATE | `reasoning_content=result.reasoning` |
| `app/services/v1_sse.py` | UPDATE | `Tail`, `realtime_events`; role chunk reasoning in `completion_events` |
| `app/routers/v1.py` | UPDATE | `_visibility`, `_CommitSink`, `_sse_outcome`, branch in `chat_completions` |
| `app/config.py` | UPDATE | comment at `:391-394` (STORY-010 reads `STREAM_COALESCE_MS`; default 50 already present and validated `:774`) |
| `tests/test_v1_realtime.py` | CREATE | all STORY-010 tests |
| `tests/test_delivery.py`, `tests/test_v1_schemas.py`, `tests/test_v1_translate_result.py` | UPDATE | additions only |

## Tasks

1. **Schemas + translate** (D-G). Validate: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_v1_schemas.py tests/test_v1_translate_result.py`. Add tests: byte-identical dumps without the field (golden strings), key absent not `null`, present when given, `v1_translate` AST purity test still passes.
2. **`Visibility.compute(streamed=)`** + pipeline `streamed=streamed` + `_upstream_result` (D-A, D-C). Add `tests/test_delivery.py` cases: v1 + `streamed=False` -> `realtime False`; chat/None unaffected. Validate: `tests/test_delivery.py tests/test_query_pipeline_streaming.py`.
3. **`v1_sse.realtime_events` + `Tail`** (D-E) and the `completion_events` role-chunk tweak. Pure-async unit tests with a fake queue and future in `tests/test_v1_realtime.py`: order, keep-alive while idle, coalescing (never across kind, window from first delta, flush before tail, window 0), drain of a threaded burst, error list without `[DONE]`, `finally` calls `on_close(False)` on `aclose()`.
4. **Router** (D-B, D-D, D-F): `_visibility`, `_CommitSink`, `_sse_outcome`, `StreamingResponse(v1_sse.realtime_events(...))` with the same headers as `v1.py:~424`; `settings.STREAM_COALESCE_MS / 1000` and `V1_SSE_KEEPALIVE_SECONDS` read per request. Everything else in the function is unchanged (`translate_request`, `_Upstream`, `detach`).
5. **Router tests** (below), then guards.

## "Unchanged" (D22) is proved by

(a) with `STREAMING_ENABLED` False (default; `tests/conftest.py` does not set it), `_visibility` returns None before any call, so `sink` is not passed and the request path is the old one; (b) the suites that pin today's bytes run unmodified: `tests/test_v1_router.py`, `test_v1_sse.py`, `test_v1_errors.py`, `test_v1_tools.py`, `test_v1_tools_registry.py`, `test_v1_models*.py`, `test_v1_translate_*.py`, `test_v1_schemas.py`, `test_v1_query_isolation.py` (their `_Upstream` stubs raise on a streamed call, so a stray streamed upstream fails them); (c) new tests with the switch ON but no grant, and legacy mode, assert the stub saw a request without `stream` and the body equals the switch-off body; (d) `tests/fixtures/prd020_legacy/` via its existing suite. None is edited.

## End-to-End Tests (`tests/test_v1_realtime.py`; file-mode registry, grants `stream:realtime` / `reasoning:view` via `ROLE_PERMISSIONS`)

Inject the stream with `monkeypatch.setattr("app.routers.v1.run_conversation", functools.partial(run_conversation, stream_upstream=fake))`, or the stub (`scripts/stub_openrouter.py`, thread, as `tests/test_stub_openrouter.py:80`).
- [ ] AC1: sequence over direct ASGI: role chunk first, content deltas, tool calls, notes, finish last, usage only with `include_usage`, `[DONE]`; every `id` matches `^chatcmpl-harness-rt-[0-9a-f]{32}$` and equals the row's `completion_id`; no `harness` key anywhere; `STREAM_COALESCE_MS` caps chunk count for 40 one-char deltas; gate on (`chat`-like policy) merges too.
- [ ] AC2: both grants -> `delta.reasoning_content`, never a `reasoning` key; reasoning only -> `stream:false` body `message.reasoning_content` and `stream:true` role chunk carries it; no grant -> key absent in all three shapes.
- [ ] AC3 (T1, T5): scripted `DROP TABLE` in nine fragments with text before/after (stub `chunk_chars`): no fragment substring in any chunk before the note; note is a content delta before the finish chunk; `finish_reason` equals `tool_release`'s; concatenated content == `content_with_notes(redacted, notes)` for each scripted stream; no stage/phase word appears.
- [ ] AC4: `fail_after` after commit -> exactly one `error` event with `_fault_code`'s code, no `[DONE]`; a `PiiRedactorError` from the gate -> `redaction_failed`; disconnect via direct ASGI mid-stream -> row `success=1`, charged, one INFO naming user and `completion_id` (caplog: no content); verdict-after-commit test keeps the WARNING (T13).
- [ ] AC5: switch off, switch on without grant, legacy mode -> stub request body has no `stream`, response equals today's. Latency: direct-ASGI drive of the app against the stub (`delay_ms` = D, `code` profile, PII gate off), N=20 runs, first non-empty `delta.content` arrival <= D + 100 ms at p95 (nearest rank), chunks fed to the `openai` SDK accumulator (`tests/test_v1_schemas.py:1081` pattern) and the final content equals the script; keep under 20 s with D around 30 ms.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_v1_realtime.py tests/test_v1_sse.py tests/test_v1_router.py tests/test_v1_errors.py tests/test_v1_schemas.py tests/test_v1_translate_result.py tests/test_delivery.py tests/test_query_pipeline_streaming.py tests/test_untouched_app.py
```
One pytest at a time. No test is renamed or removed (so no `_DELIBERATELY_SUPERSEDED_TESTS` entry). No `database.py` change (no census guard).

## Acceptance Criteria -> Tasks -> Tests

| AC | Task | Test |
|----|------|------|
| AC1 sequence, ids, coalescing | 3, 4 | `test_v1_realtime.py::test_sequence_*`, `test_coalesce_*`, `test_drain_*` |
| AC2 reasoning_content | 1, 4 | `test_v1_schemas.py` (golden), `test_v1_realtime.py::test_reasoning_*` |
| AC3 T1/T5 | 3, 4 | `test_v1_realtime.py::test_nine_fragment_drop_table`, `test_concat_equals_redacted_plus_notes` |
| AC4 fault/disconnect/T13 | 3, 4 | `test_v1_realtime.py::test_fault_*`, `test_disconnect_*`, `test_verdict_after_commit_warns` |
| AC5 unchanged + latency | 2, 4 | `test_v1_realtime.py::test_off_means_today_*`, `test_first_content_latency_p95`; existing suites |

## Risks / questions for the orchestrator

1. Pipeline edits (D-A `streamed`, D-C `_upstream_result`) go beyond "router only" but are unavoidable: the sink path never calls `_Upstream`, and the pipeline recomputes visibility. Confirm.
2. `completion_events` gets a no-op-when-absent role-chunk addition (D-G), needed for buffered `stream:true` + `reasoning:view`.
3. Reasoning-only requests (no real time) now stream upstream; the unread `QueueSink` holds only stage/phase/committed events (small, dropped with the request).
4. `_upstream_result` and pydantic `__eq__` (D-C fallback stated).
