---
story: STORY-011
prd: PRD-021
slug: chat-state-consumer
title: Chat UI state consumes the pipeline's events
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-19
---

# Plan: Chat UI state consumes the pipeline's events

## Summary

`ChatState._do_send` passes one `QueueSink(loop)` to whichever pipeline branch runs (`run_conversation` with history, `run_query` without), starts the call as a task, and a private consumer folds the sink's events into six new state vars, one `async with self` per 100 ms window. `result = await task` stays inside today's `try`, so the except chain, the final bubble and `_append_and_persist` are unchanged; the live/progress vars are cleared in the same delta that appends the final bubble. Rendering is STORY-012; this story adds vars, the consumer, `run_query`'s `sink` pass-through, and tests.

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-011-chat-state-consumer.md`
- PRD sections used: §6.3, §6.7, §7.1, D8, D16, D19, O6, Risk 5
- Systems affected: `chat_ui/chat_ui/state.py`, new `chat_ui/chat_ui/live_batch.py`, `app/services/query_pipeline.py` (`run_query`), existing chat tests whose fakes have fixed signatures

## Design Decisions

- **Reflex flush verified (Risk 5 fallback NOT needed).** `.venv/Lib/site-packages/reflex/istate/proxy.py:159-178`: the outermost `StateProxy.__aexit__` computes `root_state._get_resolved_delta()`, calls `root_state._clean()`, and `await ctx.emit_delta(delta)` if non-empty, before releasing the lock. So each `async with self` exit in a background event sends one delta; none when nothing changed. The implementer records these lines (reflex 0.9.6.post1) in the report. Nesting is refused (`proxy.py:104-155`; already documented at `state.py:952-956`).
- **`run_query` (`query_pipeline.py:1452`)** gains keyword-only `sink: Optional[DeliverySink] = None`, forwarded verbatim to `run_conversation(..., sink=sink)` (which already takes it, `:468`). `/query` passes nothing, so it is byte-identical (D20).
- **Same sink, both branches.** `_do_send` builds `sink = QueueSink(asyncio.get_running_loop())` once before the branch and adds `sink=sink` to both `run_in_pipeline(...)` calls; the comment at `state.py:~1210` ("the two branches still differ only in their input") stays true. The sink is passed with `STREAMING_ENABLED` on or off (O6: stage words need no switch); the pipeline, not the chat, decides which events exist (no grant -> no content call). `chat_history.assemble` (`:1168`) takes no sink.
- **New state vars** (public, defaults idle): `progress_stage: str = ""`, `progress_phase: str = ""`, `progress_action: str = ""` (the `PhaseEvent.action_kind` that §7.1's "Preparing an action: {kind}" needs; raw `OperationKind` string, the word mapping is STORY-012's copy), `progress_since: float = 0.0` (wall-clock `time.time()` so the browser can compute elapsed; 0.0 idle), `live_text: str = ""`, `live_reasoning: str = ""`. Six vars: the story's five plus `progress_action`. None is ever read into a `ChatMessage` or `_to_stored_message` (D8, D16).
- **Event mapping (closed)**, in pure `fold(events, *, stage, phase, now) -> dict`: `StageEvent` -> `progress_stage`; `PhaseEvent` -> `progress_phase` and `progress_action` (`action_kind or ""`); `progress_since = now` only if the resulting stage or phase differs from the current value (compared inside the block against live state); `ContentEvent` -> `live_text +=`; `ReasoningEvent` -> `live_reasoning +=`; `CommittedEvent` ignored. Within a batch the last stage/phase wins; texts concatenate in order. Empty result -> no `async with self` at all.
- **Consumer shape** (`live_batch.py`, no Reflex import, asyncio only):
  - `END = object()` sentinel via `task.add_done_callback(lambda _t: queue.put_nowait(END))`. Ordering is safe: sink puts are `call_soon_threadsafe`d before the pipeline function returns and the executor future's completion is marshalled after them, so every event precedes `END`.
  - `async def batches(queue, window_s=0.1)` async generator: `first = await queue.get()` (blocks, no spin); `END` -> stop; else collect with `asyncio.wait_for(queue.get(), remaining)` until the window (from the first event) expires or `END` arrives (a fast pipeline ends the window early, so the end is delayed by ~0, never more than one window); yield the list. At most one yield per window, so at most 10 deltas/s at any token rate. After `END`, drain leftovers with `get_nowait()` and yield them as a last batch.
  - `_do_send`: `async for batch in batches(sink.queue): await self._apply_batch(batch)`; `_apply_batch` holds the single `async with self` (the tests' spy point). Then `result = await task` INSIDE the existing `try`, so `OpenRouterError` -> `upstream_error` etc. are handled unchanged.
- **Exit paths.** `finally` around the consumer: `sink.close()` (puts dropped; pipeline never cancelled, D15). If the consumer faults or is cancelled while the task still runs, attach `task.add_done_callback(lambda t: t.cancelled() or t.exception())` so its exception is retrieved; a consumer fault propagates to today's `except Exception` -> `internal_error` bubble.
- **Clear in the same delta.** `_append_and_persist` (`:930`) already opens `async with self: self.messages.append(bubble)` first; add `self._clear_live()` (sync helper resetting the six vars) inside that same block. Every outcome bubble goes through it (`:1051,1066,1114,1242-1308,1434`), so the live entry is replaced by the bubble in one frame on every except branch too. The final `finally` (`:1436`) also calls `_clear_live()` for exits that append nothing (cancel, consumer fault). `_clear_live()` also runs in the claim block (`:1018-1027`) right after `self.pending = True`, so each send starts clean. `_append_and_persist` is still never called inside `async with self`.
- **Persistence.** Final bubble built from `result.response` exactly as `:1200-1221`. Mid-stream fault: the `OpenRouterError` arm (`:1239-1250`) builds today's bubble from `str(exc)`; `live_text` is never read there, so no partial text is persisted (D16, tested).
- **No log line carries content** (T9/T12). No new user-facing string, so `copy.py` is untouched.

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| frontend-design | "Name things by what people control and recognize": vars named for what the user sees (`progress_action`, `live_text`, `live_reasoning`); no copy here | Task 3 |

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Drain loop | `app/services/v1_sse.py:170-250` (`realtime_events`) | queue + pipeline future + coalescing window; do NOT import it |
| Sink / events | `app/services/delivery.py:74-98,150-200` | `QueueSink(loop)`, `.queue`, `.close()`, frozen event dataclasses |
| Lock rule | `chat_ui/chat_ui/state.py:952-957`, `:970` | a helper that opens `async with self` is never called inside one |
| Error chain | `state.py:1239-1330` | unchanged; `await task` sits where `await run_in_pipeline` sits |
| Test fakes | `tests/test_chat_state.py:1083-1135` (`_stub_pipeline`), `:129-143` (`_make_state`, `_send`) | `_send` calls `handler.fn(state)` on a real state, so `async with self` works there |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `chat_ui/chat_ui/live_batch.py` | CREATE | `END`, `batches()`, `fold()` (pure, no Reflex import) |
| `chat_ui/chat_ui/state.py` | UPDATE | six vars, `_clear_live`, `_apply_batch`, sink + consumer in `_do_send`, clear in `_append_and_persist` and `finally` |
| `app/services/query_pipeline.py` | UPDATE | `run_query(..., *, sink=None)` forwarded |
| `tests/test_chat_state_streaming.py` | CREATE | tests (a)-(e) + pure `batches`/`fold` tests |
| `tests/test_chat_state.py`, `tests/test_chat_history_send.py`, `tests/test_rbac.py` (+ any other fixed-signature fake the Task 4 grep finds) | UPDATE | add `sink=None` to fakes, each with a `# PRD-021 STORY-011: ChatState passes sink` comment |

