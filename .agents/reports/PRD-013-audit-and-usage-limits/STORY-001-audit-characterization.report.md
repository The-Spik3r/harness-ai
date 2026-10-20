---
story: STORY-001
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-001-audit-characterization.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 126f0da
status: COMPLETE
completed: 2026-10-05
---

# Implementation Report — STORY-001: Characterize today's audit row per arm and the client's usage parsing

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-001-audit-characterization.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits` (created from `main` @ `b184614`; base for AC 5: `5224280`)
**Commit**: `126f0da`

## Summary

`tests/test_audit_characterization.py` pins today's behaviour on untouched code:

- **The audit row on every arm.** Each of the twelve arms of `run_conversation` is forced with stubs. The rows it writes are read back through `get_audit_log` and compared, as one list, against literals covering 22 fields each. The arms are the three authorization refusals, context limit, duplicate, pattern block, pattern flag, redaction limit, input-redaction error, upstream error, output-redaction error and success.
- **The prompt on a multi-turn row.** On a `user`/`assistant`/`user` conversation and on a `system`/`user`/`assistant`/`user` one, `prompt_hash` is the hash of the last user turn and `prompt_preview` is its first 500 characters of 620.
- **The keys.** Two conversations that differ only in the assistant turn are both answered, with different `dedup_key` values and the same `prompt_hash`.
- **`usage` parsing.** `tokens_used` is `usage.total_tokens` with the split, without it, and when the split disagrees with it. A missing `total_tokens` raises `OpenRouterError`.
- **Five guards** restate the coverage against the case tables, so an edit that drops an arm or a field fails.

No model is loaded: `query_pipeline.redact` is stubbed in every pipeline case. The module runs in about 3 seconds.

No file under `app/` or `chat_ui/` changed: `git diff --name-only 5224280 HEAD -- app/ chat_ui/` is empty.

**Every value in the plan's F-3 table was confirmed.** The plan derived the expected rows by reading the code, because nothing could be run when it was written. All 27 cases passed on the first run against the database, with no value adjusted.

## Tasks Completed

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 0 | Preflight: Python 3.11 environment, Docker Desktop and `harness-libsql-dev`, epic branch, two docs commits (`3c79d43`, `5224280`), BASE recorded, baseline taken | — | ✅ (two deviations, below) |
| 1 | Module skeleton, settings fixture, row projection, 2 guards | `tests/test_audit_characterization.py` | ✅ |
| 2 | 12 arm cases, 3 guards | `tests/test_audit_characterization.py` | ✅ |
| 3 | Multi-turn prompt and key pins, 4 tests | `tests/test_audit_characterization.py` | ✅ |
| 4 | `usage` parsing, 6 cases | `tests/test_audit_characterization.py` | ✅ |
| 5 | Ten bite checks, neighbours, order checks, full suite, AC 5 diff | — | ✅ (one deviation, below) |
| 6 | This report | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A. No frontend in the change; the UI is Reflex/Python |
| `/health` smoke (uvicorn on :8765, local dev database, `RBAC_ENABLED=false`) | ✅ `{"status":"ok"}` [200]; server stopped afterwards |
| `pytest tests/test_audit_characterization.py` | ✅ 27 passed |
| Neighbours (`test_query_pipeline_pii_profiles`, `test_query_pipeline_patterns`, `test_pii_characterization`, `test_openrouter_client`) | ✅ 154 passed |
| Order: characterization → pii_profiles | ✅ 102 passed |
| Order: pii_profiles → characterization | ✅ 102 passed, twice. The first of three runs had 1 error and took 28 s against the usual 13 s; it was not captured and did not recur (see note) |
| Baseline full suite, without this module | 3328 passed, 27 skipped, 1 failed, 1 error |
| Full suite, with this module | 3355 passed, 27 skipped, 1 failed, 1 error |
| AC 5: `git diff --name-only 5224280 HEAD -- app/ chat_ui/` | ✅ empty |

**About the full-suite failures.** Each run had one failure and one error, in different tests each time, and none in this module:

- Baseline: `test_chat_state.py::test_logout_clears_every_session_var_and_every_row_survives` (failed) and `test_db.py::test_init_db_creates_users_table` (error, `STREAM_EXPIRED`).
- Final: `test_migrate_to_turso_cli.py::test_token_hashes_transfer_intact_and_the_unique_index_still_holds` (failed) and `test_query_pipeline_run_conversation.py::test_pii_in_the_last_turn_is_reflected_in_the_audit` (error).

All four pass in isolation. This is the local libSQL flakiness PRD Section 11 names ("restart the libSQL dev container, not bisect code"), and the PRD-012 STORY-002 report records the same pattern. The counts reconcile: 3330 tests at baseline, 3357 with the module's 27. The suite was therefore never fully green in one run on this machine, and that is reported here as it happened.

## Environment

- Python 3.11.x from `uv`, in a virtual environment at `C:\Users\tobip\.venvs\harness-ai`, with `requirements.txt` and `en_core_web_lg` 3.8.0 installed. spaCy 3.8.16.
- libSQL dev server: container `harness-libsql-dev`, created with the command in `tests/conftest.py`. Docker 29.8.1.

## Bite checks (Task 5)

Each was a temporary edit applied by a script that restored the file in a `finally` block. `git status` afterwards showed only the new module.

| # | Temporary change | Result |
|---|---|---|
| 1 | `run_conversation`: `prompt = messages[0].content` | 15 failed: all 12 arms, both multi-turn shapes, and the AC 3 test |
| 2 | `log_query`: `_PREVIEW_LENGTH = 400` | 2 failed: both multi-turn shapes. The arm prompts are under 400 characters, so the arm rows do not move |
| 3 | `_deny`: drop `role=identity.role` | 3 failed: the three authorization arms |
| 4 | Context-limit arm: `success=True` | 1 failed: `context-limit` |
| 5 | Upstream-error arm: drop `model_used=model` | 1 failed: `upstream-error` |
| 6 | Output-redaction-error arm: drop `tokens_used=` | 1 failed: `output-redaction-error` |
| 7 | Flag arm: drop `pattern_action=` | 1 failed: `pattern-flag` |
| 8 | `dedup_key`: drop `prefix_hash` from the hashed list | 1 failed: the AC 3 test |
| 9 | `_row_to_audit_log`: `session_id=None` | 12 failed: every arm. The read goes through the mapper |
| 10 | `call_openrouter`: `tokens_used = prompt_tokens + completion_tokens` | 3 failed: `total-only`, `split-disagrees-with-total`, and `split-without-total` (which then returns a result and no longer raises) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_audit_characterization.py` | CREATE | +645 |
| `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-001-audit-characterization.plan.md` | MOVE (archived) | 0 |
| `.agents/reports/PRD-013-audit-and-usage-limits/STORY-001-audit-characterization.report.md` | CREATE | this file |

