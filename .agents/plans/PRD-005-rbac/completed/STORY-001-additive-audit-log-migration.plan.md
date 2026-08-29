---
story: STORY-001
prd: PRD-005
slug: additive-audit-log-migration
title: Additive schema-migration mechanism for audit_logs
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-005-rbac        # all stories commit here, no per-story branch
created: 2026-08-28
---

# Plan: Additive schema-migration mechanism for audit_logs

## Summary

**The migration mechanism this story asks for already exists on `main`.** `AUDIT_LOGS_ADDED_COLUMNS` (`app/db/models.py:26-30`) and `_add_missing_columns(conn)` (`app/db/database.py:29-38`, called from `init_db()` at `app/db/database.py:23-26`) shipped with PRD-003's follow-up commit `60835dc` — after the PRD-005 PRD was written, which is why PRD Risk 4 and this story's Technical Notes both describe them as absent. What does *not* exist is proof that the mechanism satisfies the contract STORY-009 is about to depend on: three of the five acceptance criteria have no test behind them today. This plan therefore does not re-implement anything. It converts STORY-001 into what it actually is now — a **verification and hardening** story — adding four tests that pin the mechanism's contract (no-op on a current schema, NOT NULL implies non-NULL DEFAULT, idempotence across repeated calls, and correctness for *any* declared column rather than only the three PII ones that happen to be in the mapping today), plus a one-comment generalization in `app/db/models.py` so the mapping no longer reads as PRD-003-specific. Production behavior is unchanged by design: this story's deliverable is the guarantee, not the code.

## User Story

As a maintainer
I want `init_db()` to add missing columns to an existing `audit_logs` table
So that schema changes reach deployments that already have a database file instead of breaking every insert

## Story Reference

- Story file: `.agents/stories/PRD-005-rbac/STORY-001-additive-audit-log-migration.md`
- PRD: `.agents/PRDs/PRD-005-rbac/PRD.md` — Sections 6 and 14 (Risk 4)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (hardening an existing mechanism; no new capability) |
| Complexity | LOW |
| Systems Affected | `app/db/models.py` (comment only), `tests/test_db.py` |
| Story | STORY-001 |
| PRD | PRD-005 |
| Epic Branch | `epic/PRD-005-rbac` (commit directly on this branch) |

**Dependency status**: `depends_on: []` — nothing blocks this story. It blocks STORY-002 (`users` table) and STORY-009 (`role` / `denied_permission` columns).

---

## Skills In Use

None. `.agents/skills/` contains exactly one skill, `frontend-design`, whose description scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story touches `app/db/` and `tests/` only — no UI surface — so no skill applies. The story's `skills:` frontmatter field is `[]`, consistent with that.

*(Note: the PRD Appendix claims `.agents/skills/` does not exist in this repository. It does; it is simply irrelevant here.)*

---

## Patterns to Follow

### The mechanism as it exists today (this is the thing under test — do not rewrite it)
```python
# SOURCE: app/db/database.py:23-38
def init_db() -> None:
    with get_connection() as conn:
        conn.execute(CREATE_AUDIT_LOGS_TABLE)
        _add_missing_columns(conn)


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    """Brings a pre-existing audit_logs table up to the current schema.

    Additive only: existing rows keep their data and take the column default.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
    for name, ddl in AUDIT_LOGS_ADDED_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE audit_logs ADD COLUMN {name} {ddl}")
```
Matches the story's Technical Notes line for line: `PRAGMA table_info(audit_logs)`, applies only what is missing, called from `init_db()` *after* `CREATE TABLE IF NOT EXISTS`.

### The declaration mapping (contract carrier)
```python
# SOURCE: app/db/models.py:26-30
AUDIT_LOGS_ADDED_COLUMNS = {
    "pii_detected_input": "INTEGER NOT NULL DEFAULT 0",
    "pii_detected_output": "INTEGER NOT NULL DEFAULT 0",
    "pii_entities": "TEXT",
}
```
Column name to DDL fragment. Two entries declare `NOT NULL` and both carry a non-NULL `DEFAULT`; one is bare nullable `TEXT`. Both shapes must stay legal.

### Tests: env bootstrap before any `app.*` import
```python
# SOURCE: tests/test_db.py:1-4
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```
`Settings` has two required fields with no defaults, so importing `app.config` without these raises. Every test module in this repo opens with this block. New imports go *below* it.

