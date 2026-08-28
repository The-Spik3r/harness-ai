---
story: STORY-002
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-002-users-table-schema.plan.md
epic_branch: epic/PRD-005-rbac
commit: 903dee8
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-002: users table schema and CRUD helpers

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-002-users-table-schema.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `903dee8`

## Summary

Identity now has a storage home. A `users` table lives in the same SQLite file as `audit_logs` — no second service, no ORM, no new dependency — alongside eight helpers written to the exact convention every existing helper in `app/db/database.py` follows.

The layer is **storage only**. It holds an opaque `token_hash` and never generates, hashes, or compares a credential; `secrets` and `hashlib` stay in STORY-003's `app/services/identity.py`, so the database layer cannot become a second place that decides what a valid credential is. A `grep` for credential primitives under `app/db/` returns nothing, and that is asserted as an acceptance criterion.

The implementation matched the plan task-for-task. The one substantive change during execution was **more tests than the plan's summary counted** — 23 rather than 18, which is what the plan's own task lists actually enumerated (Deviation 2).

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Verify baseline (251 passed, 27 in `test_db.py`, no `users` table) | — | ✅ |
| 2 | `CREATE_USERS_TABLE`, `CREATE_USERS_TOKEN_HASH_INDEX`, `User` dataclass | `app/db/models.py` | ✅ |
| 3 | `init_db()` creates the table + index; `_TIMESTAMP_FORMAT` added | `app/db/database.py` | ✅ |
| 4 | `_row_to_user`, `get_user`, `find_user_by_token_hash`, `list_users`, `count_active_users` | `app/db/database.py` | ✅ |
| 5 | `insert_user`, `deactivate_user`, `set_user_token_hash` | `app/db/database.py` | ✅ |
| 6 | Tests — schema shape, index, idempotence, legacy-file path (AC1) | `tests/test_db.py` | ✅ |
| 7 | Tests — token-hash lookup and the active filter (AC2) | `tests/test_db.py` | ✅ |
| 8 | Tests — deactivation retains the row (AC3), active counting (AC4) | `tests/test_db.py` | ✅ |
| 9 | Test — `EXPLAIN QUERY PLAN` proves no table scan (AC5) | `tests/test_db.py` | ✅ |
| 10 | Tests — round trip, constraints, rotation, timestamp default | `tests/test_db.py` | ✅ |
| 11 | Full-suite regression + diff gate | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A — no npm frontend; the UI is Reflex (Python) and is untouched |
| Tests — `tests/test_db.py` | ✅ 50 passed (27 pre-existing + 23 new) |
| Tests — full suite | ✅ 274 passed (was 251) |
| Existing suites unmodified (`query_router`, `admin_auth`, `chat_state`) | ✅ 71 passed |
| Diff is purely additive | ✅ only 2 deletions, both import lines expanded into blocks |
| No credential primitive under `app/db/` | ✅ `grep` for `sha256`/`token_urlsafe`/`compare_digest` returns nothing |
| E2E | ✅ 11/11 |

### E2E detail

| # | Check | Result |
|---|-------|--------|
| 1 | `pytest tests/test_db.py -v` | ✅ 50 passed |
| 2 | `pytest -q` full suite | ✅ 274 passed |
| 3 | `git diff --name-only` — only the three intended code files | ✅ |
| 4 | No credential primitives in `app/db/` | ✅ clean |
| 5 | Real on-disk pre-RBAC file (14-col `audit_logs`, no `users`) migrated twice | ✅ both tables present, `1 0`, audit table also at 17 cols |
| 6 | CRUD lifecycle on a real file — create, resolve, rotate, revoke | ✅ `user 2` / `True None ana` / `True None False 1 2`, exactly as predicted |
| 7 | `uvicorn app.main:app` starts | ✅ "Application startup complete" |
| 8 | `GET /health` | ✅ `{"status":"ok"}` |
| 9 | Repo-root `harness_ai.db` schema | ✅ `audit_logs`, `users`, `idx_users_token_hash`; audit still 17 cols, rows preserved |
| 10 | Reflex ingress — `import chat_ui.chat_ui` + 4 further `init_db()` calls | ✅ no duplicate table/index error |
| 11 | Existing behavior suites unmodified | ✅ 71 passed |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +34/-0 |
| `app/db/database.py` | UPDATE | +111/-1 (the one deletion is the import line, expanded into a block) |
| `tests/test_db.py` | UPDATE | +291/-1 (same) |
| `.agents/plans/PRD-005-rbac/completed/…plan.md` | CREATE | +678 |

