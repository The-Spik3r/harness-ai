---
story: STORY-011
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-011-usage-gate-in-pipeline.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 8dc6b4d
status: COMPLETE
completed: 2026-10-19
---

# Implementation Report — STORY-011: Usage gate in the pipeline: response, audited arm and duplicate-lookup exclusion

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-011-usage-gate-in-pipeline.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `8dc6b4d`

## Summary

`run_conversation` now has step 2c, the usage gate. It runs after the three authorization arms and before the context limit, and only when `USAGE_LIMITS_ENABLED` is on (read per call). It calls `admit(identity, charges_budget=openrouter_api_key is None)` through `query_pipeline`'s own `admit` binding, so tests can spy on it. The result is kept in the local `admission`, which STORY-012 will read for `admission.day`.

- **Refusal:** writes one audit row and returns `QueryBlockedUsageLimitResponse` with `200 BLOCKED`. The row has `success=True`, `role`, `limit_exceeded`, the `dedup_key`, and the `ingress`, `message_count`, `conversation_key` and `streamed` every row carries.
- **`UsageLimitError`:** propagates with no row and no upstream call. `POST /query` maps it to `500`, and the chat routes it through the internal-error bubble.
- **Duplicate lookup:** `find_duplicate_timestamp` excludes `limit_exceeded` rows. NULL passes, so rows written before PRD-013 behave as before.
- **Chat:** an explicit interim arm renders the new result through the existing internal-error bubble. STORY-014 replaces it.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `QueryBlockedUsageLimitResponse`, appended last to `QueryResponse` | `app/models/schemas.py` | ✅ |
| 2 | Step 2c with the audited refusal arm; `QueryPipelineResult` + 1; fixed the mis-indented BYOK `_deny` line | `app/services/query_pipeline.py` | ✅ |
| 3 | `AND limit_exceeded IS NULL` in the duplicate lookup; its SQL copy and a parametrized test in `test_db.py` | `app/db/database.py`, `tests/test_db.py` | ✅ |
| 4 | `except UsageLimitError` → 500 | `app/routers/query.py` | ✅ |
| 5 | `UsageLimitError` → internal-error bubble; interim usage-limit arm; catch-all comment | `chat_ui/chat_ui/state.py` | ✅ |
| 6 | 24 tests for the gate | `tests/test_query_pipeline_usage_limits.py` | ✅ |
| 7 | Outcome 8 (additions only) | `tests/test_query_outcomes_regression.py` | ✅ |
| 8 | Schema and chat pins | `tests/test_schemas.py`, `tests/test_chat_state.py` | ✅ |
| 9 | Full-suite sweep | four guards raised (see Deviations) | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`, plus `chat_ui.chat_ui.state`) | ✅ |
| Frontend lint | N/A. There is no npm frontend (the UI is Reflex) and no Python linter is configured; `py_compile` on every changed module ✅ |
| Tests | ✅ 3644 passed, 27 skipped. One error and one failure came from libSQL connection timeouts (`os error 10060`) in `test_chat_sessions.py` and `test_duplicate_scope.py`; both files pass on rerun (150/150). |
| Mutation check | With the new lookup predicate removed, 4 tests fail (the reset-then-resend test, the SQL-shape test, and 2 lookup cases). With it restored, they pass. |
| E2E | ✅ 1/1 manual (below), plus the automated checks in the plan's E2E list |

### E2E (manual)

`uvicorn app.main:app` against the dev libSQL with `USAGE_REQUESTS_PER_MINUTE='*=2'` and a placeholder OpenRouter key, so nothing was spent. One user was created with `manage_users.py create-user`.

- Sends 1–2 returned `502`. The upstream call failed, but both attempts were counted.
- Send 3 returned `200`.
- Send 4's body was `{"status":"BLOCKED","reason":"Usage limit reached","limit":"requests","maximum":2,"actual":4,"resets_at":"2026-10-19T14:13:00Z"}`.
- `GET /audit` showed the refusal row with `limit_exceeded="requests"`, `role="user"`, `ingress="query"`, `message_count=1` and a conversation key. The upstream-failure rows show `limit_exceeded=null`.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +7 |
| `app/models/schemas.py` | UPDATE | +28 |
| `app/routers/query.py` | UPDATE | +6 |
| `app/services/query_pipeline.py` | UPDATE | +69/-1 |
| `chat_ui/chat_ui/state.py` | UPDATE | +23/-3 |
| `tests/test_query_pipeline_usage_limits.py` | CREATE | +539 |
| `tests/test_chat_state.py` | UPDATE | +61 |
| `tests/test_db.py` | UPDATE | +29 |
| `tests/test_query_outcomes_regression.py` | UPDATE | +56 |
| `tests/test_schemas.py` | UPDATE | +50 |
| `tests/test_query_pipeline_audit_fields.py` | UPDATE | +6/-2 |
| `tests/test_query_pipeline_dedup_key.py` | UPDATE | +3/-2 |
| `tests/test_query_pipeline_pii_profiles.py` | UPDATE | +4/-2 |
| `tests/test_query_pipeline_session_passthrough.py` | UPDATE | +3/-2 |
| `tests/test_two_instance_smoke.py` | UPDATE | +10/-3 |

## Deviations from Plan

1. **Four guards the plan did not anticipate were raised.** Each is a test built to fail when a new arm or statement appears, and each now carries a comment citing PRD-013 STORY-011:
   - The `log_query` call-site counts in `test_query_pipeline_dedup_key.py`, `test_query_pipeline_pii_profiles.py` and `test_query_pipeline_session_passthrough.py` went from 10 to 11 pipeline sites.
   - `test_query_pipeline_audit_fields.py`'s count of production sites went from 11 to 12.
   - `test_two_instance_smoke.py::test_round_trip_cost_is_measured_and_reported` now expects four statements instead of three. The gate's `INSERT INTO usage_daily … RETURNING` sits between the identity read and the duplicate check, the round trip PRD-013 Risk 1 accepts and STORY-017 measures.

   The three-field and per-key requirements in those tests are unchanged.
2. **`UsageLimitError` is not imported into `query_pipeline`.** It would have been unused there, so the comment names it instead, as the plan allowed.
3. **No `noqa` on `admission`.** The local is read (`admission.admitted`), so no unused-variable warning arises. It is initialized to `None`, with a comment that STORY-012 reads `None` as "charge nothing".
4. **Plan-commit hygiene.** The working tree held unrelated uncommitted docs (`pre-prds/README.md`, `pre-prds/PRE-PRD-017-test-suite-db-isolation.md`). They were left unstaged and untouched rather than stopping the run.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_usage_limits.py` | rate refusal shape and full row; budget refusal and next-midnight reset; both broken → `requests`; `run_query` reaches the arm with `ingress="query"`; admitted row has no limit; spy order (authorize, usage, context_limit, duplicate, pattern, upstream); no `query:submit` / disallowed model / BYOK denial never reach the gate and leave no `usage_daily` row; duplicate, context-limit and pattern refusals each consume one unit; usage refusal precedes the context limit; refused-then-reset prompt is answered and the next send's prior is the success; `admit` raising → no row, no upstream; `StorageError` in the counter → `UsageLimitError`, no row; `/query` 500 on `UsageLimitError`; `/query` 200 with the exact usage-limit body; switch off → no `usage_daily` statement on success, duplicate and context-limit; switch off → a refusing limit admits; switch read per call; `charges_budget` false exactly with a BYOK key; BYOK not budget-refused; BYOK still rate-limited |
| `tests/test_query_outcomes_regression.py` | `test_outcome_8_usage_limit` (real storage, budget refusal, exact body, one row) |
| `tests/test_db.py` | `test_duplicate_lookup_ignores_a_usage_limit_row[None/requests/tokens]` |
| `tests/test_schemas.py` | dump matches PRD Section 10; last member of `QueryResponse`; unknown `limit` refused (4 cases); `QueryRequest` carries no limit field |
| `tests/test_chat_state.py` | `UsageLimitError` → internal-error bubble; interim usage-limit bubble with limit and reset in `detail` |

## Acceptance Criteria

- [x] Given an identity over its rate limit or its budget, when `run_conversation` runs, then it returns `QueryBlockedUsageLimitResponse(reason="Usage limit reached", limit=..., maximum=..., actual=..., resets_at=...)`, `call_openrouter` is not called, and exactly one row is written with `success=1`, `limit_exceeded` set, `role` set and a non-NULL `dedup_key`.
- [x] Given spies on each step, when a request runs, then the order is authorization, usage gate, context limit, duplicate, patterns; a caller without `query:submit` never reaches the gate and has no `usage_daily` row; a duplicate-blocked request and a context-limit refusal each consume one unit of the rate window.
- [x] Given a prompt refused for a usage limit, when the same prompt is sent again after the window resets, then it is answered and not held as a duplicate; `test_duplicate_scope.py` and STORY-001 pass with no assertion changed.
- [x] Given `POST /query` over a limit, when it is called, then the status is `200` with the usage-limit body; given `admit` raising `UsageLimitError`, then the status is `500` and no upstream call is made.
- [x] Given `USAGE_LIMITS_ENABLED=false`, when any request runs, then no statement touches `usage_daily`, and `tests/test_query_outcomes_regression.py` gains row 8 (usage limit) with rows 1-7 unchanged.
