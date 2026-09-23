---
story: STORY-010
prd: PRD-011
plan: .agents/plans/PRD-011-pattern-policy/completed/STORY-010-narrowed-counters-and-admin-fields.plan.md
epic_branch: epic/PRD-011-pattern-policy
commit: f1e5f2e
status: COMPLETE
completed: 2026-09-23
---

# Implementation Report — STORY-010: blocked_suspicious counts blocks only; role and action surfaced in /audit and the console

**Plan**: `.agents/plans/PRD-011-pattern-policy/completed/STORY-010-narrowed-counters-and-admin-fields.plan.md`
**Epic Branch**: `epic/PRD-011-pattern-policy`
**Commit**: `f1e5f2e`

## Summary

**Counters.** `count_blocked_suspicious()` and the `blocked_suspicious` subquery in `_SUMMARY_SQL` both interpolate one module constant, `_BLOCKED_SUSPICIOUS_WHERE`:

```sql
suspicious_pattern IS NOT NULL AND (pattern_action IS NULL OR pattern_action = 'block')
```

- A flag row is excluded.
- A row with a NULL action is from before PRD-011 and was a block, so it still counts. No historical figure moves, and no row is backfilled (D6, Risk 4).
- `grep "suspicious_pattern IS NOT NULL" app/ chat_ui/ scripts/` now finds only the constant.

**`GET /audit`.** `AuditQueryEntry` gains `pattern_role` and `pattern_action`, both `Optional[str] = None` with no validator, and `get_audit` passes them through verbatim. `suspicious_pattern_detected` is unchanged: it still means "a pattern was matched", so it is true for a flag too.

**Snapshot JSON.** Both keys were already in `_SUMMARY_SQL`'s `json_object` (STORY-009). A test now decodes the raw `rows` JSON and proves they are there.

**Console Register.**
- `AuditRow` gains `pattern_role` and `pattern_action`. `to_audit_row` fills them through `_text`, so NULL becomes `—`.
- The row detail shows **Matched in** and **Pattern action** directly under **Matched pattern**.
- `derive_verdict`'s denied arm is narrowed by the same D6 rule (plan D-C). A flag row is no longer "denied": it falls through to **cleared**, since flag rows are written with `success=1`. Block rows and legacy rows stay **denied**.
- A legacy row shows `—`/`—` rather than an inferred "block". Its verdict already says it was blocked.
- No new verdict, view or layout change.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `_BLOCKED_SUSPICIOUS_WHERE`, used by both counters; `_SUMMARY_SQL` becomes an f-string (no literal braces in it) | `app/db/database.py` | ✅ |
| 2 | Block/flag/legacy fixture; counter, snapshot counter, raw snapshot JSON and shared-predicate tests | `tests/test_db.py` | ✅ |
| 3 | `/stats` block/flag/legacy test | `tests/test_stats_router.py` | ✅ |
| 4 | `AuditQueryEntry` fields; router passthrough | `app/models/schemas.py`, `app/routers/admin.py` | ✅ |
| 5 | `/audit` key pin extended; passthrough test; two more shape pins (see Deviations) | `tests/test_audit_router.py`, `tests/test_pii_redaction_integration.py`, `tests/test_schemas.py` | ✅ |
| 6 | `AuditRow` fields, two copy labels, `derive_verdict` narrowed, `to_audit_row` fills both | `chat_ui/chat_ui/admin_models.py`, `admin_copy.py`, `admin_formatting.py` | ✅ |
| 7 | Two `_detail_field` lines; `_detail` and `_row_line` docstrings | `chat_ui/chat_ui/components/register.py` | ✅ |
| 8 | Console tests and additive pin updates | `tests/test_admin_formatting.py`, `test_admin_models.py`, `test_copy.py`, `test_register.py`, `test_admin_state.py` | ✅ |
| 9 | Repository sweep | — | ✅ |
| 10 | Full suite | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Console modules import (`chat_ui.chat_ui.admin_*`) | ✅ |
| Frontend lint | n/a: there is no `frontend/`. The Reflex console is covered by the Python suites, and `reflex run` compiled 30/29 with no error |
| Tests | ✅ 2541 passed, 26 skipped, 0 failed (`pytest tests/`, 277 s, after a container restart; see the flake note below) |
| Story suites | ✅ `test_db.py` 189; `test_stats_router.py` 10; `/audit` group 70; console group 451 |
| Mutation checks | ✅ Three, each restored afterwards (see below) |
| No-change suites | ✅ `git diff` is empty for `test_integration.py`, `test_query_router.py`, `test_query_outcomes_regression.py`, `test_chat_outcomes_regression.py` and `test_history_off_integration.py` |
| E2E | ✅ 6/6 |