## Deviations from Plan

1. **Task 1's "no `users` reference" check needed interpretation.** `grep -c "users" app/db/database.py` returns `2`, not `0` — `count_unique_users()` (`:161`) and `top_users()` (`:192`), both aggregates over `audit_logs.user_id`. Neither is a `users` *table* reference, so the baseline assumption held. The plan's wording was imprecise, not wrong.

2. **23 tests written, not the 18 the plan's Summary stated.** The plan's Summary undercounted its own task lists, which enumerate 23 test names across Tasks 6–10 (5 + 4 + 5 + 1 + 8). Every named test was written; nothing extra was invented and nothing was dropped. The dependent figures in the plan are correspondingly off by five: `tests/test_db.py` finished at **50**, not 45, and the full suite at **274**, not 269. Downstream stories should use 50/274 as the new baseline.

3. **`sqlite_sequence` appears in the E2E table listing.** SQLite auto-creates it for the `AUTOINCREMENT` on `audit_logs.id`; it is pre-existing and unrelated to this story. The corresponding test asserts `{"audit_logs", "users"} <= tables` (subset, not equality), so it is unaffected.

4. **A transient `SyntaxWarning` during test authoring.** The heredoc script used to append the tests emitted `SyntaxWarning: invalid escape sequence '\d'` from its own string literal. The written file is correct — the regex landed as `r"\d{4}-..."` at `tests/test_db.py:911` — and `py_compile` with `-W error::SyntaxWarning` confirms the file compiles clean. No fix needed; noted so it is not mistaken for a latent issue.

5. **Working tree was not clean at Phase 2, and this was not treated as a stop.** `README.md` carries an unstaged 54-line roadmap edit that STORY-001's report (Deviation 4) records as deliberately left for STORY-018. Rather than halt, it was simply never staged — `git status` after the commit still shows it modified. The commit contains exactly four files.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_init_db_creates_users_table` — the table exists after `init_db()` (AC1) |
| `tests/test_db.py` | `test_users_schema_matches_expected_columns` — exact 5-column set; `notnull == 1` on **all five** (the `user_id NOT NULL` guard); `active` defaults to `1`; `user_id` is the sole PK (AC1) |
| `tests/test_db.py` | `test_init_db_creates_users_token_hash_index` — `idx_users_token_hash` exists (AC5) |
| `tests/test_db.py` | `test_init_db_is_idempotent_for_users_table` — three consecutive `init_db()` calls, the guarantee Reflex needs on every hot reload |
| `tests/test_db.py` | `test_init_db_adds_users_table_to_pre_rbac_database` — a legacy `audit_logs`-only file gains `users`, and its audit row survives |
| `tests/test_db.py` | `test_find_user_by_token_hash_returns_active_user` — resolves an active user with all fields intact (AC2) |
| `tests/test_db.py` | `test_find_user_by_token_hash_ignores_deactivated_user` — revoked credential stops resolving **while** `get_user()` still returns the row (AC2 + AC3 in one) |
| `tests/test_db.py` | `test_find_user_by_token_hash_unknown_returns_none` (AC2) |
| `tests/test_db.py` | `test_find_user_by_token_hash_is_exact_not_prefix` — guards against the `=` becoming a `LIKE`, which would let a truncated digest authenticate |
| `tests/test_db.py` | `test_deactivate_user_retains_the_row` — `active` flips, `created_at` and `role` survive, row is not deleted (AC3) |
| `tests/test_db.py` | `test_deactivate_user_unknown_returns_false` — the CLI's typo signal |
| `tests/test_db.py` | `test_deactivate_user_is_idempotent` — documents that `rowcount` counts matched, not changed, rows |
| `tests/test_db.py` | `test_count_active_users_empty_returns_zero` (AC4) |
| `tests/test_db.py` | `test_count_active_users_excludes_deactivated` — 2 active of 3 rows retained (AC4) |
| `tests/test_db.py` | `test_find_user_by_token_hash_uses_the_index` — `EXPLAIN QUERY PLAN` names the index and contains no `SCAN` (AC5) |
| `tests/test_db.py` | `test_insert_and_read_user_round_trip` — every field, with `is True`/`is False` on `active` |
| `tests/test_db.py` | `test_insert_user_defaults_created_at_to_utc_now` — matches `%Y-%m-%dT%H:%M:%SZ`, the `audit_logger.py` format |
| `tests/test_db.py` | `test_insert_user_rejects_duplicate_user_id` — `IntegrityError` |
| `tests/test_db.py` | `test_insert_user_rejects_duplicate_token_hash` — `IntegrityError`; fails if the index is ever downgraded from `UNIQUE` |
| `tests/test_db.py` | `test_get_user_missing_returns_none` |
| `tests/test_db.py` | `test_list_users_includes_deactivated` |
| `tests/test_db.py` | `test_set_user_token_hash_rotates_the_credential` — old hash stops resolving, new one resolves to the same user |
| `tests/test_db.py` | `test_set_user_token_hash_unknown_returns_false` |

