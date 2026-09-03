---
story: STORY-005
prd: PRD-008
slug: message-store-functions
title: "append_chat_message and list_chat_messages, ordered by id and scoped by owner"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-03
---

# Plan: append_chat_message and list_chat_messages, ordered by id and scoped by owner

## Summary

Add three functions to `app/db/database.py` — `append_chat_message`, `list_chat_messages` and `count_chat_sessions` — plus one private row mapper, `_row_to_stored_message`. All three carry the same undefaulted `user_id: str` that STORY-004's six carry, and all three put it in a `WHERE` clause. The two message functions reach `chat_messages`, a table with **no `user_id` column**, so ownership is expressed the way `delete_chat_session` already expresses it: a subselect against `chat_sessions` inside the same statement. `append_chat_message` is a single `INSERT ... SELECT ... WHERE EXISTS`, so the ownership check and the insert are one statement in one transaction and there is no TOCTOU window (PRD Risk 3). Reads are `ORDER BY id ASC` with no `LIMIT`. Tests extend `tests/test_chat_sessions.py`, as that file's own docstring instructs.

## User Story

As a maintainer
I want messages appended and read back in a fixed order under an ownership check
So that a restored transcript is the same transcript, in the same sequence, and only for the person who wrote it.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-005-message-store-functions.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` — Section 4 (Data access), Section 6 (stored message table, Ordering), Section 12 Phase 1, Risk 2, Risk 3

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/db/database.py`, `tests/test_chat_sessions.py` |
| Story | STORY-005 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` was listed and holds exactly one skill.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `frontend-design` | **Does not apply.** Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story adds three functions to `app/db/database.py` and touches no component, no theme token and no copy string. | None |

The story frontmatter's `skills: []` is confirmed correct against the directory rather than trusted.

---

## Patterns to Follow

### Naming — the private row mapper, one per table

```python
# SOURCE: app/db/database.py:1103-1111 (_row_to_user)
def _row_to_user(row: _Row) -> User:
    return User(
        user_id=row["user_id"],
        role=row["role"],
        token_hash=row["token_hash"],
        active=bool(row["active"]),   # INTEGER column -> bool field
        created_at=row["created_at"],
    )
```

```python
# SOURCE: app/db/database.py:1215-1227 (_row_to_chat_session)
def _row_to_chat_session(row: _Row) -> ChatSession:
    """One `chat_sessions` row as the dataclass STORY-002 declared. ..."""
    return ChatSession(session_id=row["session_id"], ...)
```

`_row_to_stored_message` follows `_row_to_user`, not `_row_to_chat_session`: `chat_messages.pii_redacted` is `INTEGER NOT NULL DEFAULT 0` against a `bool` field, so it is the one column needing `bool(...)` — the same coercion `active` gets.

### Ownership on a table with no `user_id` column

```sql
-- SOURCE: app/db/database.py:1379-1387 (delete_chat_session)
DELETE FROM chat_messages
 WHERE session_id = ?
   AND session_id IN (
       SELECT session_id FROM chat_sessions
        WHERE session_id = ? AND user_id = ?
   )
```

This is the shape both message functions reuse. Its docstring already states the reason: `chat_messages` carries no `user_id`, so a predicate on `session_id` alone would reach a foreign owner's rows.

### Transactions, and the meaning of one `with _session()` block

```python
# SOURCE: app/db/database.py:447-458 (_session) and 224-228 (_Connection.__exit__)
@contextmanager
def _session() -> Iterator[_Connection]:
    with _translated():
        conn = get_connection()
        with conn:
            yield conn
# __exit__: commit on clean exit, rollback on exception. One block = one transaction.
```

### Insert returning the new key

```python
# SOURCE: app/db/database.py:547-580 (insert_audit_log)
def insert_audit_log(entry: AuditLog) -> int:
    with _session() as conn:
        cursor = conn.execute("INSERT INTO audit_logs (...) VALUES (?, ...)", (...))
        return cursor.lastrowid
