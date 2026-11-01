---
story: STORY-005
prd: PRD-015
plan: .agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-005-message-translation.plan.md
epic_branch: epic/PRD-015-openai-compatible-endpoint
commit: d2eaf30
status: COMPLETE
completed: 2026-10-22
---

# Implementation Report — STORY-005: Request translation: messages, the developer role and edge structure checks

**Plan**: `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-005-message-translation.plan.md`
**Epic Branch**: `epic/PRD-015-openai-compatible-endpoint`
**Commit**: `d2eaf30`

## Summary

`app/services/v1_translate.py` is a new pure module: no I/O, no settings and no logging. It defines:

- `V1RequestError(code, message, param=None)`, which the router maps to a 400 in STORY-009/010
- the codes `INVALID_MESSAGES` and `TOOLS_NOT_SUPPORTED`; STORY-006 reuses `TOOLS_NOT_SUPPORTED` for the `tools` parameter
- `IGNORED_MESSAGE_NAME = "messages[].name"`
- `translate_messages(raw) -> (list[Message], frozenset[str])`

`translate_messages` makes one pass per message, in this order:

1. A `tool_calls` or `function_call` key is refused with `tools_not_supported`.
2. The `tool` role is refused with `tools_not_supported`.
3. A `name` key is recorded as ignored.
4. `developer` becomes `system`, on a copy of the message.
5. `normalize_message` runs. If it fails, its error is wrapped as `invalid_messages` with the same text and `param` set to `messages[i]`.

After the loop, an empty list or a last message that is not `user` is refused at the edge. This duplicates `query_pipeline._validate_conversation` on purpose, so `InvalidConversationError` cannot be reached from `/v1`. `app/models/messages.py` and `query_pipeline.py` are unchanged.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Module skeleton, error class and constants | `app/services/v1_translate.py` | ✅ |
| 2 | `translate_messages` | `app/services/v1_translate.py` | ✅ |
| 3 | Table tests for AC 1-3 | `tests/test_v1_translate_request.py` | ✅ |
| 4 | Canary, non-mutation and purity tests | `tests/test_v1_translate_request.py` | ✅ |
| 5 | Property test (AC 4) | `tests/test_v1_translate_request.py` | ✅ |
| 6 | Regression around the touched surface | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A: the repo has no `frontend/` and no npm lint script |
| `/health` on a live server | ✅ `{"status":"ok"}` 200. Uvicorn ran against a throwaway libSQL container on port 8086, seeded with `init_db()` and a `create-user` smoke user. The container was removed afterwards |
| `tests/test_v1_translate_request.py` | ✅ 540 passed in 1.1 s |
| Neighbours (`test_messages.py`, `test_v1_schemas.py`, the new file) | ✅ 618 passed |
| Docker-free sweep `pytest tests/ -m "not db"` | ✅ 3,249 passed, 26 skipped, 1,280 deselected (65 s) |
| Property test mutation check | ✅ With the last-is-user check disabled, 58 of 500 seeds fail. With it restored, all pass |
| E2E | ✅ 4/4 |

The full `db` suite was not run. Nothing in this story touches storage, and the shared libSQL container no longer exists.

## E2E Checklist (from plan)

- [x] `pytest tests/test_v1_translate_request.py -v`: every AC case passes and is named by its id
- [x] Property test: all 500 seeds pass, and the non-degenerate guard passes (190/500 accepted, 310 refused)
- [x] REPL: the OpenAI SDK-shaped payload returns `([Message('system','sys'), Message('user','hi')], frozenset({'messages[].name'}))`
- [x] Diff scope: only the two new files and the archived plan are in the story commit. The story and index bookkeeping are in the follow-up chore commit

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/v1_translate.py` | CREATE | +87 |
| `tests/test_v1_translate_request.py` | CREATE | +394 |
| `.agents/plans/PRD-015-openai-compatible-endpoint/completed/STORY-005-message-translation.plan.md` | CREATE (archived) | +296 |

## Deviations from Plan

1. **Property generator weights.** The plan's generator (uniform role and content picks, 0-6 messages) accepted only 75/500 inputs (15%). The plan's own guard caught this, because it requires at least 25%. The fix has two parts:
   - Half the generated messages are now ordinary valid turns. The other half still draw from every invalid shape (`tool`, `function`, no role, image parts, ints, `null`, `tool_calls`).
   - The content and role picks are weighted toward valid shapes, and the length is 0-4.

   With these changes, 190 inputs are accepted and 310 refused. The property is unchanged.
2. **Prefix assertion for list-level refusals.** The plan asserted `exc.message.startswith(f"{param}: ")` for every refusal. The two list-level messages, `messages must be a list` and `messages must not be empty`, use `messages` as the subject of the sentence and have no `messages: ` prefix. The table test therefore skips the prefix check when `param == "messages"`. The message still names the location and the rule.
3. **One extra test**, `test_v1_request_error_param_defaults_to_none`, pins the optional `param` that STORY-006 may rely on.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_v1_translate_request.py` | `test_equals_the_normalizer` (5 ids), `test_developer_becomes_system`, `test_developer_text_parts_are_joined_like_system`, `test_developer_null_content_follows_the_system_rule`, `test_name_is_ignored_and_reported_once`, `test_name_is_recorded_on_presence_even_when_null`, `test_refuses` (12 ids), `test_normalizer_failure_is_wrapped_with_its_text_kept` (4 ids), `test_first_failure_wins_tool_turn_before_last_not_user`, `test_tool_calls_are_checked_before_the_normalizer`, `test_codes_are_the_constants`, `test_v1_request_error_param_defaults_to_none`, `test_error_never_echoes_content` (6 ids), `test_input_is_never_mutated`, `test_accepts_any_sequence`, `test_is_pure`, `test_accepted_input_never_trips_the_pipeline_guard` (500 seeds), `test_property_generator_is_not_degenerate` |

## Acceptance Criteria

- [x] Given messages with string content, text-part lists and an assistant `content: null`, `translate_messages` returns `Message` objects equal to what `normalize_messages` returns for the same input.
- [x] A `developer` message becomes `Message("system", ...)`. A per-message `name` is ignored and reported as `messages[].name` in the returned ignored names.
- [x] An empty list, a last message that is not `user`, an image content part or an unknown role raises `V1RequestError(code="invalid_messages", param=<location>)`. A `tool` role or `tool_calls` raises `code="tools_not_supported"`, as the technical notes require. Messages name the location and rule and never the content, which the canary tests check.
- [x] Every input the function accepts passes `query_pipeline._validate_conversation` without `InvalidConversationError` (500-seed property test).
- [x] All tasks completed
- [x] `tests/test_v1_translate_request.py` passes with no DB
- [x] The `-m "not db"` sweep passes
- [x] Follows existing patterns (pure module, location-and-rule messages, canary tests)