## Acceptance Criteria

- [x] Given a fresh database, when `init_db()` runs, then `users(user_id TEXT PRIMARY KEY, role TEXT NOT NULL, token_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)` exists — **satisfied as a strengthening superset**: `user_id` also declares `NOT NULL`, because outside `INTEGER PRIMARY KEY` SQLite accepts NULL in a PRIMARY KEY column, and more than one row of them (verified empirically). Every constraint the AC names is present.
- [x] Given a `token_hash`, when `find_user_by_token_hash()` is called, then the matching **active** user is returned and a deactivated one is not — filtered in SQL, so an inactive `User` never reaches a caller
- [x] Given a user id, when `deactivate_user()` is called, then `active` becomes `0` and the row is retained — revocation is not deletion; there is deliberately no `delete_user`
- [x] Given an empty table, when `count_active_users()` is called, then it returns `0`
- [x] Given an index on `token_hash`, when a lookup runs, then it does not table-scan — satisfied by a `UNIQUE` index, proven via `EXPLAIN QUERY PLAN`
- [x] All tasks completed
- [x] Backend server starts without error
- [x] Full pytest suite green — 50 in `tests/test_db.py`, 274 overall
- [x] No credential primitive (`sha256`, `token_urlsafe`, `compare_digest`) appears anywhere under `app/db/`
- [x] Follows existing patterns

## Notes for downstream stories

- **New test baseline**: `tests/test_db.py` is at **50**, the full suite at **274**. The plan's 45/269 figures were derived from its undercounted summary (Deviation 2).
- **STORY-003** calls `find_user_by_token_hash(hashlib.sha256(token.encode()).hexdigest())` and receives an active `User` or `None`. `None` covers both "unknown" and "revoked" deliberately — PRD Section 9 maps both to `401`. Build `Identity` *from* the returned `User`; do not let `User` leak into the pipeline as the identity type.
- **STORY-004** has a helper per subcommand: `create-user` → `insert_user` (catch `sqlite3.IntegrityError`, which distinguishes a duplicate `user_id` from a duplicate `token_hash` by message), `list` → `list_users`, `deactivate` → `deactivate_user` (its `False` is the "no such user" exit code), `issue-token` → `set_user_token_hash`. The CLI generates and prints the plaintext token; only the digest reaches the DB layer.
- **STORY-016** uses `count_active_users() == 0`. It counts *active* users, so a deployment whose only user was revoked correctly trips the guard.
- **STORY-009** is unaffected: `_add_missing_columns` remains `audit_logs`-specific and `test_schema_has_no_ip_or_location_column` still asserts on `PRAGMA table_info(audit_logs)`, green at 17 names. STORY-009 still owes it the extension to 19.
- **Still open, still out of scope**: `get_connection()` commits but never closes, so every helper in the module leaks a connection (STORY-001 report, Design Note 8a). The new helpers follow the same shape on purpose rather than diverging mid-module. Worth a dedicated cleanup story.
