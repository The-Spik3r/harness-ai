---
story: STORY-010
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-010-redaction-size-limit.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: 46c88b6
status: COMPLETE
completed: 2026-09-25
---

# Implementation Report — STORY-010: Size limit and the redaction_characters refusal arm

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-010-redaction-size-limit.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code`
**Commit**: `46c88b6`

## Summary

`run_conversation` now has a fail-closed arm at the head of step 6. It sits after `get_pii_policy(profile_name)` and before the redaction loop.

- **What it counts:** `_analyzable_characters` counts the characters the analyzer would process. Only roles in `policy.input_roles` count. A message is measured as `strip_fenced_blocks(content)` when the policy skips fences. Every `\n` is left out.
- **When it refuses:** when `_redaction_limit_exceeded` finds that count strictly over `policy.max_characters`, the arm writes one row and returns `QueryBlockedContextLimitResponse(reason="Conversation exceeds redaction limit", limit="redaction_characters", maximum, actual)`. The row has `success=False`, `error_message="redaction limit: characters {actual} > {maximum}"`, the explicit `session_id` and the non-NULL `dedup_key`.
- **What it never does:** it never calls the analyzer or the upstream.
- **When it cannot fire:** under `chat`, whose `max_characters` is `None`, and when `PII_REDACTION_ENABLED` is off (plan D-2).
- **What it does not add:** no skip-and-flag and no new setting (D4).

`QueryBlockedContextLimitResponse.limit` gains `"redaction_characters"`.

In the chat UI, the context-limit bubble's unit now goes through `copy.CONTEXT_LIMIT_UNITS`:
- `messages` and `characters` map to themselves, so every existing detail line is byte-identical;
- `redaction_characters` renders as "characters to check for personal data N of M".

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Widen the `limit` literal, docstring for the third maximum | `app/models/schemas.py` | ✅ |
| 2 | `_analyzable_characters`, `_redaction_limit_exceeded` | `app/services/query_pipeline.py` | ✅ |
| 3 | The refusal arm at the head of step 6 | `app/services/query_pipeline.py` | ✅ |
| 4 | Pipeline tests (14 functions, 18 cases) | `tests/test_query_pipeline_pii_profiles.py` | ✅ |
| 5 | `CONTEXT_LIMIT_UNITS`; bubble detail goes through it | `chat_ui/chat_ui/copy.py`, `chat_ui/chat_ui/state.py` | ✅ |
| 6 | Schema, copy and state tests (append only) | `tests/test_schemas.py`, `tests/test_copy.py`, `tests/test_chat_state.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Baseline (touched suites, before any change) | ✅ 272 passed |
| Backend import (`from app.main import app`) | ✅ |
| Chat UI compile (`reflex compile --dry`) | ✅ compiled successfully |
| Frontend lint | n/a: no npm frontend; the chat UI is Reflex (Python), covered by the import and compile checks |
| Full suite `pytest tests/` | ✅ 3096 passed, 26 skipped (first run: 2 failed, the call-site census tests below, fixed) |
| E2E | ✅ 7/7 |

## E2E Results

