---
story: STORY-010
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-010-pipeline-identity-authorization.plan.md
epic_branch: epic/PRD-005-rbac
commit: b222be8
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-010: run_query() requires an Identity and authorizes as step 0

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-010-pipeline-identity-authorization.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `b222be8`

## Summary

`run_query()` now takes a required `identity: Identity` parameter in place of the free-standing `user_id: str`, and performs `authorize(identity, PERMISSION_QUERY_SUBMIT)` as step 0 — ahead of `check_duplicate()`. A denial follows the existing block-then-return shape: it writes exactly one audit row (`role`, `denied_permission`, `success=True`) and returns `QueryBlockedForbiddenResponse` without ever invoking `call_openrouter`. Because `identity` has no default, any caller that omits it fails outright with `TypeError` rather than proceeding unauthorized — the structural fix for PRD Risk 1. `app/routers/query.py` and `chat_ui/chat_ui/state.py` were deliberately left untouched, per the story's own Technical Notes (those callers are STORY-013 and STORY-014).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Add step-0 authorization to `run_query()` | `app/services/query_pipeline.py` | ✅ |
| 2 | Update direct `run_query()` calls (AC1/AC4) | `tests/test_chat_state.py` | ✅ |
| 3 | Update direct `run_query()` call (AC1/AC4) | `tests/test_pii_dedup_isolation.py` | ✅ |
| 4 | New authorization tests (AC2, AC3, AC4 sanity, AC5) | `tests/test_query_pipeline_authorization.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| `python -c "import app.services.query_pipeline"` | ✅ |
| Scoped suite (`test_query_pipeline_authorization.py`, `test_authz.py`, `test_schemas.py`, `test_audit_logger.py`, `test_chat_state.py`, `test_pii_dedup_isolation.py`) | 89 passed, 17 accepted-regression failures (see Deviations) |
| E2E (plan's two pytest commands + manual denial check) | ✅ 2/2, all pass |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/query_pipeline.py` | UPDATE | +26/-6 |
| `tests/test_chat_state.py` | UPDATE | +5/-4 |
| `tests/test_pii_dedup_isolation.py` | UPDATE | +2/-1 |
| `tests/test_query_pipeline_authorization.py` | CREATE | +139 |
| `.agents/plans/PRD-005-rbac/completed/STORY-010-pipeline-identity-authorization.plan.md` | CREATE (archived) | — |

## Deviations from Plan

The plan's "known, accepted regression" note originally scoped the fallout to `tests/test_query_router.py` and `tests/test_integration.py` only. Running the actual full suite after implementing showed the blast radius is wider — **71 failures total**, all still fully contained to tests that drive `run_query()` through the two real, unmigrated callers (the router and `chat_ui.state.send()`):

- `tests/test_query_router.py` — 30 failures (all of them; every test posts to `/query` via `TestClient`)
- `tests/test_pii_redaction_integration.py` — 14 failures (same path)
- `tests/test_integration.py` — 10 failures (same path)
- `tests/test_pii_dedup_isolation.py` — 11 failures (tests that hit `/query` via `TestClient`, distinct from the one direct `run_query()` call updated in Task 3, which passes)
- `tests/test_chat_state.py` — 6 failures (tests that monkeypatch only `call_openrouter` and let the real, unmigrated `chat_ui.state.send()` call the real `run_query()`; distinct from the 4 direct-call tests updated in Task 2, and from other `send()` tests that fully monkeypatch `run_query` itself, both of which pass)

No other test file is affected — `test_authz.py`, `test_schemas.py`, `test_audit_logger.py`, `test_admin_auth.py`, `test_db.py`, `test_identity.py`, `test_manage_users_cli.py`, `test_config.py`, `test_main.py`, `test_duplicate_checker.py`, `test_openrouter_client.py`, `test_pattern_detector.py`, `test_route_reservations.py`, `test_stats_router.py`, `test_chat_components_import.py`, `test_copy.py`, `test_pii_badge.py`, `test_pii_redactor.py`, `test_success_metadata_footer.py`, and the new `test_query_pipeline_authorization.py` all stay green (full suite: 276 passed alongside the 71 failures).

This is the direct, unavoidable consequence of the story's own Technical Notes deferring `app/routers/query.py` to STORY-013 and `chat_ui/chat_ui/state.py` to STORY-014 — not a bug introduced by this story. Neither caller was patched here, since a throwaway fix (no bearer-token resolution or login session exists yet on either path) would duplicate those stories' scope. The plan document was updated in place to record the verified, complete list before archiving, so STORY-013/014 implementers have an accurate starting picture rather than a surprise.

No other deviations. Implementation matches the plan's task list and file scope exactly.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_pipeline_authorization.py` | `test_forbidden_identity_blocked_before_check_duplicate` (AC2), `test_forbidden_identity_writes_exactly_one_audit_row` (AC3), `test_authorized_identity_reaches_openrouter` (AC4 sanity), `test_run_query_without_identity_raises_type_error` (AC5) |
| `tests/test_chat_state.py` (updated) | `test_run_query_success_returns_response_and_logs_row`, `test_run_query_duplicate_blocked_before_openrouter_call`, `test_run_query_suspicious_pattern_blocked_before_openrouter_call`, `test_run_query_openrouter_error_raises_and_logs_failure` — each now passes `identity=Identity(user_id=..., role="user")` |
| `tests/test_pii_dedup_isolation.py` (updated) | `test_hash_prompt_only_ever_receives_raw_text` — same `identity=` swap |

## Acceptance Criteria

- [x] Given `run_query(...)`, when its signature is defined, then `identity: Identity` is a **required** parameter and the free-standing `user_id: str` input is removed — the audited user id comes from `identity.user_id`
- [x] Given an identity lacking `query:submit`, when `run_query()` is called, then it returns `QueryBlockedForbiddenResponse` before `check_duplicate()` runs, and `call_openrouter` is never invoked
- [x] Given that denial, when it happens, then exactly one audit row is written carrying `role` and `denied_permission="query:submit"`, with `success=1`
- [x] Given an authorized identity, when `run_query()` runs, then steps 1-6 behave exactly as today and every existing pipeline test passes with only the identity argument added
- [x] Given a caller that omits `identity`, when the call is made, then it fails outright rather than proceeding unauthorized
