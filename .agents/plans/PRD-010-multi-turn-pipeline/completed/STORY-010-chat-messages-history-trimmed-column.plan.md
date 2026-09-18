---
story: STORY-010
prd: PRD-010
slug: chat-messages-history-trimmed-column
title: "chat_messages.history_trimmed column, converged by init_db()"
type: NEW_CAPABILITY
complexity: LOW
epic_branch: epic/PRD-010-multi-turn-pipeline
created: 2026-09-18
---

# Plan: chat_messages.history_trimmed column, converged by init_db()

## Summary

Add a nullable `history_trimmed INTEGER` column to `chat_messages`, declared in both `CREATE_CHAT_MESSAGES_TABLE` and a new `CHAT_MESSAGES_ADDED_COLUMNS = {"history_trimmed": "INTEGER"}`, and add `StoredMessage.history_trimmed: Optional[int] = None`. Generalize `_add_missing_columns` from an `audit_logs`-only function to one that takes `(conn, table, columns)`, and call it twice inside `init_db()`'s single `_session()` block: once for `audit_logs` where it sits today, once for `chat_messages` immediately after `CREATE_CHAT_MESSAGES_TABLE`. Thread the column through `append_chat_message`'s INSERT and `_row_to_stored_message`. Nothing writes a non-NULL value yet — STORY-012 does, through `ChatMessage` → `_to_stored_message`.

Exploration turned up five facts the story text does not mention:

1. **The parameterized signature is forced by statement ordering, not by taste.** The story offers "a `(table, columns)` pair list, or a sibling pass". A single call iterating a pair list cannot stay where `_add_missing_columns(conn)` is today (`app/db/database.py:677`), because `chat_messages` does not exist yet at that point on a fresh database — `PRAGMA table_info(chat_messages)` returns no rows, which is indistinguishable from "the table exists and is missing every column", and the loop would issue `ALTER TABLE chat_messages ADD COLUMN` against a missing table. Moving the single call below `CREATE_CHAT_MESSAGES_TABLE` is worse: `CREATE_AUDIT_LOGS_DEDUP_INDEX` must run after the `audit_logs` column add (`app/db/models.py:63-70`), so the audit pass cannot move. Two calls of a parameterized function is the only arrangement that keeps both orderings, and it is `table → columns → index` twice rather than a new shape.
2. **`tests/test_chat_state.py:2216-2250` fails the moment `StoredMessage` gains a field.** `test__to_chat_message_reads_every_stored_field` (AST walk) computes `expected = {f.name for f in fields(StoredMessage)} - {"session_id", "created_at", "id"}` and asserts `expected <= read`. `ChatMessage` has no `history_trimmed` field and `_to_chat_message` cannot read one until STORY-012 adds it. The fix is **not** a hardcoded fourth exclusion: derive the exclusion set from `ChatMessage.model_fields` (pydantic v2, 2.13.5 installed), so a stored field is excused exactly while the bubble has nowhere to put it, and pin the derived set against a literal so STORY-012 adding the field to `ChatMessage` fails this test until it also maps it. That is strictly stronger than what is there now and removes the need for anyone to remember.
3. **Three chat-table tests pass unchanged, and that is worth knowing before editing them.** `test_chat_messages_table_matches_its_ddl` (`tests/test_db.py:2014`) compares `PRAGMA table_info` **in declaration order** against `_declared_columns(CREATE_CHAT_MESSAGES_TABLE)` — so the new column must be declared **last** in the DDL, where an `ALTER` would also put it. `test_stored_message_mirrors_the_chat_messages_columns` (`:1823`) is a set comparison that stays green because the field and the column land together. `test_each_of_the_seven_kinds_round_trips_unchanged` (`tests/test_chat_sessions.py:690`) iterates a literal field tuple; adding `history_trimmed` to it is a one-line strengthening, not a repair.
4. **Two existing race harnesses change behaviour and both stay correct.** `_StaleReadConnection` (`tests/test_db.py:2886`) blanks *every* `PRAGMA table_info`, so after this story it also makes the `chat_messages` pass attempt an `ALTER` that fails with `duplicate column name` and converges — which is free extra evidence, and Task 8 asserts it. `_GatedConnection` (`:2895`) gates on every `PRAGMA table_info`, so each thread now hits the barrier twice; `threading.Barrier` is reusable and both threads run the identical path, so the cycles match. A mismatch would raise `BrokenBarrierError` inside the 30 s timeout and fail loudly rather than hang.
5. **Nothing outside `app/db/` lists the `chat_messages` columns.** `scripts/migrate_to_turso.py` covers `("audit_logs", "users")` only (`:64`). `tests/test_two_instance_smoke.py:655` deliberately asserts containment, not the full column set, and says why. `app/services/chat_sessions.py` passes `StoredMessage` through whole. Every `StoredMessage(...)` construction in the repo is by keyword, so a new defaulted field breaks none of them.

