---
story: STORY-002
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-002-retarget-tool-calling-runtime-strings.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: pending
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-002: Retarget the six "(PRD-016)" tool-calling runtime strings to "(PRD-017)"

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-002-retarget-tool-calling-runtime-strings.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `pending`

## Summary

Tool calling is PRD-017 (PRD Numbering note, D14). The six runtime strings under `app/` that said `(PRD-016)` now say `(PRD-017)`. In each one only that token changed; error codes, parameters and the rest of the text are unchanged. On the orchestrator's decision, a seventh string that also names tool calling, `duplicate_checker.py:60` (`tool turns: PRD-016`), was retargeted too. Every test that asserted one of these strings now asserts the new text, with a `PRD-016 D14 (STORY-002)` comment. The two "until tool calling ships (PRD-016)" sentences in `docs/features.md` (lines 82 and 151) now say `(PRD-017)`. Comments and docstrings that say PRD-016 were left alone, as AC4 requires.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `/v1` translator strings 1-3 (lines 120, 218, 222) | `app/services/v1_translate.py` | ✅ |
| 2 | Normalizer, OpenRouter client, pipeline step 0 (strings 4-6) | `app/models/messages.py:76`, `app/services/openrouter_client.py:199`, `app/services/query_pipeline.py:73` | ✅ |
| 3 | Tests for string 1 | `tests/test_v1_translate_request.py`, `tests/test_v1_router.py` | ✅ |
| 4 | Tests for string 4 (two `match` values + comment) | `tests/test_messages.py` | ✅ |
| 5 | Tests for string 5 (regex, negative assertion, two renames) | `tests/test_openrouter_client.py` | ✅ |
| 6 | dedup_key string 7 + test (rename), deviation kept by the orchestrator | `app/services/duplicate_checker.py:60`, `tests/test_dedup_key.py` | ✅ |
| 7 | features.md tool-calling references only (82, 151) | `docs/features.md` | ✅ |
| 7b | Register the three test renames with the rename census (not in plan; see Deviations) | `tests/test_pii_redaction_integration.py` | ✅ |
| 8 | Sweep greps, import check, targeted tests | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ `OK` |
| Frontend lint | n/a (no `frontend/` in this repo) |
| `chat_ui` import | n/a (`chat_ui/` not touched; it contains none of these strings) |
| AC4: `grep -rn "(PRD-016)" app/ --include=*.py` | ✅ no output |
| Remaining `PRD-016` in `app/` | ✅ 8 lines, all comments/docstrings from the plan's Inventory |
| Remaining `PRD-016` in `tests/*.py` | ✅ only the comment/docstring lines the plan lists, plus the new `PRD-016 D14` citations and the rename register; no assertion |
| `docs/features.md` | ✅ no `PRD-016`; `PRD-017` at lines 82 and 151 |
| Targeted run, every test file importing a changed module (57 files) | 2843 passed, 1 skipped, 2 failed (1:00:55). Failures: `test_pii_redaction_integration.py::test_no_pre_epic_test_function_was_removed_or_renamed` (caused by the renames, fixed in Task 7b) and `test_query_router.py::test_full_pipeline_latency_within_budget` (the known environmental timing failure from the `main` baseline) |
| Rerun after the fix: `test_pii_redaction_integration.py` + the 5 modified test files | ✅ 813 passed |
| Full suite | Deferred to orchestrator (user decision) |
| E2E | ✅ `test_v1_router.py::test_translation_refusal_is_400_without_row` asserts the wire body `"tools: tool calling is not supported (PRD-017)"`, `code: tools_not_supported`, 400, no row. `tests/e2e/test_continue.py:444` asserts a prefix with no PRD token, so it is unaffected and was not run (it drives the Continue CLI) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/v1_translate.py` | UPDATE | +3/-3 |
| `app/models/messages.py` | UPDATE | +1/-1 |
| `app/services/openrouter_client.py` | UPDATE | +1/-1 |
| `app/services/query_pipeline.py` | UPDATE | +1/-1 |
| `app/services/duplicate_checker.py` | UPDATE | +1/-1 |
| `docs/features.md` | UPDATE | +2/-2 |
| `tests/test_v1_translate_request.py` | UPDATE | +2/-1 |
| `tests/test_v1_router.py` | UPDATE | +2/-1 |
| `tests/test_messages.py` | UPDATE | +5/-3 |
| `tests/test_openrouter_client.py` | UPDATE | +7/-4 |
| `tests/test_dedup_key.py` | UPDATE | +4/-2 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +18 |
| `.agents/plans/PRD-016-action-policy-rules/completed/STORY-002-retarget-tool-calling-runtime-strings.plan.md` | CREATE (archived) | — |
| `.agents/stories/PRD-016-action-policy-rules/STORY-002-retarget-tool-calling-runtime-strings.md` | UPDATE | frontmatter |
| `.agents/PRDs/PRD-016-action-policy-rules/index.md` | UPDATE | regenerated |
| this report | CREATE | — |

## Deviations from Plan

1. **Seventh string retargeted (plan Task 6, kept by the orchestrator).** `app/services/duplicate_checker.py:60` names tool calling as `(tool turns: PRD-016)`. The PRD counts six strings because it counts the ones a `/v1` client can read, and no client can read this one. It is still retargeted, because D14's reason applies to any reader. Its test `tests/test_dedup_key.py` was renamed `..._naming_prd_017` and asserts `PRD-017`.
2. **Rename census updated (Task 7b, not in the plan).** `tests/test_pii_redaction_integration.py::test_no_pre_epic_test_function_was_removed_or_renamed` counts every pre-epic `def test_*` against `merge-base main HEAD` and failed on the three renames the plan calls for. The three old names were added to `_DELIBERATELY_SUPERSEDED_TESTS`, with a comment block in the file's existing shape (PRD, story, reason, old -> new). That is the repo's mechanism for deliberate renames. The guard passes again. `tests/test_untouched_app.py` has the same census, but it only covers six pinned suites, and none of them changed.
3. **Negative test.** `test_null_content_without_tool_calls_omits_prd_017_note` asserts `"PRD-017" not in`, so it still tests something after the change (plan risk 2).
4. **`docs/features.md`**: only the two tool-calling references changed. The off-by-one numbering for action policy (`PRD-015`) and the endpoint (`PRD-014`) at lines 82, 153 and 220 is left for STORY-020, on the orchestrator's decision.

## Tests Written

No new test functions. Changed assertions, each with a `PRD-016 D14 (STORY-002)` comment:

| Test File | Test Cases |
|-----------|------------|
| `tests/test_v1_translate_request.py` | `test_tool_use_is_tools_not_supported` (8 params) |
| `tests/test_v1_router.py` | `test_translation_refusal_is_400_without_row` |
| `tests/test_messages.py` | `test_refuses_table_row[tool-calls-key]`, second refusal table row `tool_calls: []` |
| `tests/test_openrouter_client.py` | `test_null_content_with_tool_calls_names_prd_017`, `test_null_content_without_tool_calls_omits_prd_017_note` (renamed) |
| `tests/test_dedup_key.py` | `test_tool_turn_anywhere_is_refused_naming_prd_017` (renamed, 2 params) |

## Acceptance Criteria

- [x] A `/v1` request with `tools` is refused with `tool calling is not supported (PRD-017)`, and the code is still `tools_not_supported`. Proven by `test_v1_router.py::test_translation_refusal_is_400_without_row` and `test_v1_translate_request.py::test_tool_use_is_tools_not_supported`.
- [x] All six strings say `(PRD-017)`, and nothing else in them changed. `git diff app/` shows a one-token change per line.
- [x] Every test that asserts one of these strings asserts the new text, and each change carries a `PRD-016 D14` comment. Full suite: deferred to the orchestrator. The targeted files are green apart from the known environmental latency test.
- [x] A search of `app/` for `(PRD-016)` finds nothing, and comments that mention PRD-016 are unchanged.
