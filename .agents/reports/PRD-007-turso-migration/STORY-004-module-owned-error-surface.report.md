---
story: STORY-004
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-004-module-owned-error-surface.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: 2961f33
status: COMPLETE
completed: 2026-09-01
---

# Implementation Report — STORY-004: app/db/errors.py, a module-owned exception surface

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-004-module-owned-error-surface.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `2961f33`

## Summary

`app/db/errors.py` now declares the exception surface `app/db/` raises: `StorageError`, with
`MissingRelationError` and `IntegrityError` beneath it. One `contextmanager` in
`app/db/database.py` — `_translated()` — is the only code in the repository that names a driver
exception class; all 21 connection blocks go through `_session()`, which wraps
`get_connection()` while preserving sqlite3's commit-on-success, rollback-on-exception,
do-not-close semantics. The two modules that imported `sqlite3` solely to name an `except` clause
no longer do. The change ships **on `sqlite3`**, verified against the STORY-002 characterization
baseline, so [[STORY-006]] swaps the driver against a green measurement rather than a remembered one.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 0 | Record the baseline (`7 failed, 1033 passed`) | — | ✅ |
| 1 | Create the exception surface | `app/db/errors.py` | ✅ |
| 2 | Add `_translated()` / `_session()` / `_constraint_of()` | `app/db/database.py` | ✅ |
| 3 | Route the 21 connection blocks through `_session()` | `app/db/database.py` | ✅ |
| 4 | Translate the 401 arm, narrowly | `app/db/database.py` | ✅ |
| 5 | Catch `StorageError` instead of `sqlite3.Error` | `app/services/duplicate_checker.py` | ✅ |
| 6 | Catch `IntegrityError` instead of `sqlite3.IntegrityError` | `scripts/manage_users.py` | ✅ |
| 7 | Update `insert_user()`'s docstring to name the new type | `app/db/database.py` | ✅ |
| 8 | Retarget the two driver-typed assertions, add `.constraint` checks | `tests/test_db.py` | ✅ |
| 9 | Prove the decoupling (greps + full suite) | — | ✅ |
| 10 | Commit on the epic branch | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ `Harness IA` |
| Frontend lint | n/a — no frontend file touched |
| Tests | ✅ 1034 passed, 8 failed (7 pre-existing + 1 superseded guard, below) |
| E2E | ✅ 5/5 |
| AC6 — `grep -rn "import sqlite3" app/ chat_ui/ scripts/` | ✅ one hit, `app/db/database.py:2` |
| AC7 — characterization tests unmodified | ✅ 4/4 pass; `git diff` empty on both files |

### E2E checklist

- [x] Missing `users` table → `find_user_by_token_hash('x')` prints `None`, not a traceback
- [x] `create-user --user-id ana` twice → second exits `1`, `Error: a user with user_id 'ana' already exists.` on stderr, stdout empty
- [x] Dropped `audit_logs` → `POST /query` still 500s with `Duplicate lookup failed`, no crash
      (`test_duplicate_check_storage_failure_returns_500`, unmodified)
- [x] `app/db/errors.py` imports only `typing` — verified by AST, not by eye
- [x] App boots — `from app.main import app` → `Harness IA`

### Suite accounting

| | Baseline (`a8f75c5`) | After |
|---|---|---|
| passed | 1033 | 1034 |
| failed | 7 | 8 |

`1033 + 2 new tests − 1 guard that flipped = 1034`. Every delta is accounted for.

**The eighth failure is a superseded containment guard, not a regression.**
`tests/test_pii_dedup_isolation.py::test_dedup_and_pattern_sources_unmodified_on_this_branch[app/services/duplicate_checker.py]`
is a PRD-003 pin — *"RF-6: this epic must not touch either module"* — asserting that file is
byte-unchanged since `merge-base main HEAD`. PRD-007 Section 6 Pattern 6, Section 7.2, and this
story's AC3 all require exactly the two-line edit that trips it. Left red deliberately, on the
user's decision, matching how PRD-006's `tests/test_untouched_app.py` guards have been left across
STORY-002 and STORY-003: a guard is not edited to green the change it is guarding against. RF-6's
*behavioral* pins in the same file (no redaction dependency, hash-before-redaction) all still pass.
Whoever retires PRD-006's guards should retire this parametrization with them.

The other seven are unchanged from the STORY-003 baseline: one environmental Reflex-annotation
failure, six from PRD-006's containment guard measuring `git diff` against pinned baseline `d3e6279`.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/errors.py` | CREATE | +71 |
| `app/db/database.py` | UPDATE | +88/−31 |
| `app/services/duplicate_checker.py` | UPDATE | +2/−2 |
| `scripts/manage_users.py` | UPDATE | +5/−2 |
| `tests/test_db.py` | UPDATE | +68/−2 |

## Deviations from Plan

