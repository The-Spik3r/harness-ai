---
story: STORY-016
prd: PRD-016
plan: .agents/plans/PRD-016-action-policy-rules/completed/STORY-016-audit-actions-endpoint-and-stats.plan.md
epic_branch: epic/PRD-016-action-policy-rules
commit: 694a619
status: COMPLETE
completed: 2026-11-15
---

# Implementation Report — STORY-016: GET /audit/actions with audit scoping, and the three action counts on /stats

**Plan**: `.agents/plans/PRD-016-action-policy-rules/completed/STORY-016-audit-actions-endpoint-and-stats.plan.md`
**Epic Branch**: `epic/PRD-016-action-policy-rules`
**Commit**: `694a619`

## Summary

`GET /audit/actions` (PRD-016 F11, 9.1, Section 10) is a new route in `app/routers/admin.py`, placed after `get_audit`. It copies `get_audit`'s two-step `authorize` scoping verbatim and reads `list_action_decisions(limit, user_id, decision)`. `?limit=` is a `Query(100, ge=1, le=500)` and `?decision=` is an `Optional[Literal["allow","flag","deny"]]`, so FastAPI returns 422 for any other value before the handler runs. Each row maps to `ActionDecisionEntry`, which has exactly the 15 fields of the Section 10 example. `classifications` is decoded from its JSON text into `ActionClassificationEntry` objects. `arguments_preview`, `arguments_hash` and `session_id` are not on the entry. `/stats` makes a second statement, `count_action_decisions()`, and maps it onto `actions_denied`, `actions_flagged` and `actions_allowed` (each defaulting to 0 on `StatsResponse`).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `ActionClassificationEntry`, `ActionDecisionEntry`, `ActionsResponse`; `StatsResponse` + 3 ints | `app/models/schemas.py` | ✅ |
| 2 | `GET /audit/actions`, `_action_entry`, `ActionDecisionFilter`, limit constants; `/stats` reads `count_action_decisions()` | `app/routers/admin.py` | ✅ |
| 3 | `@backend_routes` gains the exact path `/audit/actions` | `Caddyfile` | ✅ |
| 4 | New endpoint / scoping / validation / shape / `/stats` tests | `tests/test_admin_actions.py` | ✅ |
| 5 | Pinned key sets and bodies gain the three keys; schema shape tests; Caddy matcher | `tests/test_stats_router.py`, `tests/test_reporting_invariance.py`, `tests/test_schemas.py`, `tests/test_caddyfile_routes.py` | ✅ |
| 6 | Manual probe: routes registered `['/audit', '/audit/actions', '/stats']` | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Frontend lint | N/A (no `frontend/`) |
| `tests/test_admin_actions.py` alone | ✅ 26 passed |
| Targeted set (8 files, see below) | ✅ 118 passed, 0 failed, 0 skipped |
| Full suite | deferred to orchestrator (user decision) |
| E2E | ✅ 7/7 (all covered in-process by `tests/test_admin_actions.py` and `tests/test_caddyfile_routes.py` against the libSQL dev server) |