There is no linter or formatter in this repo. "Validate" means pytest against the local libSQL dev server (`tests/conftest.py:132-152`).

## User Story

As an **end user**
I want the "earlier exchanges were not sent" note to survive a reload
So that a restored chat tells me the same thing the live one did.

## Story Reference

- Story file: `.agents/stories/PRD-010-multi-turn-pipeline/STORY-010-chat-messages-history-trimmed-column.md`
- PRD: `.agents/PRDs/PRD-010-multi-turn-pipeline/PRD.md`, Sections 4 (History), 6.8, 6.9, 11 (fit/footer persisted)
- Depends on: none
- Blocks: STORY-012 (writes the value through `ChatMessage` → `_to_stored_message`)
- Precedent: `.agents/plans/PRD-009-duplicate-rescoping/completed/STORY-002-dedup-key-column-and-index.plan.md`, `.agents/plans/PRD-008-chat-sessions/completed/STORY-003-init-db-tables-and-audit-column.plan.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (additive schema: column + dataclass field + round trip, no writer yet) |
| Complexity | LOW |
| Systems Affected | `app/db/models.py`, `app/db/database.py`, `tests/test_db.py`, `tests/test_chat_sessions.py`, `tests/test_chat_state.py` |
| Story | STORY-010 |
| PRD | PRD-010 |
| Epic Branch | `epic/PRD-010-multi-turn-pipeline` (commit directly on this branch) |

---

## Skills In Use

I listed `.agents/skills/` in full. It holds exactly one skill:

| Skill | Applies? | Reason |
|-------|----------|--------|
| `frontend-design` | **No** | Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story edits the storage layer and three test modules and renders nothing. STORY-013 owns the footer that displays this column. |

The story's `skills:` frontmatter is `[]` and its Technical Notes say "Skills: none applicable." **No skill constrains any task below.**

---

## Patterns to Follow

### Naming: an added-columns mapping, declared twice, commented with its PRD

```python
# SOURCE: app/db/models.py:43-58
AUDIT_LOGS_ADDED_COLUMNS = {
    ...
    # PRD-009: the per-caller duplicate key, derived from a conversation rather
    # than a string (PRD Section 6.2). Nullable with no default on purpose --
    # rows written before the column existed stay NULL and are never backfilled
    # (D6), and a NULL key can never match a duplicate lookup.
    "dedup_key": "TEXT",
}
```

### Bootstrap block: one `_session()`, `table → columns → index` per table

```python
# SOURCE: app/db/database.py:674-684
    check_database_reachable()
    with _session() as conn:
        conn.execute(CREATE_AUDIT_LOGS_TABLE)
        _add_missing_columns(conn)
        conn.execute(CREATE_AUDIT_LOGS_DEDUP_INDEX)
        conn.execute(CREATE_USERS_TABLE)
        conn.execute(CREATE_USERS_TOKEN_HASH_INDEX)
        conn.execute(CREATE_CHAT_SESSIONS_TABLE)
        conn.execute(CREATE_CHAT_SESSIONS_USER_INDEX)
        conn.execute(CREATE_CHAT_MESSAGES_TABLE)
        conn.execute(CREATE_CHAT_MESSAGES_SESSION_INDEX)
```

### Error handling: the read/ALTER pair, and the single tolerated failure

```python
# SOURCE: app/db/database.py:719-728
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
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

The pre-check is what makes a steady-state boot issue no `ALTER` at all (`init_db()` re-runs on every Reflex hot reload); `_is_duplicate_column` requires the driver to name *the column being added*, so a locked or unreachable database still propagates. Neither property may weaken when the function is parameterized.

### Row mapper: coerce only what the type demands

```python
# SOURCE: app/db/database.py:1624-1640
    return StoredMessage(
        ...
        pii_redacted=bool(row["pii_redacted"]),
        ...
    )
```

`tokens_used` and `audit_id` are `INTEGER` against `Optional[int]` and are pointedly **not** coerced: `int()` around them turns a genuine `NULL` into `0`. `history_trimmed` is the same shape and takes the same treatment — and here the lie would be worse, since `0` means "nothing was dropped" and `NULL` means "this row predates the feature".

### Tests: migration fixture whose new column is the only one in flight

```python
# SOURCE: tests/test_db.py:361-372
def _create_pre_dedup_key_database(connect, url) -> None:
    """Builds the 20-column audit_logs table exactly as it shipped before
    PRD-009 -- after PRD-008's session_id, before dedup_key -- with no index.

    The fourth of these fixtures, and the only one where `dedup_key` is the sole
    column in flight, for the reason `_create_pre_chat_sessions_database` gives
    about `session_id`. The row carries a session_id so a test can show the
    migration preserved it rather than rewrote it.
    """
```

