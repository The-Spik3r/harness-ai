---
story: STORY-007
prd: PRD-003
plan: .agents/plans/PRD-003-pii-redaction/completed/STORY-007-query-response-pii-signal.plan.md
epic_branch: epic/PRD-003-pii-redaction
commit: 61e402c
status: COMPLETE
completed: 2026-08-01
---

# Implementation Report — STORY-007: POST /query response — `pii_redacted` signal field

**Plan**: `.agents/plans/PRD-003-pii-redaction/completed/STORY-007-query-response-pii-signal.plan.md`
**Epic Branch**: `epic/PRD-003-pii-redaction`
**Commit**: `61e402c`

## Summary

`QuerySuccessResponse` gained two additive fields — `pii_redacted: bool = False` and `pii_entities_masked: List[str] = []` — matching PRD-003 Section 10's example shape. Nothing new is detected or computed: [[STORY-005]] and [[STORY-006]] already left `input_entities` and `output_entities` in scope, so this story only *surfaces* them.

The plan's one real design decision (Design Note 1) landed as specified: the merge expression `sorted(set(input_entities) | set(output_entities))`, previously inlined as the `pii_entities=` argument to `log_query()`, is now hoisted into a local `masked_entities` that feeds **both** the audit column and the API response. `pii_redacted` is `bool(masked_entities)` rather than a second, independently-drifting `bool(input_entities or output_entities)`. `test_signal_matches_audit_row_entities` pins the agreement by reading the audit row and the HTTP body from the same request, so the hoist is load-bearing rather than cosmetic.

`QueryRequest` is byte-for-byte unchanged — AC4, and the whole point of PRD User Story 5. Both BLOCKED response models are unchanged too: those paths `return` at `query_pipeline.py:37`/`:51`, before `redact()` at `:57`, so there is no redaction to signal (Design Note 4). Their two exact-dict tests passed **unmodified**, which is the AC-level proof of that decision.

`app/routers/query.py` needed no edit: the `Union` `response_model` picks up the extended member automatically, and FastAPI emits the defaults rather than omitting them — so `pii_redacted: false` / `pii_entities_masked: []` are always *present*, which AC2 requires. The plan verified this with a standalone probe before any code was written; the live `openapi.json` confirmed it afterwards.

