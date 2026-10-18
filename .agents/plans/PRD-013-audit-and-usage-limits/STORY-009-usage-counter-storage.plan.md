---
story: STORY-009
prd: PRD-013
slug: usage-counter-storage
title: "usage_daily table with atomic admit and charge statements; RETURNING verified"
type: NEW_CAPABILITY   # story type: spike -- the first task is a finding that picks the implementation
complexity: MEDIUM
epic_branch: epic/PRD-013-audit-and-usage-limits   # all stories commit here, no per-story branch
created: 2026-10-18
---

# Plan: usage_daily table with atomic admit and charge statements; RETURNING verified

## Summary

First, find out whether `libsql==0.1.11` returns rows from `INSERT … ON CONFLICT … DO UPDATE … RETURNING` against the local dev server. Run the PRD Section 6.5 statement verbatim through the raw driver and paste the exact statement and output into the story report. That finding picks one of two `admit_usage` bodies: **Path A** is the single `RETURNING` statement, and **Path B** is the same upsert plus a `SELECT` in one `_session()` transaction. Then add `CREATE_USAGE_DAILY_TABLE` and a frozen `UsageAdmission` dataclass to `app/db/models.py`. Create the table in `init_db()`'s single `_session()` block. Add `admit_usage(user_id) -> UsageAdmission` and `charge_usage(user_id, day, input_tokens, output_tokens, unsplit_tokens)` to `app/db/database.py`, each one statement on the primary key, with `day` and the minute window computed only by the database. No limit is compared here; that is STORY-010.

## User Story

As a platform operator
I want usage counted in one shared row per user per day by single atomic statements
So that limits hold across instances and cost one round trip to check

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-009-usage-counter-storage.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (sections 6.5 / D3, 7 F8, 8, 14 Risk 2)
- Driver evidence: `.agents/reports/PRD-007-turso-migration/STORY-001-libsql-driver-spike.report.md` and the comment above `_SUMMARY_SQL` (`app/db/database.py:1250-1281`)

## Metadata