### Tests: temp DB via monkeypatched settings singleton
```python
# SOURCE: tests/test_db.py:28-33
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
    init_db()
    return db_path
```
`_db_path()` reads `settings.DATABASE_URL` on every `get_connection()` call, so patching the attribute on the singleton is enough — no fixture teardown, `tmp_path` is per-test.

### Tests: hand-built legacy schema + survival assertions (the AC1 precedent, already green)
```python
# SOURCE: tests/test_db.py:44-105
def test_init_db_migrates_pre_pii_database(tmp_path, monkeypatch):
    """A database created before PRD-003 gains the PII columns and keeps its rows."""
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")

    legacy = sqlite3.connect(db_path)
    legacy.execute("""CREATE TABLE audit_logs (...14 pre-PII columns...)""")
    legacy.execute(
        "INSERT INTO audit_logs (timestamp, user_id, prompt_hash) VALUES (?, ?, ?)",
        ("2026-07-04T10:30:00Z", "juan@empresa.com", "abc123"),
    )
    legacy.commit()
    legacy.close()

    init_db()

    with get_connection() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
    assert {"pii_detected_input", "pii_detected_output", "pii_entities"} <= columns
    assert count_audit_logs() == 1
    preserved = get_audit_log(1)
    assert preserved.user_id == "juan@empresa.com"
    assert preserved.pii_detected_input is False
```
Raw `sqlite3.connect` for the fixture (bypassing `get_connection`, so the pre-migration shape is exact), then `init_db()`, then column-set + row-survival + insert-still-works assertions. **This test already satisfies AC1.**

### Tests: boolean identity assertions
```python
# SOURCE: tests/test_db.py:96-97
    assert preserved.pii_detected_input is False
    assert preserved.pii_entities is None
```
`is True` / `is False`, never `== True` — identity is what proves the `int()` to `bool()` round trip rather than a raw `1`/`0` leaking through.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | Generalize the `AUDIT_LOGS_ADDED_COLUMNS` comment: it currently reads as PRD-003-specific, and STORY-009 is about to add RBAC entries to the same mapping. Point at the guard test that enforces the NOT NULL/DEFAULT rule. Comment only — the dict's contents are untouched. |
| `tests/test_db.py` | UPDATE | Extract the pre-PII schema into a module-level helper; add four tests covering AC2, AC3, AC4, AC5. |

**No production logic changes.** `app/db/database.py` is deliberately **not** in this table — `init_db()` and `_add_missing_columns()` already implement the story exactly as its Technical Notes specify (Design Note 1).

**Explicitly NOT touched**:
- `app/db/database.py` — the mechanism is correct as written; changing it here would create merge surface for STORY-002 and STORY-009 for no gain
- `AUDIT_LOGS_ADDED_COLUMNS`' contents — adding `role` / `denied_permission` is STORY-009's scope, not this story's
- `CREATE_AUDIT_LOGS_TABLE` — likewise STORY-009
- `tests/test_db.py::test_schema_has_no_ip_or_location_column` — stays at its current 17-column set (Design Note 5)
- Anything under `app/services/`, `app/routers/`, `chat_ui/` — this story has no runtime-visible effect

---

## Design Notes (decisions worth stating up front)

1. **The story and PRD Risk 4 are stale; the mechanism shipped in `60835dc`.** The story says "`AUDIT_LOGS_ADDED_COLUMNS` ... starts empty; STORY-009 populates it", and the PRD says `main` has no migration mechanism ("`init_db()` is `CREATE TABLE IF NOT EXISTS` only"). Neither is true on `main` today: `git log --oneline` shows `60835dc feat(audit_logs): add PII columns migration ...`, landed on the PRD-004 epic and merged in `66a2ba5`, i.e. *after* the PRD-005 PRD was authored on 2026-08-28. The mapping ships with three PII entries and `_add_missing_columns` is wired into `init_db()`. **The correct response is not to re-implement it and not to empty the mapping** — emptying it would un-ship PRD-003's migration and break every deployment upgrading from a pre-PII database. It is to verify the mechanism against all five ACs and add the tests that are missing. Do not let an implementer read AC5's "Given the mapping ships empty" literally.

