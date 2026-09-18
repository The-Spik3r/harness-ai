---
story: STORY-008
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-008-context-limit-refusal.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: e4de634
status: COMPLETE
completed: 2026-09-18
---

# Implementation Report — STORY-008: Context-limit refusal: response model, audited pipeline arm, /query passthrough

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-008-context-limit-refusal.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `e4de634`

## Summary

`QueryResponse` and `QueryPipelineResult` gained a fifth member,
`QueryBlockedContextLimitResponse`, and `run_conversation` gained the arm that
returns it, at STORY-007's `# context limit (STORY-008)` marker: after all
three authorization checks, before `check_duplicate`. `_context_limit_exceeded`
reads `CONTEXT_MAX_MESSAGES` and `CONTEXT_MAX_CHARACTERS` off `settings` per
call, checks messages first, returns on the first breach, and compares with a
strict `>` so a conversation exactly at a maximum is within it. The refusal
writes one audit row with `success=False`, `error_message="context limit:
<limit> <actual> > <maximum>"`, the last user turn as the audited prompt, and
the `dedup_key` and `session_id` every other arm passes.

`POST /query` needed no router change: the route already declares
`response_model=QueryResponse` and returns the pipeline result unchanged, so
widening the union *is* the passthrough. That was verified rather than assumed —
the new outcome-7 regression test asserts the HTTP body as an exact dict, which
is what proves FastAPI's non-discriminated union serializes the new member as
itself instead of matching one of the three sibling `BLOCKED` models and
dropping `limit`, `maximum` and `actual`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `QueryBlockedContextLimitResponse` + widened `QueryResponse` | `app/models/schemas.py` | ✅ |
| 2 | Model shape, union membership, `Literal` refusal tests | `tests/test_schemas.py` | ✅ |
| 3 | `_context_limit_exceeded` + the audited arm at the marker | `app/services/query_pipeline.py` | ✅ |
| 4 | Limits, boundary, precedence, audit row, check order | `tests/test_query_pipeline_context_limit.py` | ✅ |
| 5 | `test_outcome_7_context_limit` | `tests/test_query_outcomes_regression.py` | ✅ |
| 6 | Interim ChatState bubble pin (`# replaced by STORY-013`) | `tests/test_chat_state.py` | ✅ |
| — | Call-site guard counts 7 → 8 (see Deviations) | `tests/test_query_pipeline_dedup_key.py`, `tests/test_query_pipeline_session_passthrough.py` | ✅ |
| 7 | Full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`python -c "from app.main import app"`) | ✅ |
| Frontend lint | n/a — no frontend file changed (the chat UI's `state.py` is untouched) |
| Tests | ✅ 2104 passed, 25 skipped (full suite, 6m06s) |
| E2E | ✅ 6/6 |

The libSQL dev server was down at the start of the run (Docker Desktop was not
running). Started Docker Desktop and the `harness-libsql-dev` container; the
mass fixture errors cleared immediately, as the known-issue note predicts.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/models/schemas.py` | UPDATE | +25 |
| `app/services/query_pipeline.py` | UPDATE | +74/-3 |
| `tests/test_query_pipeline_context_limit.py` | CREATE | +~350 |
| `tests/test_schemas.py` | UPDATE | +40 |
| `tests/test_query_outcomes_regression.py` | UPDATE | +37 (additions only) |
| `tests/test_chat_state.py` | UPDATE | +44 |
| `tests/test_query_pipeline_dedup_key.py` | UPDATE | +9/-2 |
| `tests/test_query_pipeline_session_passthrough.py` | UPDATE | +12/-5 |

## Deviations from Plan

1. **Two guard tests updated, which the plan's file list did not name.**
   `test_every_log_query_call_site_in_the_pipeline_passes_dedup_key` and
   `…_passes_session_id` assert the exact number of `log_query(` call sites in
   the pipeline — seven — and both docstrings say they are "the guard for the
   eighth arm nobody has written yet". This story writes that eighth arm, so
   both went red on the first run and the counts were raised to eight, with a
   comment naming STORY-008 as the arm they were waiting for and telling the
   next author to raise them again. This is the tests working as designed, not
   a contract being broken: the accompanying `dedup_key=` / `session_id=`
   keyword assertions were left untouched and the new arm satisfies both.

2. **A second boundary test added** (`…_exactly_at_the_message_limit_is_not_refused`).
   The plan specified the characters boundary only; the messages boundary costs
   four lines and closes the same off-by-one on the other limit.

3. **`test_run_query_reaches_the_same_arm` added.** Not in the plan. It pins
   that the one-message adapter reaches the same check, which is the link
   between the pipeline tests and outcome 7 being reachable from `/query` at
   all.

4. **`Tuple` from `typing` rather than the builtin `tuple[...]`** in the
   helper's return annotation, matching the module's existing `typing` imports.

5. **The E2E run used a temporary harness file under `tests/`**, deleted after
   the run and not committed. It covered the one E2E item no permanent test
   covers — `GET /audit` rendering the refusal row — plus the full HTTP path
   with a real, owned `session_id`. First run surfaced a 403 from the router's
   foreign-session check, which was the harness passing an unowned session id,
   not a defect; minting a real session made it green.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_context_limit.py` | over message limit reports the counts; over both limits reports `messages`; over character limit reports the counts; exactly at the character limit is not refused (upstream reached); exactly at the message limit is not refused; character refusal writes one row naming the limit (`success=0`, preview + hash of the last user turn, `session_id`, `dedup_key`); message refusal row names the messages limit; refusal row sets no verdict column; `check_duplicate` never called on refusal; a forbidden identity gets `forbidden`; a disallowed model is refused before the limit; limits are read per call, not captured at import; `run_query` reaches the same arm |
| `tests/test_schemas.py` | context-limit response shape; membership in `QueryResponse`; unknown `limit` values rejected (4 parametrized) |
| `tests/test_query_outcomes_regression.py` | `test_outcome_7_context_limit` — 200, exact body, one row, `success=0`, `error_message`, non-NULL `dedup_key` |
| `tests/test_chat_state.py` | context-limit result lands on the interim `internal_error` bubble (`# replaced by STORY-013`) |

## Acceptance Criteria

- [x] `QueryBlockedContextLimitResponse(status, reason, limit, maximum, actual)` exists in `app/models/schemas.py`, is a member of `QueryResponse`, and `QueryPipelineResult` includes it
- [x] `CONTEXT_MAX_MESSAGES=3` + a 4-message conversation → `limit="messages", maximum=3, actual=4, reason="Conversation exceeds context limit"`; over both limits reports `messages`
- [x] `CONTEXT_MAX_CHARACTERS=10` + 12 characters → `limit="characters", maximum=10, actual=12`; exactly 10 is not refused
- [x] One audit row with `success=0`, `error_message="context limit: characters 12 > 10"` (and the `messages` equivalent), the last user turn as `prompt`, non-NULL `dedup_key`, the passed `session_id`; the check runs after all three authorization checks and before `check_duplicate` (spies both ways)
- [x] `POST /query` with a prompt of `CONTEXT_MAX_CHARACTERS + 1` characters → 200 with the context-limit body, pinned by `test_outcome_7_context_limit`; rows 1–6 unmodified (`git diff`: 37 insertions, 0 deletions)
- [x] Interim `ChatState` behaviour pinned with a `# replaced by STORY-013` comment
- [x] Full suite green
- [x] Follows existing patterns

## Notes for STORY-013 and STORY-009

- STORY-013 should **delete**
  `test_chat_state_send_context_limit_lands_on_interim_internal_error_bubble`
  and assert the real `context_limit` bubble in its place. The bubble needs
  `limit`, `maximum` and `actual` — all three are on the response.
- STORY-009's full check-order spy list now has eight arms to cover, and
  `_context_limit_exceeded` is the only one whose position is currently pinned
  by two single-purpose tests rather than the ordered list.
