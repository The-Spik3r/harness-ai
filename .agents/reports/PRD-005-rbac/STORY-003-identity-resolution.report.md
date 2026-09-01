---
story: STORY-003
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-003-identity-resolution.plan.md
epic_branch: epic/PRD-005-rbac
commit: cadaebd
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-003: Identity resolution — token hashing, Identity value object, ADMIN_TOKEN break-glass

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-003-identity-resolution.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `cadaebd`

## Summary

Added `app/services/identity.py`, a new, self-contained module providing the system's first verified-identity primitive: a frozen `Identity` dataclass (`user_id`, `role`), `hash_token()` (SHA-256), `issue_token()` (`secrets.token_urlsafe(32)`), and `resolve(token)` — which returns an `Identity` for a valid active user token or the configured `ADMIN_TOKEN` break-glass credential, and `None` for every failure case (unknown, malformed, empty, or deactivated token) alike. Nothing existing was modified; the module has no consumers yet (that begins with STORY-004/006/012).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Verify baseline (274 passed, 50 in test_db.py, no pre-existing identity module) | — | ✅ |
| 2 | Create `Identity`, `hash_token()`, `issue_token()`, `resolve()` | `app/services/identity.py` | ✅ |
| 3 | Tests — valid/unknown/malformed/empty/deactivated tokens (AC1, AC2) | `tests/test_identity.py` | ✅ |
| 4 | Tests — ADMIN_TOKEN break-glass + constant-time comparison + DB-independence (AC3) | `tests/test_identity.py` | ✅ |
| 5 | Tests — token issuance and hashing correctness (AC5) | `tests/test_identity.py` | ✅ |
| 6 | Tests — Identity immutability, equality, hash_prompt isolation guard | `tests/test_identity.py` | ✅ |
| 7 | Full-suite regression and diff gate | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A — no npm frontend, UI is Reflex (Python) |
| Tests | ✅ (22 new in `tests/test_identity.py`; 296 total, up from 274) |
| E2E | ✅ (7/7 — see below) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/services/identity.py` | CREATE | +61 |
| `tests/test_identity.py` | CREATE | +178 |
| `.agents/plans/PRD-005-rbac/completed/STORY-003-identity-resolution.plan.md` | CREATE (archived) | +548 |

## Deviations from Plan

1. **Test count is 22, not the plan's estimated 21.** The plan's own task breakdown lists 7 + 4 + 7 + 4 = 22 tests but stated the total as "21" in two places (Task 7 and the Acceptance Criteria section) — an arithmetic slip in the plan itself. Actual full-suite total is **296** (274 + 22), not the plan's stated 295. No test was dropped or added beyond what each task specified.
2. **`hash_token()`'s docstring was reworded mid-implementation.** The plan's Task 2 code block included the docstring text "Deliberately not shared with duplicate_checker.hash_prompt()", which — once written — caused Task 6's own `test_identity_module_does_not_import_hash_prompt` source-inspection test to fail (the docstring literally contains the strings `hash_prompt` and `duplicate_checker`, which the guard test checks for). Fixed by rewording the docstring to describe the same design decision without naming those tokens directly ("the prompt-hashing helper used for deduplication elsewhere in the codebase"). No behavior change; the isolation guard test now passes and still catches an actual future import/reference.

Neither deviation touched scope, acceptance criteria, or any file outside what the plan specified.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_identity.py` | `test_resolve_returns_identity_for_valid_active_user`, `test_resolve_hashes_the_credential_not_the_stored_digest`, `test_resolve_unknown_token_returns_none`, `test_resolve_empty_token_returns_none`, `test_resolve_none_token_returns_none`, `test_resolve_malformed_token_returns_none`, `test_resolve_deactivated_user_returns_none`, `test_resolve_admin_token_returns_synthetic_admin_identity`, `test_resolve_admin_token_uses_compare_digest`, `test_resolve_wrong_token_is_not_treated_as_admin`, `test_resolve_admin_token_works_without_users_table`, `test_issue_token_uses_token_urlsafe_with_32_bytes`, `test_issue_token_returns_distinct_high_entropy_values`, `test_issue_token_returns_a_string`, `test_hash_token_matches_manual_sha256`, `test_hash_token_is_deterministic`, `test_hash_token_differs_for_different_input`, `test_hash_token_is_case_sensitive`, `test_identity_is_frozen`, `test_identity_equality_by_value`, `test_identity_is_hashable`, `test_identity_module_does_not_import_hash_prompt` |

## End-to-End Verification

- [x] `tests/test_identity.py -v` — 22 passed
- [x] `pytest -q` (full suite) — 296 passed, zero pre-existing failures
- [x] Real on-disk round trip (`probe3.db`): issue → hash → persist → resolve → deactivate → resolve returns `None` — matched expected output exactly
- [x] Break-glass resolves against the real repo-root `harness_ai.db` with zero bootstrap: `resolve(settings.ADMIN_TOKEN) == Identity(user_id='admin', role='admin')`
- [x] `from app.main import app` — imports clean
- [x] `uvicorn app.main:app` starts; `curl /health` → `{"status":"ok"}`
- [x] `tests/test_admin_auth.py tests/test_db.py tests/test_query_router.py tests/test_chat_state.py` — 121 passed, unmodified

## Acceptance Criteria

- [x] Given a valid active user token, when `resolve(token)` is called, then it returns `Identity(user_id, role)`
- [x] Given an unknown, malformed, empty, or deactivated token, when `resolve(token)` is called, then it returns `None` — never a partial, default, or anonymous identity
- [x] Given the configured `ADMIN_TOKEN`, when `resolve(token)` is called, then it returns a synthetic `Identity` with role `admin`, compared with `secrets.compare_digest`
- [x] Given a token is issued, when it is persisted, then only its SHA-256 digest is stored and the plaintext appears nowhere in the database or logs
- [x] Given `issue_token()`, when it generates a credential, then it uses `secrets.token_urlsafe(32)` and returns the plaintext exactly once