2. **AC5, read for its intent rather than its letter.** The AC wants proof that the *mechanism* works — not proof that today's three PII entries work, which `test_init_db_migrates_pre_pii_database` already gives. With the mapping non-empty, the durable form of that proof is to inject a **synthetic** entry at test time and assert it lands. That test keeps its value forever: it stays green and meaningful after STORY-009 adds two more real columns, whereas a test hardcoded to today's contents rots on every schema change. Task 3 implements this.

3. **AC3 is enforced by a test, not by a runtime check.** "Every `NOT NULL` entry also declares a non-NULL `DEFAULT`" is a property of a static module-level dict, and a dict literal only changes when someone edits code — which CI sees. A runtime `raise` inside `_add_missing_columns` would move that failure from a red test to a crashed startup (and `init_db()` runs on *every* Reflex hot reload, per `chat_ui/chat_ui/chat_ui.py:22`), which is strictly worse feedback for a developer mistake. The static guard also produces a precise message naming the offending column, where the runtime path produces a bare `sqlite3.OperationalError`. Task 2 implements the guard; Task 3's synthetic-column test is its executable counterpart. They are complementary, not redundant: the static guard catches a bad entry *before* anything exercises the legacy-database path.

4. **`monkeypatch.setitem`, never `monkeypatch.setattr`, for the mapping.** `app/db/database.py:5` binds the dict by name at import time (`from app.db.models import AUDIT_LOGS_ADDED_COLUMNS`), so `database.AUDIT_LOGS_ADDED_COLUMNS` and `models.AUDIT_LOGS_ADDED_COLUMNS` are two names for **one object**. `monkeypatch.setitem(AUDIT_LOGS_ADDED_COLUMNS, ...)` mutates that shared object in place and is visible to `_add_missing_columns` immediately; `monkeypatch.setattr(models, "AUDIT_LOGS_ADDED_COLUMNS", {...})` would rebind only the `models` name and the migration would silently keep using the original dict — a test that passes for the wrong reason. `setitem` also restores cleanly at teardown, which matters because the dict is process-global across the whole test session.

5. **`test_schema_has_no_ip_or_location_column` is a STORY-009 problem, not a STORY-001 problem.** That test (`tests/test_db.py:158-186`) asserts `set(columns) == expected` against a hardcoded 17-name set, so *any* schema addition fails it by design. This story adds no columns, so it stays green and untouched here. STORY-009 must extend it to 19 names — flagged in the handoff below so it is not discovered as a surprise failure.

6. **Repeated-call idempotence is proven by "does not raise".** A second `ALTER TABLE ... ADD COLUMN` for an existing column raises `sqlite3.OperationalError: duplicate column name`, so a migration that re-fires is not silently wasteful — it is fatal, and it would be fatal on *every Reflex hot reload* against a migrated database. Task 5's three consecutive `init_db()` calls on a legacy file are therefore a real guarantee, not a formality. Task 4 additionally proves the stronger AC2 claim — that **no `ALTER` is issued at all** — via `sqlite3.Connection.set_trace_callback` (verified available: Python 3.13.3, SQLite 3.49.1), because "did not raise" and "did not execute" are different assertions and AC2 asks for the second.

7. **The `_add_missing_columns` signature stays `audit_logs`-specific.** It is tempting to generalize it to `(conn, table, columns)` now that STORY-002 is adding a `users` table. Resist it: `users` is a brand-new table created by `CREATE TABLE IF NOT EXISTS` with no legacy shape to migrate, so it needs nothing from this mechanism, and the constant is named `AUDIT_LOGS_ADDED_COLUMNS` precisely because the story scopes it to one table. Generalize when a second table actually needs migrating.

