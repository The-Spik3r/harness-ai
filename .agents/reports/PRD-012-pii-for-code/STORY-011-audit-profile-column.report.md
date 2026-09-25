---
story: STORY-011
prd: PRD-012
plan: .agents/plans/PRD-012-pii-for-code/completed/STORY-011-audit-profile-column.plan.md
epic_branch: epic/PRD-012-pii-for-code
commit: faaa4be
status: COMPLETE
completed: 2026-09-25
---

# Implementation Report — STORY-011: audit_logs.profile on every arm; /audit and the Register show it

**Plan**: `.agents/plans/PRD-012-pii-for-code/completed/STORY-011-audit-profile-column.plan.md`
**Epic Branch**: `epic/PRD-012-pii-for-code`
**Commit**: `faaa4be`

## Summary

Every audit row now says which profile ran. Under `code`, `pii_detected_output = 0` means the output was not analyzed, and the profile column makes that readable instead of looking like "clean" (PRD-012 D9).

**Schema.** `audit_logs.profile TEXT` is declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`. It is nullable, has no default and is never backfilled.
- `AuditLog.profile` sits before `id`, so `id` stays the trailing field.
- The writer, `_row_to_audit_log` and the summary snapshot's `json_object(...)` all carry it.

**Pipeline.** `run_conversation` resolves `profile_name` once, directly after step 0, so the three forbidden arms record it too. Before this story it was resolved at step 5.
- `_deny` has a new required `profile: str`, so forgetting it is a `TypeError`.
- All ten `log_query(...)` call sites in the pipeline pass `profile=`, and a source-scan test enforces it.
- `log_query` keeps `profile: Optional[str] = None` for one caller: `/query`'s foreign-session refusal, which writes before any profile is resolved. That call passes `profile=None` explicitly, and the reason is documented in `audit_logger.py`, the router, `AuditQueryEntry` and a test.

**Read side.**
- `GET /audit` returns `AuditQueryEntry.profile`, which is nullable.
- The admin Register shows **Profile** in the row disclosure, directly above the PII types / PII in prompt / PII in response lines it qualifies. The row itself keeps its ten cells.
- `/stats` and the admin summary figures are unchanged. No query gained a profile predicate.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Column in both DDL places; `AuditLog.profile` | `app/db/models.py` | ✅ |
| 2 | Writer (+1 placeholder), mapper, `_SUMMARY_SQL` `json_object`, `init_db` docstring | `app/db/database.py` | ✅ |
| 3 | `log_query(..., profile=None)` with the router exception documented | `app/services/audit_logger.py` | ✅ |
| 4 | Resolve once at the top; required `profile` on `_deny`; `profile=` on all ten call sites; step-5 and step-8 comments | `app/services/query_pipeline.py` | ✅ |
| 5 | Foreign-session arm passes `profile=None` explicitly (comment item 6) | `app/routers/query.py` | ✅ |
| 6 | `AuditQueryEntry.profile`; `/audit` passthrough | `app/models/schemas.py`, `app/routers/admin.py` | ✅ |
| 7 | Register: `AuditRow.profile`, `to_audit_row`, `DETAIL_PROFILE_LABEL`, disclosure field | `chat_ui/chat_ui/admin_models.py`, `admin_formatting.py`, `admin_copy.py`, `components/register.py` | ✅ |
| 8 | Profile on every arm: pipeline, `/query`, chat UI | `tests/test_query_pipeline_pii_profiles.py`, `tests/test_query_router.py`, `tests/test_query_session_id.py`, `tests/test_chat_state.py` | ✅ |
| 9 | Pinned lists, convergence, read side, stats invariance, Register | `tests/test_db.py`, `test_migrate_to_turso_cli.py`, `test_audit_logger.py`, `test_audit_router.py`, `test_schemas.py`, `test_stats_router.py`, `test_admin_models.py`, `test_admin_formatting.py`, `test_register.py` | ✅ |
| 10 | Full regression | `tests/` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Baseline (touched suites, before any change) | ⚠️ partial: 236 passed and 0 failed before the 900 s timeout I set on that run cut it off |
| Backend import (`from app.main import app`) | ✅ |
| Chat UI compile (`reflex compile --dry`) | ✅ compiled successfully |
| Frontend lint | n/a: there is no npm frontend. The chat UI is Reflex (Python) and is covered by the import and compile checks |
| Touched suites | ✅ 868 passed (first run: 1 failed, see Deviation 3) |
| Full suite `pytest tests/` | ✅ 3152 passed, 26 skipped (first run: 2 failed, see Deviation 2) |
| E2E | ✅ 8/8 |

## E2E Results

Every run used the local libSQL dev server (`DATABASE_URL=http://127.0.0.1:8080`, overriding `.env`'s Turso URL), a dummy OpenRouter key and a throwaway admin token, so no real credentials were used.

