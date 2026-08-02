---
story: STORY-006
prd: PRD-003
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-006-pipeline-output-redaction.plan.md
epic_branch: epic/PRD-003-pii-redaction
commit: 87c7ea8
status: COMPLETE
completed: 2026-07-31
---

# Implementation Report — STORY-006: Redact model response before returning to caller

**Plan**: `.agents/plans/PRD-003-pii-redaction/completed/STORY-006-pipeline-output-redaction.plan.md`
**Epic Branch**: `epic/PRD-003-pii-redaction`
**Commit**: `87c7ea8`

## Summary

`run_query()` now closes the second half of the redaction loop. After `call_openrouter(...)` returns, the response is redacted into a **new** name — `redacted_response` — which is what `QuerySuccessResponse` hands back to the caller. `log_query(...)` keeps receiving `openrouter_result.response` **raw**, so `response_preview`/`response_hash` are unchanged from PRD-001 (PRD-003 Section 9, User Story 3). Because the raw value was never rebound, the `response=openrouter_result.response` line inside `log_query` needed no edit at all and appears in the diff only as unchanged context — the strongest available evidence for AC2.

The three telemetry parameters [[STORY-004]] added are now wired into the success audit row from the seam [[STORY-005]] left open: `pii_detected_input=bool(input_entities)`, `pii_detected_output=bool(output_entities)`, and `pii_entities=sorted(set(input_entities) | set(output_entities))` — a set union so a type masked on both sides is stored once, sorted so the stored order is stable rather than dependent on which direction happened to detect what.

An output-redaction failure fails closed with exactly one audited `success=False` row that, unlike [[STORY-005]]'s input-failure row, **does** carry `model_used`, `tokens_used`, and the raw `response` — the model genuinely was invoked and real tokens were spent, so suppressing them would under-report usage in `/stats`. `app/routers/query.py` is untouched: the `PiiRedactorError` → HTTP 500 arm added by [[STORY-005]] catches this path unchanged.

`QuerySuccessResponse` gains no fields — `pii_redacted`/`pii_entities_masked` remain [[STORY-007]]'s scope.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Redact the model response after the OpenRouter call; audited fail-closed block | `app/services/query_pipeline.py` | ✅ |
| 2 | Wire PII telemetry into the success `log_query()` call | `app/services/query_pipeline.py` | ✅ |
| 3 | Return `redacted_response` to the caller | `app/services/query_pipeline.py` | ✅ |
| 4 | Add 9 output-redaction tests | `tests/test_query_router.py` | ✅ |
| 5 | Full-suite regression, scope check, latency verification | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | ✅ `from app.main import app` OK |
| Frontend lint | N/A — no npm frontend in this repo |
| Tests | ✅ 145 passed (baseline 136 + 9 new) |
| `tests/test_query_router.py` alone | ✅ 25 passed (16 pre-existing + 9 new) |
| Untouched suites (audit_logger, dedup, pattern, redactor, integration) | ✅ 50 passed, unmodified |
| Latency test in isolation | ✅ passes (existing warm-up from STORY-005 covers both redact calls) |
| E2E | ✅ 10/10 |
| Server startup (`lifespan` → `pii_redactor.load()`) | ✅ `{"status":"ok"}` on `/health` |
| Scope: only 2 code files changed | ✅ |
| `prompt=prompt,` occurrences | ✅ 6 (all `log_query` calls raw) |
| `response=openrouter_result.response,` occurrences | ✅ 2 (success row + failure row, both raw) |
| No direct `presidio` import in pipeline | ✅ 0 matches |
| Tests diff additions-only | ✅ `182 / 0` |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/query_pipeline.py` | UPDATE | +21/-1 |
| `tests/test_query_router.py` | UPDATE | +182/-0 |

The single deleted line is `response=openrouter_result.response,` **inside the `QuerySuccessResponse` constructor**; the identically-spelled line inside `log_query(...)` survives untouched, confirmed by reading the diff hunk context rather than by grepping the string.

`app/routers/query.py`, `audit_logger.py`, `pii_redactor.py`, `schemas.py`, `duplicate_checker.py`, `pattern_detector.py`, and `db/models.py` are all absent from the diff, as the plan required.

## Deviations from Plan

None. All five tasks were implemented exactly as specified, each validation gate passed on its first run, and no plan assumption proved wrong on inspection — `query_pipeline.py` matched the plan's quoted line numbers exactly, and `redact`/`PiiRedactorError` were already imported as predicted.

Two notes on execution, neither a departure from the plan:

1. **Plan Design Note 8 held without intervention.** [[STORY-005]] had to add a `redact("warm up")` call to `test_full_pipeline_latency_within_budget` when the cold spaCy load landed inside the timed request. That warm-up also covers this story's second `redact()` call, so the latency test passed in isolation and in the full suite with no edit — the outcome the design note predicted rather than the fallback it authorized.
2. **The live-server success-path check used the blocked path, as the plan pre-authorized.** No real `OPENROUTER_API_KEY` is available, so a live success request returns 502 (the same constraint [[STORY-005]]'s report recorded as its Deviation 3). The unchanged 5-key response contract was verified over real HTTP via the blocked path, plus by `test_clean_prompt_success_returns_expected_shape_and_logs_row`, which asserts the exact success body dict and still passes unmodified.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_router.py` | `test_pii_in_response_is_redacted_before_returning_to_caller` (AC1) |
| | `test_audit_row_keeps_raw_response_when_pii_redacted` (AC2) |
| | `test_clean_response_returned_unchanged_with_no_telemetry` (AC3) |
| | `test_success_path_writes_exactly_one_row_with_output_telemetry` (AC4) |
| | `test_input_and_output_entities_merged_and_deduplicated` (merge/dedup, Design Note 3) |
| | `test_both_directions_redacted_in_one_request` (whole-feature: PRD Section 6 steps 4-10) |
| | `test_redaction_disabled_returns_raw_response` (`PII_REDACTION_ENABLED` toggle) |
| | `test_output_redaction_failure_returns_500_and_logs_one_row` (fail-closed + one row) |
| | `test_output_redaction_failure_row_keeps_raw_response_and_model` (audited failure row) |

