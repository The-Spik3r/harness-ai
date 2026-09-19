---
story: STORY-016
prd: PRD-010
plan: .agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-016-seven-outcome-and-chat-ui-regression.plan.md
epic_branch: epic/PRD-010-multi-turn-pipeline
commit: 233b208
status: COMPLETE
completed: 2026-09-19
---

# Implementation Report — STORY-016: Seven-outcome /query regression and chat UI regression on the finished epic

**Plan**: `.agents/plans/PRD-010-multi-turn-pipeline/completed/STORY-016-seven-outcome-and-chat-ui-regression.plan.md`
**Epic Branch**: `epic/PRD-010-multi-turn-pipeline`
**Commit**: `233b208`

## Summary

The proof pass for the epic. Three of the five acceptance criteria were already carried by
earlier stories, and this story's work there was to run them and record the evidence: the
seven `/query` outcomes and the STORY-003 characterization are pure additions to `main`, and
`tests/test_history_off_integration.py` is byte-identical to it. The two that were not carried
are new: `tests/test_chat_outcomes_regression.py` drives all seven result kinds through
`ChatState._do_send` with history on and off, and a new D7 section in
`tests/test_reporting_invariance.py` proves a multi-turn send with PII only in turn 1 is
counted exactly as its single-turn equivalent. **No production line changed.**

One quality-indicator gap was found and fixed in its own commit citing the story that
introduced it, per this story's Technical Notes.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Record the no-diff evidence for AC 1, AC 2, AC 4 | — | ✅ |
| 2 | Fix the quality-indicator gap (own commit, cites STORY-013) | `tests/test_chat_components_import.py` | ✅ |
| 3 | Seven chat outcomes, history ON | `tests/test_chat_outcomes_regression.py` | ✅ |
| 4 | Seven chat outcomes, history OFF | `tests/test_chat_outcomes_regression.py` | ✅ |
| 5 | D7 at the reporting surfaces | `tests/test_reporting_invariance.py` | ✅ |
| 6 | Full suite | — | ✅ |
| 7 | This report | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| `tests/test_chat_outcomes_regression.py` | ✅ 22 passed |
| `tests/test_reporting_invariance.py` | ✅ 9 passed |
| `tests/test_query_outcomes_regression.py` | ✅ 9 passed |
| Full suite | ✅ **2249 passed, 26 skipped** in 195.43s |
| E2E checklist (7 items) | ✅ 7/7 |

## PRD Section 11 — quality indicators, checked explicitly

### Full suite green

`2249 passed, 26 skipped, 2 warnings in 195.43s`. Frontend lint is not applicable: this repo's
UI is Reflex (Python), there is no `frontend/` npm project, and this story changed no UI code.

**The libSQL dev-server note applied, and was needed.** Running the full suite twice
back to back produced, on the later runs, fixture errors in modules this story never touches —
`test_manage_users_cli.py`, then `test_two_instance_smoke.py`, then `test_identity.py`, a
different unrelated module each time. That is the degradation signature the note describes, not
a regression: this story's own modules passed cleanly on every one of those runs, and the
rotating victim module is the tell. Per the note and this story's Technical Notes the container
was restarted rather than the code bisected, and the suite then came back fully green with the
figures above. Recorded here because a future reader hitting the same thing should reach for
the same action.

### No outcome assertion modified

| File | Evidence |
|------|----------|
| `tests/test_query_outcomes_regression.py` | `git diff --numstat main` → `72  0` — **72 insertions, 0 deletions**. Rows 1–6 are untouched by construction; the additions are `test_outcome_7_context_limit` and the STORY-003 characterization, exactly what AC 1 permits. |
| `tests/test_integration.py` | `git diff main` → empty. Not modified at all. |
| `tests/test_history_off_integration.py` | `git diff main` → empty. Byte-identical to `main`, as AC 4 requires. |
| `tests/test_query_router.py` | `+83 / -2`. Both deleted lines are the same edit in a **capture helper**, not an assertion: `seen.append(prompt)` → `seen.append(prompt[-1].content)`, each carrying an inline `# PRD-010 STORY-004: upstream now receives list[Message]`. No assertion changed. |

### Every modified pre-existing test carries a PRD-010 comment

`grep -rn "PRD-010" tests/` cross-referenced against `git diff --name-only main -- tests/`.
Eighteen pre-existing test modules are modified on this epic; all eighteen now carry a citation:

| File | PRD-010 mentions |
|------|------------------|
| `test_chat_components_import.py` | 2 *(was 0 — the gap this story found; see below)* |
| `test_chat_sessions.py` | 4 |
| `test_chat_state.py` | 8 |
| `test_chat_ui_startup_guard.py` | 1 |
| `test_config.py` | 2 |
| `test_copy.py` | 1 |
| `test_db.py` | 10 |
| `test_main.py` | 1 |
| `test_openrouter_client.py` | 6 |
| `test_pii_dedup_isolation.py` | 1 |
| `test_pii_redaction_integration.py` | 5 |
| `test_query_outcomes_regression.py` | 4 |
| `test_query_pipeline_dedup_key.py` | 1 |
| `test_query_pipeline_session_passthrough.py` | 1 |
| `test_query_router.py` | 4 |
| `test_schemas.py` | 1 |
| `test_success_metadata_footer.py` | 1 |
| `test_two_instance_smoke.py` | 1 |
| `test_reporting_invariance.py` | 2 *(added by this story, which modifies it)* |