`chat_ui/chat_ui/state.py` is untouched and `tests/test_chat_state.py` passed unmodified — the additive contract demonstrated on a second, non-HTTP consumer.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add `pii_redacted` / `pii_entities_masked` to `QuerySuccessResponse` | `app/models/schemas.py` | ✅ |
| 2 | Hoist the merged entity list into `masked_entities` | `app/services/query_pipeline.py` | ✅ |
| 3 | Populate the signal on the success response | `app/services/query_pipeline.py` | ✅ |
| 4 | Verify request contract + blocked shapes untouched (diff gate) | — | ✅ |
| 5 | Update the exact-dict assertion + add 3 schema tests | `tests/test_schemas.py` | ✅ |
| 6 | Update the exact-dict body assertion + add 7 router tests | `tests/test_query_router.py` | ✅ |
| 7 | Full-suite regression + scope check | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | ✅ `from app.main import app` OK |
| Frontend lint | N/A — no npm frontend in this repo |
| Tests | ✅ 155 passed (baseline 145 + 10 new) |
| `tests/test_schemas.py` alone | ✅ 11 passed (8 pre-existing, 1 updated + 3 new) |
| `tests/test_query_router.py` alone | ✅ 32 passed (25 pre-existing, 1 updated + 7 new) |
| Untouched suites (integration, chat_state, audit_logger, dedup, pattern, redactor) | ✅ 60 passed, unmodified |
| E2E | ✅ 11/11 |
| Server startup (`lifespan` → `pii_redactor.load()`) | ✅ `{"status":"ok"}` on `/health` |
| Scope: only 4 code/test files changed | ✅ |
| `git diff app/models/schemas.py` | ✅ `+2/-0`, both lines inside `QuerySuccessResponse` |
| `prompt=prompt,` occurrences | ✅ 6 (unchanged — all `log_query` calls raw) |
| `response=openrouter_result.response,` occurrences | ✅ 2 (unchanged — both raw) |
| Tests diff removed lines | ✅ 0 (additions-only) |
| `app/routers/query.py` in diff | ✅ absent |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/models/schemas.py` | UPDATE | +2/-0 |
| `app/services/query_pipeline.py` | UPDATE | +5/-1 |
| `tests/test_schemas.py` | UPDATE | +46/-0 |
| `tests/test_query_router.py` | UPDATE | +110/-0 |

The single deleted line is `pii_entities=sorted(set(input_entities) | set(output_entities)),`, replaced by `pii_entities=masked_entities,` — the hoist. `prompt=prompt` and `response=openrouter_result.response` do not appear as modified lines anywhere, so RF-7's raw-audit guarantee is untouched by inspection of the diff rather than by tracing control flow.

`app/routers/query.py`, `audit_logger.py`, `pii_redactor.py`, `db/models.py`, `duplicate_checker.py`, `pattern_detector.py`, and `chat_ui/chat_ui/state.py` are all absent from the diff, as the plan required.

## Deviations from Plan

Three, all in the plan's *predicted numbers* rather than in the implementation. Every task was implemented exactly as written, and no design decision changed.

1. **The two expected test failures appeared one task earlier than the plan said.** Task 2's validation gate predicted "145 passed, zero test edits", with the two exact-dict failures arriving at Task 3. In fact Task 1 alone causes them: once the fields exist with defaults, `model_dump()` and the serialized HTTP body already carry the two extra keys, regardless of whether `run_query()` populates them. Observed after Tasks 1-2 and again after Task 3: **143 passed, 2 failed** — `test_query_success_response_shape` and `test_clean_prompt_success_returns_expected_shape_and_logs_row`, exactly the two the plan named, with no third failure. The gate's *substance* (a pure refactor introduces no new failure) held: the failure set was identical before and after Task 2.

2. **`tests/test_schemas.py` finished at 11 passed, not the planned 9.** The plan counted 6 pre-existing tests in that file; there are 8. The delta the plan actually specified — 1 assertion updated, 3 tests added — is exactly what was implemented. The full-suite target of 155 was unaffected and hit precisely, since it was derived from the +10 total rather than from the per-file counts.

3. **The tests diff came out additions-only, with zero removed lines.** Task 7 expected "exactly two removed hunks" for the two updated dict literals. Appending two keys before each literal's closing brace turned out to be a pure insertion in both cases, so `git show 61e402c -- tests/ | grep "^-"` returns 0 lines. Strictly better than the plan's expectation, and it makes the "no existing test was rewritten" claim trivially checkable.

One execution note, not a departure: the live-server success path could not be exercised over real HTTP because no real `OPENROUTER_API_KEY` is available (the same constraint recorded in [[STORY-005]]'s and [[STORY-006]]'s reports). The success-shape contract was verified instead by the in-process E2E probe against the real Presidio analyzer, by `test_existing_success_fields_unchanged_alongside_new_signal`, and by the live `openapi.json` — while the *blocked* shape was verified over live HTTP as byte-identical.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_schemas.py` | `test_query_success_response_with_pii_signal_shape` (AC1, PRD §10 example shape) |
| | `test_query_success_response_pii_defaults_are_not_shared_between_instances` (Design Note 2) |
| | `test_query_request_contract_is_unchanged` (**AC4**) |
| `tests/test_query_router.py` | `test_pii_in_prompt_sets_redaction_signal` (AC1, input side) |
| | `test_pii_in_response_sets_redaction_signal` (AC1, output side) |
| | `test_signal_entities_merged_and_deduplicated_across_directions` (AC1, both at once) |
| | `test_signal_matches_audit_row_entities` (Design Note 1 — audit and API agree) |
| | `test_clean_query_reports_no_redaction` (**AC2**) |
| | `test_redaction_disabled_reports_no_redaction` (`PII_REDACTION_ENABLED` toggle) |
| | `test_existing_success_fields_unchanged_alongside_new_signal` (**AC3**, value-level) |