```

### Rowcount as the "did it match" signal

```python
# SOURCE: app/db/database.py:1338-1344 (rename_chat_session)
        cursor = conn.execute(
            "UPDATE chat_sessions SET title = ? WHERE session_id = ? AND user_id = ?",
            (title, session_id, user_id),
        )
        return cursor.rowcount == 1
```

### The `pii_entities` encoding, at its existing writer

```python
# SOURCE: app/services/audit_logger.py:45
pii_entities=",".join(pii_entities) if pii_entities else None,
```

`if pii_entities else None` is the whole of the empty-list rule: `[]` becomes `NULL`, never `""`. `StoredMessage.pii_entities` is `Optional[str]` (`app/db/models.py`) — the joined string, not a list — so this layer's obligation is to keep `None` as `None` and never manufacture `""`.

### Tests — structural assertions over the module, then behaviour

```python
# SOURCE: tests/test_chat_sessions.py:126-138
def test_every_signature_requires_an_undefaulted_user_id():
    for name in THE_SIX:
        parameters = inspect.signature(getattr(database, name)).parameters
        assert "user_id" in parameters, name
        user_id = parameters["user_id"]
        assert user_id.default is inspect.Parameter.empty, name
        assert user_id.annotation is str, name
        assert user_id.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, name
```

```python
# SOURCE: tests/test_chat_sessions.py:48-60 (_statements_of)
def _statements_of(name: str) -> str:
    """The named function's body with its docstring removed. Through `ast` because
    the prose in these docstrings quotes the very SQL fragment the assertion looks for."""
```

```python
# SOURCE: tests/test_chat_sessions.py:63-71 (_seed_users)
def _seed_users() -> None:
    """Two real users, so a foreign id in a test is a foreign id that exists."""
    insert_user(User(user_id="ana", role="user", token_hash="hash-ana"))
    insert_user(User(user_id="bob", role="user", token_hash="hash-bob"))
```

---

## Design Decisions

Four choices this plan settles, each with the reasoning, so `/implement` does not re-litigate them.

### D1 — `append_chat_message` is one `INSERT ... SELECT ... WHERE EXISTS`, not a read then a write

The story's technical note is explicit: "The ownership check on `append_chat_message` must be part of the same transaction as the insert, not a read followed by a write." Calling `get_chat_session` and then inserting would satisfy "same transaction" only by accident of both landing in one `_session()` block, and it would still read the session twice. One statement is the honest form:

```sql
INSERT INTO chat_messages (
    session_id, kind, content, created_at, prompt, model_used, tokens_used,
    audit_id, pii_redacted, pii_entities, pattern, required_permission,
    first_query_at, detail
)
SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
 WHERE EXISTS (
     SELECT 1 FROM chat_sessions WHERE session_id = ? AND user_id = ?
 )
