---
story: STORY-007
prd: PRD-007
slug: concurrent-safe-init-db
title: "Make init_db() and _add_missing_columns() converge under concurrent multi-instance startup"
type: ENHANCEMENT
complexity: MEDIUM
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-01
---

# Plan: Concurrency-safe `init_db()` / `_add_missing_columns()`

## Summary

`_add_missing_columns()` reads `PRAGMA table_info(audit_logs)` and then conditionally issues one
`ALTER TABLE ... ADD COLUMN` per entry in `AUDIT_LOGS_ADDED_COLUMNS`. `ALTER TABLE ADD COLUMN` has
no `IF NOT EXISTS` form, so that read-then-write pair is the one non-idempotent step in `init_db()`
— and against a database shared by N instances it is a race whose loser raises
`duplicate column name: <col>`. Because `init_db()` runs at import time
(`chat_ui/chat_ui/chat_ui.py:33`, `app/main.py:13`), the loser is a container that will not boot.
The fix is deliberately small and local: keep the pre-check (it is what keeps the steady-state run
a true no-op, which `test_init_db_issues_no_alter_when_schema_is_current` pins), and wrap **only**
the `ALTER` in a narrow handler that treats *this column already exists* as success and re-raises
everything else. The discriminator is the driver's message text, not its code — `SQLITE_UNKNOWN`
covers both `duplicate column name` and `no such table`, so the code cannot separate them
(STORY-001 §3.5). The bulk of the story is the test work: proving convergence **deterministically**,
because a threaded test that passes because the interleave happened not to occur is not evidence.

## User Story

As a platform engineer
I want N application instances booting simultaneously against one shared database to converge on the correct schema
So that scaling past one container does not produce a container that will not start or a half-migrated `audit_logs` table

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-007-concurrent-safe-init-db.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 6 Pattern 5, Section 11
  (functional requirements), Section 12 Phase 2, Section 14 Risk 3

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (story frontmatter says `technical`; the observable behavior of a losing instance changes, so this is not a pure refactor) |
| Complexity | MEDIUM (≈12 production lines; the weight is in five new tests and one probe) |
| Systems Affected | `app/db/database.py`, `tests/test_db.py` |
| Story | STORY-007 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | none | — |

`.agents/skills/` was listed in full and holds exactly one skill, `frontend-design`, whose
`description` scopes it to *"distinctive, intentional visual design when building new UI or
reshaping an existing one … aesthetic direction, typography, and making choices that don't read as
templated defaults."* This story changes two files, neither of which renders anything. No rule in
that `SKILL.md` constrains any task below. The story frontmatter's `skills: []` is confirmed
correct rather than merely inherited.

---

## Findings from Exploration

Six things that change what gets built. Each was read out of the codebase or a prior story's
report, not assumed.

### F1 — Inside `_add_missing_columns()` the exception is a raw `ValueError`, not a `StorageError`

`init_db()` runs inside `_session()` (`app/db/database.py:274-284`), which is
`with _translated(): conn = get_connection(); with conn: yield conn`. `_translated()`
(`app/db/database.py:250-271`) is a `contextmanager` that converts on the way **out of the whole
block**. A statement failing part-way through the block therefore arrives at
`_add_missing_columns()` as the driver's bare `ValueError`, and only becomes a `StorageError` once
it escapes `init_db()` entirely.

So `except StorageError:` inside `_add_missing_columns()` would never fire. The story asks for the
module-owned error surface from [[STORY-004]], and the way to get it is to wrap the single `ALTER`
in its own `with _translated():` — one statement, one translation, the same seam, no second
error-parsing site.

Re-raising the resulting `StorageError` from inside the outer `_translated()` is safe and was
checked against its body: it catches `ValueError` only, and `StorageError` derives from
`Exception`, so a genuine failure passes through untranslated rather than being parsed twice.

### F2 — The exact failure text is already recorded, and the code is useless as a discriminator

STORY-006 collected it from the live endpoint expressly for this story
(`.agents/reports/PRD-007-turso-migration/STORY-006-libsql-connection-layer.report.md:235-238`,
first captured at `STORY-001-driver-decision.md:160-166`):

```
builtins.ValueError: Hrana: `stream error: `Error {
    message: "SQLite error: duplicate column name: pii_detected_input",
    code: "SQLITE_UNKNOWN" }`
