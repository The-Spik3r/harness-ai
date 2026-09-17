---
story: STORY-001
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-001-message-model-and-normalization.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: a41155f
status: COMPLETE
completed: 2026-09-17
---

# Implementation Report — STORY-001: Message model, Role type and OpenAI content normalization

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-001-message-model-and-normalization.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `a41155f`

## Summary

Added `app/models/messages.py`, the internal message shape for the PRD-010 track (PRD Section 6.2). It exports:
- `Role = Literal["system", "user", "assistant", "tool"]`
- `@dataclass(frozen=True) Message(role, content: str)`
- `MessageNormalizationError`
- `normalize_message(raw)` and `normalize_messages(raw)`

The module imports only `dataclasses` and `typing`: no I/O, settings, pydantic or `app` import.

Normalization rules:

| Input | Result |
|---|---|
| String content | Passes through unchanged (whitespace preserved) |
| List of text parts | Joined with `"\n"`, so part boundaries stay visible to pattern detection |
| `null` content on `assistant` (or a missing `content` key) | `""` |
| `null` content on any other role | Refused |
| Non-text parts, unknown roles, malformed shapes | Refused |
| Any `tool_calls` key | Refused. This is checked before content, so OpenAI's `content: null` + `tool_calls` turn cannot normalize to `""` |

- Errors name a location (`messages[3]`, `content[1]`) and a rule, never a value.
- `normalize_messages` does not check cross-message structure; that is STORY-007's job.

`Message` gives the same `dedup_key` result as `query_pipeline._UserTurn` and matches the digests pinned in `test_dedup_key.py`, with no import in either direction. No production file changed.