**Mutation checks.**

1. Predicate reverted to `suspicious_pattern IS NOT NULL`: 3 new counter tests fail.
2. Predicate made strict, `pattern_action = 'block'`: 4 fail, including the pre-existing `test_count_blocked_suspicious_counts_only_flagged_rows`. That is the "legacy row still counts" claim, proven.
3. `derive_verdict` narrowing removed: `test_a_flag_row_is_not_denied` and `test_a_flag_row_renders_cleared_with_its_role_and_action` fail.

**Full-suite flake, recorded rather than hidden.** The first full run had 2540 passed and 1 setup ERROR, in `tests/test_two_instance_smoke.py::test_a_user_created_by_the_cli_resolves_on_both_running_instances`. That file passed 14/14 in isolation. After restarting `harness-libsql-dev`, as the libSQL memory note advises, the full run was clean: 2541 passed. The test does not touch this story's code.

### Sweep (Task 9)

- `suspicious_pattern IS NOT NULL` appears only in `app/db/database.py:938` (the constant).
- `suspicious_pattern is not None` appears in two places:
  - `app/routers/admin.py:52`: `suspicious_pattern_detected`, deliberately not narrowed.
  - `chat_ui/chat_ui/admin_formatting.py:93`: narrowed with `and log.pattern_action != "flag"`.
- `class _Log` appears only in `tests/test_register.py`, which was updated.
- The comment at `app/db/models.py:68-70` ("The counters read it that way as of STORY-010") is now true, and was left as is.

### E2E detail

Everything ran against the local libSQL dev server (`DATABASE_URL=http://127.0.0.1:8080`), never the `.env` database, with `ADMIN_TOKEN` and `TURSO_AUTH_TOKEN` overridden in the environment only. The dev DB's `audit_logs` was cleared and seeded with four rows: block (`user`/`block`), flag (`tool`/`flag`), legacy (a pattern, both fields NULL) and clean. A throwaway user, `e2e-story010@example.com`, was created with `scripts.manage_users create-user`.

| # | Check | Result |
|---|-------|--------|
| 1 | `summary_snapshot()` | `blocked_suspicious == 2`, `errors == {}`. Rows carry `(user, block)`, `(tool, flag)`, `(None, None)` ×2. |
| 2 | `GET /stats` (uvicorn :8765) | `blocked_suspicious: 2`, `total_queries: 4` |
| 3 | `GET /audit` | Each entry has 16 keys, including `pattern_role` and `pattern_action`. Values: block `user/block/True`, flag `tool/flag/True`, legacy `None/None/True`, clean `None/None/False`. |
| 4 | `POST /query` `please ignore previous instructions` (user token) | `{"status":"BLOCKED","reason":"Suspicious pattern detected","pattern":"ignore previous instructions"}`, byte-identical. `/stats` `blocked_suspicious` becomes 3. The newest `/audit` entry is `user/block/True`. |
| 5 | Admin console `/admin/audit` (`reflex run`, chrome-devtools) | Verdicts: #5 and #4 (blocks) **DENIED**, #3 (flag) **cleared**, #1 (clean) **cleared**, #2 (legacy) **DENIED**. The flag's detail reads "Matched in tool · Pattern action flag", the block's "user · block", and the legacy row's "— · —". No console errors or warnings. The layout is unchanged apart from the two new detail lines. |
| 6 | Admin console `/admin/stats` | "Denied on a pattern: 3, 60.0% of all queries" (5 rows). This agrees with `/stats`. |

**Environment notes.**

- Docker Desktop was stopped at the start and was launched so the dev container could run.
- `reflex run` bumped `chat_ui/reflex.lock/bun.lock` and `package.json`; both were reverted and are not in the commit.
- The Reflex processes and the E2E uvicorn were stopped afterwards.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +16/-3 |
| `app/models/schemas.py` | UPDATE | +12/-0 |
| `app/routers/admin.py` | UPDATE | +5/-0 |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | +7/-0 |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | +11/-2 |
| `chat_ui/chat_ui/admin_models.py` | UPDATE | +5/-0 |
| `chat_ui/chat_ui/components/register.py` | UPDATE | +10/-4 |
| `tests/test_db.py` | UPDATE | +99/-0 |
| `tests/test_stats_router.py` | UPDATE | +44/-0 |
| `tests/test_audit_router.py` | UPDATE | +42/-0 |
| `tests/test_admin_formatting.py` | UPDATE | +63/-0 |
| `tests/test_admin_state.py` | UPDATE | +42/-0 |
| `tests/test_register.py` | UPDATE | +24/-0 |
| `tests/test_copy.py` | UPDATE | +9/-0 |
| `tests/test_admin_models.py` | UPDATE | +3/-0 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +3/-0 |
| `tests/test_schemas.py` | UPDATE | +3/-0 |
| `.agents/plans/.../completed/STORY-010-...plan.md` | CREATE (archived plan) | +394 |