```

Sixteen placeholders: fourteen values, then `session_id` and `user_id` again for the predicate. The row is written if and only if the session exists and is owned, decided by the database in one evaluation.

Side benefit worth naming: this statement contains the literal `user_id = ?`, so it passes `test_every_statement_over_existing_rows_scopes_on_user_id` unchanged and will pass STORY-007's discovery sweep. It does **not** need `create_chat_session`'s exclusion, even though it is an INSERT.

### D2 — a foreign or unknown session raises `StorageError`, and the two cases are not distinguishable

AC 6: "no row is written and the failure is visible to the caller — a silent no-op here would look like a working write in STORY-014's degraded arm." The return type is `int`, so there is no in-band failure value; it must raise.

**Type: `StorageError`, from `app/db/errors.py`, already imported at `app/db/database.py:14-20`.** Not a new exception class — the story scopes itself to "New functions only" in `database.py` — and not a builtin like `PermissionError`, which would slip past every existing `except StorageError` in the codebase and land in STORY-014's degraded arm as an unhandled crash rather than the notice PRD Section 6 specifies. `StorageError` is the surface `app/db/` raises and the one consumers already catch.

**One message for both cases.** An unknown `session_id` and a foreign one raise the same exception with the same text. `get_chat_session` (`app/db/database.py:1263`) returns `None` for both for exactly this reason — a caller who can tell "yours but missing" from "someone else's" has a membership oracle over other people's session ids. Raising is required here; distinguishing is not, and must not happen. The message names no user and no session: `"chat session not available for this owner"`.

### D3 — the `session_id` parameter is authoritative; `message.session_id` is never read

The story's signature is `append_chat_message(message, session_id, user_id) -> int`, and `StoredMessage` also carries a `session_id` field (`app/db/models.py`). Two sources for one value.

The parameter wins, for both the written column and the predicate. `message.session_id` is not read at all. The reason is security, not tidiness: the ownership check is evaluated against the parameter, so if the dataclass field were what got written, a `StoredMessage` carrying a foreign `session_id` would be checked against one session and filed under another. Reading one value in both places makes that impossible by construction. The docstring states this, and a test pins it.

Likewise `message.id` and `message.created_at` are ignored on write when unset: `id` comes from `AUTOINCREMENT`, and `created_at` is stamped here when the caller leaves it `None`, matching `insert_user`'s documented "stamps it when omitted" behaviour and `StoredMessage.created_at`'s own comment.

### D4 — empty `pii_entities` is normalized to `NULL` on write

`StoredMessage.pii_entities` is `Optional[str]`. A caller building one from `",".join([])` produces `""`, not `None`, and `"".split(",")` is `[""]` — the classic bug the story's technical note calls out by name, which would surface in STORY-015 as a phantom PII entity on a message that had none.

The column already permits `NULL`. `append_chat_message` writes `message.pii_entities or None`, so `""` and `None` both store `NULL` and both read back as `None`. The split in STORY-015 is then never handed an empty string. This is the same `if pii_entities else None` guard `app/services/audit_logger.py:45` applies one layer up, applied again at the layer that owns the column — cheap, and it means the invariant does not depend on every future caller remembering it.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | Import `StoredMessage`; add `_row_to_stored_message`, `append_chat_message`, `list_chat_messages`, `count_chat_sessions` |
| `tests/test_chat_sessions.py` | UPDATE | Extend with the structural assertions for the three new names and the behavioural round trips (the file's docstring already directs STORY-005 here) |

No new files. `app/db/models.py` is untouched — STORY-002 already declared `StoredMessage`, `CREATE_CHAT_MESSAGES_TABLE` and `idx_chat_messages_session_id`, and STORY-003 already creates them in `init_db()`.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Confirm `rowcount` reports 0 for a non-matching `INSERT ... SELECT`

- **File**: none — a throwaway probe under the scratchpad, nothing committed
- **Action**: VERIFY (this is the one assumption D1 rests on)
- **Implement**: With the libSQL dev server up, open a `get_connection()`, create the tables via `init_db()`, insert one `chat_sessions` row for `ana`, then run the D1 statement twice — once with `ana` (expect `rowcount == 1`) and once with `bob` (expect `rowcount == 0`). Existing code trusts `rowcount` only for `UPDATE`/`DELETE` (`rename_chat_session`, `touch_chat_session`, `delete_chat_session`, `deactivate_user`); an `INSERT ... SELECT` that selects no rows is a shape this codebase has never exercised against this driver.
- **Mirror**: `app/db/database.py:1322-1344` — how `rowcount == 1` is already used as the matched/not-matched signal
- **Validate**: the `bob` call reports `0` and `SELECT COUNT(*) FROM chat_messages` is still `0`
- **If it does not hold**: fall back to `conn.execute("SELECT changes() AS n").fetchone()["n"]` immediately after the insert, inside the same `_session()` block, and record the deviation in the implementation report. Do **not** fall back to a separate `SELECT` of the session — that reintroduces the TOCTOU gap D1 exists to close.

### Task 2: Import `StoredMessage`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Add `StoredMessage` to the `from app.db.models import (...)` block at lines 21-33, in the existing order — the block lists the SQL constants alphabetically, then the dataclasses alphabetically (`AuditLog`, `ChatSession`, `User`), so `StoredMessage` goes between `ChatSession` and `User`.
- **Mirror**: `app/db/database.py:21-33`
- **Validate**: `python -c "from app.db.database import StoredMessage"` (no database contact needed)

### Task 3: Add `_row_to_stored_message`

- **File**: `app/db/database.py`
- **Action**: UPDATE — append after `delete_chat_session` (currently ends at line 1400), keeping the session functions as one contiguous block and starting the message functions below them
- **Implement**: Map all fifteen columns of `chat_messages` onto `StoredMessage` by name. Only `pii_redacted` is coerced — `bool(row["pii_redacted"])`, an `INTEGER NOT NULL DEFAULT 0` column against a `bool` field. `tokens_used` and `audit_id` are `INTEGER` columns against `Optional[int]` fields and are passed through untouched: coercing them would turn a genuine `NULL` into `0`, and `0` is a meaningful token count. `id` is read straight from the row.
- **Docstring must record**: that `pii_redacted` is the only coercion and why (mirroring `_row_to_chat_session`'s docstring, which explains the *absence* of coercion for its table).
- **Mirror**: `app/db/database.py:1103-1111` (`_row_to_user`) for the coercion; `app/db/database.py:1215-1227` (`_row_to_chat_session`) for the docstring's shape
- **Validate**: `python -c "import app.db.database"`

### Task 4: Add `append_chat_message(message, session_id, user_id) -> int`

- **File**: `app/db/database.py`
- **Action**: UPDATE — directly after `_row_to_stored_message`
- **Implement**: One `_session()` block containing the single `INSERT ... SELECT ... WHERE EXISTS` from D1. Stamp `created_at` with `message.created_at or datetime.now(timezone.utc).strftime(_TIMESTAMP_FORMAT)`. Write `int(message.pii_redacted)` (the `int(...)` on a bool field going to an INTEGER column that `insert_audit_log` applies at lines 566-570) and `message.pii_entities or None` (D4). Bind the `session_id` and `user_id` **parameters** in both the value list and the `EXISTS` predicate — never `message.session_id` (D3). Then:

```python
        if cursor.rowcount != 1:
            raise StorageError("chat session not available for this owner")
        return cursor.lastrowid