Targeted set: `tests/test_admin_actions.py tests/test_audit_router.py tests/test_stats_router.py tests/test_reporting_invariance.py tests/test_schemas.py tests/test_caddyfile_routes.py tests/test_route_reservations.py tests/test_untouched_app.py`, run with `PYTHONUTF8=1 ... -q -p no:cacheprovider`. Result: `118 passed, 2 warnings in 229.04s`.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/models/schemas.py` | UPDATE | +54 |
| `app/routers/admin.py` | UPDATE | +103/-4 |
| `Caddyfile` | UPDATE | +1/-1 |
| `tests/test_admin_actions.py` | CREATE | +393 |
| `tests/test_caddyfile_routes.py` | UPDATE | +4/-1 |
| `tests/test_reporting_invariance.py` | UPDATE | +8 |
| `tests/test_schemas.py` | UPDATE | +58 |
| `tests/test_stats_router.py` | UPDATE | +19 |

## Deviations from Plan

- **Caddyfile (R1, accepted by the orchestrator).** This file is not named in the story. `/audit` is an exact token in `@backend_routes`, so without `/audit/actions` Caddy would serve the new route from the static file server in Docker. `tests/test_caddyfile_routes.py` guards this.
- **Pinned `/stats` assertions (R4).** Six exact key-set and body assertions gain the three keys, each with a PRD-016 F11 comment. No value assertion changed. `test_stats_does_not_fetch_the_register_rows` asserts the three as 0, because `count_action_decisions()` reads the real empty `temp_db` and not the faked snapshot. Its `calls == [((), {"row_limit": 0})]` assertion is unchanged.
- **Extra tests beyond the plan.** `test_audit_read_all_...` is parametrized over an `auditor` user and the admin token. `test_action_classification_entry_kind_defaults_to_none` was added in `tests/test_schemas.py`.
- **`decision=""`.** I ran it to confirm that FastAPI passes an empty query value through as `""` (not as missing), so it returns 422. It stays in the parametrization.
- **R2 (accepted as is).** Query validation runs before the handler body. A caller lacking both audit permissions who sends `?limit=0` gets 422, not 403. A missing or wrong token still gets 401/403 before any DB access (`test_missing_or_wrong_token_rejected_before_db_access`).
- **R3 (accepted).** With `RBAC_ENABLED=false`, every caller reads all rows, as on `GET /audit`.
- **Q1 / Q2 (orchestrator decisions).** `session_id` is off the entry. `/stats` makes two round trips, and the `/stats` comment documents why.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_admin_actions.py` | `test_audit_read_all_sees_every_users_rows_newest_first[auditor,admin-token]`, `test_audit_read_own_sees_only_own_rows`, `test_identity_lacking_both_audit_permissions_returns_403_naming_own`, `test_missing_or_wrong_token_rejected_before_db_access[x2]`, `test_decision_deny_limit_1_returns_one_deny_row`, `test_decision_filter_combines_with_own_scope`, `test_limit_out_of_range_is_422[0,501,-1,x]`, `test_limit_bounds_are_accepted[1,500]`, `test_unknown_decision_is_422[block,DENY,""]`, `test_default_limit_is_100`, `test_decision_literal_mirrors_the_db_vocabulary`, `test_entry_has_exactly_the_section_10_fields`, `test_reason_is_returned_as_stored`, `test_classifications_is_a_list_of_objects` (T9, real `evaluate()` → `record()`), `test_null_kind_classification_and_nullable_fields_pass_through`, `test_stats_action_counts_are_zero_on_an_empty_table`, `test_stats_reports_action_counts`, `test_stats_rejected_before_action_counts_read` |
| `tests/test_schemas.py` | `test_actions_response_shape`, `test_action_classification_entry_kind_defaults_to_none` |

## Acceptance Criteria

- [x] `audit:read:all` → every user's rows newest first; `audit:read:own` → own only; neither → 403 `Permission denied: audit:read:own`, matching `GET /audit` (`test_audit_read_all_...`, `test_audit_read_own_sees_only_own_rows`, `test_identity_lacking_both_audit_permissions_returns_403_naming_own`)
- [x] `?decision=deny&limit=1` → one deny row; `limit` outside 1–500 or unknown `decision` → 422 (`test_decision_deny_limit_1_returns_one_deny_row`, `test_limit_out_of_range_is_422`, `test_unknown_decision_is_422`)
- [x] Entry has exactly the Section 10 fields, not `arguments_preview`/`arguments_hash`; `classifications` is a list of objects (`test_entry_has_exactly_the_section_10_fields`, `test_classifications_is_a_list_of_objects`, `test_actions_response_shape`)
- [x] `/stats` includes `actions_denied`, `actions_flagged`, `actions_allowed`, 0 on an empty table; existing fields and values unchanged (`test_stats_action_counts_are_zero_on_an_empty_table`, `test_stats_reports_action_counts`, `test_zero_rows_returns_zeroed_stats_without_error`, and all of `tests/test_stats_router.py` green)