```

`SQLITE_UNKNOWN` is shared with `no such table` (STORY-001 §3.5), which is precisely why
`app/db/database.py:230-233` already carries the comment *"Matching on the code is not an option."*
The new pattern must match the message and must capture the column name, so the handler can assert
the driver is reporting the column **we just tried to add** and not some other one.

### F3 — AC6 (`PRAGMA table_info` result shape) is already satisfied by STORY-006

`_Cursor` (`app/db/database.py:104-158`) and `_Row` (`app/db/database.py:57-102`) map
`cursor.description` back onto the tuple rows, and STORY-001 §2.5 verified `description` is
populated for `PRAGMA` rows specifically (`STORY-001-driver-decision.md:141-156`: *"mapped name:
id <- description-based mapping works on PRAGMA rows too"*). `_Cursor.__iter__` closes the second
gap — the driver's own cursor is not iterable. The line
`{row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}` therefore already works
unchanged. **No code change is expected for AC6.** It still gets a task, because the AC asks for a
verified answer and a note in the report, not for an assumption.

### F4 — The pre-check must stay, and the story is right to scope the fix to the `ALTER`

Deleting the `if name not in existing` guard and relying on the new handler would make the
steady-state run issue five `ALTER`s and swallow five errors on every boot and every Reflex hot
reload. `tests/test_db.py:101-181` (`test_init_db_issues_no_alter_when_schema_is_current`) asserts
*no `ALTER` is issued at all* — "did not raise" and "did not execute" are different claims and that
test asks for the second. It is also AC4 of this story. The guard stays; the handler is the safety
net for the window between the read and the write, not a replacement for the read.

### F5 — The concurrency test must use threads over the **shared** client, and can

`_shared_client()` (`app/db/database.py:27-55`) returns one client per process, keyed on
`(DATABASE_URL, TURSO_AUTH_TOKEN)`. STORY-006 measured the alternative: eight threads with a client
each lost 169 of 200 writes to `TRANSACTION_TIMEOUT`, while eight threads over one shared client
completed all 200. `tests/conftest.py::_reset_database` holds the same line for the fixtures. So
the concurrency tests here must reach the database through `get_connection()` like everything else,
and must not construct a client of their own.

Serialization at the client does **not** remove the race, which is what makes the test possible:
the interleave being tested is `PRAGMA(A) → PRAGMA(B) → ALTER(A) → ALTER(B)`, four individually
serialized statements. `_client_lock` is held only around client *construction*, never around
`execute`, so a test may block a thread between its `PRAGMA` and its `ALTER` without holding
anything another thread needs.

### F6 — There is prior art for both new test shapes, and it is a connection proxy

`tests/test_db.py:104-140` (`_RecordingConnection`) and `tests/test_db.py:1102-1130`
(`_LockedConnection`) both monkeypatch `database.get_connection` with a lambda returning a proxy
that implements `__enter__` / `__exit__` / `execute` and delegates. STORY-006 introduced the idiom
because the libSQL connection has no `set_trace_callback` equivalent. Every new test below is built
on the same proxy rather than on a new mechanism.

---

## Design Notes

### D1 — What is caught, stated precisely

The handler treats a failure as success under **all** of these conditions, and no fewer:

1. it is a `StorageError` produced by `_translated()` (so it carries the `Hrana:` marker — a
   `ValueError` from our own code is not a driver error and must not be swallowed);
2. it is not an `IntegrityError` or `MissingRelationError` (those are separate translations and
   neither can mean "column exists");
3. its message matches `duplicate column name: <name>`, where `<name>` is the exact column the loop
   was adding.

Anything else — a permissions failure, an unreachable endpoint, `database is locked`, a duplicate
report naming a *different* column — propagates. The story's own words: swallowing a genuine schema
error here would hide a broken migration behind a healthy-looking boot.

Condition 3 subsumes 2 in practice (a constraint message never contains `duplicate column name`),
so the implementation expresses 3 alone, and the test in Task 6 is what keeps 2 honest.

### D2 — The open question: does a failed statement poison the surrounding transaction?

`init_db()` executes four-to-nine statements inside one `_Connection` block that commits on exit
(`app/db/database.py:204-212`). If libSQL aborts the implicit transaction when a statement fails,
then swallowing the duplicate-column error would leave `CREATE_USERS_TABLE` and
`CREATE_USERS_TOKEN_HASH_INDEX` executing against a doomed transaction — a losing instance that
*appears* to boot with a *silently incomplete* schema, which is a worse failure than the crash this
story removes. No prior report answers this: STORY-001 probed error shapes, not transaction state
after an error.

**This is Task 1, and it gates the design.** It cannot be answered from the codebase; it needs the
live endpoint. Both outcomes have a written answer:

- **Not poisoned** (expected — SQLite's default is statement-level failure, and the driver reports
  per-statement): the design above stands unchanged.
- **Poisoned**: `_add_missing_columns()` stops taking a connection and instead opens one
  `with _session() as conn:` per `ALTER`, so a swallowed failure discards only its own statement.
  `init_db()` then calls `_add_missing_columns()` outside its own block. Cost: N+1 round trips on a
  migrating boot (once, on a database that predates the columns) and still zero extra on a current
  one, because the pre-check runs first. `test_init_db_issues_no_alter_when_schema_is_current`
  patches `database.get_connection`, so it keeps observing the statements either way.

### D3 — What this story does not fix, said out loud

Three windows remain open by decision, all outside the AC set:

- **`CREATE TABLE IF NOT EXISTS` / `CREATE UNIQUE INDEX IF NOT EXISTS`** are idempotent by
  construction, which is why the story scopes the fix to the `ALTER`. If libSQL turns out to race
  even on those, that is a driver defect and a new story — Task 7's empty-database test is where it
  would surface.
- **A column added by another instance between our `PRAGMA` and our `ALTER` gets its DDL from
  `AUDIT_LOGS_ADDED_COLUMNS` on *that* instance.** Two instances running different code versions
  could therefore disagree about a column's type. That is a deployment-ordering concern (a rolling
  restart across a schema change), not a concurrency bug, and the MVP does not address it. AC5
  covers the single-version case: whichever instance wins, it wrote the definition from `models.py`.
- The two-instance, two-*process* end-to-end proof is [[STORY-016]]. This story proves convergence
  at the function level, where a failure is diagnosable.

---

## Patterns to Follow

### Naming — driver message patterns live together, above `_translated()`

```python
# SOURCE: app/db/database.py:224-242
# The driver states both conditions in the exception message and nowhere else.
# ...
# Matching on the code is not an option: SQLITE_UNKNOWN covers both a missing
# table and a duplicate column, and SQLITE_CONSTRAINT covers both duplicates.
_MISSING_RELATION = re.compile(r"no such table: (\w+)")
_CONSTRAINT = re.compile(r"constraint failed: ([\w.]+)")

