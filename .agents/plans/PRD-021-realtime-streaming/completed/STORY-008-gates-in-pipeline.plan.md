---
story: STORY-008
prd: PRD-021
slug: gates-in-pipeline
title: Gates in the pipeline, final pass, divergence and reasoning result
type: ENHANCEMENT
complexity: medium
epic_branch: epic/PRD-021-realtime-streaming
created: 2026-11-18
---

# Plan: Gates in the pipeline, final pass, divergence and reasoning result

## Summary

Wire STORY-007's `OutputGate` at the two seams STORY-006 left in step 7 of `run_conversation`, make step 8 take its output redaction from the gate's final pass for a gated realtime request, add a private `reasoning` result field, and measure gate latency with a script. Only `app/services/query_pipeline.py` and `app/models/schemas.py` change in `app/`. Buffered and `sink=None` requests build no gate and run today's step 8.

- Story: `.agents/stories/PRD-021-realtime-streaming/STORY-008-gates-in-pipeline.md`
- PRD sections used: 6.1, 6.5, D7, D8, T3, T12, Risk 1-2, Quality indicators
- Systems affected: `query_pipeline.py` (step 7, step 8, error arm), `schemas.py` (`QuerySuccessResponse`), `scripts/`, tests

## Design Decisions

Orchestrator design points are binding and carried as written; the rest are mine.

- **Gates are built before the `try` at `query_pipeline.py:985`**, next to `released` (`:979`):
  - `content_gate = OutputGate(policy, settings.STREAM_HOLDBACK_MAX_CHARACTERS, final_redact=_redact)` only when `visibility.realtime and gate_applies(policy, settings.PII_REDACTION_ENABLED)`; else `None` (code with output off, or master switch off: raw forward, no final pass; step 8 then behaves as today).
  - `reasoning_gate = OutputGate(reasoning_policy(policy), <same holdback>, final_redact=redact_reasoning)` when `visibility.reasoning and visibility.realtime`. Master switch off: `redaction_spans` returns `[]` (`pii_redactor.py:618`), so reasoning passes unredacted with no extra code.
  - Reasoning with the grant but not `realtime`: no gate, no sink. Raw reasoning is appended to a local list; after the loop `redact_reasoning(raw, policy)` runs once and its text goes on the result (`None` when empty or without the grant). One whole-text call is exactly "collected and returned whole, redacted".