## Tasks

### Task 1: `run_query` passes `sink` through
- **File**: `app/services/query_pipeline.py` (grep `def run_query`)
- **Implement**: keyword-only `sink: Optional[DeliverySink] = None` after `ingress`, comment citing PRD-021 D18/D20 in the voice of `:468-471`; `sink=sink` in the `run_conversation` call. `/query` unchanged.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_untouched_app.py tests/test_query_pipeline_audit_fields.py`

### Task 2: `live_batch.py`
- **Implement**: `END`, `batches(queue, window_s=0.1)`, `fold(...)` as in Design Decisions. Module docstring cites PRD-021 D19 and Risk 5; imports only `app.services.delivery` events.
- **Mirror**: `app/services/delivery.py:1-28` docstring style.

### Task 3: wire `_do_send` and `ChatState`
- **File**: `chat_ui/chat_ui/state.py`
- **Implement**: vars next to `pending` (`:234`) with a PRD-021 comment; `_clear_live` and `_apply_batch` beside `_append_and_persist` (docstring states the no-nesting rule); `_clear_live()` in the claim block, in `_append_and_persist`'s first block, and in the final `finally`. Before the branch create `sink`; per branch `task = asyncio.ensure_future(run_in_pipeline(<fn>, ..., sink=sink))`, then the consumer loop under `try/finally: sink.close()`, then `result = await task`. Both argument lists stay identical except for the input.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chat_ui_startup_guard.py`