_DRIVER_ERROR = "Hrana:"
```

### Error handling — translation happens at one seam, and predicates read it back

```python
# SOURCE: app/db/database.py:245-247
def _constraint_of(exc: ValueError) -> Optional[str]:
    match = _CONSTRAINT.search(str(exc))
    return match.group(1) if match is not None else None
```

### Tests — a proxy connection, installed over `database.get_connection`

```python
# SOURCE: tests/test_db.py:1102-1130
class _LockedConnection:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._conn.__exit__(*exc_info)

    def execute(self, *args, **kwargs):
        raise ValueError(
            "Hrana: `stream error: `Error { message: \"SQLite error: database "
            'is locked", code: "SQLITE_BUSY" }``'
        )

real_get_connection = database.get_connection
monkeypatch.setattr(
    database, "get_connection", lambda: _LockedConnection(real_get_connection())
)
```

### Tests — convergence is asserted on the schema, never on timing

```python
# SOURCE: tests/test_db.py:296-303
    with get_connection() as conn:
        columns = [
            row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")
        ]

    assert {"pii_detected_input", "pii_detected_output", "pii_entities"} <= set(columns)
    assert len(columns) == len(set(columns)), "a column was added twice"
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | `_DUPLICATE_COLUMN` pattern + `_is_duplicate_column()` predicate + the narrow handler in `_add_missing_columns()` |
| `tests/test_db.py` | UPDATE | One new section: the forced-loser test, the deterministic two-thread interleave, the propagation test, and two N-thread convergence tests |
| `.agents/reports/PRD-007-turso-migration/STORY-007-concurrent-safe-init-db.report.md` | CREATE | AC6's recorded answer and Task 1's probe result (written by `/implement`) |

No file is created under `app/`. No public signature changes; `_add_missing_columns()` is private
and its only caller is `init_db()` (`app/db/database.py:290`).

---

## Tasks

Execute in order. Task 1 gates Task 3.

