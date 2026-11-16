---
story: STORY-011
prd: PRD-017
plan: .agents/plans/PRD-017-tool-calling/completed/STORY-011-completion-shape.plan.md
epic_branch: epic/PRD-017-tool-calling
commit: 9a98b52
status: COMPLETE
completed: 2026-11-16
---

# Implementation Report - STORY-011: Completion shape

**Plan**: `.agents/plans/PRD-017-tool-calling/completed/STORY-011-completion-shape.plan.md`
**Epic Branch**: `epic/PRD-017-tool-calling`
**Commit**: `9a98b52`

## Summary

`translate_result` now reads `result.tool_outcome` (never `upstream.tool_calls`, T1). With an outcome: released calls as `message.tool_calls` (arguments the same string objects, D13), `content: null` when calls are released and there is no text or note, `finish_reason` from the release, and `harness.actions` (one entry per decision, model order, D14). All calls denied keeps `tool_calls: null`. With no outcome the body is PRD-015's byte for byte (neither new key present). New wire models `ToolCallFunction`, `CompletionToolCall`, `HarnessAction`; `FinishReason` gains `"tool_calls"`. The SSE writer is untouched.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Wire shapes + conditional-key serializers | `app/models/v1_schemas.py` | done |
| 2 | `translate_result` consumes the outcome | `app/services/v1_translate.py` | done |
| 3 | Router docstring | `app/routers/v1.py` | done |
| 4 | Pinned SDK into project `.venv` | environment | done |
| 5 | Schema tests | `tests/test_v1_schemas.py` | done |
| 6 | Translator tests | `tests/test_v1_translate_result.py` | done |
| 7 | Router tests replace interim pins | `tests/test_v1_tools.py` | done |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | OK |
| Targeted tests (8 files) | 946 passed, 0 failed, 0 skipped (`-rs` listed none), 485.95s |
| OpenAI SDK tests | passed, not skipped (openai 3.40.0) |
| E2E | in-process via TestClient (Task 7 tests); live clients are STORY-016/017 |
| Full suite | deferred to orchestrator (user decision) |

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_v1_schemas.py tests/test_v1_translate_result.py tests/test_v1_tools.py tests/test_v1_router.py tests/test_v1_sse.py tests/test_v1_errors.py tests/test_query_outcomes_regression.py tests/test_untouched_app.py -q -rs`

SDK install (project venv only, requirements files not edited): `.venv/Scripts/python -m pip install openai==3.40.0` -> `openai.__version__ == 3.40.0`.

## Files Changed

| File | Action |
|------|--------|
| `app/models/v1_schemas.py` | UPDATE |
| `app/services/v1_translate.py` | UPDATE |
| `app/routers/v1.py` | UPDATE (docstring only) |
| `tests/test_v1_schemas.py` | UPDATE |
| `tests/test_v1_translate_result.py` | UPDATE (append only) |
| `tests/test_v1_tools.py` | UPDATE |
| `.agents/PRDs/PRD-017-tool-calling/PRD.md` | UPDATE (Section 10 amendment, orchestrator-approved) |

## Deviations from Plan

1. **DD-1 (orchestrator accepted): text-only bodies carry neither `tool_calls` nor `harness.actions`.** The story's AC3 (`actions == []` on text-only) and AC5 (`tool_calls: null`, `actions: []` on text-only) are read through this decision: an absent key means "no call evaluated". It keeps D10 (flag off = PRD-015 byte for byte). PRD Section 10 was amended in the working tree and is staged with this commit. Readers use `.get("actions", [])`.
2. **Interim streamed shape (orchestrator accepted):** a stream with an allowed call has an empty-delta content chunk and a `tool_calls` finish reason with no call data, until STORY-012. `test_interim_streamed_allowed_call_is_not_yet_streamed` pins only "no call data leaks" and says STORY-012 replaces it.
3. **Approved pre-existing test edits:** `tests/test_v1_schemas.py` parametrize value `"tool_calls"` -> `"function_call"` (PRD-017 comment); in `tests/test_v1_tools.py`, `_assert_no_call_released` no longer checks `'"tool_calls"'` and the JSON branch of `test_drop_table_via_shell...` asserts `tool_calls is None` (both with PRD-017 comments). The three `test_interim_*` tests were replaced/renamed (STORY-008/010 tests created on this epic, so no `_DELIBERATELY_SUPERSEDED_TESTS` entry). No other pre-existing assertion changed.
4. The plan said the orchestrator note about openai being installed was wrong; it was absent, so it was installed (Task 4).

## Tests Written

- `test_v1_schemas.py`: text-only no keys, explicit null kept, Section 10 shape, harness actions shape, decision vocabulary pin, SDK parses released calls, SDK parses null tool_calls.
- `test_v1_translate_result.py`: two released calls no text, all denied, text plus calls, mixed, actions order, release finish_reason wins, no-outcome body, T1 AST guard, SDK parse.
- `test_v1_tools.py`: denied note + null + stop, streamed denied, allowed released, interim streamed allowed, mixed, flag-on text-only equals flag-off, router SDK round trip.

## Acceptance Criteria

- [x] AC1: `test_two_released_calls_and_no_text`, `test_allowed_call_is_released_with_content_null_and_finish_tool_calls`
- [x] AC2: `test_every_call_denied_is_the_notes_with_tool_calls_null`, `test_text_plus_released_calls_carries_both`, `test_denied_call_is_the_note_with_tool_calls_null_and_stop`, `test_mixed_response_releases_the_allowed_call_and_notes_the_denied_one`
- [x] AC3 (DD-1 reading): `test_harness_actions_list_every_decision_in_model_order`, `test_harness_actions_serialize_one_entry_per_decision`, `test_without_an_outcome_the_body_is_prd_015s`
- [x] AC4: `test_openai_sdk_parses_released_calls`, `test_completion_with_calls_parses_in_the_openai_sdk`, `test_router_sdk_round_trip` (passed on openai 3.40.0)
- [x] AC5 (DD-1 reading): `test_without_an_outcome_the_body_is_prd_015s`, `test_flag_on_text_only_body_is_the_flag_off_body`, unedited PRD-015 expectations
- [x] T1: `test_translate_result_never_reads_upstream_tool_calls`, unedited `test_router_never_reads_raw_upstream_tool_calls`