8. **Pre-existing issues observed and deliberately left alone.** (a) `with get_connection() as conn:` commits but never closes the connection — `sqlite3`'s context manager is a transaction manager, not a resource manager — so every helper in `app/db/database.py` leaks a connection, and `init_db()` leaks one per Reflex reload. It is module-wide, pre-existing, and unrelated to migration correctness. (b) The repo-root `harness_ai.db` is a real developer database; running the app after this story migrates it in place, which is additive and harmless. Neither belongs in this story's diff.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Verify the mechanism is present and the baseline is green (no code)

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**: Confirm Design Note 1 before writing anything, so nothing gets re-implemented:
  - `app/db/models.py` contains `AUDIT_LOGS_ADDED_COLUMNS` with the three PII entries.
  - `app/db/database.py` contains `_add_missing_columns(conn)` and `init_db()` calls it **after** `conn.execute(CREATE_AUDIT_LOGS_TABLE)`.
  - `tests/test_db.py::test_init_db_migrates_pre_pii_database` exists and passes — this is AC1, already satisfied.
  - **If any of the above is missing**, stop and re-plan: the branch is not where this plan assumes it is.
  - **Do not** empty `AUDIT_LOGS_ADDED_COLUMNS` to match the story's stale "ships empty" wording (Design Note 1).
