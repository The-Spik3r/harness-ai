---
story: STORY-002
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-002-exception-characterization-tests.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: TBD
status: COMPLETE
completed: 2026-09-01
---

# Implementation Report — STORY-002: Characterization tests pinning the three driver-exception behaviors

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-002-exception-characterization-tests.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `TBD`

## Summary

Pinned the three `except sqlite3.*` behaviors that STORY-004 will decouple from the driver, plus the endpoint-level consequence of the first. Four new tests and one strengthened test, all asserting **observable behavior** — return value, HTTP status code, CLI exit code and stderr — so none of them needs rewriting when the driver changes. No production code was touched: across the entire branch versus `main`, the only non-`.agents` paths that differ are the four `tests/` files.

Two of the story's acceptance criteria described behavior the code does not have. Both were pinned **as they actually are**, per AC5's rule that a characterization test must never require a production change to go green. Both are flagged below and in the tests' own docstrings.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Clear the local `.env` blocker (3 extra keys rejected by pydantic) | `.env` (untracked) | ✅ |
| 1 | `find_user_by_token_hash()` returns `None` with no `users` table | `tests/test_db.py` | ✅ |
| 2 | Same condition resolves to 401, not 500 | `tests/test_auth_dependencies.py` | ✅ |
| 3 | Duplicate-check storage failure → 500 through the real router | `tests/test_query_router.py` | ✅ |
| 4 | CLI duplicate `user_id` — exit code, stream, no credential leak | `tests/test_manage_users_cli.py` | ✅ |
| 5 | CLI duplicate `token_hash` — pinned as *not* distinguished | `tests/test_manage_users_cli.py` | ✅ |
| 6 | Green baseline + tests-only diff verification | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `from app.config import settings` (after Task 0) | ✅ |
| Four target suites + `test_duplicate_checker.py` | ✅ 121 passed |
| Full suite | ⚠️ 1021 passed, 7 failed — **all 7 pre-existing, identical to baseline** (see below) |
| Regressions introduced | ✅ none (baseline 1017 passed / 7 failed → 1021 passed / same 7 failed) |
| Production code changed | ✅ none |
| E2E checklist | ✅ 6/6 (two checks refined — see Deviations) |
| Mutation spot-checks | ✅ 3/3 fail correctly and revert clean |

### The 7 pre-existing failures are not this story's

They fail identically on the clean tree (verified by stashing all work and re-running). Six belong to `tests/test_untouched_app.py`, PRD-006's containment guard, which diffs against the pinned base `_BASE = "d3e6279"` — the tree as it stood before PRD-006 began. The four files it reports as violations were legitimately changed by **PRD-005 (RBAC)** commits that landed after that base:

| Pinned file | Changed since `d3e6279` by |
|---|---|
| `tests/test_db.py` | `936cff8`, `903dee8`, `320d2d2` (PRD-005 STORY-001/002/009) |
| `tests/test_audit_router.py` | `6e0d3ca` (PRD-005 STORY-015) |
| `tests/test_stats_router.py` | `6e0d3ca` (PRD-005 STORY-015) |
| `tests/test_chat_state.py` | `b222be8`, `a38f38b`, `0056d30` (PRD-005 STORY-010/014/017) |

The seventh, `tests/test_chat_state.py::test_chat_state_holds_no_token_or_role_var`, is likewise pre-existing.

**This needs a decision, and it is not STORY-002's to make.** The guard is now permanently red on this branch and will get redder: PRD-007 modifies `tests/test_db.py` again in STORY-003, and STORY-006 rewrites `app/db/database.py`, which will also keep `test_no_file_under_app_changed_since_prd_006_began` failing. Either the guard is re-baselined for the post-PRD-005 line of history, or it is retired as having served its purpose. Raised here rather than fixed, because touching it would be a change outside this story's scope.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `tests/test_db.py` | UPDATE | +24 |
| `tests/test_auth_dependencies.py` | UPDATE | +31 |
| `tests/test_query_router.py` | UPDATE | +30 |
| `tests/test_manage_users_cli.py` | UPDATE | +55/-1 |

Total: 4 files, +139/-1. `git diff main --stat -- . ':!.agents'` lists these four and nothing else.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `uninitialized_db` fixture; `test_find_user_by_token_hash_returns_none_when_users_table_does_not_exist` |
| `tests/test_auth_dependencies.py` | `uninitialized_db` fixture; `test_require_identity_returns_401_not_500_when_users_table_does_not_exist` |
| `tests/test_query_router.py` | `test_duplicate_check_storage_failure_returns_500` |
| `tests/test_manage_users_cli.py` | `test_create_user_duplicate_token_hash_is_not_distinguished_from_duplicate_user_id`; strengthened `test_create_user_duplicate_user_id_exits_nonzero` |