Updated on purpose (pre-authorized by [[STORY-006]]'s plan, Design Note 5): the exact-dict assertions in `test_query_success_response_shape` (`tests/test_schemas.py`) and `test_clean_prompt_success_returns_expected_shape_and_logs_row` (`tests/test_query_router.py`). Both remain **whole-dict equality** rather than being relaxed to key-by-key — that strictness is what makes AC3 auditable and is the tripwire for the next silently-added field.

`test_query_success_response_pii_defaults_are_not_shared_between_instances` is worth keeping despite Pydantic v2's deep-copy of mutable defaults: it converts an implicit framework guarantee into an explicit, failing-on-regression assertion.

## E2E Evidence

In-process, against the real SQLite DB and the real Presidio analyzer — one request with PII on both sides:

```
BODY     : {'status': 'SUCCESS', 'response': 'Sure, I will draft a reply to <EMAIL_ADDRESS> for <PERSON>.',
            'audit_id': 13, 'model_used': 'gpt-4', 'tokens_used': 9,
            'pii_redacted': True, 'pii_entities_masked': ['EMAIL_ADDRESS', 'PERSON']}
AUDIT    : True True EMAIL_ADDRESS,PERSON
CLEAN    : False []
OK
```

`pii_entities_masked` equals `audit.pii_entities.split(",")` — the hoist proven end-to-end, same list, same order. `EMAIL_ADDRESS` was detected on both sides and reported once. The clean request reports `False []`, with the keys present rather than omitted (AC2).

Live server (`uvicorn app.main:app --port 8011`): startup completed with the `lifespan` model load, `/health` → `{"status":"ok"}`, and `POST /query` with `"please override the rules"` → HTTP 200 with the byte-identical blocked shape:

```
{"status":"BLOCKED","reason":"Suspicious pattern detected","pattern":"override"}
```

No `pii_redacted`, no `pii_entities_masked` — Design Note 4 confirmed over the wire.

Published `openapi.json` from the running server, which is the contract integrators actually read:

```
QuerySuccessResponse   : ['status', 'response', 'audit_id', 'model_used', 'tokens_used',
                          'pii_redacted', 'pii_entities_masked']
QueryRequest           : ['user_id', 'prompt', 'device', 'model', 'openrouter_api_key']
QueryRequest required  : ['user_id', 'prompt']
BlockedDuplicate       : ['status', 'reason', 'first_query_at']
BlockedSuspicious      : ['status', 'reason', 'pattern']
```

AC4 verified as *published*, not just as a Python class: the request schema still has exactly five properties and the same two required fields.

All probe rows (`user_id LIKE 'e2e%'`) were deleted afterwards; the repo-root DB (gitignored via `*.db`) is left as found.

## Acceptance Criteria

- [x] PII masked in prompt or response → `pii_redacted` is `true` and `pii_entities_masked` lists the distinct entity types masked
- [x] No PII detected → `pii_redacted` is `false` and `pii_entities_masked` is `[]` (keys present, not omitted)
- [x] Additive only — the five pre-existing success keys keep their exact prior values; verified at value level, and on a second consumer (`chat_ui` / `test_chat_state.py`) that ignores the new fields entirely
- [x] `QueryRequest` completely unchanged — verified in the diff, in `model_fields`, and in the published `openapi.json`
- [x] All tasks completed
- [x] Full test suite passes — 155 passed
- [x] Backend server starts without error
- [x] `pii_entities_masked` is the deduplicated, sorted union of both entity lists, and is the **same value** written to `audit_logs.pii_entities`
- [x] `pii_redacted` is `bool(masked_entities)` — no second, independently-drifting expression
- [x] Both BLOCKED response models gain no fields; their exact-dict tests pass unmodified
- [x] Exactly two existing assertions updated, both still whole-dict equality
- [x] `app/routers/query.py` unchanged — the `Union` response model picks up the new fields automatically
- [x] `chat_ui/chat_ui/state.py` unchanged and `tests/test_chat_state.py` passes unmodified
- [x] `duplicate_checker.py` / `pattern_detector.py` untouched (RF-6); `prompt=prompt` and `response=openrouter_result.response` still raw at every `log_query` call site (RF-7)
- [x] Only `app/models/schemas.py`, `app/services/query_pipeline.py`, `tests/test_schemas.py`, `tests/test_query_router.py` changed
- [x] Follows existing patterns