### Task 4: fix existing fakes
- `grep -n 'chat_state_mod, "run_\(query\|conversation\)"' tests/*.py`. Add `sink=None` to every fixed-signature fake: `tests/test_chat_state.py:1106` (`_via_query` forwards `**kwargs` to `fake`, so it must drop `sink` as it drops `ingress`) and `:1134` (`_via_conversation`), `tests/test_rbac.py:315`, `tests/test_chat_history_send.py:107` (`_fake`) and `_capturing_run_query` (`:118`; check it takes `**kwargs`). `**kwargs` fakes (`test_usage_bubble.py`, `test_pipeline_concurrency.py`, `test_query_pipeline_audit_fields.py`) need nothing. Do not change assertions.

### Task 5: `tests/test_chat_state_streaming.py`
Fake pipeline: a plain function installed as `chat_state_mod.run_conversation` / `run_query` that accepts `sink` and drives `sink.stage/phase/content/reasoning` with `time.sleep` pacing; the real `run_in_pipeline` runs it on the executor thread. Copy the `temp_db` fixture, `_make_state` and `_send` patterns (do not import private names across test modules). Record batches by wrapping `ChatState._apply_batch` (call through).
- (a) scripted stage -> `waiting` -> `thinking` -> `writing`, no content/reasoning calls: `progress_phase` order preserved across the recorded batches; `live_text`/`live_reasoning` empty at every batch. Parametrize history on/off and assert the same sink type reaches both branches.
- (b) `STREAMING_ENABLED` off (`monkeypatch.setattr(settings, ...)`): stages only; stage words applied; final bubble equals the one from a fake that ignores `sink`.
- (c) ~1.5 s at 200 tokens/s: `len(batches) <= elapsed/0.1 + 2` and rate `<= 12/s`; the concatenated batch text equals everything emitted.
- (d) content then `raise OpenRouterError("boom")`: `messages[-1].kind == "upstream_error"`, `detail == "boom"`; partial text absent from every `messages[*]` field and from `chat_sessions.messages_for` rows; six vars at defaults; `pending is False`.
- (e) success: six vars at defaults; `messages[-1].content == result.response`; exactly one assistant row persisted.
- Pure: `batches` returns promptly after the task ends with no events (no spin; end delayed by far less than a window) and yields leftovers after `END`; `fold` leaves `progress_since` unchanged on a repeated stage and ignores `CommittedEvent`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chat_state_streaming.py`

## End-to-End Tests

- [ ] Real `ChatState` send with the threaded fake pipeline through both branches (Task 5)
- [ ] `tests/test_chat_ui_startup_guard.py` (chat_ui touched)
- [ ] Real `run_conversation` + stub upstream through `QueueSink` is STORY-014/015's, not here

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_chat_state_streaming.py tests/test_chat_state.py tests/test_chat_history_send.py tests/test_rbac.py tests/test_chat_outcomes_regression.py tests/test_usage_bubble.py tests/test_chat_ui_storage_failures.py tests/test_pipeline_concurrency.py tests/test_query_pipeline_audit_fields.py tests/test_chat_ui_startup_guard.py tests/test_untouched_app.py
```
Use `-k` on DB-heavy files if slow. No test is renamed or removed, so `test_pii_redaction_integration.py` is not needed. Full suite: GitHub CI.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test |
|----|---------|------|
| AC1 sink + 100 ms batches, one `async with self` each | 1, 2, 3 | `tests/test_chat_state_streaming.py` (a), (c), pure `batches` |
| AC2 bubble from `result.response`, live/progress cleared, persisted once, no reasoning persisted | 3 | (e) |
| AC3 mid-stream fault -> `upstream_error`, no partial text | 3 | (d) |
| AC4 no-grant phase order; switch off: stage words, identical bubble | 3 | (a), (b) |
| AC5 <=10 updates/s at 200 tok/s; Reflex flush verified | 2, 3 | (c); report cites `reflex/istate/proxy.py:159-178` |

## Risks / open questions

- Task 4 touches several existing test files (fixed-signature fakes); mechanical, comments required.
- **Orchestrator correction (3.2): seven vars.** Add `progress_sent_at: float = 0.0`, set to `time.time()` in the claim block right after `_clear_live()` (so the clear does not undo it) and reset to 0.0 by `_clear_live()`. §7.1 needs both: `progress_sent_at` drives "Thinking · 14 s" (elapsed from the send) and `progress_since` drives the 300 ms no-flicker rule (time the current stage/phase started). `_clear_live` resets all seven. **Guard:** the user's own bubble also goes through `_append_and_persist` (`state.py:1114`, after the claim block), so the clear there runs only for `bubble.kind != "user"`; otherwise it would zero `progress_sent_at` before the pipeline starts. A test asserts `progress_sent_at` survives the user-bubble append. Test (e) also asserts `progress_sent_at` is non-zero during the stream and 0.0 after.
- A stubbed pipeline that ignores `sink` emits nothing: the consumer yields nothing, no deltas, no spin.
