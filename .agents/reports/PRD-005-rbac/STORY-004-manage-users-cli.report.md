---
story: STORY-004
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-004-manage-users-cli.plan.md
epic_branch: epic/PRD-005-rbac
commit: 10e63fc
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-004: Bootstrap CLI — scripts/manage_users.py

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-004-manage-users-cli.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `10e63fc`

## Summary

Added `scripts/manage_users.py`, the MVP's only administration surface, as a stdlib-`argparse` CLI with four subcommands: `create-user`, `list-users`, `deactivate-user`, `issue-token`. It is pure orchestration on top of STORY-002's database helpers (`insert_user`, `list_users`, `deactivate_user`, `get_user`, `set_user_token_hash`) and STORY-003's identity primitives (`issue_token`, `hash_token`) — no new business logic. Role validity (`admin`/`auditor`/`user`) is enforced through argparse's own `choices=`, which satisfies "exits non-zero with a message listing the valid roles" without hand-written validation. `app/config.py` gained one additive field, `RBAC_DEFAULT_ROLE: str = "user"`, needed for the "`--role` omitted" acceptance criterion since this story depends only on STORY-003, not STORY-005 (which formally introduces the rest of the `RBAC_*` env-var group on top of this field).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Verify baseline (296 tests green, target files absent) | — | ✅ |
| 2 | Add `RBAC_DEFAULT_ROLE` to `Settings` | `app/config.py` | ✅ |
| 3 | Create package marker | `scripts/__init__.py` | ✅ |
| 4 | Create the CLI | `scripts/manage_users.py` | ✅ |
| 5 | Tests: `create-user` (AC1, AC2, AC3) | `tests/test_manage_users_cli.py` | ✅ |
| 6 | Tests: `list-users` (AC4) | `tests/test_manage_users_cli.py` | ✅ |
| 7 | Tests: `deactivate-user` (AC5) | `tests/test_manage_users_cli.py` | ✅ |
| 8 | Tests: `issue-token` (Design Note 4) | `tests/test_manage_users_cli.py` | ✅ |
| 9 | Full-suite regression + diff gate | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`app.main`) | ✅ |
| `scripts.manage_users` import | ✅ |
| `manage_users.py --help` | ✅ |
| Tests | ✅ (10 new, 306 total, 0 regressions) |
| E2E | ✅ (6/6 — see below) |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/config.py` | UPDATE | +4 |
| `scripts/__init__.py` | CREATE | +0 |
| `scripts/manage_users.py` | CREATE | +99 |
| `tests/test_manage_users_cli.py` | CREATE | +140 |

## Deviations from Plan

One small deviation, no behavior change: Task 5's test file imports `hash_token` directly at module scope and calls `find_user_by_token_hash(hash_token(token))` inline in the assertion, rather than the plan's sketched local helper function `find_user_by_token_hash_matches()`. Equivalent behavior, simpler code — the plan's nested-function indirection wasn't needed once written out.

Everything else — subcommand set, argparse `choices=` validation strategy, `RBAC_DEFAULT_ROLE` placement, `sqlite3.IntegrityError` handling, `issue-token` inclusion — matches the plan exactly, including the predicted test count (10) and full-suite total (306).

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_manage_users_cli.py` | `test_create_user_prints_token_exactly_once_with_recovery_warning`, `test_create_user_role_omitted_uses_rbac_default_role`, `test_create_user_invalid_role_exits_nonzero_and_lists_valid_roles`, `test_create_user_duplicate_user_id_exits_nonzero`, `test_list_users_prints_expected_fields_never_token_or_hash`, `test_list_users_empty_table_prints_nothing`, `test_deactivate_user_blocks_next_resolve`, `test_deactivate_user_unknown_user_exits_nonzero`, `test_issue_token_rotates_credential`, `test_issue_token_unknown_user_exits_nonzero` |

## End-to-End Verification

- [x] Real on-disk round trip against a scratch SQLite database: `create-user` → `list-users` → `issue-token` → `deactivate-user` → `list-users` — token printed once each time, row retained (not deleted) after deactivation, `active` flips `True` → `False`
- [x] `--role nope` on `create-user` exits non-zero (argparse exit code 2) and stderr lists `admin`, `auditor`, `user`
- [x] `from app.main import app` imports clean — no circular-import issue from the new `Settings` field
- [x] `tests/test_identity.py tests/test_db.py` — 72 passed, unmodified

## Acceptance Criteria

- [x] Given `python scripts/manage_users.py create-user --user-id ana --role user`, when it runs, then the row is created and the plaintext token is printed exactly once with a warning that it cannot be recovered
- [x] Given `--role` is omitted, when a user is created, then the role is `RBAC_DEFAULT_ROLE`
- [x] Given a role outside the known set, when `create-user` runs, then it exits non-zero with a message listing the valid roles
- [x] Given `list-users`, when it runs, then it prints `user_id`, `role`, `active`, `created_at` — and never a token or a hash
- [x] Given `deactivate-user --user-id ana`, when it runs, then that user's next `resolve()` returns `None`
