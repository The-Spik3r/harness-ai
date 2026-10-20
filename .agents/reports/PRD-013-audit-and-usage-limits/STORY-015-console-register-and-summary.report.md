---
story: STORY-015
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-015-console-register-and-summary.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: b6085a4
status: COMPLETE
completed: 2026-10-19
---

# Implementation Report: STORY-015, Admin console: Register fields, verdict, search and summary figures

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-015-console-register-and-summary.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `b6085a4`

## Summary

The admin console now shows PRD-013's audit fields. It gains no column and no new visual direction, and no file under `app/` changed.

- **Tokens cell.** It reads `2,140 / 312` when the row recorded a split, the total when it recorded only that, and `—` when it recorded neither. A half split falls back to the total. Both forms use thousands separators.
- **Disclosure.** It gains six lines in evidence-first order: Usage limit under the pattern lines, Conversation under the prompt hash, then Ingress, Messages, Streamed and Tool calls. Every value is a string formatted once in `to_audit_row`. The two flags read "yes"/"no", and NULL reads `—`. `AuditRow` still has no preview field.
- **Verdict.** `derive_verdict` gains one line: `limit_exceeded is not None` → **denied**, after the pattern arm and before the success check. It uses the same predicate as `/stats`. Every existing verdict test is byte-identical.
- **Search.** `_matches` also matches `conversation_key` and `ingress`, still in memory over the loaded window. Pasting a key isolates a conversation.
- **Summary.** "Denied at a usage limit" is the third indented blocked figure, shown as a share of the total. A new **Tokens** block, between Traffic and Who and what, shows input and output totals. Its scope line is "All time, rows that recorded an input and output split", because the sums read NULL as 0.
- **AC 5.** `load()` is unchanged. A failed read of any of the three new figures is named by its own `READ_LABEL_*`. Nothing is committed, so the last good sheet stays rendered under the fault (plan D-G).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Inventory grep + baseline (408 passed) | — | ✅ |
| 1 | `AuditRow` + 6 `str` fields | `chat_ui/chat_ui/admin_models.py`, `tests/test_admin_models.py` | ✅ |
| 2 | Verdict line + precedence comment; `TOKENS_SPLIT_SEPARATOR`, `_format_tokens`, `_flag`; `to_audit_row` | `chat_ui/chat_ui/admin_formatting.py` | ✅ |
| 2b | Formatting tests (appended only) | `tests/test_admin_formatting.py` | ✅ |
| 3 | Copy: 8 detail labels/words, `COLUMN_TOKENS_TITLE`, placeholder, Tokens heading/scope, 3 figure labels | `chat_ui/chat_ui/admin_copy.py`, `tests/test_copy.py` | ✅ |
| 4 | `_matches` + 2 fields; `_count_figure(scope=)`; third blocked figure; `token_figures` | `chat_ui/chat_ui/admin_state.py` | ✅ |
| 5 | State tests: search, 12-figure inventory, token scope, AC 5 per new figure | `tests/test_admin_state.py` | ✅ |
| 6 | Disclosure lines; tokens track; head `title`; search field width | `chat_ui/chat_ui/components/register.py` | ✅ |
| 6b | Register tests | `tests/test_register.py` | ✅ |
| 7 | Tokens block | `chat_ui/chat_ui/components/summary.py` | ✅ |
| 7b | Summary tests | `tests/test_summary.py` | ✅ |
| 8 | Full suite + regression gates | — | ✅ (see Validation) |
| 9 | Browser E2E | — | ✅ 8/8 |
| 10 | Commit, report, status | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import | n/a. No `app/` change; `chat_ui.chat_ui.admin_state` imports cleanly |
| Frontend lint | n/a (no Node frontend). The Reflex probes in `test_register.py`/`test_summary.py` compile every factory ✅ |
| Affected suites (admin_*, register, summary, admin_shell, copy, pii guard, untouched_app, stats_router) | ✅ 648 passed |
| AC 4: `git diff tests/test_admin_formatting.py` removes no line | ✅ additions only |
| Full suite | ✅ 3744 passed, 27 skipped. 3 errors were libSQL fixture-setup flakes (below) |
| Flaked tests rerun after `docker restart harness-libsql-dev` | ✅ 220 passed + `test_two_instance_smoke.py` 14 passed |
| App builds and serves (`reflex run --env prod`) | ✅ `App running at: http://0.0.0.0:3000/` |
| E2E | ✅ 8/8 |

