---
story: STORY-006
prd: PRD-021
slug: streamed-step-7
title: Streamed step 7 with phases, held tool calls and real-time charging
type: NEW_CAPABILITY
complexity: large
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-18
---

# Plan: Streamed step 7 with phases, held tool calls and real-time charging

## Summary

Step 7 of `run_conversation` gains a streamed arm, taken only when `visibility.upstream_streamed`. It iterates an injectable `stream_upstream=`, drives `sink.phase` through a new pure `stream_assembly.phase_of`, forwards raw text/reasoning to the sink (gates are STORY-007/008, seam left), holds every `ToolCallDelta`, then builds the `UpstreamResult` with `collect()` so 7b/7c/8 are unchanged. The commit id and the real-time flag live in locals. A mid-stream `UpstreamError` after release charges the PRD-020 D8 estimate before the `success=0` row. The adapter's `stream()` enforces one total deadline (D20). `sink=None` is today's path byte for byte.

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-006-streamed-step-7.md` (AC text lives there)
- PRD sections used: 6.1, 6.2 (Consuming, Usage, Errors), 6.3 commit bullet, F2, F4, F6, D4, D6, D8, D13, D17, D20, T1, T6
- Systems affected: `query_pipeline.py` step 7, `upstream/openai_compatible.py`, new `stream_assembly.py`

## Design Decisions

Binding (from the orchestrator), plus how the code realizes them:

- **Commit and id.** With a sink, `completion_id = "chatcmpl-harness-rt-" + uuid4().hex` is generated at commit; `safe.committed(completion_id)` exactly once: on the first event the iterator yields (streamed), or immediately before `call_openrouter(...)` (buffered, on entry). Iterator raises before yielding -> `committed` never called. Locals `completion_id: Optional[str]` and `realtime_request = bool(visibility and visibility.realtime)` stay in `run_conversation` for STORY-008/009 (comment `# STORY-009 persists these`); no DB columns. `sink=None`: no id, no phases, no stream.
- **Buffered `committed` placement**: before the `try:` that wraps `call_openrouter`, so an `OpenRouterError` there still means "committed" (matches today's `_Upstream.__call__`, `v1.py:120-151`).
- **Usage (D4).** Streamed + `visibility.realtime`: `collect(events, provider=route.provider, request=req, usage_missing="estimate")` (signature `collect.py:33-38`). Streamed without realtime (chat progress-only): `usage_missing=None`, so an `error` provider still raises today's `UpstreamError` at step 7; collect runs inside the same `try`, nothing was released, so nothing is charged.
- **`UpstreamRequest` for `collect`**: build `UpstreamRequest(redacted_messages, route.upstream_model, params, tools)` locally (same fields `stream_upstream` builds, `upstream/__init__.py:120-125`); needed for the D8 estimate and the `tools=` gate.
- **Release tracking / T6.** `released_text: list[str]`; `released` = a non-empty text was passed to `safe.content` or `safe.reasoning` (reasoning counts only when actually forwarded: `visibility.reasoning and visibility.realtime`). On `UpstreamError` mid-iteration: if `released`, `estimate_tokens(redacted_messages, ("".join(released_text), ()), route.provider.estimate_chars_per_token, tools=tools.tools if tools is not None else None)` (already imported, `query_pipeline.py:53`; same formula `reply.py:118-123`, so no new helper or formula is needed), then `charge(identity.user_id, admission.day, None, None, estimate)` under the 7b guard (`admission is not None and openrouter_api_key is None`), BEFORE `log_query(success=False)`. Not released: charge nothing (today's rule). The failure row's token columns stay NULL (audit columns are STORY-009).
- **Total deadline (D20).** In `OpenAICompatibleAdapter.stream()` (`openai_compatible.py:167-190`): `deadline = time.monotonic() + provider.timeout_seconds` before sending; after each event from `parse_events`, if `time.monotonic() > deadline` raise `self._http_error(httpx.ReadTimeout(f"stream exceeded {provider.timeout_seconds}s"), label)`. This reuses today's classification (`_classify_http_error`, `:53-62`: TransportError -> `retryable=True`, text `"<label> request failed: ..."`), raised inside the existing `except httpx.HTTPError`. Limit: the check runs between events, so overshoot is bounded by one httpx per-read timeout; a silent connection is still cut by httpx's own read timeout. Say so in the docstring.
- **Phases.** `phase_of(event, previous, tool_kinds=None) -> Optional[tuple[PhaseName, Optional[OperationKind]]]`, pure (imports `upstream.types`, `delivery.PhaseName`, `action_classifiers.OperationKind` only). `tool_kinds` is a `Mapping[str, OperationKind]` the pipeline builds per request as `{n: m.kind for n, m in action_config.get_policy().tools.items()}` (`ToolMapping.kind`, `action_adapters.py:186`); the pure module reads no config. Rules: non-empty `ReasoningDelta` -> `thinking`; `TextDelta` with `text != ""` -> `writing`; `ToolCallDelta` with a truthy `name` -> `preparing_action` with `tool_kinds.get(name)` (None when unmapped); everything else, or an unchanged phase, -> `None`. `previous` is the last emitted `PhaseName`. Pipeline: `safe.phase("waiting")` on entry to step 7 (both arms, whenever a sink exists), then `safe.phase(name, kind)` on each non-None result. Note `preparing_action` for a second named call with the same phase name is not a change, so it emits once.
- **Forwarding (T1, D6).** `TextDelta` non-empty and `visibility.realtime` -> `safe.content(text)` (raw; marker `# STORY-008: output gate`); `ReasoningDelta` non-empty and `visibility.reasoning and visibility.realtime` -> `safe.reasoning(text)` (marker `# STORY-007/008: reasoning gate`); `ToolCallDelta`, `UsageReport`, `Finish` kept only. Empty `TextDelta("")` stays in `events` (collect needs it) but never reaches `safe.content` nor yields `writing`. A `ToolCallDelta` is read only inside `phase_of` for `.name`; no sink method ever receives one (phase carries a kind, never text, T4).
- **Errors.** The event loop and `collect(...)` share one `try/except OpenRouterError`; the arm decides charging by `released`. The failure `log_query` kwargs stay identical to today's so `sink=None` rows are byte-identical.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; no UI work).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Injection | `query_pipeline.py:422` (`call_openrouter=` default) | add `stream_upstream: Callable[..., Iterator[UpstreamEvent]] = stream_upstream` beside it; import it and `collect` from `app.services.upstream` (`collect` exported at `__init__.py:16,52`) |
| Sink calls | `query_pipeline.py:304-334`, `:493` | only `safe.*`, never the raw sink |
| Error arm | `query_pipeline.py:957-981` | one failure `log_query` block shared by both arms |
| Charge guard | `query_pipeline.py` step 7b | `admission is not None and openrouter_api_key is None` |
| Pure module | `app/services/delivery.py:1-30` | docstring citing PRD-021 sections; no settings, no I/O |
| Tests | `tests/test_query_pipeline_delivery.py:59-110` | `_RecordingSink`, `_upstream`, `_run`, `temp_db`, `provider_file` fixture (`tests/_providers.py`) for a `streaming: true` registry |
| Stub timing | `tests/test_stub_openrouter.py:957` | `stream: {delay_ms}` scripts |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/stream_assembly.py` | CREATE | pure `phase_of` |
| `app/services/query_pipeline.py` | UPDATE | step 7 streamed arm, `stream_upstream=` kwarg, phases, commit id, T6 arm, `usage_missing` choice |
| `app/services/upstream/openai_compatible.py` | UPDATE | total deadline in `stream()` |
| `tests/test_stream_assembly.py` | CREATE | `phase_of` unit tests + purity (no `settings`/I/O imports) |
| `tests/test_query_pipeline_streaming.py` | CREATE | streamed step 7 with scripted iterators |
| `tests/test_upstream_adapter.py` | UPDATE | one new deadline test (existing assertions untouched) |

## Tasks

### Task 1: `phase_of`
- **File**: `app/services/stream_assembly.py` (CREATE)
- **Implement**: as in Design Decisions.
- **Mirror**: `app/services/delivery.py:1-50`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stream_assembly.py`

### Task 2: total deadline
- **File**: `app/services/upstream/openai_compatible.py:167-190` (add `import time`)
- **Implement**: per Design Decisions; the deadline starts before `http_client.stream(...)`, so connect time counts.
- **Validate**: `... pytest -q -p no:cacheprovider tests/test_upstream_adapter.py tests/test_upstream_stream_collect.py`

### Task 3: pipeline kwarg and locals
- **File**: `query_pipeline.py` (signature `:422`; the wrapper at `:1210` passes nothing, leave it)
- **Implement**: add `stream_upstream=`; define `completion_id = None`, `realtime_request`, `released_text`, `streamed_step = visibility is not None and visibility.upstream_streamed`.

### Task 4: step 7 branches
- **File**: `query_pipeline.py` step 7 (`:944-981`)
- **Implement**: `safe.phase("waiting")` on entry. Buffered arm: if `safe`, make the id and `safe.committed(id)` before the existing `call_openrouter` call, which stays unchanged (same `extra` rule). Streamed arm: `stream_upstream(redacted_messages, model=model, api_key=openrouter_api_key, **extra)` inside the `try` (route/key errors raise at call time), loop per Design Decisions, id + `safe.committed` on the first event, then `collect(...)` with `usage_missing="estimate" if visibility.realtime else None`. Error arm: `if released: charge(...)`, existing `log_query(...)`, `raise`.
- **Mirror**: `query_pipeline.py:957-981`
- **Validate**: `... pytest -q -p no:cacheprovider tests/test_query_pipeline_streaming.py tests/test_query_pipeline_delivery.py`

### Task 5: tests
Scripted iterators are plain generators passed as `stream_upstream=`; use a file-mode registry with `streaming: true` (and `reasoning: true`) and a role holding `stream:realtime` (+ `reasoning:view` where needed). Mid-stream faults: generator that yields N events then raises `UpstreamError`.

## End-to-End Tests

- [ ] `run_conversation(..., sink=recording, stream_upstream=scripted)` with a realtime identity: phases `waiting, writing`, ordered content, one `committed` before any content, id matches `^chatcmpl-harness-rt-[0-9a-f]{32}$`, returned result equals a buffered run's.
- [ ] Real stub (free port, `stream: {chunk_chars, delay_ms}`) through the default `stream_upstream` with a tiny `timeout_seconds`: `OpenRouterError`, `retryable=True`, row `success=0`.
- [ ] Nine-fragment `DROP TABLE` call with text before and after: no fragment substring in any sink call; 7c decides as today (T1).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_stream_assembly.py tests/test_query_pipeline_streaming.py tests/test_query_pipeline_delivery.py tests/test_upstream_adapter.py tests/test_upstream_stream_collect.py tests/test_stream_upstream_seam.py tests/test_untouched_app.py
```

Also run the existing pipeline test file(s) that inject `call_openrouter` stubs (`tests/test_query_pipeline*.py`), unchanged.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 stream iterated, `committed` on first event, id format, collect; buffered commits on entry | 3, 4 | `test_query_pipeline_streaming.py::test_committed_once_on_first_event_with_rt_id`, `::test_buffered_commits_on_entry`, `::test_no_commit_when_iterator_raises_first`, `::test_sink_none_is_todays_path` |
| AC2 `phase_of` and emission | 1, 4 | `test_stream_assembly.py::test_phase_of_*` (empty text, nameless call, unmapped kind, change-only), `test_query_pipeline_streaming.py::test_waiting_then_changes_only` |
| AC3 content/reasoning/held calls | 4 | `::test_content_in_order_skips_empty`, `::test_reasoning_only_with_both_grants`, `::test_no_tool_fragment_reaches_any_sink_method`, `::test_7c_runs_over_collect_calls` |
| AC4 usage mode | 4 | `::test_realtime_missing_usage_is_estimated_on_error_provider`, `::test_progress_only_error_provider_still_raises` |
| AC5 mid-stream fault charge | 4 | `::test_fault_after_release_charges_estimate_before_failure_row`, `::test_fault_before_release_charges_nothing` |
| D20 total deadline | 2 | `test_upstream_adapter.py::test_stream_total_deadline_bounds_whole_stream` |

## Risks / open points

- Gate seams: forwarding here is unredacted on purpose; STORY-007/008 wrap the two marked call sites. No real-time ingress may be wired before then.
- `phase_of` has an extra optional `tool_kinds` parameter beyond the briefed two-argument signature (the pure module cannot read `action_config`); the two-argument call works.
- Deadline overshoot is bounded by one per-read timeout.
- Orchestrator decision (3.2): the T6 estimate counts **everything received before the fault** ("the estimate of what was received", T6): all non-empty `TextDelta` and `ReasoningDelta` text plus every `ToolCallDelta` name and arguments fragment, whether or not it was forwarded. `released` still decides whether anything is charged at all. Keep a separate `received_text` accumulator for this; test that held tool-call arguments raise the estimate.
