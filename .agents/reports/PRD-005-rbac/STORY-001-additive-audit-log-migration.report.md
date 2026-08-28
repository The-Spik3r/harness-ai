---
story: STORY-001
prd: PRD-005
plan: .agents/plans/PRD-005-rbac/completed/STORY-001-additive-audit-log-migration.plan.md
epic_branch: epic/PRD-005-rbac
commit: 936cff8
status: COMPLETE
completed: 2026-08-28
---

# Implementation Report — STORY-001: Additive schema-migration mechanism for audit_logs

**Plan**: `.agents/plans/PRD-005-rbac/completed/STORY-001-additive-audit-log-migration.plan.md`
**Epic Branch**: `epic/PRD-005-rbac`
**Commit**: `936cff8`

## Summary

The migration mechanism this story specifies already existed on `main`: `AUDIT_LOGS_ADDED_COLUMNS` and `_add_missing_columns(conn)` shipped in commit `60835dc`, which landed on the PRD-004 epic and merged in `66a2ba5` — *after* the PRD-005 PRD was authored. That is why PRD Risk 4 and the story's Technical Notes both describe them as absent, and why AC5 says "given the mapping ships empty" when it ships with three PII entries.

The story was therefore executed as a **verification and hardening** story rather than an implementation one. Nothing was re-implemented and the mapping was **not** emptied — emptying it would have un-shipped PRD-003's migration and broken every deployment upgrading from a pre-PII database. Instead, the four acceptance criteria that had no test behind them were given one, pinning the contract STORY-009 is about to depend on. `app/db/database.py` is byte-identical to `main`; the only production edit is a comment.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Verify mechanism present, baseline green (23 passed) | — | ✅ |
| 2 | DDL-contract guard test (AC3) | `tests/test_db.py` | ✅ |
| 3 | Synthetic-column proof, mechanism-generic (AC5) | `tests/test_db.py` | ✅ |
| 4 | No-`ALTER`-on-current-schema trace test (AC2) | `tests/test_db.py` | ✅ |
| 5 | Helper extraction + repeated-call idempotence (AC4) | `tests/test_db.py` | ✅ |
| 6 | Generalize `AUDIT_LOGS_ADDED_COLUMNS` comment | `app/db/models.py` | ✅ |
| 7 | Full-suite regression + diff gate | — | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A — no npm frontend; the UI is Reflex (Python) |
| Tests — `tests/test_db.py` | ✅ 27 passed (23 pre-existing + 4 new) |
| Tests — full suite | ✅ 251 passed |
| Guard non-vacuity (mutation check) | ✅ rejects both `NOT NULL` without `DEFAULT` and `DEFAULT NULL` |
| `app/db/database.py` unchanged | ✅ empty diff |
| E2E | ✅ 8/8 |

### E2E detail

| # | Check | Result |
|---|-------|--------|
| 1 | `pytest tests/test_db.py` | ✅ 27 passed |
| 2 | `pytest` full suite | ✅ 251 passed |
| 3 | Only the two intended code files changed | ✅ |
| 4 | Real on-disk pre-PII file migrated twice | ✅ 17 distinct columns, row preserved |
| 5 | `uvicorn app.main:app` starts | ✅ "Application startup complete" |
| 6 | `GET /health` | ✅ `{"status":"ok"}` |
| 7 | `harness_ai.db` schema | ✅ 17 columns, no duplicates |
| 8 | Reflex ingress repeated `init_db()` | ✅ no `duplicate column name` |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +8/-5 (comment only) |
| `tests/test_db.py` | UPDATE | +111/-7 |
| `.agents/plans/PRD-005-rbac/completed/…plan.md` | CREATE | +479 |

## Deviations from Plan