**Flakes, not regressions.** Three full-suite runs each errored on a *different* small set of DB-backed tests outside the console: `test_duplicate_checker`, `test_manage_users_cli`, `test_two_instance_smoke`, `test_query_pipeline_pii_profiles`, `test_query_pipeline_usage_limits`, `test_audit_logger`, `test_chat_components_import`, `test_query_pipeline_patterns`. Every one failed at fixture setup with Hrana `STREAM_EXPIRED` or a `tcp connect error` (os error 10060). These are the signatures PRE-PRD-017 describes. None of these files import console code. A peer Claude session on this machine shares the dev container, and during E2E the DB was reset to an empty schema by a process outside this session. After a container restart, every test that had errored passed.

## End-to-End Checks

All checks ran in Chrome (DevTools MCP) against `reflex run --env prod` on the dev libSQL container. The console was signed in with `ADMIN_TOKEN`. Four rows were written through `insert_audit_log` under `user_id='e2e-story015'` and deleted afterwards. (a) has a split and `v1`, with conversation key K. (b) is a second `v1` row on K. (c) has a total only. (d) is a usage-limit row on `chat`.

| # | Check | Result |
|---|-------|--------|
| 1 | Tokens cell: (a) `2,140 / 312` (`scrollWidth == clientWidth`, untruncated), (c) `88`, (d) `—`. The Tokens head has `title` "Input / output tokens, or the total where no split was recorded" | ✅ |
| 2 | (d) carries the **DENIED** stamp. The *denied* verdict filter leaves only (d) | ✅ |
| 3 | Disclosure (a): Usage limit `—`, Conversation K (wraps, not clipped), Ingress `v1`, Messages `7`, Streamed `no`, Tool calls `no`. (c): `—` on ingress, messages, conversation, limit. (d): Usage limit `tokens`. Order matches D-C | ✅ |
| 4 | Find K gives #1, #2 ("2 of 4 shown"). Find `chat` gives #4. Clear filters empties the field and restores 4 | ✅ |
| 5 | Summary: "Denied at a usage limit" 1, `25.0% of all queries`, indented. Tokens block 2,170 / 322 with the split scope line. `summary_snapshot()` in-process returns `{} 2170 322 1` | ✅ `docs/screenshots/admin-stats-usage-and-tokens.png` |
| 6 | 390px: `documentElement.scrollWidth == innerWidth` on Register and Summary. The table scrolls in its container (1106 vs 390). Find field at x 60–299px. Summary values wrap under labels | ✅ |
| 7 | Light theme at 390px: Traffic and Tokens blocks legible with existing ink only | ✅ `docs/screenshots/admin-stats-tokens-light-390.png` |
| 8 | Rebuilt app after the two width fixes: placeholder text 223px inside a 238px field; tokens cell 120px | ✅ |

AC 5's failure arm was proved by `test_a_failed_new_figure_is_named_and_the_sheet_stays_standing`, not live, as planned.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | +46/-6 |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | +70/-5 |
| `chat_ui/chat_ui/admin_models.py` | UPDATE | +12/-1 |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +81/-16 |
| `chat_ui/chat_ui/components/register.py` | UPDATE | +57/-13 |
| `chat_ui/chat_ui/components/summary.py` | UPDATE | +22/-9 |
| `tests/test_admin_formatting.py` | UPDATE | +128 |
| `tests/test_admin_models.py` | UPDATE | +29/-1 |
| `tests/test_admin_state.py` | UPDATE | +168/-18 |
| `tests/test_copy.py` | UPDATE | +20 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +17 |
| `tests/test_register.py` | UPDATE | +77 |
| `tests/test_summary.py` | UPDATE | +23/-14 |
| `docs/screenshots/admin-stats-usage-and-tokens.png`, `admin-stats-tokens-light-390.png` | CREATE | binary |

## Deviations from Plan

