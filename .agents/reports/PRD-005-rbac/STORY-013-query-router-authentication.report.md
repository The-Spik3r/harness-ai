---
story: STORY-013
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-013-query-router-authentication.plan.md
epic_branch: epic/PRD-005-rbac
commit: PENDING
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-013: POST /query bearer authentication and status-code mapping

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-013-query-router-authentication.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: PENDING

## Summary

`POST /query` now authenticates via `Depends(require_permission(PERMISSION_QUERY_SUBMIT))` (STORY-012's dependencies), giving the endpoint the documented `401`/`403` split ahead of — and in addition to — `run_query()`'s own `query:submit` defense-in-depth check (STORY-010). `QueryRequest.user_id` is now `Optional[str] = None`, deprecated and never trusted as identity; a body value that doesn't match the authenticated credential is refused with `403` instead of silently overridden, and the router now passes the resolved `Identity` into `run_query()` so the audited user id always comes from the credential. Model-allowlist and BYOK-without-permission refusals are untouched — `run_query()` already returns them in-band as `200` + `status: "BLOCKED"`.

Making `POST /query` require auth broke five other pre-existing test files that posted to it without a credential (`tests/test_integration.py`, `tests/test_pii_dedup_isolation.py`, `tests/test_pii_redaction_integration.py`, `tests/test_schemas.py`, and `tests/test_query_router.py` itself) — all were updated to seed a real `users` row and send a bearer token, per-identity where a test needed two distinct audited users in one flow. Two of `tests/test_pii_redaction_integration.py`'s own epic-wide regression guards (`_PRE_EPIC_UNTOUCHED_TESTS`, and the "no pre-epic test function removed or renamed" census) were also updated to record this story's contract change as a deliberate, documented exception rather than silently bypassing them — see Deviations below.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | `QueryRequest.user_id` becomes optional and deprecated | `app/models/schemas.py` | ✅ |
| 2 | Wire `require_permission(PERMISSION_QUERY_SUBMIT)` and identity-sourced `user_id` into the router | `app/routers/query.py` | ✅ |
| 3 | Update `tests/test_query_router.py` for the new auth contract | `tests/test_query_router.py` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `python -c "import app.models.schemas"` | ✅ |
| `python -c "import app.routers.query"` | ✅ |
| `python -c "from app.main import app"` | ✅ |
| `pytest tests/test_query_router.py -q` | ✅ (36 passed) |
| `pytest tests/test_query_pipeline_authorization.py tests/test_auth_dependencies.py tests/test_authz.py -q` | ✅ (52 passed) |
| `pytest tests/ -q` (full repo) | ✅ (368 passed, 6 failed — all in `tests/test_chat_state.py`, pre-existing on this branch before this story's changes (verified via `git stash`), out of scope: `chat_ui/chat_ui/state.py` is explicitly STORY-014's responsibility per STORY-010's own Technical Notes) |
| E2E | ✅ (4/4 — see below) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/models/schemas.py` | UPDATE | +5/-1 |
| `app/routers/query.py` | UPDATE | +14/-5 |
| `tests/test_query_router.py` | UPDATE | +83/-9 |
| `tests/test_schemas.py` | UPDATE | +5/-4 |
| `tests/test_integration.py` | UPDATE | +29/-5 |
| `tests/test_pii_dedup_isolation.py` | UPDATE | +50/-9 |
| `tests/test_pii_redaction_integration.py` | UPDATE | +37/-4 |

## Deviations from Plan

1. **Four additional test files needed updates beyond the plan's file list.** The plan scoped only `tests/test_query_router.py`, but `tests/test_integration.py`, `tests/test_pii_dedup_isolation.py`, `tests/test_pii_redaction_integration.py`, and `tests/test_schemas.py` all exercised `POST /query` (or `QueryRequest`'s old required-`user_id` contract) without anticipating the new auth requirement, and broke once it landed. Each was updated using the same pattern already established for `tests/test_query_router.py`: seed a real `users` row via `insert_user(User(..., token_hash=hash_token(...)))` and send the matching `Authorization: Bearer` header; where a test needed two distinct audited users in one flow (`test_integration.py`, `test_pii_dedup_isolation.py`), two identities were seeded and each `client.post(...)` call carries its own `headers=`.
2. **`tests/test_pii_redaction_integration.py`'s epic-wide regression guards were updated, not bypassed.** That file pins two invariants across the whole `epic/PRD-005-rbac` branch: a list of files the epic should never need to touch (`_PRE_EPIC_UNTOUCHED_TESTS`), and a census asserting no pre-epic test function is ever removed or renamed. This story's contract change (`user_id` optional, credential-sourced identity) genuinely invalidated three pre-RBAC tests' premises (`test_query_request_missing_user_id_raises`, `test_missing_user_id_returns_422`, `test_empty_user_id_returns_400_before_any_side_effect`) and required opening `tests/test_integration.py`. Rather than weakening the guard tests silently, `tests/test_integration.py` was removed from `_PRE_EPIC_UNTOUCHED_TESTS` (with a comment explaining why), and a new `_DELIBERATELY_SUPERSEDED_TESTS` allowlist was added to the removed/renamed-test census, naming exactly the three superseded tests and the new tests that replace them — so any *other*, unrelated test deletion would still be caught.
3. **`_USER_ID`/two-identity handling in `test_pii_dedup_isolation.py` and `test_integration.py`** followed the same "seed both identities, header per call" shape rather than a single shared default-header client, because both files post as two different `user_id`s within the same test and a single default-header `TestClient` (as used in `test_query_router.py`, which only ever needs one identity) can't represent that.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_query_router.py` | `test_missing_authorization_header_returns_401_and_no_audit_row`, `test_identity_lacking_query_submit_returns_403_naming_permission`, `test_body_user_id_mismatch_returns_403_without_overriding`, `test_body_user_id_absent_proceeds_with_credential_user_id`, `test_body_user_id_matching_credential_proceeds`, `test_byok_without_permission_returns_200_blocked_with_required_permission` |
| `tests/test_schemas.py` | `test_query_request_missing_user_id_defaults_to_none` (replaces `test_query_request_missing_user_id_raises`) |

## End-to-End Verification

- [x] `pytest tests/test_query_router.py -q` — all green, including every pre-existing test unmodified in behavior
- [x] `pytest tests/test_query_pipeline_authorization.py tests/test_auth_dependencies.py tests/test_authz.py -q` — no regression
- [x] Manual: started `uvicorn app.main:app` against the real dev DB; `POST /query` with no `Authorization` header returned `401` `{"detail": "Invalid or missing credential"}`
- [x] Manual: same server, `Authorization: Bearer <ADMIN_TOKEN>` with a mismatching body `user_id` returned `403` `{"detail": "user_id does not match the authenticated identity"}`

## Acceptance Criteria

- [x] Given no `Authorization` header, when `POST /query` is called, then it returns `401` and no audit row is written
- [x] Given a valid credential whose role lacks `query:submit`, when it is called, then it returns `403` naming the permission
- [x] Given a body `user_id` different from the authenticated user, when it is called, then it returns `403` rather than silently overriding it
- [x] Given a body `user_id` that matches or is absent, when it is called, then the request proceeds and the audited user id comes from the credential
- [x] Given a policy refusal (model outside the allowlist, or BYOK without permission), when it is called, then it returns `200` with `status: "BLOCKED"` and `required_permission`
