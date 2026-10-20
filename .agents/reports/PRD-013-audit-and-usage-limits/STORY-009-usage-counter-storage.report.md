---
story: STORY-009
prd: PRD-013
plan: .agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-009-usage-counter-storage.plan.md
epic_branch: epic/PRD-013-audit-and-usage-limits
commit: 13f01f6
status: COMPLETE
completed: 2026-10-18
---

# Implementation Report — STORY-009: usage_daily table with atomic admit and charge statements; RETURNING verified

**Plan**: `.agents/plans/PRD-013-audit-and-usage-limits/completed/STORY-009-usage-counter-storage.plan.md`
**Epic Branch**: `epic/PRD-013-audit-and-usage-limits`
**Commit**: `13f01f6`

## Summary

The spike found that **`RETURNING` works on `libsql==0.1.11`**. The PRD Section 6.5 admit statement, run verbatim through the raw driver, returns the admission row on both the insert path and the conflict path. The row persists after commit. So `admit_usage` ships as **Path A**: one statement, one round trip. The upsert-plus-`SELECT` fallback was not needed.

`usage_daily` (PRD 6.5 DDL, composite primary key `(user_id, day)`) is created by CREATE alone, at the end of `init_db()`'s one bootstrap `_session()`. `admit_usage(user_id) -> UsageAdmission` and `charge_usage(user_id, day, input_tokens, output_tokens, unsplit_tokens) -> bool` were added to `app/db/database.py`. Each is one statement on the primary key, with `day` and the minute window computed only by the database. No limit is compared, and no pipeline code calls either function yet (STORY-010/011).

## The finding (AC 1)

**Environment.** `libsql==0.1.11` on CPython 3.11.17, from the venv at `C:\Users\tobip\.venvs\harness-ai`. The server was `harness-libsql-dev` (`ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb27…`) at `http://127.0.0.1:8080`. The probe used the raw driver (`libsql.connect`), never `app.db`'s wrappers. It ran against a scratch table `usage_daily_probe` with the PRD 6.5 DDL.

**Exact statement** (PRD 6.5 verbatim; only the table name is changed), bound with `("probe-user",)`:

```sql
INSERT INTO usage_daily_probe (user_id, day, requests, window_start, window_requests)
VALUES (?, date('now'), 1, strftime('%s','now') / 60, 1)
ON CONFLICT(user_id, day) DO UPDATE SET
    requests = requests + 1,
    window_requests = CASE WHEN window_start = excluded.window_start
                           THEN window_requests + 1 ELSE 1 END,
    window_start = excluded.window_start
RETURNING day, window_start, window_requests,
          input_tokens + output_tokens + unsplit_tokens AS tokens_today
```

**Run 1 output:**

```
libsql 0.1.11
--- 1. first admit (insert path)
description   = (('day', None, None, None, None, None, None), ('window_start', None, None, None, None, None, None), ('window_requests', None, None, None, None, None, None), ('tokens_today', None, None, None, None, None, None))
fetchall()    = [('2026-10-18', 29872699, 1, 0)]
rowcount      = 0
in_transaction= True
--- 2. second admit (conflict path)
description   = (('day', ...), ('window_start', ...), ('window_requests', ...), ('tokens_today', ...))
fetchall()    = [('2026-10-18', 29872699, 2, 0)]
rowcount      = 0
in_transaction= True
--- 3. fresh-client read-back
[('probe-user', '2026-10-18', 2, 0, 0, 0, 29872699, 2)]
--- 4. charge rowcount = 1
--- 4b. re-admit after charge
fetchall()    = [('2026-10-18', 29872699, 3, 150)]
rowcount      = 0
in_transaction= True
--- 5. dropped
```

**Run 2**, after `docker restart harness-libsql-dev`: identical, apart from the clock (`window_start` 29872700). The insert path gave `[('2026-10-18', 29872700, 1, 0)]`, the conflict path gave `[('2026-10-18', 29872700, 2, 0)]`, the fresh-client read-back gave `[('probe-user', '2026-10-18', 2, 0, 0, 0, 29872700, 2)]`, the charge reported `rowcount` 1, and the re-admit gave `tokens_today` 150.

**Conclusions:**

| Question | Answer |
|---|---|
| Do rows come back from `INSERT … ON CONFLICT … DO UPDATE … RETURNING`? | **Yes**, one row on both the insert and conflict paths |
| Is `cursor.description` populated for a `RETURNING` cursor? | **Yes**, all four names, so `_Row` reads them by name |
| Does the write persist after `commit()`? | **Yes**, a fresh client reads it back |
| Is `window_start` an integer? | **Yes** (`29872699`, not `'29872699'`). SQLite coerces `strftime`'s TEXT for the division |
| `rowcount` on a `RETURNING` statement? | **0**, on insert and update alike. New finding: nothing may branch on it. The plain `UPDATE` (the charge) reports 1 as STORY-001 found |
| Path taken | **Path A**, the single statement. The fallback was not implemented |

The probe was a throwaway script and is not committed. `tests/test_usage_storage.py::test_upsert_returning_yields_the_admission_row` pins the same behaviour through `get_connection()`, so a driver bump that breaks it fails CI. The finding is also recorded in the comment above `_ADMIT_USAGE_SQL`.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Spike: verify `RETURNING` (two runs, one after a restart) | throwaway probe, evidence above | ✅ |
| 2 | `CREATE_USAGE_DAILY_TABLE` and frozen `UsageAdmission` | `app/db/models.py` | ✅ |
| 3 | Table created in `init_db()`'s bootstrap `_session()`, plus a docstring paragraph | `app/db/database.py` | ✅ |
| 4 | `_ADMIT_USAGE_SQL`, `_CHARGE_USAGE_SQL`, `admit_usage`, `charge_usage`, plus the finding comment | `app/db/database.py` | ✅ |
| 5 | Tests | `tests/test_usage_storage.py` | ✅ |
| 6 | Regression and report | full suite, this file | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ |
| Frontend lint | N/A. The repo has no `frontend/` and no lint configuration; the Reflex UI was not touched |
| `tests/test_usage_storage.py` | ✅ 13 passed |
| `tests/test_db.py -k init_db` | ✅ 49 passed |
| Full suite `pytest tests/` | ✅ 3575 passed, 27 skipped (final run) |
| E2E | ✅ 3/3 |
| Readers of the new names (`grep` over `app chat_ui scripts`) | Only `database.py` and `models.py`; no pipeline caller |