1. **Task 7's literal validation was wrong.** The plan asserted
   `grep -n "sqlite3.IntegrityError" app/db/database.py` returns nothing. It cannot: the
   translation seam written in Task 2 must name that class — that is the entire design. The two
   remaining hits are `app/db/database.py:44` (`_constraint_of`'s annotation) and `:58`
   (`_translated`'s catch), both inside the seam. The check applied instead: no occurrence in any
   docstring or public function, which holds.
2. **Two tests added beyond the plan.** The plan noted that the Design Note 3 narrowing was
   invisible to the suite and that AC2 had no direct test; `/implement`'s "error and edge cases
   need tests" makes closing both mandatory. Added to `tests/test_db.py`:
   `test_no_driver_exception_escapes_app_db` and
   `test_find_user_by_token_hash_raises_when_the_failure_is_not_a_missing_table`.
3. **An unanticipated red** — the RF-6 guard above. Resolution decided by the user; recorded rather
   than papered over.
4. **Task 0's clean-tree precondition was not literally met**: the working tree carried this
   story's own plan file and the frontmatter/index edits from `/plan`. Nothing unrelated.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_no_driver_exception_escapes_app_db` — drops `audit_logs`, asserts `count_audit_logs()` raises `MissingRelationError` carrying `relation == "audit_logs"`, that it *is* a `StorageError` (the subclassing duplicate_checker depends on) and is *not* a `sqlite3.Error` (AC2) |
| `tests/test_db.py` | `test_find_user_by_token_hash_raises_when_the_failure_is_not_a_missing_table` — a connection proxy raising `OperationalError("database is locked")` proves the 401 arm no longer swallows a real outage (Design Note 3) |
| `tests/test_db.py` | `test_insert_user_rejects_duplicate_user_id` — retargeted to the module-owned type, extended with `constraint == "users.user_id"` (AC1) |
| `tests/test_db.py` | `test_insert_user_rejects_duplicate_token_hash` — retargeted, extended with `constraint == "users.token_hash"` (AC1) |

## Acceptance Criteria

- [x] **AC1** — `app/db/errors.py` covers the three conditions the codebase distinguishes, and
      `IntegrityError.constraint` tells a duplicate `user_id` from a duplicate `token_hash`
      (asserted in both `insert_user` tests).
- [x] **AC2** — every driver exception escaping a query is translated at the boundary;
      `test_no_driver_exception_escapes_app_db` asserts the negative directly.
- [x] **AC3** — `app/services/duplicate_checker.py` no longer imports `sqlite3` and catches
      `StorageError`; the `DuplicateCheckError` message is unchanged, and `POST /query` still 500s
      on a storage failure.
- [~] **AC4** — `scripts/manage_users.py` no longer imports `sqlite3` and catches the module-owned
      integrity error. **Partially met, by design and by explicit user decision.** The two cases are
      distinguishable *through the exception* (`.constraint`), but the CLI still prints one message
      for both: AC7 and
      `tests/test_manage_users_cli.py::test_create_user_duplicate_token_hash_is_not_distinguished_from_duplicate_user_id`
      pin that output, and that test's own docstring rules that changing it "is a behavior change
      and belongs in its own story". **Follow-up owed:** a story making the CLI branch on
      `IntegrityError.constraint`, which will rewrite that characterization test on purpose.
- [x] **AC5** — a database with no `users` table still returns `None` — 401, not 500 — now via
      `MissingRelationError`.
- [x] **AC6** — the only `import sqlite3` under `app/`, `chat_ui/`, `scripts/` is
      `app/db/database.py:2`.
- [x] **AC7** — all four STORY-002 characterization tests pass **unmodified**;
      `git diff` on `tests/test_query_router.py` and `tests/test_manage_users_cli.py` is empty, and
      `tests/test_db.py`'s characterization test was not among the lines touched.
- [x] All tasks completed
- [x] Backend imports without error
- [x] Follows existing patterns (`app/services/authz.py:52-58`; per-module error ownership, no
      re-export through `app/db/__init__.py`)

## Behavior Change to Carry Forward

`find_user_by_token_hash()`'s catch is now narrow. Before: any `sqlite3.OperationalError` — a
locked database, an unreadable file, a disk error — resolved as "no match" and produced a 401.
After: only a missing `users` table does; everything else raises `StorageError` and surfaces as a
500. This is what the story's Technical Notes directed ("catching more than the missing-relation
case here would turn a real storage outage into a silent 401") and was confirmed with the user
before implementation. It is now covered by
`test_find_user_by_token_hash_raises_when_the_failure_is_not_a_missing_table`.

**Relevant to [[STORY-006]]:** `_translated()` identifies both conditions by parsing the driver's
message (`no such table: (\w+)`, `constraint failed: ([\w.]+)`). `sqlite_errorname` was rejected —
it is CPython-only and collapses "no such table" and "duplicate column name" into the same
`SQLITE_ERROR`. libSQL is SQLite-derived and is expected to emit the same text, but STORY-006 must
re-verify both patterns against the real client. That is why the parsing lives in one function.