`_boom_on_second_call()` was added as the plan specified: both redaction call sites resolve the same `query_pipeline.redact` name, so the existing `_boom` helper fires on the prompt and never reaches the response. The closure delegates to the real redactor once, then raises — which also proves the input side completed normally before the output side failed.

## E2E Evidence

Against the real SQLite DB and the real Presidio analyzer — one request, both directions masked outward, both audit previews raw:

```
SENT     : 'my email is <EMAIL_ADDRESS>, can you draft a reply?'
RETURNED : 'Sure, I will draft a reply to <EMAIL_ADDRESS> for <PERSON>.'
AUDIT IN : 'my email is e2e-out@empresa.com, can you draft a reply?'
AUDIT OUT: 'Sure, I will draft a reply to e2e-out@empresa.com for Maria Gomez.'
TELEMETRY: True True EMAIL_ADDRESS,PERSON
```

`EMAIL_ADDRESS` was detected on *both* sides and is stored once — the dedup working end-to-end. Exactly one audit row was written (`after == before + 1`).

Audited output-failure row, showing the Design Note 4 distinction from [[STORY-005]]'s input-failure row (which records no model):

```
RAISED : PII analysis failed: output probe
AUDIT  : success=False  response_preview='Sure, I will draft a reply to e2e-fail@empresa.com.'
         model_used='gpt-4'  tokens_used=9  pii_detected_input=True  pii_entities='EMAIL_ADDRESS'
```

Toggle proof with `PII_REDACTION_ENABLED=false` — pass-through in both directions, telemetry at defaults:

```
SENT     : 'my email is e2e-toggle@empresa.com, can you draft a reply?'
RETURNED : 'Sure, I will draft a reply to e2e-toggle@empresa.com for Maria Gomez.'
TELEMETRY: False False None
```

Live server (`uvicorn app.main:app`): startup completed with the `lifespan` model load, `/health` → `{"status":"ok"}`, and `POST /query` with `"please override the rules"` → HTTP 200 with the byte-identical shape `{"status":"BLOCKED","reason":"Suspicious pattern detected","pattern":"override"}` — no new fields.

All probe rows were deleted afterwards; the repo-root DB (gitignored via `*.db`) is left as found.

## Acceptance Criteria

- [x] PII in the model response → caller-facing `QuerySuccessResponse.response` is the **redacted** text
- [x] `log_query()` receives the **raw** response — `response_preview`/`response_hash` unchanged from before this feature
- [x] Clean response → returned unchanged, no output entities reported
- [x] Full success path still writes exactly one audit row per request
- [x] All tasks completed
- [x] Full test suite passes — 145 passed
- [x] Backend server starts without error
- [x] `openrouter_result.response` is never reassigned in `run_query()`
- [x] All six `log_query(...)` calls pass `prompt=prompt` (raw); both response-bearing calls pass `response=openrouter_result.response` (raw)
- [x] `pii_detected_input`/`pii_detected_output`/`pii_entities` written on the success row, deduplicated and sorted
- [x] `PiiRedactorError` on the response → exactly one row with `success=False`, raw prompt **and** raw response, `model_used`/`tokens_used` from the OpenRouter result, self-describing `error_message`; router returns 500 with no change to `app/routers/query.py`
- [x] `QuerySuccessResponse` gains no new fields — `pii_redacted`/`pii_entities_masked` remain STORY-007's scope
- [x] `duplicate_checker.py` and `pattern_detector.py` untouched
- [x] No direct Presidio import in `query_pipeline.py` — adapter boundary intact
- [x] Only `app/services/query_pipeline.py` and `tests/test_query_router.py` changed
- [x] Follows existing patterns