### Tests: the forced race

```python
# SOURCE: tests/test_db.py:3099-3132
    _create_pre_dedup_key_database(db_connect, uninitialized_db)
    gate = threading.Barrier(2, timeout=30)
    _install(monkeypatch, lambda conn: _GatedConnection(conn, gate))

    failures = _run_concurrently(2, init_db)

    assert not failures, f"a concurrent init_db() raised: {failures}"

    monkeypatch.undo()
    with get_connection() as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")]

    assert columns.count("dedup_key") == 1, columns
```

### Tests: the built column's nullability, read off PRAGMA

```python
# SOURCE: tests/test_db.py:1922-1928
def test_init_db_adds_a_nullable_dedup_key_column(temp_db):
    with get_connection() as conn:
        info = {row["name"]: row for row in conn.execute("PRAGMA table_info(audit_logs)")}

    assert info["dedup_key"]["type"] == "TEXT"
    assert info["dedup_key"]["notnull"] == 0
    assert info["dedup_key"]["dflt_value"] is None
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | `history_trimmed INTEGER` last in `CREATE_CHAT_MESSAGES_TABLE`; new `CHAT_MESSAGES_ADDED_COLUMNS`; `StoredMessage.history_trimmed` |
| `app/db/database.py` | UPDATE | `_add_missing_columns(conn, table, columns)`; second call after `CREATE_CHAT_MESSAGES_TABLE`; `init_db` docstring; `append_chat_message` INSERT; `_row_to_stored_message` |
| `tests/test_db.py` | UPDATE | Constants, built table, pre-PRD-010 fixture + migration, ALTER-after-CREATE ordering, steady state, stale read, forced race; one docstring correction |
| `tests/test_chat_sessions.py` | UPDATE | Round trip `history_trimmed=3` and absent-reads-`None`; extend the seven-kinds field tuple |
| `tests/test_chat_state.py` | UPDATE | Derive `_to_chat_message`'s excused fields from `ChatMessage.model_fields`, pinned against a literal that STORY-012 must update |

No files are created. `chat_ui/chat_ui/models.py`, `chat_ui/chat_ui/state.py`, `app/services/chat_sessions.py`, `app/routers/*` and `scripts/migrate_to_turso.py` are **not touched**.

---

## Tasks

Execute in order. Each task is atomic + verifiable. Tasks 1–3 are production code; Tasks 4–10 are tests and verification.

### Task 1: Declare the column, the mapping and the dataclass field

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**:
  1. `CREATE_CHAT_MESSAGES_TABLE`: change `    detail TEXT` to `    detail TEXT,` and add `    history_trimmed INTEGER` as the **last** column. One column per line, no table constraints — `_declared_columns` in the tests splits on lines and `test_chat_messages_table_matches_its_ddl` compares in declaration order against `PRAGMA table_info`, which appends an `ALTER`ed column at the end.
  2. Directly below the DDL, add:
     ```python
     CHAT_MESSAGES_ADDED_COLUMNS = {"history_trimmed": "INTEGER"}
     ```
     with a comment in `AUDIT_LOGS_ADDED_COLUMNS`' style (`:29-42`): the second such mapping, so `init_db()` converges a pre-PRD-010 `chat_messages` the same way it converges `audit_logs`. Say that every entry is also declared in the CREATE above and why the pair is not redundant. Say the column is **nullable with no default on purpose**: `NULL` means "written before this PRD", `0` means "this send dropped nothing", and a `NOT NULL DEFAULT 0` would erase that distinction on every restored row. Note that nothing writes a non-NULL value until STORY-012.
  3. `StoredMessage`: add `history_trimmed: Optional[int] = None` after `detail` and **before** `created_at`/`id`, so the dataclass mirrors the table's declaration order and `id` stays the trailing field. Comment it: PRD-010, the count of whole exchanges `chat_history.fit` dropped from this send (STORY-011), carried on the assistant row so a reload renders the same footer note as the live bubble (STORY-013). `Optional[int]`, not `int`, for the reason in item 2.
  4. Update the `CREATE_CHAT_MESSAGES_TABLE` header comment (`:139-157`) where it says the table mirrors `ChatMessage` field for field: note that as of PRD-010 STORY-010 the column exists before the `ChatMessage` field does, and STORY-012 closes that gap.
- **Mirror**: `app/db/models.py:29-58` (mapping + comments), `:184-196` (field comment), `:233-256` (dataclass shape)
- **Validate**: `python -c "from app.db.models import CHAT_MESSAGES_ADDED_COLUMNS, CREATE_CHAT_MESSAGES_TABLE, StoredMessage; assert CHAT_MESSAGES_ADDED_COLUMNS == {'history_trimmed': 'INTEGER'}; assert CREATE_CHAT_MESSAGES_TABLE.rstrip().rstrip(')').rstrip().endswith('history_trimmed INTEGER'); assert StoredMessage(session_id='s', kind='user', content='c').history_trimmed is None"`

### Task 2: Generalize `_add_missing_columns` and give `chat_messages` its pass

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  1. Add `CHAT_MESSAGES_ADDED_COLUMNS` to the `from app.db.models import (...)` block, keeping the existing sort (after `AUDIT_LOGS_ADDED_COLUMNS`, before `CREATE_AUDIT_LOGS_DEDUP_INDEX`).
  2. Change the signature to `def _add_missing_columns(conn: _Connection, table: str, columns: dict[str, str]) -> None:` and replace the two hardcoded `audit_logs` occurrences with `table` — the `PRAGMA table_info({table})` read and the `ALTER TABLE {table} ADD COLUMN ...`. The loop iterates `columns.items()`. **Nothing else in the body changes**: the `if name in existing: continue` pre-check, the `_translated()` wrapper around the single `ALTER`, and the `_is_duplicate_column(exc, name)` re-raise stay exactly as they are.
  3. Keep the docstring's race reasoning intact (the AC requires it). Generalize only the wording: "Brings a pre-existing `table` up to the current schema", and note in a short added paragraph that PRD-010 STORY-010 made the function take its table and mapping because `chat_messages` needs the same convergence and `init_db()` must run the two passes at different points in the block — the `audit_logs` pass before `CREATE_AUDIT_LOGS_DEDUP_INDEX`, the `chat_messages` pass after `CREATE_CHAT_MESSAGES_TABLE`, because a `PRAGMA` against a table that does not exist yet reports "no columns" and would `ALTER` a missing table.
  4. In `init_db()`: change line 677 to `_add_missing_columns(conn, "audit_logs", AUDIT_LOGS_ADDED_COLUMNS)` (same position, immediately before `CREATE_AUDIT_LOGS_DEDUP_INDEX`), and insert `_add_missing_columns(conn, "chat_messages", CHAT_MESSAGES_ADDED_COLUMNS)` **between** `conn.execute(CREATE_CHAT_MESSAGES_TABLE)` and `conn.execute(CREATE_CHAT_MESSAGES_SESSION_INDEX)`. Same `_session()` block — no second block; `test_init_db_issues_no_alter_when_schema_is_current` counts connections (`== 2`).
  5. Extend the `init_db` docstring with a PRD-010 paragraph in the voice of the PRD-008/PRD-009 ones already there: this PRD adds one column to `chat_messages`, the second table to need a column convergence, so the pass that `audit_logs` has had since STORY-007 is now run for it too. Its position is load-bearing in the same way the dedup index's is, for the opposite reason: it must come *after* the CREATE, since on a fresh database the table does not exist until then. Steady-state cost is one more `PRAGMA table_info` and no `ALTER`.
  6. **Do not touch `_is_duplicate_column`.** If a task appears to need that, stop.
- **Mirror**: `app/db/database.py:674-684` (block), `:687-730` (function)
- **Validate**: `pytest tests/test_db.py -q -k "init_db or add_missing_columns or racing"` — the whole existing bootstrap, migration, stale-read, race and no-ALTER set stays green against the parameterized function before any new test is written

### Task 3: Write and read `history_trimmed` on the transcript path

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  1. `append_chat_message` (`:1643-1736`): add `history_trimmed` to the INSERT column list after `detail`, add a **15th** `?` to the `SELECT ?, ?, ...` row, and append `message.history_trimmed,` to the values tuple after `message.detail,` and **before** the trailing `session_id, user_id` pair that feeds the `WHERE EXISTS`. Count them: 15 columns, 15 placeholders in the SELECT, 15 values followed by the 2 predicate values. No `or None` and no `int()` — the field is already `Optional[int]` and `0` is a meaningful value that `or None` would destroy (unlike `pii_entities`, where `""` and `NULL` mean the same thing).
  2. `_row_to_stored_message` (`:1609-1640`): add `history_trimmed=row["history_trimmed"],` after `detail=row["detail"],`. No coercion, and extend the docstring's existing "`tokens_used` and `audit_id` are pointedly *not* coerced" paragraph to name `history_trimmed` alongside them, with the reason specific to it: `0` is "this send dropped nothing" and `NULL` is "this row predates the feature", and `int()` would report the second as the first on every restored pre-PRD row.
- **Mirror**: the `detail` threading in the same two functions; `:1616-1623` (the no-coercion paragraph)
- **Validate**: `pytest tests/test_chat_sessions.py -q` (every existing round-trip test passes with the extra column in flight)

### Task 4: Make `_to_chat_message`'s coverage test derive its exclusions

- **File**: `tests/test_chat_state.py`
- **Action**: UPDATE
- **Implement**: in the test at `:2216-2250` (the AST walk over `_to_chat_message`), replace the hardcoded
  ```python
  expected = {f.name for f in dataclasses.fields(StoredMessage)} - {
      "session_id",
      "created_at",
      "id",
  }
  ```
  with a set derived from the bubble model, plus a pin:
  ```python
  # Excused = the stored fields ChatMessage has nowhere to put. Derived rather
  # than listed, so a field is excused exactly while the bubble lacks it:
  # PRD-010 STORY-010 adds chat_messages.history_trimmed, and STORY-012 adds
  # ChatMessage.history_trimmed -- at which moment this set shrinks by itself
  # and the mapping becomes required.
  stored = {f.name for f in dataclasses.fields(StoredMessage)}
  excused = stored - set(ChatMessage.model_fields)
  assert excused == {"session_id", "created_at", "id", "history_trimmed"}, excused
  expected = stored - excused
  ```
  Update the docstring's "`session_id`, `created_at` and `id` are excluded" sentence accordingly, naming `history_trimmed` and STORY-012. Add the `ChatMessage` import if the module does not already have one (it does — `_fields(bubble: ChatMessage)` at `:1731`; confirm rather than assume).
- **Mirror**: `tests/test_chat_state.py:2216-2250`
- **Validate**: `pytest tests/test_chat_state.py -q -k "to_chat_message or stored"` → green. Then, as a deliberate check that the trap is live, temporarily add `history_trimmed: int = 0` to `chat_ui/chat_ui/models.py::ChatMessage`, re-run, confirm the test **fails** on the literal, and revert. That failure is STORY-012's starting point; leave no trace of the experiment in the diff.

### Task 5: Constant-level tests for the declaration pair

- **File**: `tests/test_db.py`
- **Action**: UPDATE (add `CHAT_MESSAGES_ADDED_COLUMNS` to the `app.db.models` import)
- **Implement**: next to `test_audit_logs_added_columns_carries_a_nullable_dedup_key` (`:1751`) and the chat DDL constants section (`:1679-1700`), add:
  - `test_chat_messages_added_columns_carries_a_nullable_history_trimmed`: `CHAT_MESSAGES_ADDED_COLUMNS == {"history_trimmed": "INTEGER"}` and `"history_trimmed INTEGER" in CREATE_CHAT_MESSAGES_TABLE`. Docstring: nullable with no default, so `NULL` (predates the PRD) stays distinguishable from `0` (nothing dropped).
  - `test_every_chat_messages_added_column_is_also_declared_in_the_create`: the twin of `test_every_added_column_is_also_declared_in_the_create` (`:1777`), over `_declared_columns(CREATE_CHAT_MESSAGES_TABLE)`. Same invariant, second table: a column in only the mapping means every fresh deployment `ALTER`s its own brand-new table on first boot.
  - `test_chat_messages_added_columns_declaring_not_null_also_declare_a_default`: the twin of `:76-93`. SQLite rejects `ADD COLUMN NOT NULL` without a default, and the mapping will grow.
  - `test_stored_message_carries_history_trimmed_without_breaking_construction`: defaults to `None`; carries `3`; `[f.name for f in fields(StoredMessage)][-3:] == ["history_trimmed", "created_at", "id"]` so the declaration order mirrors the table and `id` stays trailing.
  - `test_stored_message_mirrors_the_chat_messages_columns` (`:1823`) is **unchanged** and must pass.
- **Mirror**: `tests/test_db.py:76-93`, `:1739-1790`
- **Validate**: `pytest tests/test_db.py -q -k "history_trimmed or mirrors_the_chat_messages or every_added_column"`

### Task 6: The built column on a fresh database (AC 1, AC 2 first clause)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: next to `test_init_db_adds_a_nullable_dedup_key_column` (`:1922`) and the built-table section (`:2014`):
  - `test_init_db_adds_a_nullable_history_trimmed_column(temp_db)`: `PRAGMA table_info(chat_messages)`'s `history_trimmed` row has `type == "INTEGER"`, `notnull == 0`, `dflt_value is None`.
  - `test_chat_messages_table_matches_its_ddl` (`:2014`) is **unchanged** and must pass — it is what pins the column to the end of the declaration order on a fresh build. If it fails, the DDL edit in Task 1 put the column somewhere other than last.
  - `test_init_db_is_idempotent_for_the_chat_tables` (`:2055`) is **unchanged** and must pass; its `len(columns) == len(set(columns))` check over three consecutive `init_db()` calls is the steady-state proof for the new pass.
- **Mirror**: `tests/test_db.py:1922-1928`, `:2014-2035`
- **Validate**: `pytest tests/test_db.py -q -k "history_trimmed or chat_messages_table_matches or idempotent_for_the_chat"`

### Task 7: A pre-PRD-010 database converges (AC 2)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  1. Add `_create_pre_history_trimmed_database(connect, url)` after `_create_pre_dedup_key_database` (`:361-410`). It builds the pre-PRD-010 transcript schema by hand: `CREATE_AUDIT_LOGS_TABLE` and `CREATE_CHAT_SESSIONS_TABLE` **imported** (both are current — `history_trimmed` must be the only column in flight, for the reason `_create_pre_dedup_key_database`'s docstring gives about `dedup_key`), plus a hand-written 15-column `chat_messages` — STORY-002's shape minus `history_trimmed`. Seed one session (`session_id="0f6c2e5a-9b3d-4c81-a7f2-1d5e8c9b0a34"`, `user_id="carla@empresa.com"`) and one message row in it (`kind="assistant"`, `content="an answer"`, `model_used`, `tokens_used=7`) so a test can show the migration preserved the row rather than rewrote it. Docstring: the fifth of these fixtures, the first to predate a *chat* column rather than an audit one, and the only one where `history_trimmed` is the sole column in flight.
  2. `test_init_db_migrates_a_pre_history_trimmed_database(uninitialized_db, db_connect)`: `init_db()`, then `history_trimmed` is in `_column_names(conn, "chat_messages")`; the seeded row reads back through `list_chat_messages(session_id, "carla@empresa.com")` with `history_trimmed is None` and `tokens_used == 7` and its original `content`; a freshly appended message with `history_trimmed=2` reads back `2`. Docstring cites AC 2 and names `_add_missing_columns` as generalized-but-behaviourally-unchanged.
  3. `test_init_db_adds_the_history_trimmed_column_after_creating_the_table(uninitialized_db, db_connect, monkeypatch)`: the ordering rule pinned directly, mirroring `test_init_db_creates_the_dedup_index_after_adding_the_column` (`:2182`). Record statements via `_install` + a `_DelegatingConnection` subclass; assert exactly one `ALTER TABLE chat_messages ADD COLUMN history_trimmed` (normalize whitespace and case as that test does), that `CREATE_CHAT_MESSAGES_TABLE` appears before it, and that `len(connections) == 2` (probe + the one bootstrap `_session()`).
  4. `test_init_db_adds_the_history_trimmed_column_to_a_fresh_chat_table(uninitialized_db, db_connect, monkeypatch)`: the same recording against a database with **no** tables at all — assert **no** `ALTER ... chat_messages` is issued, because `CREATE TABLE` already declared the column. This is the half that catches a regression where the pass runs before the CREATE and silently `ALTER`s a table it just conjured, and it is the reason the story's "after `CREATE_CHAT_MESSAGES_TABLE`" clause exists.
  5. `test_init_db_issues_no_alter_when_schema_is_current` (`:126`) is **unchanged** and must pass (AC 2's steady-state clause).
- **Mirror**: `tests/test_db.py:361-410`, `:2142-2215`, `:126-198`
- **Validate**: `pytest tests/test_db.py -q -k "pre_history_trimmed or history_trimmed_column_after or fresh_chat_table or no_alter_when_schema_is_current"`

### Task 8: Convergence under a stale read and a forced race (AC 3)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  1. `test_two_init_db_calls_racing_on_history_trimmed_both_converge(uninitialized_db, db_connect, monkeypatch)`, directly after `test_two_init_db_calls_racing_on_dedup_key_both_converge` (`:3099-3132`): `_create_pre_history_trimmed_database`, `threading.Barrier(2, timeout=30)`, `_install(..., _GatedConnection)`, `_run_concurrently(2, init_db)`. Assert `not failures`; `columns.count("history_trimmed") == 1`; `set(CHAT_MESSAGES_ADDED_COLUMNS) <= set(columns)`; `len(columns) == len(set(columns))`; the seeded message still reads back once, unchanged, with `history_trimmed is None`. Docstring: AC 3, asserted the way the two audit races above are; each thread now crosses the reusable barrier twice, once per table, and both run the identical path so the cycles match.
  2. Extend `test_add_missing_columns_treats_an_existing_column_as_success` (`:2987`) — `_StaleReadConnection` now blanks the `chat_messages` PRAGMA too, so the `chat_messages` pass also `ALTER`s a column that exists and must also converge. Add to its existing assertions: every name in `CHAT_MESSAGES_ADDED_COLUMNS` appears exactly once in `_column_names(conn, "chat_messages")`, and add one sentence to the docstring recording that the deterministic half of the race now covers both tables. Keep the `users`-table assertion — it is what shows the statements after the swallowed failures still landed.
  3. `test_add_missing_columns_propagates_a_failure_that_is_not_a_duplicate_column` (`:3135`) and `..._propagates_a_duplicate_naming_a_different_column` (`:3157`) are **unchanged** and must pass: the narrow re-raise must survive parameterization.
- **Mirror**: `tests/test_db.py:3052-3132`, `:2987-3010`
- **Validate**: `pytest tests/test_db.py -q -k "racing or existing_column_as_success or propagates"`, then the race set 3× to catch a flaky interleave: `for i in 1 2 3; do pytest tests/test_db.py -q -k racing || break; done`

### Task 9: Round trip through the store (AC 4)

- **File**: `tests/test_chat_sessions.py`
- **Action**: UPDATE
- **Implement**: next to `test_tokens_used_and_audit_id_round_trip_as_integers` (`:724`):
  - `test_history_trimmed_round_trips_as_an_integer(temp_db)`: `append_chat_message(_stored(session_id, "assistant", history_trimmed=3), ...)` → `list_chat_messages` returns `3`, with `isinstance(restored.history_trimmed, int)` for the reason that test's docstring gives (`"3"` would be caught by `==`, `3.0` would not). Assert a neighbouring field (`content`, `tokens_used`) on the same row too, which catches a miscounted placeholder shift in the INSERT.
  - `test_absent_history_trimmed_reads_back_as_none_not_zero(temp_db)`: a message appended without it reads `None`. Docstring: `0` means "this send dropped nothing" and `NULL` means "written before the feature existed"; an `int()` in the mapper would report every pre-PRD row as the former.
  - `test_history_trimmed_zero_round_trips_as_zero(temp_db)`: `history_trimmed=0` reads back `0`, not `None`. This is the one an `or None` in `append_chat_message` would break, and nothing else in the suite would notice.
  - Extend the field tuple in `test_each_of_the_seven_kinds_round_trips_unchanged` (`:706-720`) with `"history_trimmed"`, so all seven kinds carry it through the round trip.
- **Mirror**: `tests/test_chat_sessions.py:724-765`
- **Validate**: `pytest tests/test_chat_sessions.py -q -k "history_trimmed or seven_kinds"`

### Task 10: Confirm the untouched surfaces and the whole suite (AC 5)

- **Files**: none edited
- **Action**: VERIFY
- **Implement**:
  - `git diff --stat -- chat_ui/ app/services app/routers app/models scripts/` → **empty**. `ChatMessage` gains nothing here; STORY-012 owns it.
  - Correct the one stale claim the generalization invalidates: `tests/test_db.py:1581`'s docstring says "This is why `_add_missing_columns` stays audit_logs-specific". Amend it to say the argument is unchanged (a new *table* needs no ALTER-based migration, a new *column* does) and that PRD-010 STORY-010 gave the function a second table rather than a second mechanism. Assertions unchanged.
  - `pytest tests/test_db.py tests/test_chat_sessions.py tests/test_chat_state.py -q` → green.
  - `pytest tests/test_two_instance_smoke.py tests/test_history_off_integration.py tests/test_session_ownership.py tests/test_migrate_to_turso_cli.py tests/test_chat_shell.py -q` → green **unmodified**. The two-instance smoke is the real proof that two boots converge on one schema through the new pass.
  - Full suite: `pytest tests/ -q`.
- **Validate**: all of the above green; the diff stat empty for the listed paths

---

## End-to-End Tests

For `/implement` to execute:

- [ ] Start the libSQL dev server (`docker start harness-libsql-dev`), then `pytest tests/test_db.py -q` → green, including every new `history_trimmed` test
- [ ] Fresh DB: `init_db()` → `PRAGMA table_info(chat_messages)` has `history_trimmed` as `INTEGER`, `notnull == 0`, `dflt_value is None`, **last** in declaration order; no `ALTER` was issued
- [ ] Pre-PRD-010 DB (15-column `chat_messages`, one seeded message): `init_db()` → column added, the existing row reads `history_trimmed is None` with its other fields intact, and a new append with `history_trimmed=2` round-trips
- [ ] Steady state: a second and third `init_db()` issue no `ALTER`, on one `_session()` connection plus the probe
- [ ] Race: two gated `init_db()` on a pre-PRD-010 DB → no failures, exactly one `history_trimmed` column, seeded row intact (run 3×)
- [ ] `append_chat_message(StoredMessage(..., history_trimmed=3))` → `list_chat_messages` returns `3` as an `int`; `0` returns `0`; omitted returns `None`
- [ ] `tests/test_chat_state.py` green, and the Task 4 trap verified live: adding `history_trimmed` to `ChatMessage` fails the coverage test until `_to_chat_message` maps it (revert the experiment)
- [ ] Full suite `pytest tests/ -q` green. On mass fixture errors, `docker restart harness-libsql-dev` and re-run; a single scattered `no such table` in an unrelated test is the known environment flake — re-run and confirm it moves

---

## Validation

```bash
docker start harness-libsql-dev   # or the docker run command in tests/conftest.py:139-147
pytest tests/test_db.py -q
pytest tests/test_chat_sessions.py tests/test_chat_state.py -q
pytest tests/test_two_instance_smoke.py tests/test_history_off_integration.py tests/test_session_ownership.py tests/test_migrate_to_turso_cli.py -q
pytest tests/ -q
git diff --stat -- chat_ui/ app/services app/routers app/models scripts/   # must be empty
```

No frontend and no server-start change, so the template's `npm run lint` and `uvicorn` checks don't apply. `init_db()` is exercised by the fixtures themselves, and `tests/test_two_instance_smoke.py` boots real instances through it.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| The `chat_messages` pass placed before `CREATE_CHAT_MESSAGES_TABLE` → `PRAGMA` reports no columns on a fresh DB and the `ALTER` hits a missing table, failing every boot | Task 2.4 fixes the position; Task 7.4 asserts **no** `ALTER` is issued on a fresh database, and Task 7.3 asserts the CREATE precedes the ALTER on a pre-PRD one |
| Parameterizing `_add_missing_columns` weakens the pre-check or the narrow re-raise | Task 2.2 changes only the two table names and the iterated mapping; Task 8.3 keeps both propagation tests unmodified, and `test_init_db_issues_no_alter_when_schema_is_current` keeps the pre-check honest |
| `_GatedConnection` now crosses the barrier twice per thread; an asymmetric path would deadlock | Both threads run the identical `init_db()`, and `threading.Barrier` is reusable. The existing 30 s timeout turns any asymmetry into a `BrokenBarrierError` and a red test, never a hung suite |
| `StoredMessage` gaining a field breaks `tests/test_chat_state.py`'s `_to_chat_message` coverage walk | Task 4 derives the excused set from `ChatMessage.model_fields` and pins it; the pin is what forces STORY-012 to map the field when it adds it to the bubble |
| Miscounted placeholders in `append_chat_message` shift every value one column left | Task 3.1 counts 15/15/15 + 2 predicate values; Task 9 asserts a neighbouring field on the same round-tripped row |
| `or None` or `int()` applied to `history_trimmed` erases the `0` / `NULL` distinction | Task 3 forbids both explicitly; Task 9's zero and absent tests are the pair that catches each |
| The new column is declared somewhere other than last in the DDL | `test_chat_messages_table_matches_its_ddl` compares `PRAGMA` order against declaration order and fails; Task 6 keeps it unmodified as the pin |
| A future second entry in `CHAT_MESSAGES_ADDED_COLUMNS` declares `NOT NULL` without a default → SQLite rejects the `ADD COLUMN` | Task 5 adds the twin of the existing guard test over the new mapping |
| libSQL dev server degrades across repeated suites | Restart the container on mass fixture errors; don't bisect code (`.agents/stories/.../STORY-010`'s Technical Notes, and the standing note) |

---

## Acceptance Criteria

(Copied from story `STORY-010`)

- [ ] Given [app/db/models.py](../../../app/db/models.py), when it is read, then `CREATE_CHAT_MESSAGES_TABLE` declares `history_trimmed INTEGER` (nullable), a new `CHAT_MESSAGES_ADDED_COLUMNS = {"history_trimmed": "INTEGER"}` exists, and `StoredMessage.history_trimmed: Optional[int] = None`.
- [ ] Given a pre-PRD database whose `chat_messages` lacks the column, when `init_db()` runs, then the column is added, existing rows read `NULL`, and a second `init_db()` issues no `ALTER`.
- [ ] Given two concurrent `init_db()` calls racing the add, when one gets `duplicate column name`, then it converges via `_is_duplicate_column` instead of failing boot.
- [ ] Given `database.append_chat_message` with `history_trimmed=3`, when `list_chat_messages` reads it back, then the value is `3`. Rows written without it read `None`.
- [ ] Given the full suite, including [tests/test_db.py](../../../tests/test_db.py) and [tests/test_chat_sessions.py](../../../tests/test_chat_sessions.py), when this story lands, then it is green.
- [ ] All tasks completed
- [ ] Full test suite passes (`pytest tests/ -q`), since this repo has no frontend lint