**About the full-suite runs.** Three were needed:

1. **Run 1 (`-x`):** stopped on a setup **ERROR** in `tests/test_session_ownership.py::test_the_owners_own_writes_still_land`, after 3331 passed. The file passed 29/29 in isolation, and the test passed in both later full runs. Its traceback was lost to an output `tail`, so the cause is not recorded. I'm treating it as an intermittent fixture error against the shared dev server, not a regression from this story. Flagged here for STORY-018's regression sweep.
2. **Run 2:** one real failure caused by this story. `tests/test_two_instance_smoke.py::test_both_instances_boot_simultaneously_against_one_database` pins the exact list of tables, and `usage_daily` is now the fifth. Fixed (see Deviations).
3. **Run 3:** green.

## E2E

- [x] The probe ran twice against `harness-libsql-dev` (once after a restart), with identical findings (above).
- [x] `admit_usage('e2e')` → `UsageAdmission(day='2026-10-18', window_start=29872719, window_requests=1, tokens_today=0)`. Then `charge_usage('e2e', day, 1, 2, 3)` → `True`, and the re-admit → `window_requests=2, tokens_today=6`.
- [x] With `usage_daily` dropped from the dev DB, booting `uvicorn app.main:app` logged "Application startup complete" and `/health` returned `{"status":"ok"}` 200. The tables after boot were `audit_logs, chat_messages, chat_sessions, usage_daily, users`. The first boot attempt created the table but then stopped at the existing RBAC guard (`RbacNotBootstrappedError`), because the suite's reset had left the dev DB with no users. Creating one throwaway user (`e2e-s009`) on the local dev DB fixed that. Unrelated to this story.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/models.py` | UPDATE | +52 |
| `app/db/database.py` | UPDATE | +98 |
| `tests/test_usage_storage.py` | CREATE | +282 |
| `tests/test_two_instance_smoke.py` | UPDATE | +3/-1 |

## Deviations from Plan

1. **`tests/test_two_instance_smoke.py` was changed.** The plan's risk table said no test pinned the exact set of tables. That was wrong: the grep covered `test_db.py` only. The two-instance test asserts the boot schema list exactly, and it now includes `usage_daily`, with its comment extended. The suite stayed as strict as before.
2. **One extra test beyond the plan:** `test_init_db_creates_usage_daily_inside_the_one_bootstrap_session`. It proves the half of AC 2 that says "in the same `_session()` block" directly, by recording each connection's statements, rather than relying on the existing tests indirectly. Also added `test_admitted_row_persists_after_the_session`, the in-suite twin of the probe's fresh-client read-back.
3. **Path B tests were not written**, because Path A shipped. The plan made them conditional.
4. **New driver fact recorded:** `rowcount` is 0 on `RETURNING`. The plan didn't anticipate it, and it changes nothing here because `admit_usage` never read it. It is documented above `_ADMIT_USAGE_SQL` so STORY-010 doesn't rely on it.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_usage_storage.py` | `test_init_db_creates_usage_daily_with_its_columns`, `test_init_db_is_idempotent_for_usage_daily`, `test_init_db_adds_usage_daily_to_a_pre_usage_database`, `test_init_db_creates_usage_daily_inside_the_one_bootstrap_session`, `test_upsert_returning_yields_the_admission_row`, `test_admitted_row_persists_after_the_session`, `test_admit_usage_counts_three_attempts_in_one_window`, `test_admit_usage_resets_the_window_on_a_new_minute`, `test_admit_usage_is_per_user`, `test_admit_usage_on_a_missing_table_raises_missing_relation`, `test_charge_usage_accumulates_into_tokens_today`, `test_charge_usage_charges_the_admitted_day_not_today`, `test_charge_usage_without_a_row_returns_false_and_creates_none` |
| `tests/test_two_instance_smoke.py` | Pinned table list updated (no new case) |

## Acceptance Criteria

- [x] Given the pinned `libsql==0.1.11` against the local dev server, when `INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING` is executed, then the story report records whether rows come back, with the exact statement and output. **Rows come back (see "The finding"); no fallback was needed.**
- [x] Given a fresh database, when `init_db()` runs, then `usage_daily` exists with primary key `(user_id, day)` and the columns in PRD Section 6.5, created in the same `_session()` block as the other tables.
- [x] Given a user with no row today, when `admit_usage(user_id)` is called three times within one minute, then it returns `window_requests` 1, 2, 3, `tokens_today` 0, and a `day` and `window_start` taken from the database clock; `requests` on the row is 3.
- [x] Given a row whose `window_start` is an earlier minute, when `admit_usage` is called, then `window_requests` is 1 and `requests` keeps increasing.
- [x] Given `charge_usage(user_id, day, input_tokens=120, output_tokens=30, unsplit_tokens=0)` and then `charge_usage(..., 0, 0, 150)`, when `admit_usage` is called next, then `tokens_today` is 300.
- [x] All tasks completed
- [x] Full `pytest tests/` passes
- [x] Follows existing patterns