```

  The order matters and the docstring must say so: `lastrowid` after an insert that wrote nothing returns the *previous* row's id, so a caller reading it before checking `rowcount` gets a plausible integer for a write that never happened — precisely the silent success AC 6 forbids. Raising inside the `with` block also rolls the transaction back via `_Connection.__exit__`, so the "no row is written" half of AC 6 holds even if the check is ever wrong.
- **Docstring must record**: D1 (one statement, no TOCTOU, PRD Risk 3), D2 (why `StorageError` and why unknown and foreign are one message), D3 (the parameter is authoritative), D4 (`""` normalized to `NULL`), and the `rowcount`-before-`lastrowid` ordering.
- **Mirror**: `app/db/database.py:547-580` (`insert_audit_log` — the INSERT and `lastrowid`); `app/db/database.py:1379-1387` (`delete_chat_session` — the ownership subselect)
- **Validate**: `python -c "import app.db.database"`, then Task 7's tests

### Task 5: Add `list_chat_messages(session_id, user_id) -> list[StoredMessage]`

- **File**: `app/db/database.py`
- **Action**: UPDATE — directly after `append_chat_message`
- **Implement**:

```sql
SELECT * FROM chat_messages
 WHERE session_id = ?
   AND session_id IN (
       SELECT session_id FROM chat_sessions
        WHERE session_id = ? AND user_id = ?
   )
 ORDER BY id ASC