## Deviations from Plan

1. **The virtual environment is outside the repository.** The plan said `.venv` in the repo. The repo is inside OneDrive, and a spaCy environment there would sync several hundred megabytes and risk file locks. It is at `C:\Users\tobip\.venvs\harness-ai`. Nothing in the repo refers to it.
2. **The first docs commit was made in the pre-plan state.** `/plan` had already edited the STORY-001 story and the index. They were set back for `3c79d43` and restored for `5224280`, so the plan commit shows the status change as its own diff.
3. **Bite check 5 failed one test, not two.** The plan expected `test_the_upstream_error_row_names_the_requested_model` to fail as well. That guard reads the case table, not production, so it cannot. The arm case catches the change, which is what matters.
4. **Bite check 9 needed a narrower anchor.** `session_id=row["session_id"]` appears three times in `app/db/database.py`. The edit was anchored on the following `dedup_key` line so it changed only `_row_to_audit_log`.
5. **Two helpers the plan did not name.** `_redact_stub` builds the `redact` replacements for three arms, and `_row` asserts that every override names a real audit field.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_audit_characterization.py` | `test_every_audit_field_is_pinned_volatile_or_added_since`; `test_the_fixed_conversation_is_111_characters`; `test_each_arm_writes_exactly_this_row` × 12 (`permission-denied`, `model-not-permitted`, `byok-denied`, `context-limit`, `duplicate`, `pattern-block`, `pattern-flag`, `redaction-limit`, `input-redaction-error`, `upstream-error`, `output-redaction-error`, `success`); `test_the_arm_cases_cover_the_twelve_arms`; `test_only_a_permission_refusal_records_a_role`; `test_the_upstream_error_row_names_the_requested_model`; `test_success_row_describes_the_last_user_turn` × 2 (`chat-shaped`, `v1-shaped`); `test_the_three_message_shape_has_three_messages`; `test_an_earlier_turn_changes_the_dedup_key_and_not_the_prompt_hash`; `test_tokens_used_is_total_tokens` × 3 (`with-split`, `total-only`, `split-disagrees-with-total`); `test_missing_total_tokens_raises_openrouter_error` × 3 (`empty-usage`, `split-without-total`, `no-usage-key`) |

## For later stories

- **STORY-002**: add the eight column names to `FIELDS_ADDED_SINCE` and add assertions for them. `test_every_audit_field_is_pinned_volatile_or_added_since` fails until the names are there, which is the prompt to do it. No expected row in `ARM_CASES` is edited.
- **STORY-003**:
  - `"usage": null` escapes `call_openrouter` as an uncaught `TypeError` today, because the `except` clause covers `KeyError`, `IndexError` and `ValueError` only. It is not pinned, so this story is free to wrap it.
  - `split-disagrees-with-total` pins that `tokens_used` stays the reported total and is never recomputed from the split.
  - The module asserts the three attribute values of `OpenRouterResult`, never its field list, so adding two fields does not touch it.
- **STORY-005**: import `ARM_CASES` and `_drive` for the new-field assertions on every arm. Do not copy them. `_drive` passes no `ingress`, so its rows will record `NULL` there, which is the PRD's stated result for a direct call.
- **STORY-018**: diff this module against `126f0da`. Lines may be added. No assertion may change (PRD Section 11, *Quality indicators*).

## Observations (recorded, not fixed)

- **`role` is `NULL` on every row that is not a permission refusal.** Only `_deny` passes it. A success row by a `user` does not say which role sent it. PRD-013's usage view joins to `users` for the role, so it is unaffected, but a reader of `/audit` cannot filter successes by role.
- **The upstream-error row records the requested model; the success and output-redaction-error rows record the reported one.** One column holds two meanings.
- **The output-redaction-error row keeps the unmasked response's hash and preview,** with `tokens_used` set and `success` false. PRD-013's charge at step 7b relies on the tokens being on this row.
- **The flag arm writes two rows with one `dedup_key`.** The flag row has no response and no model.
- **`"usage": null` raises an uncaught `TypeError`** (see *For later stories*, STORY-003).

## Acceptance Criteria

- [x] Given untouched code on `main`, when `tests/test_audit_characterization.py` runs, then it is green and asserts the full `AuditLog` row written by each arm of `run_conversation`: the three authorization arms, context limit, duplicate, pattern block, pattern flag, redaction limit, input-redaction error, upstream error, output-redaction error and success.
- [x] Given a three-message conversation, when the success arm writes its row, then the test asserts `prompt_hash == hash_prompt(messages[-1].content)` and `prompt_preview` is the first 500 characters of the last user turn, not of the system turn.
- [x] Given two conversations that differ only in an earlier turn, when both are run, then the test asserts their rows carry different `dedup_key` values and the same `prompt_hash`.
- [x] Given a stub HTTP client returning `usage` with `total_tokens`, `prompt_tokens` and `completion_tokens`, and one returning only `total_tokens`, when `call_openrouter` runs, then the test pins that `tokens_used` equals `total_tokens` in both cases and that a missing `total_tokens` raises `OpenRouterError`.
- [x] Given the story's diff, when it is reviewed, then it contains test files only and no file under `app/` or `chat_ui/` changed.
- [x] All tasks completed
- [ ] Full suite green in a single run. Not achieved: each run had one failure and one error from libSQL flakiness, in different unrelated tests, all passing in isolation
- [x] Follows existing patterns