### Task 1: Probe whether a failed statement poisons the surrounding transaction

- **File**: `scratchpad/probe_alter_failure.py` (throwaway — **not** committed, not under `app/`)
- **Action**: CREATE, run, delete
- **Implement**: Start the local dev server from `tests/conftest.py`'s docstring. Then, inside one
  `get_connection()` block: `CREATE TABLE t (a INTEGER)`, `ALTER TABLE t ADD COLUMN b INTEGER`, a
  second `ALTER TABLE t ADD COLUMN b INTEGER` (catch the `ValueError`), then
  `CREATE TABLE t2 (a INTEGER)` and an `INSERT` into `t`. Exit the block normally so it commits.
  Reopen and check that `t2` exists and the row is there. Record the driver's exact message for the
  duplicate `ALTER` verbatim, and print the `keys()` of a `PRAGMA table_info(t)` row for Task 9.
- **Mirror**: the probe style of `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md` §2.5
- **Decides**: D2. If `t2` and the row survive → Task 3 as written. If they do not → apply D2's
  fallback shape (one `_session()` per `ALTER`) in Task 3 and say so in the report.
- **Validate**: the script prints a yes/no plus the captured message; paste both into the report

### Task 2: Add the duplicate-column pattern and predicate

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Beside `_MISSING_RELATION` / `_CONSTRAINT` (`app/db/database.py:234-235`) add
  `_DUPLICATE_COLUMN = re.compile(r"duplicate column name: (\w+)")`, extending the existing comment
  block to say why this one is also matched on text (`SQLITE_UNKNOWN` is shared with
  `no such table`) and citing the STORY-006 report line the message came from. Beside
  `_constraint_of()` (`app/db/database.py:245`) add:

  ```python
  def _is_duplicate_column(exc: StorageError, name: str) -> bool:
      """True when the driver is reporting that `name` already exists.

      Narrow on purpose: it must name the column we just tried to add. A
      permissions failure, an unreachable endpoint or a duplicate report for a
      different column is a real failure and must reach the caller.
      """
      match = _DUPLICATE_COLUMN.search(str(exc))
      return match is not None and match.group(1) == name
  ```
- **Mirror**: `app/db/database.py:224-247`
- **Validate**: `python -c "import app.db.database"` imports clean; `pytest tests/test_db.py -q`
  still green (no behavior change yet)

### Task 3: Make `_add_missing_columns()` converge

- **File**: `app/db/database.py:295-303`
- **Action**: UPDATE
- **Implement**: Keep the `PRAGMA` pre-check and the `if name not in existing` guard exactly as they
  are (F4). Wrap only the `ALTER`:

  ```python
  for name, ddl in AUDIT_LOGS_ADDED_COLUMNS.items():
      if name in existing:
          continue
      try:
          with _translated():
              conn.execute(f"ALTER TABLE audit_logs ADD COLUMN {name} {ddl}")
      except StorageError as exc:
          if not _is_duplicate_column(exc, name):
              raise
  ```

  Extend the docstring: the "additive only" constraint is unchanged; what is new is that the read
  and the write are not atomic against a shared database, so the losing instance converges instead
  of crashing at import time. Note why the translation is applied here rather than inherited from
  `_session()` (F1), and why the pre-check survives (F4). Apply D2's fallback shape instead if
  Task 1 said the transaction is poisoned.
- **Mirror**: `app/db/database.py:250-271` for the `_translated()` idiom; `app/db/errors.py` for
  docstring register
- **Validate**: `pytest tests/test_db.py -q` — in particular
  `test_init_db_issues_no_alter_when_schema_is_current`,
  `test_init_db_migration_is_idempotent_across_repeated_calls` and
  `test_add_missing_columns_applies_any_declared_column` pass **unmodified** (AC4)

### Task 4: The deterministic forced-loser test

- **File**: `tests/test_db.py` — new section `# PRD-007 STORY-007: concurrent init_db()` after the
  STORY-006 section at `tests/test_db.py:1171`
- **Action**: UPDATE
- **Implement**: `test_add_missing_columns_treats_an_existing_column_as_success(temp_db, monkeypatch)`.
  `temp_db` leaves the schema current. Install a proxy over `database.get_connection` that delegates
  everything but returns an **empty result** for `PRAGMA table_info(audit_logs)` — the stale read a
  losing instance gets. `init_db()` then issues all five `ALTER`s against a table that already has
  them. Assert: `init_db()` returns (no exception), and afterwards `PRAGMA table_info(audit_logs)`
  still lists each key of `AUDIT_LOGS_ADDED_COLUMNS` exactly once. Docstring must say this is the
  deterministic half of AC7: it reproduces the loser's exact condition without depending on an
  interleave occurring.