```

  Return `[_row_to_stored_message(row) for row in rows]`. **No `limit` parameter and no `LIMIT` clause** — the story is explicit that a partial transcript is a wrong transcript, and PRD Section 4 caps sessions, not messages within one. A foreign owner gets `[]` from the subselect, with no separate branch: the empty list is the natural result of the predicate, not a special case bolted on (AC 5).
- **Docstring must record**: why the order is `id ASC` and not `created_at` (PRD Section 6's "a transcript that reorders itself on reload would be a visible instance of the same defect", and `list_chat_sessions`' own "Known tie" note at lines 1300-1306 which points here); that `(session_id, id)` is `idx_chat_messages_session_id` read exactly; and that the absence of a `limit` is a decision, with paging named as the alternative if volume ever forces it.
- **Mirror**: `app/db/database.py:1289-1319` (`list_chat_sessions` — the read-and-map shape); `app/db/database.py:1379-1387` (the subselect)
- **Validate**: `python -c "import app.db.database"`, then Task 7's tests

### Task 6: Add `count_chat_sessions(user_id) -> int`

- **File**: `app/db/database.py`
- **Action**: UPDATE — directly after `list_chat_messages`
- **Implement**: `SELECT COUNT(*) AS n FROM chat_sessions WHERE user_id = ?`, returning `row["n"]`. The `AS n` alias is not optional — `_Row` maps names from `cursor.description`, and the seven existing counters all alias for this reason.
- **Docstring must record**: what it is for — the rail states its cap against a true total, the way PRD-006's register states "100 most recent of 3,180". It counts *sessions*, not messages, and it deliberately ignores `CHAT_SESSION_LIMIT`: a count that respected the display cap could never report a number larger than the cap, which is the only number worth printing.
- **Mirror**: `app/db/database.py:643-653` (`count_audit_logs`); `app/db/database.py:1160-1166` (`count_active_users`)
- **Validate**: `python -c "import app.db.database"`, then Task 7's tests

### Task 7: Extend `tests/test_chat_sessions.py`

- **File**: `tests/test_chat_sessions.py`
- **Action**: UPDATE — add to this file, not a new one. Its module docstring (lines 3-5) already says so: "STORY-005 extends **this file** with the message-store round trips ... add to it rather than opening a third suite over the same two tables."
- **Implement**: Extend the imports with `StorageError`, `append_chat_message`, `count_chat_sessions` and `list_chat_messages`, and `StoredMessage` from `app.db.models`. Add a `THE_THREE` tuple beside `THE_SIX`, and a `_stored(session_id, kind, **overrides)` builder so each kind's round trip is one readable call. Then the cases below. Update the module docstring to say the file now covers both stories.

  Structural (no database):
  1. `test_the_three_message_functions_are_declared` — AC 1, `hasattr` + `callable` over `THE_THREE`.
  2. `test_every_message_signature_requires_an_undefaulted_user_id` — AC 2. Same four assertions as lines 126-138, over `THE_THREE`.
  3. `test_omitting_user_id_is_a_type_error_on_the_message_functions` — AC 2, exercised.
  4. `test_every_message_statement_scopes_on_user_id` — AC 2, the SQL half, via `_statements_of`. **All three included, `append_chat_message` too** — unlike `create_chat_session`, its INSERT carries a `WHERE EXISTS` and so genuinely does scope. A comment should say that this is the difference between the two inserts, not an oversight in the earlier exclusion.
  5. `test_list_chat_messages_orders_by_id_and_not_by_a_timestamp` — AC 3. Assert `"ORDER BY id ASC"` in `_statements_of("list_chat_messages")` **and** that neither `"ORDER BY created_at"` nor `"ORDER BY timestamp"` appears. The negative half is the one that catches the regression.
  6. `test_list_chat_messages_takes_no_limit_parameter` — the story's "do not add a `limit`" note, pinned so a future convenience parameter fails a test rather than silently truncating a transcript.

  Behavioural (`temp_db`):

  7. `test_twenty_messages_appended_in_one_second_read_back_in_order` — AC 4. Append twenty with identical `created_at`, assert the contents come back in append order. This is the case a timestamp sort gets wrong.
  8. `test_append_returns_the_new_row_id_and_ids_increase` — the returned `int` is the row's key, and successive appends increase.
  9. `test_each_of_the_seven_kinds_round_trips_unchanged` — AC 7 and AC 8. **Parametrized over the seven kinds** (`user`, `assistant`, `duplicate`, `injection`, `forbidden`, `upstream_error`, `internal_error`), each with the metadata PRD Section 6's table gives it — `first_query_at` for `duplicate`, `pattern` for `injection`, `required_permission` for `forbidden`, `detail` for the two error kinds — asserting every `StoredMessage` field except `id` survives. Parametrized rather than looped, so a failure names the kind that broke.
  10. `test_tokens_used_and_audit_id_round_trip_as_integers` — AC 7. Assert both `== 1234` **and** `isinstance(..., int)`, and separately that `None` stays `None` rather than becoming `0`.
  11. `test_empty_pii_entities_stores_null_and_reads_back_as_none` — D4. Three cases: `None`, `""`, and `"EMAIL,PHONE"`. The first two must read back `None` (never `""`), the third unchanged. The test's docstring names `"".split(",") == [""]` as the bug being prevented and STORY-015 as where it would have surfaced.
  12. `test_pii_redacted_round_trips_as_a_bool` — the one coerced column; assert `is True` / `is False`, not truthiness, so an `INTEGER` leaking through fails.
  13. `test_list_chat_messages_returns_empty_for_a_foreign_owner` — AC 5. Seed via `_seed_users()`, write ana's messages, read as `bob`, assert `== []` and that ana still reads them all.
  14. `test_append_for_a_foreign_owner_writes_nothing_and_raises` — AC 6. `pytest.raises(StorageError)` and `_count_messages(...) == 0`.
  15. `test_append_to_an_unknown_session_raises_the_same_way` — D2. Assert the same type and the same message string as case 14, so the two are not distinguishable. This is the oracle test, and it fails if someone later "improves" the error by naming which case it was.
  16. `test_append_ignores_the_session_id_on_the_message` — D3. Build a `StoredMessage` whose `session_id` field is bob's session, append it with ana's `session_id` and ana's `user_id`, assert the row lands in ana's session and bob's is untouched.
  17. `test_append_stamps_created_at_when_omitted_and_keeps_it_when_given` — the `StoredMessage.created_at` comment, both arms.
  18. `test_count_chat_sessions_counts_only_the_callers_own` — ana with three, bob with two; each sees their own number.
  19. `test_count_chat_sessions_is_zero_for_an_unknown_user` — returns `0`, does not raise.
  20. `test_count_chat_sessions_ignores_the_list_limit` — write more sessions than `list_chat_sessions`' default of 50 would return, assert the count exceeds what the list returns. Pins the docstring's claim in Task 6.
  21. `test_delete_chat_session_removes_messages_written_through_append` — STORY-004's `_add_message` helper (lines 88-101) writes rows directly because `append_chat_message` did not exist yet. It does now; this asserts the two agree. Leave `_add_message` in place — its comment should be updated to say it is kept so STORY-004's cases stay independent of this story's function.
- **Mirror**: `tests/test_chat_sessions.py:119-170` (structural block), `tests/test_chat_sessions.py:240-256` (the foreign-owner shape), `tests/test_chat_sessions.py:63-71` (`_seed_users`)
- **Validate**: `python -m pytest tests/test_chat_sessions.py -q`

### Task 8: Full suite and the two adjacent modules

- **File**: none
- **Action**: VERIFY
- **Implement**: Run the whole suite. `append_chat_message` and `list_chat_messages` are new names with no existing callers, so nothing should move; the check is that the new import in `database.py` and the extended test module have not disturbed `tests/test_db.py` or the STORY-004 cases.
- **Validate**: `python -m pytest -q`

---

## End-to-End Tests

For `/implement` to execute:

- [ ] libSQL dev server reachable — `docker ps` shows `harness-libsql-dev`, or start it per `tests/conftest.py`'s docstring
- [ ] `python -m pytest tests/test_chat_sessions.py -q` — the STORY-004 cases still pass alongside the new ones
- [ ] `python -m pytest tests/test_db.py -q` — schema and migration unaffected
- [ ] `python -m pytest -q` — full suite green
- [ ] Append twenty messages in a loop with one fixed `created_at`, read back, confirm order is append order (AC 4, also covered by test 7)
- [ ] From a Python shell: `append_chat_message(msg, ana_session, "bob")` raises `StorageError` and `SELECT COUNT(*)` is unchanged (AC 6)
- [ ] `grep -n "ORDER BY" app/db/database.py` — the `chat_messages` read is `ORDER BY id ASC` and no `chat_messages` statement orders by a timestamp (AC 3)

---

## Validation

```bash
docker ps --filter name=harness-libsql-dev
python -c "import app.db.database"
python -m pytest tests/test_chat_sessions.py -q
python -m pytest tests/test_db.py -q
python -m pytest -q
```

---

## Risks

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | `rowcount` may not report `0` for an `INSERT ... SELECT` that selects nothing under libSQL — the codebase has only ever relied on it for `UPDATE`/`DELETE`. If it reports `1` regardless, AC 6 fails silently and D2's raise never fires. | Task 1 probes it before any code is written. Documented fallback is `SELECT changes()` in the same transaction — never a separate ownership `SELECT`, which would reopen the TOCTOU gap. |
| 2 | The libSQL dev server degrades under repeated suite runs, producing mass fixture errors that look like a code regression. | Restart the container rather than bisecting the code — mass fixture errors across unrelated tests are the server, not this story. |
| 3 | `message.session_id` and the `session_id` parameter disagreeing (D3) is invisible at runtime — nothing raises, the row simply lands somewhere. | The parameter is read in both the value list and the predicate, so the two can never diverge; test 16 pins it. |
| 4 | `""` in `pii_entities` reaching the column would surface only in STORY-015, as a phantom entity on a message that had none. | D4 normalizes at write; test 11 covers `None`, `""` and a real value. |
| 5 | A future caller adds a `limit` to `list_chat_messages` "for performance", silently truncating transcripts. | Test 6 asserts the parameter does not exist, and the docstring names paging as the correct alternative. |
| 6 | STORY-007's discovery sweep over `*_chat_message*` callables could trip on `_row_to_stored_message`, which takes no `user_id`. | It is private (leading underscore) and maps a row rather than reaching the database; STORY-007's plan must exclude private helpers, exactly as this file's existing structural tests enumerate public names only. Noted here so that story inherits it. |

---

## Acceptance Criteria

(Copied from story `STORY-005`)

- [ ] Given `app/db/database.py`, when it is read, then it declares `append_chat_message(message, session_id, user_id) -> int`, `list_chat_messages(session_id, user_id) -> list[StoredMessage]` and `count_chat_sessions(user_id) -> int`.
- [ ] Given all three signatures, when they are inspected, then `user_id: str` is required and undefaulted, and each statement scopes on ownership — `append_chat_message` writes only after confirming the session belongs to `user_id`, in the same transaction as the insert.
- [ ] Given `list_chat_messages`, when it is called, then the statement reads `ORDER BY id ASC` and **not** by any timestamp column.
- [ ] Given twenty messages appended inside one second, when they are read back, then their order is exactly the order they were appended.
- [ ] Given `list_chat_messages(session_id, foreign_user_id)`, when it is called, then it returns an empty list, not the rows.
- [ ] Given `append_chat_message(message, session_id, foreign_user_id)`, when it is called, then no row is written and the failure is visible to the caller.
- [ ] Given each of the seven `ChatMessage` kinds, when one is appended and read back, then every stored field round-trips unchanged, including `pii_entities` through its comma-joined encoding and `tokens_used`/`audit_id` as integers.
- [ ] Given `tests/test_chat_sessions.py`, when it runs, then the round trip is asserted per kind rather than once for a representative kind.
- [ ] All tasks completed
- [ ] Full test suite passes
- [ ] `app/db/database.py` imports nothing from `chat_ui/`
- [ ] Follows existing patterns