### Mutation verification

Each pin was proven to actually bite, by inverting the production behavior by hand and confirming the failure, then reverting:

| Mutation | Result |
|---|---|
| `app/db/database.py` — `except sqlite3.OperationalError` re-raises instead of returning `None` | 401 test fails ✅ |
| `app/routers/query.py` — `DuplicateCheckError` → 503 instead of 500 | 500 test fails ✅ (`assert 503 == 500`) |
| `scripts/manage_users.py` — distinguish `token_hash` from `user_id` violations | AC4 test fails ✅ |

All three reverted; `git status app/ scripts/` clean.

## Findings Raised

### Finding A — AC2 and PRD Section 6 Pattern 6 both misstate the duplicate-check behavior

Both claim a storage failure "degrades the duplicate check without failing the query". It does not. `app/services/duplicate_checker.py:32` raises `DuplicateCheckError`, and `app/routers/query.py:35` converts it to **HTTP 500**. Verified: `500 {"detail":"Duplicate lookup failed: no such table: audit_logs"}`. There is no degradation path anywhere.

Pinned as-is. STORY-004 must preserve the 500. **The AC and PRD Pattern 6 wording both need correcting.**

### Finding B — AC4's "distinguishably" does not hold today

`scripts/manage_users.py:37` prints one message for both constraint violations, so a duplicate `token_hash` on a *new* `user_id` reports `Error: a user with user_id 'bob' already exists.` — the wrong cause, and false, since `bob` was never created. `insert_user()`'s docstring says it deliberately leaves the exception uncaught because the caller "needs to tell those two cases apart"; the caller then does not.

Pinned as-is, in a test whose name says `is_not_distinguished`. **Making the two cases distinguishable is a behavior change and needs its own story** — the mutation check above confirms this test will flag it when someone does.

### Finding C — the local `.env` blocked the entire suite

The untracked `.env` carried three keys (`tursoDBToken`, `databaseTursoDB`, `databaseURL`) that `app/config.py`'s pydantic `Settings` rejects as `extra_forbidden`, so `from app.config import settings` raised and **no test could run from the repo root**. Removed in Task 0 after backing the file up. The Turso endpoint and token those keys held are still needed by STORY-005 and were preserved outside the repo — they belong in the `TURSO_AUTH_TOKEN` setting that story adds, not in ad-hoc keys. `Settings` was deliberately **not** loosened to `extra="ignore"`, which would mask exactly the misconfiguration PRD-007's startup guard is meant to catch.

## Deviations from Plan

| # | Deviation | Rationale |
|---|---|---|
| 1 | E2E checks 4 and 5 (`grep sqlite3` returns nothing; `sqlite3.` count in `test_db.py` unchanged at 7) were replaced with an AST check | The greps were too blunt: they match the word `sqlite3` in **docstring prose**, which every characterization test needs in order to name the arm it pins. All 5 added `sqlite3` mentions are prose. The AST check verifies the real invariant — `sqlite3` is neither imported nor referenced in code in any of the three newly-touched files, and `test_db.py`'s pre-existing code-level uses are untouched. |
| 2 | Task 4 drains `capsys` after the first `create-user` | The original test read `capsys` once, capturing **both** invocations, so the new "no credential leaked on failure" assertion would have tripped on the *first* create's token line. Draining scopes the assertion to the failing call. |
| 3 | Full suite is not 100% green | 7 pre-existing failures, identical to the clean-tree baseline, all from PRD-006's stale containment guard. Documented above rather than fixed — fixing is out of scope and needs a decision. |

## Acceptance Criteria

- [x] Missing `users` table → `find_user_by_token_hash()` returns `None`; endpoint resolves to **401, not 500** *(Tasks 1-2)*
- [x] Storage failure during the duplicate check is pinned — **amended per Finding A**: the verified behavior is `DuplicateCheckError` → HTTP 500, not a completed query *(Task 3)*
- [x] Existing `user_id` → CLI reports a duplicate-user error, not a traceback *(Task 4)*
- [x] Existing `token_hash` on a different `user_id` — **amended per Finding B**: pinned as *not* distinguishable, which is what the code does *(Task 5)*
- [x] All new tests pass with no production changes *(121 passed across the target suites; zero production files modified)*
- [x] Only files under `tests/` are modified *(`git diff main --stat -- . ':!.agents'` lists exactly the four test files)*
- [x] All tasks completed
- [x] No new test asserts on a driver exception type *(AST-verified)*
- [x] Follows existing fixture and assertion patterns; STORY-003's centralization not pre-empted