## Deviations from Plan

1. **Two `/audit` shape pins the plan did not list.** Both are exact-shape assertions over `AuditQueryEntry`:
   - `tests/test_pii_redaction_integration.py:195` (`sorted(entry) == [...]`);
   - `tests/test_schemas.py:139` (`model_dump() == {...}`).

   Each gained the two keys, with a `PRD-011 D6` comment. No existing value changed. The plan's Task 5 grep for `suspicious_pattern_detected` is what found them.
2. **Raw snapshot JSON test.** It executes `database._SUMMARY_SQL` directly with `(100, 5, 5, 5)` (row limit, then three ranked limits) and decodes `rows` before `_row_to_audit_log` sees it. This proves the keys are in the per-row object, not merely defaulted by the mapper.
3. **`_SUMMARY_SQL` became an f-string**, as the plan allowed once the SQL was checked for literal braces (there are none).

Nothing else deviated. D-C (the `derive_verdict` narrowing) was implemented as planned. It is still the one change the story text does not name, and it is worth a look in review.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `_seed_block_flag_and_legacy` (helper), `test_count_blocked_suspicious_excludes_flags_and_keeps_legacy_rows`, `test_summary_snapshot_blocked_suspicious_excludes_flags_and_keeps_legacy_rows`, `test_summary_snapshot_rows_carry_pattern_role_and_action`, `test_blocked_suspicious_predicate_is_shared` |
| `tests/test_stats_router.py` | `test_stats_blocked_suspicious_counts_blocks_and_legacy_rows_not_flags` |
| `tests/test_audit_router.py` | `test_audit_entry_carries_pattern_role_and_action`; key-set pin extended |
| `tests/test_admin_formatting.py` | `test_a_flag_row_is_not_denied`, `test_a_block_row_is_denied`, `test_a_legacy_pattern_row_is_still_denied`, `test_a_duplicate_still_outranks_a_flag`, `test_to_audit_row_carries_pattern_role_and_action`; `test_null_columns_render_the_absent_mark` extended |
| `tests/test_admin_state.py` | `test_a_flag_row_renders_cleared_with_its_role_and_action` |
| `tests/test_register.py` | `test_the_role_and_action_follow_the_pattern`; parametrized label and field tuples extended (+4 cases); `_Log` stand-in extended |
| `tests/test_admin_models.py`, `tests/test_copy.py`, `tests/test_pii_redaction_integration.py`, `tests/test_schemas.py` | Additive pin extensions only |

## Notes for Later Stories

- **STORY-013 (README):** Risk 4 asks for the narrowed `blocked_suspicious` to be called out. The facts to state:
  - NULL-action rows still count;
  - only flags are excluded;
  - a deployment with no `tool` traffic sees no change;
  - on the console, a flag row reads **cleared**, with its role and action in the row detail.
- **PRD-016:** once `tool` turns reach `/query`, flag rows become producible over HTTP. The console and counters already treat them correctly, so no follow-up is needed here.

## Acceptance Criteria

- [x] `count_blocked_suspicious()` and the admin snapshot query both use `suspicious_pattern IS NOT NULL AND (pattern_action IS NULL OR pattern_action = 'block')`, as one shared constant (`test_blocked_suspicious_predicate_is_shared`).
- [x] With one block row, one flag row and one legacy row, `/stats` and the admin snapshot both report `blocked_suspicious == 2`. The flag is excluded and the legacy row counts (`test_db.py`, `test_stats_router.py`, E2E 1–2).
- [x] `GET /audit` entries carry nullable `pattern_role` and `pattern_action`. `suspicious_pattern_detected` still means "a pattern was matched" and is true for a flag (`test_audit_entry_carries_pattern_role_and_action`, E2E 3).
- [x] The Register shows the triggering role and block/flag for a pattern row. A pre-PRD row renders `—`/`—` with its **denied** verdict, with no error and no misleading label; a flag row is not labelled denied (E2E 5, console tests).
- [x] Both new fields appear in the snapshot's per-row JSON object (`test_summary_snapshot_rows_carry_pattern_role_and_action`). Existing reports and admin tests pass with only additive changes.
- [x] All tasks completed
- [x] Full `pytest tests/` green
- [x] Backend starts without error
- [x] Every modified pre-existing test carries a PRD-011 D6 comment. No assertion changed in `test_query_router.py`, `test_integration.py` or `test_query_outcomes_regression.py`.
- [x] Follows existing patterns (one D6 predicate text; verbatim passthrough; absence stated at the boundary)