- **Mirror**: `tests/test_db.py:104-140` (`_RecordingConnection`)
- **Validate**: `pytest tests/test_db.py -k treats_an_existing_column -q`; confirm it **fails**
  against `git stash`-ed production code, which is what proves it tests the change

### Task 5: The deterministic two-thread interleave

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: `test_two_init_db_calls_interleaved_between_read_and_alter_both_succeed(uninitialized_db, db_connect)`.
  Build the pre-PII schema with the module's existing `_create_pre_pii_database` helper. Patch
  `database.get_connection` with a proxy that, **after** a `PRAGMA table_info` execute returns,
  waits on a shared `threading.Barrier(2, timeout=30)` — so both threads hold the same stale view
  before either `ALTER`s. That is the race, forced rather than hoped for. Start both threads, join
  with a timeout, collect their exceptions. Assert: both exception slots are empty, all five columns
  present exactly once, the pre-existing row intact.
  Two things the docstring must state: the barrier is released only after `execute` returns, so no
  thread blocks while the driver holds anything (F5); and the `timeout=` turns a deadlock into a
  failed test rather than a hung suite.
- **Mirror**: `tests/test_db.py:285-303` for the assertions; F6's proxy for the mechanism
- **Validate**: `pytest tests/test_db.py -k interleaved -q`, run 10× in a shell loop
  (`pytest-repeat` is not installed) with zero flakes; confirm it fails against stashed production
  code

### Task 6: The propagation test — a non-duplicate failure still raises

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: `test_add_missing_columns_propagates_a_failure_that_is_not_a_duplicate_column(uninitialized_db, db_connect)`.
  Pre-PII schema again, so at least one `ALTER` will fire. The proxy passes the `PRAGMA` through but
  raises the driver's `database is locked` shape (`SQLITE_BUSY`) on any `ALTER`. Assert
  `pytest.raises(StorageError)`, `not isinstance(exc, MissingRelationError)`, and
  `"locked" in str(exc)`. Add a sibling case raising `duplicate column name: some_other_column`,
  proving the predicate checks the *name* and does not merely pattern-match the phrase. This is
  AC3's second half and the reason `_is_duplicate_column` takes `name` at all.
- **Mirror**: `tests/test_db.py:1092-1140`
- **Validate**: `pytest tests/test_db.py -k propagates_a_failure -q`

### Task 7: N-thread convergence on an empty database

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: `test_concurrent_init_db_on_an_empty_database_converges(database_url)`. Eight
  threads released from a `threading.Barrier(8)`, each calling `init_db()`, each appending any
  exception to a list. Assert the list is empty (**every** call returned — AC1), then that the
  schema is complete: `audit_logs` carries every column including all five added ones with no
  duplicate, `users` exists, `idx_users_token_hash` exists. No client is constructed by the test
  (F5). The docstring must be honest that this test alone is not evidence — it passes whether or not
  the interleave occurred — and point at Tasks 4 and 5 for the deterministic proof.
- **Mirror**: `tests/test_db.py:807-868` for the users-table and index assertions
- **Validate**: `pytest tests/test_db.py -k empty_database_converges -q`, 10× with no flakes

### Task 8: N-thread convergence on a partially migrated database

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: `test_concurrent_init_db_on_a_partially_migrated_database_converges(uninitialized_db, db_connect)`.
  `_create_pre_pii_database` first, so a subset of `AUDIT_LOGS_ADDED_COLUMNS` is genuinely missing
  and there is real migration work to race over. Then the Task 7 barrier pattern. Assert: no
  exception from any thread, all five columns present exactly once
  (`len(columns) == len(set(columns))`), `count_audit_logs() == 1`, and the pre-existing row's
  `user_id` preserved — the migration is still additive under concurrency (AC2).
- **Mirror**: `tests/test_db.py:285-303`
- **Validate**: `pytest tests/test_db.py -k partially_migrated -q`, 10× with no flakes

### Task 9: Record the `PRAGMA table_info` shape answer (AC6)