- **Mirror**: — (verification gate; same shape as the PRD-003 STORY-003 plan's Task 6 full-suite gate)
- **Validate**:
  ```bash
  cd /f/AI/harness-ai
  grep -n "AUDIT_LOGS_ADDED_COLUMNS" app/db/models.py app/db/database.py
  grep -n "_add_missing_columns" app/db/database.py
  .venv/Scripts/python.exe -m pytest tests/test_db.py -q
  ```
  Expect `23 passed`, with `_add_missing_columns` defined at `app/db/database.py:29` and called at line 26.

### Task 2: Add the DDL-contract guard test (AC3)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  - Change the existing import at `tests/test_db.py:26` from `from app.db.models import AuditLog` to `from app.db.models import AUDIT_LOGS_ADDED_COLUMNS, AuditLog`.
  - Add this test immediately after `test_init_db_creates_table`:
    ```python
    def test_added_columns_declaring_not_null_also_declare_a_default():
        """SQLite rejects ALTER TABLE ... ADD COLUMN NOT NULL without a DEFAULT.

        A violation only surfaces against a database that predates the column, so
        it passes every fresh-database test and breaks on exactly the deployments
        the migration exists to serve.
        """
        for name, ddl in AUDIT_LOGS_ADDED_COLUMNS.items():
            declaration = ddl.upper()
            if "NOT NULL" in declaration:
                assert "DEFAULT" in declaration, (
                    f"{name}: NOT NULL requires a DEFAULT -- "
                    f"SQLite rejects ADD COLUMN NOT NULL without one"
                )
                assert "DEFAULT NULL" not in declaration, (
                    f"{name}: DEFAULT NULL does not satisfy NOT NULL"
                )
    ```
  - Takes no fixture: it asserts on a module constant and touches no database.
- **Mirror**: `tests/test_db.py:1-4` (import block placement), `app/db/models.py:26-30` (the mapping being asserted on).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_db.py::test_added_columns_declaring_not_null_also_declare_a_default -v` — passes against today's three entries (two `INTEGER NOT NULL DEFAULT 0`, one bare `TEXT`).

### Task 3: Prove the mechanism applies *any* declared column (AC5)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: Add after the Task 2 test:
  ```python
  def test_add_missing_columns_applies_any_declared_column(tmp_path, monkeypatch):
      """The mechanism is proven independently of whichever columns the mapping
      happens to hold today, so this stays meaningful after STORY-009 adds more."""
      db_path = tmp_path / "synthetic.db"
      monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
      init_db()
      insert_audit_log(
          AuditLog(
              timestamp="2026-08-28T10:00:00Z",
              user_id="ana@empresa.com",
              prompt_hash="abc123",
          )
      )

      # setitem, not setattr: app/db/database.py binds this dict by name at import,
      # so both modules share one object and only in-place mutation is visible.
      monkeypatch.setitem(
          AUDIT_LOGS_ADDED_COLUMNS, "synthetic_flag", "INTEGER NOT NULL DEFAULT 7"
      )

      init_db()

      with get_connection() as conn:
          columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
          row = conn.execute(
              "SELECT synthetic_flag FROM audit_logs WHERE id = 1"
          ).fetchone()

      assert "synthetic_flag" in columns
      assert row["synthetic_flag"] == 7  # the pre-existing row took the declared default
      assert count_audit_logs() == 1     # and nothing was lost
  ```
  - `settings`, `init_db`, `insert_audit_log`, `get_connection`, `count_audit_logs`, and `AuditLog` are all already imported (`tests/test_db.py:11-26`); only `AUDIT_LOGS_ADDED_COLUMNS` is new, added in Task 2.
  - `DEFAULT 7` rather than `DEFAULT 0` deliberately: `0` is indistinguishable from a zero-fill, `7` proves the declared default was actually applied.
- **Mirror**: `tests/test_db.py:28-33` (the `monkeypatch.setattr(settings, "DATABASE_URL", ...)` temp-DB idiom), `tests/test_db.py:85-88` (`PRAGMA table_info` column-set assertion).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_db.py::test_add_missing_columns_applies_any_declared_column -v`

### Task 4: Prove no `ALTER` is issued against a current schema (AC2)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  - Add `from app.db import database` below the existing `from app.db.database import (...)` block (`tests/test_db.py:8-25`) — the module object is needed to monkeypatch the name `init_db` resolves at call time.
  - Add this test after the Task 3 test:
    ```python
    def test_init_db_issues_no_alter_when_schema_is_current(temp_db, monkeypatch):
        """A no-op run must not re-issue ALTER: init_db() runs on every Reflex
        hot reload, and a redundant ADD COLUMN is fatal, not merely wasteful."""
        statements: list[str] = []
        real_get_connection = database.get_connection

        def traced() -> sqlite3.Connection:
            conn = real_get_connection()
            conn.set_trace_callback(statements.append)
            return conn

        monkeypatch.setattr(database, "get_connection", traced)

        init_db()  # temp_db already migrated this database to the current schema

        assert statements, "trace callback captured nothing -- the patch did not take"
        assert not any("ALTER" in sql.upper() for sql in statements), statements
    ```
  - `sqlite3` is already imported (`tests/test_db.py:6`).
  - The `assert statements` line is not filler: without it, a monkeypatch that silently failed to take would make the `ALTER` assertion vacuously true.
  - Patch `database.get_connection`, **not** the `get_connection` imported into the test module — `init_db` resolves the name from `app.db.database`'s globals at call time.
- **Mirror**: `tests/test_db.py:28-33` (the `temp_db` fixture supplies an already-current schema), `app/db/database.py:23-26` (the `init_db` body whose statements are being traced).
- **Validate**: `.venv/Scripts/python.exe -m pytest tests/test_db.py::test_init_db_issues_no_alter_when_schema_is_current -v`

### Task 5: Prove repeated `init_db()` calls stay idempotent on a legacy file (AC4)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  - First extract the pre-PII schema so it is written once. Add a module-level helper immediately above `test_init_db_migrates_pre_pii_database`:
    ```python
    def _create_pre_pii_database(db_path) -> None:
        """Builds the 14-column audit_logs table exactly as it shipped before PRD-003.

        Uses raw sqlite3.connect rather than get_connection() so the fixture is the
        genuine pre-migration shape, unaffected by whatever init_db() does today.
        """
        legacy = sqlite3.connect(db_path)
        legacy.execute(
            """
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id TEXT NOT NULL,
                device TEXT,
                prompt_hash TEXT NOT NULL,
                prompt_preview TEXT,
                response_hash TEXT,
                response_preview TEXT,
                model_used TEXT,
                tokens_used INTEGER,
                was_duplicate_blocked INTEGER NOT NULL DEFAULT 0,
                suspicious_pattern TEXT,
                success INTEGER NOT NULL DEFAULT 1,
                error_message TEXT
            )
            """
        )
        legacy.execute(
            "INSERT INTO audit_logs (timestamp, user_id, prompt_hash) VALUES (?, ?, ?)",
            ("2026-07-04T10:30:00Z", "juan@empresa.com", "abc123"),
        )
        legacy.commit()
        legacy.close()
    ```
  - Replace the inline `legacy = sqlite3.connect(...)` ... `legacy.close()` block inside `test_init_db_migrates_pre_pii_database` with a single `_create_pre_pii_database(db_path)` call. **Leave that test's docstring and every one of its assertions byte-for-byte unchanged** — this is a setup extraction, not a behavior change, and the test must still pass without any assertion being touched.
  - Then add the new test after it:
    ```python
    def test_init_db_migration_is_idempotent_across_repeated_calls(tmp_path, monkeypatch):
        """Reflex calls init_db() on every hot reload; a second ADD COLUMN for an
        existing column raises sqlite3.OperationalError: duplicate column name."""
        db_path = tmp_path / "legacy.db"
        monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")
        _create_pre_pii_database(db_path)

        init_db()
        init_db()
        init_db()

        with get_connection() as conn:
            columns = [
                row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")
            ]

        assert {"pii_detected_input", "pii_detected_output", "pii_entities"} <= set(columns)
        assert len(columns) == len(set(columns)), "a column was added twice"
        assert count_audit_logs() == 1
        preserved = get_audit_log(1)
        assert preserved.user_id == "juan@empresa.com"
    ```
- **Mirror**: `tests/test_db.py:44-105` (legacy-database fixture and survival assertions), `tests/test_db.py:36-42` (`init_db()` called twice as the existing idempotence precedent).
- **Validate**:
  ```bash
  .venv/Scripts/python.exe -m pytest tests/test_db.py -k "migrat or idempotent" -v
  ```
  Both the extracted-setup original and the new repeated-call test pass.

### Task 6: Generalize the mapping's comment beyond PRD-003

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**: Replace the comment block above `AUDIT_LOGS_ADDED_COLUMNS` (lines 22-25) with:
  ```python
  # Columns added after the initial schema shipped (PRD-003 PII telemetry; PRD-005
  # RBAC adds to this in STORY-009). CREATE TABLE IF NOT EXISTS is a no-op against
  # a database created before they existed, so init_db() ALTERs in whichever of
  # these an old file is missing.
  # Additive only: no drops, renames, or type changes.
  # Every NOT NULL entry needs a non-NULL DEFAULT -- SQLite rejects ADD COLUMN
  # NOT NULL without one. Enforced by
  # tests/test_db.py::test_added_columns_declaring_not_null_also_declare_a_default.
  ```
  The dict itself and every other line in the file are untouched. This is the one production-file change in the story, and it is a comment: the mapping is about to stop being PRD-003-only, and the NOT NULL rule now has a named enforcer worth pointing at.
- **Mirror**: `app/db/models.py:22-25` (existing comment voice — it states the failure mode, not just the rule).
- **Validate**: `.venv/Scripts/python.exe -c "from app.db.models import AUDIT_LOGS_ADDED_COLUMNS; print(AUDIT_LOGS_ADDED_COLUMNS)"` — prints the same three entries as before, proving the edit was comment-only.

### Task 7: Full-suite regression and diff gate

- **File**: — (no file change)
- **Action**: VERIFY
- **Implement**:
  - Run the entire suite. Expect `tests/test_db.py` at 23 + 4 = **27 passed**, with **no** pre-existing test modified except the setup extraction inside `test_init_db_migrates_pre_pii_database` (Task 5).
  - `git diff --name-only` must list **exactly** `app/db/models.py` and `tests/test_db.py`. Anything else — especially `app/db/database.py` — means the mechanism was rewritten instead of verified (Design Note 1); revert it.
  - Confirm `app/db/database.py` is byte-identical to `main`.
- **Mirror**: the PRD-003 STORY-003 plan's Task 6 — same "prove the change is invisible to existing callers" gate.
- **Validate**:
  ```bash
  cd /f/AI/harness-ai
  .venv/Scripts/python.exe -m pytest -q
  git diff --name-only
  git diff --stat app/db/database.py   # must be empty
  ```

---

## End-to-End Tests

Checks for `/implement` to execute:

- [ ] `.venv/Scripts/python.exe -m pytest tests/test_db.py -v` — 27 tests pass (23 existing + 4 new)
- [ ] `.venv/Scripts/python.exe -m pytest -q` — full suite green
- [ ] `git diff --name-only` — exactly `app/db/models.py` and `tests/test_db.py`; `app/db/database.py` is **not** listed
- [ ] Migration against a real file, not just a `tmp_path` fixture: build a 14-column pre-PII database at a scratch path, point `DATABASE_URL` at it, call `init_db()` twice, and confirm 17 distinct columns plus the probe row intact:
  ```bash
  .venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('probe.db'); c.executescript(\"CREATE TABLE audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, user_id TEXT NOT NULL, device TEXT, prompt_hash TEXT NOT NULL, prompt_preview TEXT, response_hash TEXT, response_preview TEXT, model_used TEXT, tokens_used INTEGER, was_duplicate_blocked INTEGER NOT NULL DEFAULT 0, suspicious_pattern TEXT, success INTEGER NOT NULL DEFAULT 1, error_message TEXT); INSERT INTO audit_logs (timestamp,user_id,prompt_hash) VALUES ('2026-01-01T00:00:00Z','probe','h');\"); c.commit()"
  DATABASE_URL=sqlite:///probe.db .venv/Scripts/python.exe -c "from app.db.database import init_db, count_audit_logs, get_connection; init_db(); init_db(); print(len([r['name'] for r in get_connection().execute('PRAGMA table_info(audit_logs)')]), count_audit_logs())"
  ```
  expect `17 1`; then delete `probe.db`
- [ ] `uvicorn app.main:app --reload` — starts without error; `init_db()` in the lifespan migrates the repo-root `harness_ai.db` in place (additive, Design Note 8b)
- [ ] `curl http://localhost:8000/health` — returns `{"status":"ok"}`
- [ ] `.venv/Scripts/python.exe -c "import sqlite3; print([r[1] for r in sqlite3.connect('harness_ai.db').execute('PRAGMA table_info(audit_logs)')])"` — 17 columns, no duplicates
- [ ] Reflex ingress: `cd chat_ui && reflex run` — starts and hot-reloads without a `duplicate column name` error (the AC4 guarantee under its real caller, `chat_ui/chat_ui/chat_ui.py:22`)

---

## Validation

```bash
cd /f/AI/harness-ai
.venv/Scripts/python.exe -m pytest tests/test_db.py -v
.venv/Scripts/python.exe -m pytest -q
git diff --name-only
git diff --stat app/db/database.py
.venv/Scripts/python.exe -c "from app.db.models import AUDIT_LOGS_ADDED_COLUMNS; print(AUDIT_LOGS_ADDED_COLUMNS)"
curl http://localhost:8000/health
```

---

## Handoff to downstream stories

- **STORY-009** adds `role TEXT` and `denied_permission TEXT` to **both** `CREATE_AUDIT_LOGS_TABLE` and `AUDIT_LOGS_ADDED_COLUMNS`. Both are nullable `TEXT`, so the Task 2 guard passes trivially. STORY-009 **must** extend `test_schema_has_no_ip_or_location_column`'s hardcoded `expected` set from 17 to 19 names (Design Note 5) — that failure is expected maintenance of a schema-pinning test, not a regression. Its `ip`/`location` substring assertion must be left exactly as-is; both new names were checked and contain neither substring.
- **STORY-002** creates the `users` table via a plain `CREATE TABLE IF NOT EXISTS` next to the audit table in `init_db()`. It needs nothing from this mechanism (Design Note 7) — no legacy `users` table exists anywhere.

---

## Acceptance Criteria

(Copied from story `STORY-001`)

- [ ] Given a database whose `audit_logs` table predates a column listed in `AUDIT_LOGS_ADDED_COLUMNS`, when `init_db()` runs, then the column is added via `ALTER TABLE ... ADD COLUMN` and existing rows take its default — *already satisfied by `test_init_db_migrates_pre_pii_database`; confirmed in Task 1 and re-proven generically in Task 3*
- [ ] Given a database already at the current schema, when `init_db()` runs, then no `ALTER` is issued and the call is a no-op — *Task 4*
- [ ] Given an entry declaring `NOT NULL`, when it is applied, then it also declares a non-NULL `DEFAULT`, because SQLite rejects `ADD COLUMN NOT NULL` without one — *Task 2*
- [ ] Given `init_db()` is called repeatedly, when it runs, then it stays idempotent — Reflex calls it on every hot reload — *Task 5*
- [ ] Given the mapping ships empty, when the suite runs, then a fixture database built from the pre-migration schema proves a synthetic column is added and existing rows survive — *Task 3, read for intent per Design Note 2: the mapping does **not** ship empty and must not be emptied; the synthetic-column injection is the durable form of this proof*
- [ ] All tasks completed
- [ ] Backend server starts without error
- [ ] Full pytest suite green (27 tests in `tests/test_db.py`)
- [ ] `app/db/database.py` unchanged — the mechanism was verified, not rewritten
- [ ] Follows existing patterns