1. **Task order: copy (Task 3) before formatting (Task 2).** `_flag` imports the flag words from `admin_copy`, so the copy had to exist first. The content is unchanged.
2. **`tests/test_copy.py` added.** It holds a census, `declared == asserted`, over every `admin_copy` constant, which the plan's inventory grep missed. Each new constant was added to it with a `# PRD-013 (STORY-015)` comment.
3. **`tests/test_pii_redaction_integration.py` added.** Its `test_no_pre_epic_test_function_was_removed_or_renamed` flags renamed tests. The three renames the plan called for are recorded in `_DELIBERATELY_SUPERSEDED_TESTS`, with an old → new comment in the established format:
   - `…all_nine_stats_response_figures` → `…all_twelve…`
   - `…two_that_indent` → `…three_that_indent`
   - `test_the_three_blocks_are_headed` → `test_the_four_blocks_are_headed`
4. **Tokens track 7.5rem, not 7rem.** I measured live in the data face: `999,999 / 99,999` is 115.2px and a 7rem track is 112px. `_MIN_WIDTH` is `63.75rem` (+2.5rem) instead of `63.25rem`. The comment states the measurement.
5. **Placeholder shortened and field widened.** The planned placeholder "user, model, id, ingress or conversation" clipped in the 13rem field (about 290px of text in 208px). Widening the field enough to hold it would overflow a 360px viewport beside its label. The copy is now "user, model, id or conversation", which names the paste-a-key use, and the field is 15rem: the text measures 223px inside a 238px field. Ingress search still works. `admin_copy` and `_matches` both state that the placeholder omits it.
6. **Search tests use a separate fixture** (`_AUDIT_FILTER_ROWS`). The plan allowed this, and it leaves every `_FILTER_ROWS` expectation unchanged.
7. **`_head_cell` gained a `title` keyword instead of `**props`.** The plan anticipated this: its existing `custom_attrs` would have collided.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_formatting.py` | `test_tokens_cell_reads_input_slash_output_when_split`, `test_tokens_cell_falls_back_to_the_total`, `test_tokens_cell_absent_when_neither`, `test_to_audit_row_carries_the_audit_fields`, `test_pre_prd013_row_shows_the_absent_mark`, `test_a_null_flag_is_absent_never_no`, `test_a_usage_limit_row_is_denied`, `test_a_duplicate_still_outranks_a_usage_limit`, `test_no_limit_changes_no_existing_verdict`, `test_no_preview_reaches_the_audit_fields` |
| `tests/test_admin_state.py` | `test_free_text_matches_conversation_key_and_ingress` (×7), `test_the_conversation_search_composes_with_the_verdict`, `test_the_token_figures_are_thousands_separated_and_unshared`, `test_a_failed_new_figure_is_named_and_the_sheet_stays_standing` (×3). Extended: the no-read test, 12-figure inventory, scopes, blocked trio, zero total |
| `tests/test_register.py` | `test_the_usage_limit_and_the_conversation_keep_evidence_first`, `test_the_row_gains_no_column`, `test_the_tokens_head_states_the_split_order`. Extended: `DETAIL_LABELS`/`DETAIL_ROW_FIELDS` (+6 parametrized cases each) |
| `tests/test_summary.py` | `test_the_four_blocks_are_headed` (now also asserts heading order). Extended: `FIGURE_VARS`, `COPY_NAMES` |
| `tests/test_admin_models.py` | The 6 fields in the exact field set, defaults and `str` types |

## Acceptance Criteria

- [x] A row with a token split renders `2,140 / 312`. A row with only a total shows the total, and a row with neither shows the absent mark.
- [x] An opened disclosure shows ingress, message count, conversation key, streamed, tool calls and limit, each with the absent mark when NULL. `AuditRow` has no preview field, and `tests/test_admin_models.py` passes.
- [x] A typed `conversation_key` or ingress name filters the Register to only those rows, without a database read.
- [x] A row with `limit_exceeded` set is **denied**, and no existing verdict changes. The existing `derive_verdict` tests pass unmodified.
- [x] The summary shows total input tokens, total output tokens and the usage-limit count, each with its scope line. A failure of one of those reads names that figure and leaves the others rendered.
- [x] All tasks completed
- [x] Console builds and serves
- [x] Follows existing patterns