| # | Check | Result |
|---|-------|--------|
| 1 | Built a database with the pre-story 23-column `audit_logs` table and 3 legacy rows (2 with PII). Booted the API, then ran a second `init_db()` with a spy on `execute`. | ✅ The column was added once (24 columns). The second `init_db()` issued **no `ALTER`**. All 3 legacy rows read `profile: null` on `GET /audit`. |
| 2 | `POST /query` with a user token | ✅ 502, because the dummy key makes the upstream call fail. Row 7 has `profile='chat'` in the DB and on `/audit`. |
| 3 | `POST /query` with a `session_id` owned by another user | ✅ 403. Row 8 has `profile=null` in the DB and on `/audit`. |
| 4 | `POST /query`, user token, BYOK key (the pipeline's forbidden arm) | ✅ 200 `BLOCKED`, `required_permission: query:byok`. Row 9 has `denied_permission='query:byok'` and `profile='chat'`. |
| 5 | Chat UI (`reflex run --env prod --single-port`): signed in as `e2e-user`, sent one message | ✅ Upstream-error bubble (dummy key). Row 11 has `profile='chat'`. |
| 6 | In-process `run_conversation(profile="code")`; the upstream stub returns `alice@example.com` | ✅ Response returned unmasked. Row 10 has `profile='code'` and `pii_detected_output=false`, in the DB and on `/audit`. |
| 7 | Admin console Register: expanded rows #10 and #2 | ✅ #10 shows **PROFILE: code** directly above PII TYPES / PII IN PROMPT / PII IN RESPONSE. Legacy #2 shows the absent mark `—`. |
| 8 | PII figures before and after the migration, on the same data | ✅ Pre-story SQL gave 2. After migration, `/stats` and the admin Summary both show `pii_detected_queries = 2` and `top_pii_entities = [EMAIL_ADDRESS, PERSON]`. |

Observed along the way, and unchanged by this story: a caller without `query:submit` is refused by the router's `require_permission` dependency (403) before the pipeline runs, so that refusal writes no audit row. The pipeline's forbidden arms are reached over HTTP through BYOK and model checks, and E2E check 4 exercises the BYOK one.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +9/-3 |
| `app/db/models.py` | UPDATE | +17/-2 |
| `app/models/schemas.py` | UPDATE | +6/-0 |
| `app/routers/admin.py` | UPDATE | +2/-0 |
| `app/routers/query.py` | UPDATE | +5/-0 |
| `app/services/audit_logger.py` | UPDATE | +10/-0 |
| `app/services/query_pipeline.py` | UPDATE | +32/-8 |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | +4/-0 |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | +1/-0 |
| `chat_ui/chat_ui/admin_models.py` | UPDATE | +3/-0 |
| `chat_ui/chat_ui/components/register.py` | UPDATE | +6/-3 |
| `tests/test_admin_formatting.py` | UPDATE | +7/-0 |
| `tests/test_admin_models.py` | UPDATE | +2/-0 |
| `tests/test_audit_logger.py` | UPDATE | +20/-0 |
| `tests/test_audit_router.py` | UPDATE | +27/-0 |
| `tests/test_chat_state.py` | UPDATE | +32/-0 |
| `tests/test_copy.py` | UPDATE | +6/-0 |
| `tests/test_db.py` | UPDATE | +193/-3 |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | +3/-2 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +2/-0 |
| `tests/test_query_pipeline_pii_profiles.py` | UPDATE | +222/-1 |
| `tests/test_query_router.py` | UPDATE | +36/-0 |
| `tests/test_query_session_id.py` | UPDATE | +26/-0 |
| `tests/test_register.py` | UPDATE | +20/-0 |
| `tests/test_schemas.py` | UPDATE | +2/-0 |
| `tests/test_stats_router.py` | UPDATE | +34/-0 |

## Deviations from Plan

1. **The foreign-session test is in `tests/test_query_session_id.py`, not `tests/test_query_router.py`.** That module already has the two-real-users fixture and `_session_owned_by`, so the test reuses them instead of rebuilding them in the router suite. `test_query_router.py` still gets the two `profile='chat'` tests: success, and BYOK-forbidden. The success test also sends a `"profile": "code"` body field and asserts the row says `chat`, which shows that no request field can pick the profile (PRD T1).
2. **Two more pinned lists than the plan named.**
   - `tests/test_copy.py` keeps an admin-copy constant inventory: an import, a non-empty assert and the name set.
   - `tests/test_pii_redaction_integration.py::test_audit_endpoint_contract_has_no_preview_fields` pins the sorted `/audit` key list.
   - Both gained `profile` / `DETAIL_PROFILE_LABEL` with a PRD-012 D9 comment. No other assertion in either file changed. The full suite caught both on its first run.
3. **Register comment reworded.** `test_register.py::test_no_copy_value_is_written_as_a_literal` rejects any copy string that appears literally in `register.py`, and the first version of the new comment quoted "PII in response". The comment now reads "no output PII means the response was not analyzed".
4. **Duplicate arm counts two rows.** In `test_every_arm_records_the_resolved_profile`, the duplicate case counts both the seed send and the blocked send. Both rows are asserted to carry the profile, which is stronger than the one row the plan sketched.
5. **E2E item 4 as planned was not reachable over HTTP.** The plan's "role without `query:submit` → forbidden body, `profile='chat'`" is refused by the router dependency before the pipeline runs (see above), with no row. BYOK exercises the same pipeline arm (`_deny`), and the test suite drives all three forbidden arms in-process.
6. **E2E side effect reverted.** `reflex run` rewrote `chat_ui/reflex.lock/{package.json,bun.lock}`, the same as in STORY-010. This is unrelated to the story, so both files were restored with `git restore` and are not in the commit.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_pii_profiles.py` | `test_every_arm_records_the_resolved_profile` (×30: 10 arms × default/chat/code), `test_the_code_only_arms_record_code` (×2: pattern flag, redaction limit), `test_code_success_row_says_output_was_not_analyzed`, `test_the_default_profile_setting_is_what_the_row_records`, `test_profile_is_resolved_before_authorization`, `test_deny_requires_profile_with_no_default`, `test_every_log_query_call_site_in_the_pipeline_passes_profile` |
| `tests/test_db.py` | `test_audit_logs_added_columns_carries_nullable_profile`, `test_init_db_adds_a_nullable_profile_column`, `test_init_db_migrates_a_pre_profile_database`, `test_profile_defaults_to_none_when_not_supplied`, `test_profile_round_trips`, `test_profile_survives_the_batched_read`, `test_audit_log_carries_profile_without_breaking_construction` (plus the `_create_pre_profile_database` fixture) |
| `tests/test_query_router.py` | `test_query_success_row_records_profile_chat`, `test_query_denied_row_records_profile_chat` |
| `tests/test_query_session_id.py` | `test_the_403_row_records_no_profile_and_the_owned_send_records_chat` |
| `tests/test_chat_state.py` | `test_chat_state_send_records_profile_chat_on_both_pipeline_paths` |
| `tests/test_audit_logger.py` | `test_profile_persisted_when_supplied`, `test_profile_defaults_to_none_when_omitted` |
| `tests/test_audit_router.py` | `test_audit_entry_carries_profile` |
| `tests/test_stats_router.py` | `test_pii_figures_are_unchanged_by_the_profile_column` |
| `tests/test_admin_formatting.py` | `test_to_audit_row_carries_the_profile` |
| `tests/test_register.py` | `test_the_profile_precedes_the_pii_lines` (plus the new label and field in the parametrized disclosure tests) |

## Acceptance Criteria

- [x] `profile TEXT` is declared in both `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`, and `AuditLog.profile: Optional[str] = None`. `init_db()` adds the column to a pre-story database and backfills nothing.
- [x] Every `run_conversation` arm passes `profile` explicitly and it holds the resolved name: forbidden ×3, context limit, duplicate, pattern block, pattern flag, redaction limit, redaction error ×2, upstream error, success. `_deny` requires it, and a source scan covers the direct call sites.
- [x] `/query` and the chat UI write `profile='chat'`. The one exception is `/query`'s foreign-session refusal, which writes before any profile exists; it is documented and tested as NULL.
- [x] `GET /audit` returns `AuditQueryEntry.profile`, which is nullable, and the admin Register shows it in the row disclosure.
- [x] `/stats` and the admin snapshot `pii_detected_queries` / `top_pii_entities` are unchanged for a database of `chat` rows.
- [x] All tasks completed
- [x] `pytest tests/` passes. The only existing assertions changed are pinned field, column and key lists.
- [x] Backend server starts without error (after the RBAC bootstrap user exists, as always)
- [x] Follows existing patterns
