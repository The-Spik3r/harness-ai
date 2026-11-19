---
story: STORY-013
prd: PRD-021
plan: .agents/plans/PRD-021-realtime-streaming/completed/STORY-013-audit-api-and-register.plan.md
epic_branch: epic/PRD-021-realtime-streaming
commit: 5313d70
status: COMPLETE
completed: 2026-11-19
---

# Implementation Report - STORY-013: GET /audit real-time fields, completion_id filter and Register LIVE marker

## Summary
Four additive fields on `AuditQueryEntry` / `get_audit`; optional exact-match `?completion_id=` (min 1, max 128, empty = 422) applied after scoping; `LIVE` tag in the Register via `AuditRow.live`. No index on `completion_id` (orchestrator decision). LIVE ink: `theme.INK` (see Deviations).

## Validation
- Import OK. Targeted: test_audit_router, test_schemas, test_register, test_admin_formatting, test_admin_models, test_chat_ui_startup_guard, test_untouched_app: 352 passed, 1 failed (palette test, fixed, test_register rerun 208 passed). test_db -k audit_logs list/count: 8 passed. test_admin_state -k audit: 4 passed. test_db_resilience_retry: 168 passed.
- Full suite: GitHub CI on push (user decision).
- Not verified in a real browser (narrow verdict track, 360 px).

## Files
app/db/database.py (private `_audit_filter`, readers take `completion_id`), app/models/schemas.py, app/routers/admin.py, chat_ui admin_models/admin_formatting/admin_copy/components/register.py, tests (audit_router, schemas, register, admin_formatting, admin_models).

## Deviations
- LIVE ink: plan suggested INK_UPSTREAM; it is the chat's upstream-failure ink and INK_SELF is not in the Register's palette allow-list (`test_no_colour_outside_the_allowed_set`). Used `theme.INK` (plain text ink, already allowed, no verdict uses it).
- `_tag` gained an optional `title` argument (verdict tags unchanged).

## Acceptance Criteria
- [x] AC1 four fields: test_audit_router round-trip + key-set guard; test_schemas
- [x] AC2 exact completion_id + scoping: exact/prefix/own-scope/injection/422 tests
- [x] AC3 LIVE only on streamed_realtime rows: test_register probe test; test_admin_formatting
- [x] AC4 existing tests pass, modified assertions cite PRD-021 F7