1. **Import placement (cosmetic).** The plan put `from app.db import database` *below* the `from app.db.database import (...)` block; it was placed *above* instead, which is the correct isort ordering. No functional difference.
2. **E2E step 8 adapted.** The plan called for `cd chat_ui && reflex run`. A full Reflex dev server needs a Node frontend build and is interactive, so the guarantee was exercised directly instead: `import chat_ui.chat_ui` (which runs the module-level `init_db()` at `chat_ui/chat_ui/chat_ui.py:22`) followed by four further `init_db()` calls simulating hot reloads. This tests exactly the property AC4 protects — repeated migration through the real chat-UI entry point — without the build. Result: 17 distinct columns, no error.
3. **Extra verification not in the plan.** A mutation check was added to prove the AC3 guard is not vacuous, injecting `INTEGER NOT NULL` and `INTEGER NOT NULL DEFAULT NULL` and confirming each is rejected with a column-naming message. A guard that cannot fail is worthless; this proves it can.
4. **Commit structure.** The working tree already held the user's pre-staged PRD-005 planning docs and a modified `README.md`. An initial commit swept all of them in; it was reset (unpushed) and rebuilt as two commits — `7d705e5 docs(PRD-005)` for the PRD/story scaffolding, `936cff8` for this story's three files. `README.md` was deliberately left modified and **unstaged**: its roadmap expansion is STORY-018's territory, not STORY-001's.
5. **Design Note 8a confirmed empirically.** The E2E probe could not delete its own scratch database on Windows because `get_connection()` never closes connections — `sqlite3`'s context manager commits but does not close. Pre-existing, module-wide, out of scope here, and worth a dedicated cleanup story.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_added_columns_declaring_not_null_also_declare_a_default` — every `NOT NULL` entry carries a non-NULL `DEFAULT` (AC3) |
| `tests/test_db.py` | `test_add_missing_columns_applies_any_declared_column` — a synthetic entry is applied and the pre-existing row takes its declared default `7` (AC5) |
| `tests/test_db.py` | `test_init_db_issues_no_alter_when_schema_is_current` — `set_trace_callback` proves zero `ALTER` on a current schema (AC2) |
| `tests/test_db.py` | `test_init_db_migration_is_idempotent_across_repeated_calls` — three consecutive `init_db()` calls on a pre-PII file (AC4) |
| `tests/test_db.py` | `_create_pre_pii_database()` helper extracted from the existing migration test and reused; that test's docstring and every assertion are byte-for-byte unchanged |

## Acceptance Criteria

- [x] Given a database whose `audit_logs` table predates a column listed in `AUDIT_LOGS_ADDED_COLUMNS`, when `init_db()` runs, then the column is added via `ALTER TABLE ... ADD COLUMN` and existing rows take its default — pre-satisfied by `test_init_db_migrates_pre_pii_database`, re-proven generically by the synthetic-column test
- [x] Given a database already at the current schema, when `init_db()` runs, then no `ALTER` is issued and the call is a no-op
- [x] Given an entry declaring `NOT NULL`, when it is applied, then it also declares a non-NULL `DEFAULT`
- [x] Given `init_db()` is called repeatedly, when it runs, then it stays idempotent
- [x] Given the mapping ships empty, when the suite runs, then a fixture database built from the pre-migration schema proves a synthetic column is added and existing rows survive — **satisfied in intent, not letter**: the mapping does not ship empty and was not emptied; a synthetic entry is injected at test time so the proof is about the mechanism rather than today's contents, and survives STORY-009 adding real columns
- [x] All tasks completed
- [x] Backend server starts without error
- [x] Full pytest suite green (27 in `tests/test_db.py`, 251 overall)
- [x] `app/db/database.py` unchanged — the mechanism was verified, not rewritten
- [x] Follows existing patterns

## Notes for downstream stories

- **STORY-009** must extend `test_schema_has_no_ip_or_location_column`'s hardcoded `expected` set from 17 to 19 names when it adds `role` and `denied_permission`. That test asserts set equality, so any schema addition fails it by design — expected maintenance, not a regression. Both new names were checked against its `ip`/`location` substring assertion and neither contains either substring, so that assertion stays as-is. Both columns are nullable `TEXT`, so the new AC3 guard passes trivially.
- **STORY-002** needs nothing from this mechanism: `users` is a new table with no legacy shape to migrate. `_add_missing_columns` was deliberately left `audit_logs`-specific.