**The gap.** `tests/test_chat_components_import.py` was modified by STORY-013 — two rows
adding `render_context_limit` and the `context_limit` kind — with no citation, while every
other modified module had one. Fixed in its own commit citing STORY-013 as the story that
introduced it, per this story's Technical Notes. The fix is comments only; the file's four
tests were green before and after.

### The seven `/query` outcomes and the seven chat kinds

| # | Outcome | `/query` (router) | Chat UI (`_do_send`) |
|---|---------|-------------------|----------------------|
| 1 | Success | `test_outcome_1_success` | `…[success]` (kind `assistant`) |
| 2 | Duplicate block | `test_outcome_2_duplicate_block_after_same_user_success` | `…[duplicate]` |
| 3 | Suspicious pattern | `test_outcome_3_suspicious_pattern_block` | `…[injection]` |
| 4 | Policy refusal | `test_outcome_4_policy_refusal` | `…[forbidden]` |
| 5 | Upstream failure | `test_outcome_5_upstream_failure` | `…[upstream_error]` |
| 6 | Internal failure | `test_outcome_6_internal_failure_{redactor,duplicate_storage}` | `…[internal_error]` |
| 7 | Context limit | `test_outcome_7_context_limit` | `…[context_limit]` |

Chat rows run twice each, once per arm, in
`test_each_outcome_renders_its_kind_and_persists_one_bubble`,
`test_only_the_success_adds_an_exchange_to_the_next_sends_history` and
`test_history_off_renders_the_same_bubbles_and_stores_nothing`.
`test_the_table_covers_every_outcome_kind_do_send_can_append` fails loudly if an eighth kind
is added to `_do_send` without a row in the table.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_chat_outcomes_regression.py` | CREATE | +459 |
| `tests/test_reporting_invariance.py` | UPDATE | +192 / −1 |
| `tests/test_chat_components_import.py` | UPDATE | +6 / −0 *(separate commit, cites STORY-013)* |

The single deleted line in `test_reporting_invariance.py` is an import widened from
`from app.services.identity import hash_token` to `… import Identity, hash_token`. PRD-009's
fixed seed, its ledger constants and every one of its existing assertions are untouched.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_chat_outcomes_regression.py` | `test_the_table_covers_every_outcome_kind_do_send_can_append`; `test_each_outcome_renders_its_kind_and_persists_one_bubble` ×7; `test_only_the_success_adds_an_exchange_to_the_next_sends_history` ×7; `test_history_off_renders_the_same_bubbles_and_stores_nothing` ×7 — **22 cases** |
| `tests/test_reporting_invariance.py` | `test_multi_turn_pii_in_turn_one_is_counted_like_the_single_turn_equivalent`; `test_the_follow_up_row_records_no_pii_although_history_carried_it`; `test_audit_and_stats_expose_the_multi_turn_row_with_no_new_field` — **3 cases** |

## Deviations from Plan

1. **A restore step the plan did not anticipate (Task 3).** The plan had the follow-up send
   run against an unmodified pipeline, but `arrange` for the `context_limit` case leaves
   `CONTEXT_MAX_CHARACTERS` shrunk for the rest of the test. The follow-up send then had its
   history trimmed away by `fit`, and "the refused turn is absent from the next history" passed
   because the history was *empty* — the exact way the plan's Risk 1 said this test could rot
   into proving nothing. Caught by a failing assertion (`assert any("an answered question" …)`)
   that was there for that purpose. Fixed with `_restore_ordinary_conditions`, applied
   unconditionally rather than per-outcome, and the reasoning is a docstring in the helper.
2. **The upstream assertion compares against the redacted text, not the raw text (Task 4).**
   The plan specified `messages[0] == Message("user", text)`. The success prompt names a place,
   which Presidio masks to `<LOCATION>` on the way upstream — correct D5 behaviour. Asserting
   the raw text would have been asserting that the single-turn path skips redaction, which it
   must not. The assertion now compares against the redactor's own output, and still pins the
   count, which is AC 4's actual claim.
3. **`/audit`'s body is `{"total", "queries"}`, not `{"entries"}` (Task 5).** The plan did not
   name the shape; the test now uses the same keys `test_audit_query_entry_has_no_dedup_key_d5`
   already reads.
4. **Frontend lint (implement.md Phase 4) is not applicable.** There is no npm frontend in this
   repo; the UI is Reflex. The backend import check was run in its place.

## Acceptance Criteria

- [x] Outcomes 1–6 pass with no assertion diff from `main` (`72 insertions, 0 deletions`), and outcome 7 passes — `tests/test_query_outcomes_regression.py`, 9 passed.
- [x] The upstream payload is byte-identical to STORY-003's characterization (`test_characterization_query_upstream_receives_prompt_model_and_no_api_key`), and a `null`-content reply still maps to 502 (`tests/test_query_router.py::test_null_content_openrouter_error_maps_to_502`).
- [x] History **on**: each of the seven renders its kind and persists exactly one outcome bubble (asserted as the kind list `["user", <kind>]`, since the user turn is persisted too), and only the success reaches the next send's history.
- [x] History **off**: bubbles identical to history-on (both arms parametrized over one table), nothing persisted (`chat_messages` empty, no session created), and upstream receives exactly one message where it is reached at all — with `_fail_if_called` proving the other five never reach it. `tests/test_history_off_integration.py` unmodified from `main`.
- [x] `pii_detected_queries` counts only sends whose new turn or output had PII, and every other figure matches the single-turn equivalent — asserted as an equality between two arms' deltas, not against a literal. The full suite is green.
- [x] All tasks completed
- [x] Full suite green; PRD Section 11 quality indicators checked explicitly above
- [x] Follows existing patterns