This commit is the first on the new epic branch, so it also adds the PRD-010 PRD, story board, 18 stories and the promoted PRE-PRD-010, following PRD-009 STORY-001 (`9abef61`).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Branch precondition: epic cut from `main` @ `51e794f` (PRD-009 merged via PR #12) | — | ✅ |
| 1 | Message model and normalizer | `app/models/messages.py` | ✅ |
| 2 | Module surface, 6.2 table rows, malformed shapes | `tests/test_messages.py` | ✅ |
| 3 | `normalize_messages` index naming, no-echo canaries, non-sequence input | `tests/test_messages.py` | ✅ |
| 4 | `dedup_key` structural equivalence, import direction, purity | `tests/test_messages.py` | ✅ |
| 5 | No production caller changed | — (verification) | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A (no UI change; no linter configured in repo) |
| `tests/test_messages.py` | ✅ 50 passed |
| `test_dedup_key.py` + `test_query_pipeline_dedup_key.py` | ✅ 38 passed |
| Full suite (`pytest -q`) | ✅ 2015 passed, 25 skipped, 0 failed (157.9 s) |
| E2E | ✅ 5/5 |

### E2E checklist

- [x] `dedup_key('juan@empresa.com', normalize_messages([{'role':'user','content':[{'type':'text','text':'hi'}]}]))` printed the 64-hex key `4ef89cb51a961f71a940f3837559e331a6baf768c7ed3c0078f7ad533932240f`
- [x] `normalize_messages([{…'a'}, {'role':'user','content':None}])` raised `MessageNormalizationError: messages[1]: null content is only allowed on assistant messages`
- [x] `pytest tests/test_messages.py -v` green, with every 6.2 row shown as a named parametrize id
- [x] Full suite green
- [x] `git grep "models.messages"` over `app`, `chat_ui` and `tests` found only `tests/test_messages.py`

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/models/messages.py` | CREATE | +91 |
| `tests/test_messages.py` | CREATE | +351 |
| `.agents/PRDs/PRD-010-multi-turn-pipeline/{PRD,index}.md`, 18 story files | CREATE | +1,613 |
| `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-001-…plan.md` | CREATE | +339 |
| `pre-prds/PRE-PRD-010-multi-turn-pipeline.md` | UPDATE | +2/-2 |

## Deviations from Plan

1. **Branch base (Task 0).** The plan expected that the user would have to choose a base, because PRD-009 was not in `main`. By implementation time, `origin/main` @ `51e794f` included PRD-009 (PR #12), and `app/`/`tests/` were identical to `epic/PRD-009-duplicate-rescoping`. The epic was therefore cut from `main` exactly as `/implement` Phase 2.2 prescribes, and no question was needed. Local `main` was 22 commits behind, and its copy of `pre-prds/PRE-PRD-010…` blocked the checkout. That one-file edit (status → `promoted`) was stashed, then restored on the new branch unchanged.
2. **`test_is_pure` checks the AST, not source substrings.** The plan's substring check (`"settings" not in inspect.getsource(module)`) would fail on the module docstring, which states "no settings, no pydantic". The test instead combines two checks:
   - the import set must be a subset of `{dataclasses, typing}` (`test_no_import_in_either_direction`)
   - no `Name`/`Attribute` node may reference `settings`, `open`, `httpx`, `pydantic`, `log_query` or `redact`
3. **Canary cases extended.** Two extra fixtures: non-str `text` holding the canary, and dict content holding the canary. Every canary case runs through both `normalize_message` and `normalize_messages`, and also asserts the `messages[1]: ` prefix.
4. **Pinned-digest assertion is its own test.** It is `test_message_list_matches_pinned_single_turn_digest`, separate from the parametrized `_UserTurn` equivalence test, so STORY-007 can drop the `_UserTurn` test without touching the pin.
5. **Environment.** Docker Desktop and the `harness-libsql-dev` container were stopped. Both were started before running the tests, which the conftest autouse fixture requires. There were no fixture errors.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_messages.py` (50 cases) | See the groups below |

- **Surface**: `test_exports_the_specified_names_and_signatures`, `test_message_is_frozen`
- **6.2 valid rows**: `test_normalizes_table_row[string-content, two-text-parts-joined-with-newline, null-on-assistant-becomes-empty, tool-role-with-string-content, system-role-with-string-content]`
- **6.2 refused rows**: `test_refuses_table_row[image-url-part, null-on-user, null-on-system, null-on-tool, tool-calls-key, unknown-role-developer]`
- **Malformed shapes**: `test_refuses_malformed_shape[text-part-missing-text, text-part-non-str-text, part-not-a-mapping, message-is-a-list, message-is-a-string, missing-role, non-str-role, content-is-int, content-is-dict, tool-calls-empty-list]`
- **Normalization details**: `test_missing_content_key_is_treated_as_null`, `test_empty_text_is_not_refused`, `test_part_join_keeps_boundaries_visible`, `test_whitespace_and_extra_keys_are_preserved_and_ignored`
- **`normalize_messages`**: `test_normalize_messages_preserves_order_and_length`, `test_normalize_messages_accepts_empty_and_does_not_validate_structure`, `test_normalize_messages_accepts_any_sequence`, `test_invalid_element_names_its_index_and_rule`, `test_normalize_messages_refuses_a_string_or_non_sequence[4]`
- **No echo**: `test_error_never_echoes_content[7 canary cases]`
- **`dedup_key`**: `test_message_list_keys_like_the_pipeline_user_turn_today[ascii, non-ascii, empty]`, `test_message_list_matches_pinned_single_turn_digest`, `test_multi_turn_message_list_matches_structural_turns`, `test_normalized_output_feeds_dedup_key`
- **Boundaries**: `test_no_import_in_either_direction`, `test_is_pure`

## Notes for later stories

- **STORY-007**: when `_UserTurn` is deleted, remove only `test_message_list_keys_like_the_pipeline_user_turn_today`. The pinned-digest tests keep the guarantee.
- **Open policy question (plan Risk 2)**: `""` or `[]` content on a `user` turn normalizes to `""`. The 6.2 table refuses only `null`, and `test_empty_text_is_not_refused` pins that choice. A stricter rule would change the normalizer and flip that one test.

## Acceptance Criteria

- [x] `app/models/messages.py` exports `Role`, frozen `Message(role: Role, content: str)`, `MessageNormalizationError`, `normalize_message(raw: Mapping[str, Any]) -> Message` and `normalize_messages(raw: Sequence[Mapping[str, Any]]) -> list[Message]`.
- [x] Each row of PRD Section 6.2's table is a parametrized case with the specified result.
- [x] An invalid element at index 3 raises a message naming `messages[3]` and the rule, and content is never echoed.
- [x] A `list[Message]` ending in a user turn gives the same `dedup_key` as the equivalent `_UserTurn` list, with no import in either direction.
- [x] The full suite is green, with no production caller changed; `messages.py` is imported only by its tests.