| Field | Value |
|-------|-------|
| Type | spike (finding first), then NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/db/models.py`, `app/db/database.py`, tests |
| Story | STORY-009 |
| PRD | PRD-013 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch) |
| Depends on | none |
| Blocks | STORY-010 (`usage_limits.admit/charge` wrap these), STORY-016 (usage view reads `usage_daily`) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`. This story has no UI surface (the story's Technical Notes say the same) | — |

---

## Patterns to Follow

### Table DDL constant with a rationale comment
```python
# SOURCE: app/db/models.py:150-165  (CREATE_USERS_TABLE: NOT NULL spelled out on PK columns)
CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY NOT NULL,
    ...
)
"""
```
The PRD 6.5 DDL declares `user_id TEXT NOT NULL, day TEXT NOT NULL` with a composite `PRIMARY KEY (user_id, day)`. That already covers the users-table comment's point that, outside `INTEGER PRIMARY KEY`, SQLite lets a PK column hold NULL. Keep both `NOT NULL`s and say so in the comment.

### Schema built in the one bootstrap `_session()`
```python
# SOURCE: app/db/database.py:706-720
    check_database_reachable()
    with _session() as conn:
        conn.execute(CREATE_AUDIT_LOGS_TABLE)
        ...
        conn.execute(CREATE_CHAT_MESSAGES_TABLE)
        _add_missing_columns(conn, "chat_messages", CHAT_MESSAGES_ADDED_COLUMNS)
        conn.execute(CREATE_CHAT_MESSAGES_SESSION_INDEX)
```
`usage_daily` is new, so it gets no added-columns mapping. Tables arrive through CREATE and columns through ALTER (`tests/test_db.py:2030-2033`). Append one `conn.execute(CREATE_USAGE_DAILY_TABLE)` at the end of the block.

### One-statement write returning a bool from `rowcount`
```python
# SOURCE: app/db/database.py:1632-1637  (set_user_limits)
    with _session() as conn:
        cursor = conn.execute(
            f"UPDATE users SET {set_clause} WHERE user_id = ?",
            (*(value for _, value in assignments), user_id),
        )
        return cursor.rowcount == 1
```
`rowcount` is verified: `1` on a hit, `0` on a miss, never `-1` (PRD-007 STORY-001 behaviour 4).

### Frozen dataclass
```python
# SOURCE: app/db/database.py:1158-1159  (SummarySnapshot)
@dataclass(frozen=True)
class SummarySnapshot:
```
Put `UsageAdmission` in `app/db/models.py`, as the story asks, beside `User`. `models.py` already imports `dataclass`.

### Tests
```python
# SOURCE: tests/test_db.py:3551-3586  (set_user_limits unit tests on temp_db)
def test_set_user_limits_unknown_user_returns_false_and_writes_nothing(temp_db):
    assert set_user_limits("ghost", token_budget_daily=5) is False
    assert get_user("ghost") is None

# SOURCE: tests/test_db.py:2454-2460  (table exists via sqlite_master)
# SOURCE: tests/test_db.py:3414, 3514, 3639  ("probe plus the one bootstrap _session()" assertions)
```

| Category | File:Lines | Pattern |
|----------|------------|---------|
| SCHEMAS | `app/db/models.py:150-165, 196-207` | `CREATE_* = """CREATE TABLE IF NOT EXISTS …"""` with a comment explaining each non-obvious choice |
| MIGRATION | `app/db/database.py:637-720` | Every table is created in `init_db()`'s single `_session()` block; the docstring gains one paragraph per PRD change |
| NAMING | `app/db/database.py:1604-1637` | `verb_noun(user_id, …)` in `database.py`; SQL constants as module-level `_UPPER_SQL` strings with a comment |
| ERRORS | `app/db/database.py:584-634` | No local `try`: `_session()`/`_translated()` turns driver errors into `StorageError`/`MissingRelationError`. STORY-010 maps them to fail-closed or fail-open (D9) |
| ROW ACCESS | `app/db/database.py:194-301` | `_Row` gives named access through `cursor.description`. The probe must show `description` is populated for a `RETURNING` cursor |
| TESTS | `tests/conftest.py:263-283`, `tests/test_db.py` | `temp_db` (initialized); autouse `_reset_database()` drops every table, so `usage_daily` needs no cleanup |

---

## Design Notes

1. **The probe uses the raw driver, not `_session()`.** The question is what `libsql==0.1.11` does, so the probe calls `libsql.connect("http://127.0.0.1:8080")` directly. That rules out the wrappers hiding or adding anything. It records, verbatim:
   - the SQL;
   - `cursor.description`;
   - `fetchall()` for a first insert and for a conflict update;
   - `rowcount`;
   - whether the row persists after `commit()`, read back from a **fresh** client, as STORY-001 did for `lastrowid`.

   It also records the error string if the statement raises. The probe is a throwaway heredoc. Paste its output into the report; do not commit it as a script. A permanent pytest test (Task 5) pins the same behaviour through `_session()`, so a driver bump that changes it fails CI.
2. **Path A (rows come back).** `_ADMIT_USAGE_SQL` is the PRD 6.5 statement verbatim, with one `?` (user_id). `admit_usage` runs it in one `_session()`, calls `fetchone()`, and builds `UsageAdmission` from `row["day"]`, `row["window_start"]`, `row["window_requests"]`, `row["tokens_today"]`. If the probe shows `description` is empty for `RETURNING`, unpack the row positionally in RETURNING-column order instead, and say why in a comment.
3. **Path B (no rows, or it raises).** Same `_session()`. First run the upsert without `RETURNING`. Then run `SELECT day, window_start, window_requests, input_tokens + output_tokens + unsplit_tokens AS tokens_today FROM usage_daily WHERE user_id = ? ORDER BY day DESC LIMIT 1`.
   - **Why not `WHERE day = date('now')`:** `'now'` is stable only within one statement. A pair straddling 00:00 UTC would upsert yesterday's row and then select today's, which does not exist. The newest row for the user is the one just written, because the upsert's own `day` is the database's latest date.
   - **Atomicity:** the upsert takes the write lock, so the SELECT in the same transaction reads its own write. The probe also records `conn.in_transaction` after the upsert, to confirm the driver opened an implicit transaction.
   - The docstring and the report state that this costs two round trips, which STORY-017 measures (PRD Risk 2).
4. **The database is the only clock.** Python never computes `day` or `window_start`. `charge_usage` takes the `day` that `admit_usage` returned, so a request admitted before midnight is charged to the day it was admitted (PRD 6.5). Note `strftime('%s','now') / 60`: `strftime` returns TEXT, and SQLite coerces it to INTEGER for the division, so the result is an integer minute. Test 3 asserts `isinstance(window_start, int)`.
5. **`charge_usage` signature.** It is `charge_usage(user_id: str, day: str, input_tokens: int, output_tokens: int, unsplit_tokens: int) -> bool`. The story calls it positionally, as in `charge_usage(user_id, day, 0, 0, 150)`, so the parameters are not keyword-only. It returns `rowcount == 1`. `False` means there is no row for that `(user_id, day)`, which cannot happen after a successful admit. STORY-012 decides what to do with it, under D9's "charge fails open". The function has one statement, `_CHARGE_USAGE_SQL`, from PRD 6.5 verbatim, binding `(input, output, unsplit, user_id, day)` positionally. Named placeholders are not a verified driver behaviour, per the `_SUMMARY_SQL` comment.
6. **`UsageAdmission(day: str, window_start: int, window_requests: int, tokens_today: int)`, frozen.** It has no defaults: every field always comes from the database.
7. **No settings are read.** `USAGE_LIMITS_ENABLED` gating belongs to STORY-010/011. These functions only count and report.

## Risks

| Risk | Mitigation |
|------|-----------|
| `RETURNING` returns nothing, raises, or returns rows but loses the write on commit (PRD Risk 2) | Task 1 decides from pasted evidence, including a fresh-client read-back. Path B is fully specified, so either outcome finishes the story |
| `RETURNING` rows come back but `cursor.description` is empty, so `_Row` named access raises `IndexError` | The probe records `description`. Design Note 2 gives the positional fallback |
| Path B's SELECT reads a different day than the upsert wrote, at midnight | `ORDER BY day DESC LIMIT 1` instead of `date('now')` (Design Note 3) |
| Tests that pin the set of tables or the statements of the bootstrap block break on a new table | Grep found no exact-set assertion: `tests/test_db.py:2041` uses `<=`. Run the `_RecordingConnection` tests (`:3391-3440`, `:3485-3530`, `:3617-3640`) and `test_init_db_issues_no_alter_when_schema_is_current` (`:136`) in Task 6. A CREATE adds no ALTER and no second `_session()` |
| `scripts/migrate_to_turso.py` `_TABLES = ("audit_logs", "users")` does not copy `usage_daily` | Intended: it is a one-time SQLite-to-Turso migration from before PRD-013, and no SQLite file holds counters. No change |
| The AC 3 test can cross a minute boundary between admits | It asserts the rollover rule over the returned `window_start`s when they differ, and `[1, 2, 3]` otherwise (Task 5). Rollover itself is tested by inserting a row with an old `window_start` directly (story note), with no sleep |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | `CREATE_USAGE_DAILY_TABLE` (PRD 6.5 DDL) with a rationale comment; frozen `UsageAdmission` dataclass |
| `app/db/database.py` | UPDATE | Imports; `conn.execute(CREATE_USAGE_DAILY_TABLE)` in `init_db()` plus a docstring paragraph; `_ADMIT_USAGE_SQL`, `_CHARGE_USAGE_SQL` with a comment recording the RETURNING finding; `admit_usage()`, `charge_usage()` |
| `tests/test_usage_storage.py` | CREATE | Schema, RETURNING pin, admit counting, rollover, charge, isolation tests |
| `.agents/reports/PRD-013-audit-and-usage-limits/STORY-009-usage-counter-storage.report.md` | CREATE (by `/implement`) | AC 1 evidence: exact statement, pasted output, path taken |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Spike — verify `RETURNING` on the pinned driver

- **File**: none committed (throwaway probe). Output goes into the report.
- **Action**: RUN
- **Implement**:
  - Confirm the pins: `pip show libsql` shows `0.1.11`, and `docker ps` shows `harness-libsql-dev` up.
  - Against a scratch table, run this with the raw driver: `python - <<'EOF' … EOF`. It does `import libsql; c = libsql.connect("http://127.0.0.1:8080")`.
  - `DROP TABLE IF EXISTS usage_daily_probe`, then create it with the PRD 6.5 DDL (table name changed to `usage_daily_probe`). Then:
    1. Execute the PRD 6.5 admit statement verbatim (table renamed), with `("probe-user",)`. Print `repr(cur.description)`, `cur.fetchall()`, `cur.rowcount` and `c.in_transaction`. Then `c.commit()`.
    2. Execute it again (the conflict path) and print the same four.
    3. Read back from a **new** `libsql.connect(...)` with `SELECT * FROM usage_daily_probe` and print it.
    4. Run the charge `UPDATE` with `(120, 30, 0, "probe-user", <day>)`, commit, re-admit, and print `tokens_today`.
    5. `DROP TABLE usage_daily_probe`.
  - Run it twice, the second time after `docker restart harness-libsql-dev`, matching STORY-001's two-run discipline.
  - **Decision**: if steps 1–2 return one row each, with `window_requests` 1 then 2, and step 3 shows the row persisted, take **Path A**. Otherwise take **Path B**. Record which, and why, in the report.
- **Validate**: the report draft contains the exact SQL, both runs' raw output, and the path decision.

### Task 2: Schema and dataclass

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**:
  - After `USERS_ADDED_COLUMNS`, add `CREATE_USAGE_DAILY_TABLE`: the PRD 6.5 DDL verbatim, including its inline `--` column comments. The rationale comment above it covers these points:
    - one row per user per UTC day, also holding the fixed rate window, so the gate is one statement (D3);
    - `day` and `window_start` are written only from the database clock;
    - the composite PK is the only access path, so there is no extra index;
    - no added-columns mapping, because the table is new;
    - no foreign key to `users`, for the reason the chat tables give (and the break-glass `admin` has no `users` row but is counted, PRD 6.6);
    - no cleanup, since rows accumulate at one per active user per day and are what STORY-016 reads.
  - After `User`, add `@dataclass(frozen=True) class UsageAdmission: day: str; window_start: int; window_requests: int; tokens_today: int`, with a short docstring. Say it is what the gate needs in one read, and that STORY-010 compares it to limits.
- **Mirror**: `app/db/models.py:150-165` (DDL and comment), `:196-207` (chat-table no-FK rationale)
- **Validate**: `python -c "from app.db.models import CREATE_USAGE_DAILY_TABLE, UsageAdmission; print(UsageAdmission('2026-10-18', 1, 1, 0))"`

### Task 3: Create the table in `init_db()`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - Import `CREATE_USAGE_DAILY_TABLE` and `UsageAdmission`, keeping the alphabetical import order.
  - Append `conn.execute(CREATE_USAGE_DAILY_TABLE)` as the last line of the bootstrap `_session()` block.
  - Add an `init_db()` docstring paragraph: "PRD-013 STORY-009 adds `usage_daily`, a new table, so it arrives by CREATE alone with no added-columns mapping. In steady state it is one more `CREATE … IF NOT EXISTS` no-op in the same transaction. Its position is not load-bearing: no other statement reads it."
- **Mirror**: `app/db/database.py:695-720`
- **Validate**: `pytest tests/test_db.py -q -k "init_db"`

### Task 4: `admit_usage` and `charge_usage`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Below `set_user_limits`, add a `# Usage counters (PRD-013 Section 6.5)` section with the following.
  - A comment block recording the Task 1 finding in the style of the `_SUMMARY_SQL` comment:
    - what was run;
    - what came back;
    - which path ships;
    - that `day` and the window come from the database clock;
    - that the four RETURNING / SELECT columns are read by name (or positionally, per Design Note 2).
  - `_ADMIT_USAGE_SQL`: Path A uses the PRD statement verbatim. Path B uses the upsert without `RETURNING`, plus `_ADMIT_USAGE_READ_SQL` from Design Note 3.
  - `_CHARGE_USAGE_SQL`: PRD statement verbatim.
  - `admit_usage(user_id: str) -> UsageAdmission`. Its docstring says:
    - it counts one authorized attempt and returns what both checks need;
    - it is atomic, so two instances get distinct `window_requests`;
    - it costs one round trip (Path A) or two in one transaction (Path B);
    - it raises `StorageError` on failure and decides nothing (fail-closed is STORY-010's call);
    - it compares no limit.
  - `charge_usage(user_id, day, input_tokens, output_tokens, unsplit_tokens) -> bool`. Its docstring says it charges the day `admit_usage` returned, and returns `rowcount == 1`.
- **Mirror**: `app/db/database.py:1604-1637`, `:1250-1281`
- **Validate**: covered by Task 5

### Task 5: Tests

- **File**: `tests/test_usage_storage.py`
- **Action**: CREATE
- **Implement**: Use the module prologue from `tests/test_db.py:1-4` (the env `setdefault`s), and use `temp_db` throughout.
  - `test_init_db_creates_usage_daily_with_its_columns` (AC 2): `PRAGMA table_info(usage_daily)` gives exactly the eight names, in order. `pk` is 1 for `user_id` and 2 for `day`, 0 elsewhere. `notnull` is 1 on all eight, and the `dflt_value`s are `'0'` for the five counters and None for `window_start`.
  - `test_init_db_is_idempotent_for_usage_daily`: call `init_db()` twice, and the table still exists with no rows.
  - `test_init_db_on_a_pre_usage_database_adds_the_table`: use `uninitialized_db` with an `audit_logs`/`users` built from the current constants, then `init_db()`. `usage_daily` exists, and the existing tables are untouched.
  - `test_upsert_returning_yields_the_admission_row` (AC 1 pin): run `_ADMIT_USAGE_SQL` through `get_connection()` and assert one row with the four named columns. This is **Path A only**. On Path B, replace it with `test_admit_usage_reads_its_own_write_in_one_session`, which wraps `get_connection` in a recorder and asserts both statements went through one connection with one commit.
  - `test_admit_usage_counts_three_attempts_in_one_window` (AC 3):
    - Three calls give `window_requests` `[1, 2, 3]` and `tokens_today` `[0, 0, 0]`.
    - `day` equals `SELECT date('now')`, and `window_start` equals `SELECT strftime('%s','now') / 60`, both read from the DB in the same test and allowing a one-minute tolerance.
    - `window_start` is an `int`.
    - `SELECT requests FROM usage_daily` gives 3.
    - Minute-boundary guard (never skip): the three calls usually share a minute, and then the test asserts exactly `[1, 2, 3]`. If the returned `window_start`s differ, a boundary was crossed. The test then asserts the rollover rule over the returned values instead: `1` when `window_start` changed, otherwise the previous value + 1. It still asserts `requests == 3`.
  - `test_admit_usage_resets_the_window_on_a_new_minute` (AC 4):
    - Insert `('dana', date('now'), 7, 0, 0, 0, strftime('%s','now')/60 - 5, 9)` directly.
    - Call `admit_usage('dana')`. `window_requests` is 1, `requests` on the row is 8, and `window_start` moved forward.
    - A second call gives 2, and `requests` is 9.
  - `test_charge_usage_accumulates_into_tokens_today` (AC 5):
    - `a = admit_usage('dana')`.
    - `charge_usage('dana', a.day, input_tokens=120, output_tokens=30, unsplit_tokens=0)` returns True.
    - `charge_usage('dana', a.day, 0, 0, 150)` returns True.
    - `admit_usage('dana').tokens_today == 300`.
    - The row has `(input, output, unsplit) == (120, 30, 150)`.
  - `test_charge_usage_charges_the_admitted_day_not_today`: insert a row for `'2000-01-01'` directly, then charge that day. Only that row changes, and today's row (if any) is untouched.
  - `test_charge_usage_without_a_row_returns_false_and_creates_none`.
  - `test_admit_usage_is_per_user`: two users each start at 1.
  - `test_admit_usage_on_a_missing_table_raises_missing_relation`: use `uninitialized_db`, and expect `MissingRelationError` (`_translated` maps it).
- **Mirror**: `tests/test_db.py:3551-3586`, `:2454-2460`
- **Validate**: `pytest tests/test_usage_storage.py -q`

### Task 6: Regression and report

- **Action**: RUN
- **Validate**:
  - `pytest tests/test_db.py tests/test_usage_storage.py -q`
  - `pytest tests/ -q`, the full suite. Watch the `_RecordingConnection` "one bootstrap `_session()`" tests, `test_init_db_issues_no_alter_when_schema_is_current`, the `test_two_init_db_calls_racing_*` tests and `tests/test_conftest_fixtures.py` (the reset must drop the new table).
  - Run `grep -rn "admit_usage\|charge_usage\|usage_daily" app chat_ui scripts`. Readers should appear only in `database.py` and `models.py`, with no pipeline caller (STORY-010/011).
  - Write the report with the AC 1 evidence from Task 1, and the path taken and why. On Path B, add the line "admit_usage is upsert plus SELECT in one `_session()` transaction (two round trips)".

---

## End-to-End Tests

- [ ] Task 1 probe runs twice against `harness-libsql-dev` (once after a restart), with identical findings pasted into the report
- [ ] `python -c "from app.db.database import init_db, admit_usage, charge_usage; init_db(); a=admit_usage('e2e'); print(a); print(charge_usage('e2e', a.day, 1, 2, 3)); print(admit_usage('e2e'))"` against the dev server prints `window_requests=1, tokens_today=0`, then `True`, then `window_requests=2` (same minute) and `tokens_today=6`
- [ ] Booting the API (`uvicorn app.main:app`) on an existing dev DB creates `usage_daily` and starts without error

---

## Validation

```bash
pip show libsql | head -2            # Version: 0.1.11
pytest tests/test_usage_storage.py -q
pytest tests/test_db.py -q
pytest tests/ -q
```

---

## Acceptance Criteria

(Copied from story `STORY-009`)

- [ ] Given the pinned `libsql==0.1.11` against the local dev server, when `INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING` is executed, then the story report records whether rows come back, with the exact statement and output; if they do not, `admit_usage` is implemented as upsert plus `SELECT` in one `_session()` transaction and the report says so.
- [ ] Given a fresh database, when `init_db()` runs, then `usage_daily` exists with primary key `(user_id, day)` and the columns in PRD Section 6.5, created in the same `_session()` block as the other tables.
- [ ] Given a user with no row today, when `admit_usage(user_id)` is called three times within one minute, then it returns `window_requests` 1, 2, 3, `tokens_today` 0, and a `day` and `window_start` taken from the database clock; `requests` on the row is 3.
- [ ] Given a row whose `window_start` is an earlier minute, when `admit_usage` is called, then `window_requests` is 1 and `requests` keeps increasing.
- [ ] Given `charge_usage(user_id, day, input_tokens=120, output_tokens=30, unsplit_tokens=0)` and then `charge_usage(..., 0, 0, 150)`, when `admit_usage` is called next, then `tokens_today` is 300.
- [ ] All tasks completed
- [ ] Full `pytest tests/` passes
- [ ] Follows existing patterns (DDL constant in `models.py`, schema in the one bootstrap `_session()`, one statement per call, `-> bool` from `rowcount`, no Python-side clock)