All runs used the local libSQL dev server (`DATABASE_URL=http://127.0.0.1:8080`, overriding `.env`'s Turso URL) and a dummy OpenRouter key, so no real credentials were used.

| # | Check | Result |
|---|-------|--------|
| 1 | API booted with `PII_MAX_CHARACTERS_CODE=5`; `GET /health` | ✅ `{"status":"ok"}` |
| 2 | `POST /query` with a 124-character prompt (over the code limit of 5) | ✅ reached step 7: upstream 401 → HTTP 502, **not** `redaction_characters`; audit row 1 is the upstream-error row |
| 3 | `run_conversation(profile="code")` in-process, limit 50, 93 analyzable characters, upstream stub that raises | ✅ `BLOCKED` / `redaction_characters` / `maximum=50` / `actual=93`; upstream not called |
| 4 | Refusal row read back from the DB (and listed by the live `GET /audit`) | ✅ `success=False`, `error_message='redaction limit: characters 93 > 50'`, `session_id='e2e-010-2c299566'`, `dedup_key` non-NULL |
| 5 | Fence-heavy `code` conversation, 294 raw characters, limit 50 | ✅ answered; fenced block reached the upstream stub byte-identical |
| 6 | Identical over-limit request after raising the limit | ✅ `QuerySuccessResponse`, `was_duplicate_blocked=False`, same `dedup_key` as the refusal row |
| 7 | Chat UI (`reflex run --env prod --single-port`, `CONTEXT_MAX_CHARACTERS=20`): sign in, send 44 characters | ✅ `context_limit` bubble: "This chat is too long to send." / "Detail: characters 44 of 20" / "Start a new chat to continue." |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/models/schemas.py` | UPDATE | +11/-3 |
| `app/services/query_pipeline.py` | UPDATE | +80/-2 |
| `chat_ui/chat_ui/copy.py` | UPDATE | +11/-0 |
| `chat_ui/chat_ui/state.py` | UPDATE | +7/-2 |
| `tests/test_query_pipeline_pii_profiles.py` | UPDATE | +239/-1 |
| `tests/test_schemas.py` | UPDATE | +24/-0 |
| `tests/test_copy.py` | UPDATE | +56/-0 |
| `tests/test_chat_state.py` | UPDATE | +42/-0 |
| `tests/test_query_pipeline_dedup_key.py` | UPDATE | +4/-2 |
| `tests/test_query_pipeline_session_passthrough.py` | UPDATE | +4/-2 |

## Deviations from Plan

1. **Two call-site census tests updated (not in the plan).**
   - The tests: `test_every_log_query_call_site_in_the_pipeline_passes_dedup_key` (`tests/test_query_pipeline_dedup_key.py`) and `..._passes_session_id` (`tests/test_query_pipeline_session_passthrough.py`).
   - What they check: they count `log_query(` call sites in `query_pipeline` and assert every one passes the keyword.
   - Why they changed: the new arm is the tenth call site. Both tests say "Raise it again with the tenth". The count went from 9 to 10, and a comment cites PRD-012 STORY-010 (D4), per the PRD's quality indicator on modified pre-existing tests.
   - What did not change: the keyword assertions. The new arm passes both keywords.
2. **Chat UI copy tests import locally.** `test_copy.py` and `test_chat_state.py` are census-pinned, so the new tests import `CONTEXT_LIMIT_UNITS` inside the test functions and leave the existing import blocks untouched.
3. **`schemas.py` docstring:** "which of the two configured maxima" became "which configured maximum", so the docstring stays true with three values.
4. **E2E side effect reverted.** `reflex run` rewrote `chat_ui/reflex.lock/{package.json,bun.lock}` (dependency re-resolution, for example `lucide-react` 1.14 → 1.26). This is unrelated to the story, so both files were restored with `git restore` and are not in the commit.
5. **For review (plan D-2, a judgement call the PRD does not spell out):** the arm is off when `PII_REDACTION_ENABLED=false`. With nothing analyzed there is no redaction to bypass, and "exceeds redaction limit" would be untrue. Pinned by `test_the_master_switch_turns_the_arm_off`. Reversing it means deleting one guard clause and that test.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_pii_profiles.py` | `test_code_over_the_limit_is_refused_without_analyzing_or_calling_upstream`, `test_code_refusal_writes_exactly_one_row`, `test_a_refused_request_is_not_a_prior_query`, `test_fenced_blocks_do_not_count_toward_the_limit`, `test_the_fence_is_what_was_excluded`, `test_newline_runs_are_not_counted` (×2), `test_exactly_at_the_limit_is_not_refused_and_one_over_is`, `test_an_uncovered_system_turn_does_not_count`, `test_a_covered_system_turn_counts`, `test_assistant_history_counts`, `test_the_master_switch_turns_the_arm_off`, `test_a_pattern_block_wins_over_the_size_limit`, `test_chat_has_no_redaction_limit`, `test_the_arm_cannot_fire_under_chat` (×4: prose/fenced × `run_conversation`/`run_query`) |
| `tests/test_schemas.py` | `test_query_blocked_context_limit_response_accepts_redaction_characters` |
| `tests/test_copy.py` | `test_every_limit_value_has_a_unit_and_nothing_else_does`, `test_the_two_context_units_read_exactly_as_before`, `test_every_unit_obeys_the_context_limit_vocabulary_rules`, `test_the_redaction_unit_names_what_is_counted` |
| `tests/test_chat_state.py` | `test_chat_state_send_redaction_limit_renders_a_context_limit_bubble` |

## Acceptance Criteria

- [x] Given `profile="code"` and analyzable characters (covered roles, fenced blocks blanked, newline runs not counted) above `PII_MAX_CHARACTERS_CODE`, `run_conversation` returns `QueryBlockedContextLimitResponse(reason="Conversation exceeds redaction limit", limit="redaction_characters", maximum=..., actual=...)` and `call_openrouter` is not called.
- [x] That refusal writes exactly one row: `success=0`, `error_message="redaction limit: characters {actual} > {maximum}"`, explicit `session_id`, non-NULL `dedup_key`; a later identical request is not held as a duplicate.
- [x] A conversation over the limit raw only because of fenced blocks is not refused under `code`.
- [x] `limit` is `Literal["messages", "characters", "redaction_characters"]`, and the chat UI's context-limit bubble renders the new value with copy that names it.
- [x] Under `/query` or the chat UI (`chat`, `max_characters=None`) this arm cannot fire for any input within `CONTEXT_MAX_CHARACTERS`, and a test pins it.
- [x] All tasks completed
- [x] Full suite green; no assertion changed in `test_pii_redactor.py`, `test_pii_redaction_integration.py`, `test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py`
- [x] Follows existing patterns (step-3 arm shape, `_set` + `load()`, append-only census suites)