- **`released` flips only on a non-empty string sent to the sink.** Content: `out = content_gate.feed(t)`; `if out: safe.content(out); released = True`. Ungated: `safe.content(t); released = True` as today. Reasoning likewise.
- **Order at loop end** (inside the `try`, before `collect`): `reasoning_gate.finish()`, then `content_gate.finish()`. Each non-empty `remainder` goes to its channel (content remainder is the last content delta), setting `released`. The reasoning tail goes at the end, not at the first content event: the channels are separate so their relative order is immaterial, and a gate cannot be finished twice (`stream_redaction.py:246`).
- **Failure semantics.** Widen the handler at `:1042` to `except (OpenRouterError, PiiRedactorError) as exc:`. The body is unchanged: if `released`, charge the T6 estimate from `received_text`/`received_calls`, then `log_query(success=False, error_message=str(exc), ...)`, then `raise`. It surfaces as `PiiRedactorError`, the type and row shape step 8's redaction arm already produces (`:1159`), so routers keep their mapping (`routers/query.py:88`, `routers/v1.py:246`) and nothing new is mapped. Messages carry no content (T9).
  - A poisoned gate never releases raw: `feed` returns nothing when it raises. Do **not** use `released_so_far` for the flag: `finish()` releases the remainder inside the gate before `final_redact`, and if that fails the remainder was never sent. Only the local `released` counts.
  - Nothing released: no charge (today's rule). The abandoned upstream generator is closed when the exception leaves the loop.
- **Step 8 for a gated request.** Keep `gate_result: Optional[GateResult]`. Step 8: `if gate_result is not None: redacted_response, output_entities = gate_result.final_text, gate_result.final_entities`, with no `_redact` call and no `masking_output` stage (nothing is masked now); otherwise today's branch exactly. The audit row's `response=openrouter_result.response` stays the raw upstream text, as today (`:1213`). Response, bubble and entities come from the final pass.
- **Divergence.** Right after `content_gate.finish()`: `if result.diverged: logger.warning("stream redaction diverged: user_id=%s completion_id=%s", ...)`, never content. The flag lives in local `stream_redaction_divergence: bool` with a `# STORY-009` comment. **Deviation to report:** `log_query` has no such parameter and STORY-009 adds the column, so "carried to the row writer" can only be a local here; tests assert the WARNING, not a row. Reasoning divergence: a separate WARNING (same fields, says "reasoning"), not carried further.
- **Result field.** `QuerySuccessResponse._reasoning`: `PrivateAttr(default=None)` plus a `reasoning` property, mirroring `_tool_outcome` (`schemas.py:100-104`). Never serialized, so `/query`'s body and OpenAPI do not move. Set only when `visibility.reasoning and not visibility.realtime`. Never passed to `log_query` or any `chat_messages` writer (D8).
- **AC 5 is a script**, `scripts/measure_stream_gate_latency.py`, recording and asserting nothing (a wall-clock assertion on CI is flaky), like `scripts/measure_pii_latency.py:1-40`. The 150 ms two-sentence batching is implemented only if p95 per segment exceeds it; if so, stop and tell the orchestrator before designing the batching.

## Skills In Use

None apply (`.agents/skills/frontend-design` is UI-only; no `chat_ui/` change).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Seams | `query_pipeline.py:1006-1017` | the `# STORY-008` / `# STORY-007/008` markers sit where `safe.content` / `safe.reasoning` are called |
| Charge on fault | `query_pipeline.py:1042-1086` | reuse as is; only the `except` tuple changes |
| Step 8 error arm | `query_pipeline.py:1157-1188` | `PiiRedactorError` type and row shape |
| Private result field | `models/schemas.py:100-104` | `PrivateAttr` + property |
| Gate contract | `stream_redaction.py:176-241, 284-313` | `feed`, `finish`, `GateResult.remainder`, `gate_applies`, `reasoning_policy`, `redact_reasoning` |
| Recorder, stream stub, spies, fixture | `tests/test_query_pipeline_streaming.py:74-160, 304-320` | same shapes for the new test file |
| Script style | `scripts/measure_pii_latency.py` | load analyzers before the window, warm up, report not assert |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/query_pipeline.py` | UPDATE | imports; gate construction; two seams; remainders; widened except; step 8 branch; result field |
| `app/models/schemas.py` | UPDATE | private `reasoning` on `QuerySuccessResponse` |
| `scripts/measure_stream_gate_latency.py` | CREATE | AC 5 numbers |
| `tests/test_query_pipeline_gates.py` | CREATE | pipeline-level gate tests |
| `tests/test_query_pipeline_streaming.py` | UPDATE | three existing tests change under the gate (Task 4) |

## Tasks

### Task 1: Result field
- **File**: `app/models/schemas.py` (UPDATE). Add `_reasoning: Optional[str] = PrivateAttr(default=None)` and a `reasoning` property under `_tool_outcome`; the comment cites PRD-021 D8.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Gates in step 7
- **File**: `app/services/query_pipeline.py` (UPDATE). Import `OutputGate`, `GateResult`, `gate_applies`, `reasoning_policy`, `redact_reasoning` from `app.services.stream_redaction`. Remove `# noqa: F841` at `:972` (`realtime_request` is now read, by the gate condition or kept as a local for STORY-009: if it is still unused, keep the noqa). Build the gates and the non-realtime reasoning list before the `try`; replace the two seam bodies; add the end-of-loop block (reasoning finish, content finish, remainders, divergence warning, whole-reasoning redaction); widen the `except` at `:1042`. All new code stays inside the existing `try` so one handler serves every fault.
- **Mirror**: `:1006-1024`, `:1042-1064`.

### Task 3: Step 8 and the result
- **File**: `query_pipeline.py` (UPDATE). Step 8 at `:1154`: the `gate_result` branch ahead of today's `if policy.output:`. Set `success._reasoning` next to `_tool_outcome` (`:1302`). Do not touch the `log_query` calls.

### Task 4: Existing tests the gate changes
- **File**: `tests/test_query_pipeline_streaming.py` (UPDATE). Under `chat` (the `_run` default) the gate holds text until a boundary or the end:
  - `test_content_in_order_skips_empty` (`:229`): `["a", "b"]` becomes `["ab"]` (the remainder). Comment citing PRD-021 STORY-008, D7.
  - `test_fault_after_release_charges_estimate_before_failure_row` (`:322`): `"abc","de"` are held, nothing released, so no charge. Run it with `profile="code"` (output off: raw forward). Comment the change.
  - `test_fault_counts_everything_received_including_held_calls_and_reasoning` (`:342`): `"think"` is held by the reasoning gate. Use `"think. "` and update the expected string. Comment the change.
  - No rename, so no `_DELIBERATELY_SUPERSEDED_TESTS` entry.

### Task 5: New tests
- **File**: `tests/test_query_pipeline_gates.py` (CREATE), with the file-mode registry fixture (`tests/_providers.py`) and scripted `stream_upstream` stubs. Cases:
  - content: sink gets only gate output plus the remainder as the last delta; an email split across deltas never appears raw in any delta; `code` with output off forwards raw and never calls `_redact` (spy); master switch off forwards raw;
  - step 8: a gated request makes no second `_redact` call (spy); response, `pii_entities_masked` and the row's entities equal `final_text`/`final_entities`; a buffered request and `ingress="chat"` without realtime build no gate (patch `OutputGate` to raise) and run step 8 once;
  - divergence: a forced cut across an entity (set `settings.STREAM_HOLDBACK_MAX_CHARACTERS` with `monkeypatch.setattr`, which skips the 100 minimum validator) logs one WARNING with user id and `completion_id` and no content (caplog); the response is the final text;
  - reasoning: realtime sends redacted reasoning per segment; reasoning-only grant returns `result.reasoning` redacted and the sink gets none; no grant gives `None`; reasoning text is in no `audit_logs` or `chat_messages` row; master switch off leaves it unredacted;
  - faults: `PiiRedactorError` from `feed` (monkeypatch `pii_redactor.redaction_spans`) after a release charges the estimate before the failure row and raises `PiiRedactorError`; before any release charges nothing; no raw text reaches the sink after the error; a `final_redact` failure in `finish` behaves the same; a gate holding everything then faulting charges nothing (T6).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_query_pipeline_gates.py`

### Task 6: Latency script
- **File**: `scripts/measure_stream_gate_latency.py` (CREATE). A scripted 2 000-character reply (sentences plus a few emails/phones) for `chat` and `code` (with `PII_CODE_REDACT_OUTPUT` on so the gate applies). Per arm: time each `feed` call that released a segment (p95 per segment), the whole feed+finish loop (p95 per response, final pass excluded), and one `_redact` over the same text (step 8's cost). Load analyzers and warm up first; at least 50 reps; print p50/p95/max. Run it once with `PYTHONUTF8=1 .venv/Scripts/python scripts/measure_stream_gate_latency.py` and put the numbers in the report.

## End-to-End Tests

- [ ] `run_conversation` with a recording sink and a scripted stream under `chat`: concatenated sink content equals the returned response equals `final_text` (text without divergence)
- [ ] The same prompt through `sink=None` and a buffered stub returns the same `response`
- [ ] `tests/test_query_pipeline_delivery.py` and the PRD-020 legacy fixtures pass unchanged

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider \
  tests/test_query_pipeline_gates.py tests/test_query_pipeline_streaming.py \
  tests/test_query_pipeline_run_conversation.py tests/test_query_pipeline_delivery.py \
  tests/test_query_pipeline_pii_profiles.py tests/test_stream_redaction.py \
  tests/test_untouched_app.py
```

Add `tests/test_pii_redaction_integration.py` only if a test is renamed (none planned).

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 gate output + remainder; code/off raw | 2, 5 | `test_query_pipeline_gates.py` content and `code` cases; `test_content_in_order_skips_empty` |
| AC2 step 8 replaced by final pass; buffered unchanged | 3, 5 | `test_query_pipeline_gates.py` step 8 cases; delivery suite unchanged |
| AC3 divergence WARNING + local flag | 2, 5 | `test_query_pipeline_gates.py` divergence case (caplog) |
| AC4 reasoning per segment / whole on result / never persisted | 1, 2, 5 | `test_query_pipeline_gates.py` reasoning cases |
| AC5 latency numbers | 6 | script output pasted in the report |
| T6 failure semantics | 2, 4, 5 | `test_query_pipeline_gates.py` fault cases; `test_query_pipeline_streaming.py` fault tests |

Plus: all tasks completed, validation passes, no `ToolCallDelta` reaches a gate or sink.