- **File**: `.agents/reports/PRD-007-turso-migration/STORY-007-concurrent-safe-init-db.report.md`
- **Action**: CREATE (the report `/implement` writes anyway; this task fixes one required section)
- **Implement**: State the verified answer: the result shape does **not** differ in a way that
  reaches `_add_missing_columns()`, because `_Cursor` maps `cursor.description` onto the tuple rows
  and makes the cursor iterable (`app/db/database.py:104-158`), and `description` is populated for
  `PRAGMA` rows (STORY-001 §2.5). Confirm it empirically rather than by citation — paste the row
  keys printed by Task 1's probe. Record that no code change was needed, and that
  `SELECT name FROM pragma_table_info(...)` remains the fallback if a future driver version drops
  `description`. Also record Task 1's transaction answer and, if the fallback shape was taken, why.
- **Mirror**: `.agents/reports/PRD-007-turso-migration/STORY-006-libsql-connection-layer.report.md`
- **Validate**: the report's AC table has a filled row for every AC below

---

## End-to-End Tests

Run with the local libSQL dev server up:

```bash
docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
  ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
```

- [ ] `pytest tests/test_db.py -q` — green, with `test_init_db_issues_no_alter_when_schema_is_current`,
      `test_init_db_migration_is_idempotent_across_repeated_calls`,
      `test_init_db_migrates_pre_pii_database` and `test_init_db_migrates_pre_rbac_database`
      passing **unmodified**
- [ ] `pytest -q` — the whole suite, no regression and no new flake
- [ ] Repeated boot: `python -c "from app.db.database import init_db; init_db(); init_db()"` against
      an already-migrated database → exits 0 (the Reflex hot-reload path,
      `chat_ui/chat_ui/chat_ui.py:33`)
- [ ] **Four real processes, not threads** — the smallest honest rehearsal of [[STORY-016]]: start
      four `python -c "from app.db.database import init_db; init_db()"` processes at once against a
      database reset to the pre-PII schema; every one exits 0 and the schema afterwards has all five
      columns exactly once
- [ ] `cd chat_ui && reflex run` starts and hot-reloads with no `duplicate column name` error (the
      same ingress check PRD-005 STORY-001 used)

## Validation

```bash
pytest tests/test_db.py -q
pytest -q
python -c "import app.db.database"
grep -rn "sqlite3" app/ chat_ui/ scripts/   # must stay at zero code-level hits (STORY-006 invariant)
```

## Acceptance Criteria

(Copied from story `STORY-007`)

- [ ] Given an empty database and N concurrent `init_db()` calls, when they all complete, then the
      schema is correct and complete and **every** call returns successfully. No caller crashes
      because another won the race. *(Task 7)*
- [ ] Given a database whose `audit_logs` table exists but is missing a subset of
      `AUDIT_LOGS_ADDED_COLUMNS`, when N concurrent `init_db()` calls run, then all five columns are
      present exactly once afterward and every call returns successfully. *(Tasks 5, 8)*
- [ ] Given an `ALTER TABLE ADD COLUMN` that fails because the column already exists, when
      `_add_missing_columns()` handles it, then that specific condition is treated as success. Any
      other failure still propagates. *(Tasks 3, 4, 6)*
- [ ] Given a database already at the current schema, when `init_db()` runs, then it is a no-op: no
      `ALTER` is issued and no error is raised. *(Task 3 — existing
      `test_init_db_issues_no_alter_when_schema_is_current`, unmodified)*
- [ ] Given the five columns are added, when their definitions are checked, then each matches
      `AUDIT_LOGS_ADDED_COLUMNS` in `app/db/models.py:36-42` — including that every `NOT NULL` entry
      carries a non-NULL `DEFAULT`. *(Existing
      `test_added_columns_declaring_not_null_also_declare_a_default`, unmodified; Task 8 checks the
      pre-existing row took the default under concurrency)*
- [ ] Given `PRAGMA table_info(audit_logs)` executed against the libSQL endpoint, when
      `_add_missing_columns()` reads it, then the column names are extracted correctly; any shape
      difference is handled here and recorded in the report. *(Task 9 — expected: no change needed,
      recorded rather than assumed)*
- [ ] Given the concurrency tests, when they run in CI, then they are deterministic. *(Tasks 4 and 5
      are the deterministic evidence; Tasks 7 and 8 are realism and say so in their docstrings)*
- [ ] All tasks completed
- [ ] Backend imports and server starts without error
- [ ] Follows existing patterns
