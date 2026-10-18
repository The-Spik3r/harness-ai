---
story: STORY-008
prd: PRD-013
slug: per-user-overrides
title: "Per-user limit overrides: users columns, Identity fields and manage_users set-limits"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-013-audit-and-usage-limits   # all stories commit here, no per-story branch
created: 2026-10-18
---

# Plan: Per-user limit overrides: users columns, Identity fields and manage_users set-limits

## Summary

Add two nullable columns, `token_budget_daily` and `requests_per_minute`, to `users`. They are declared in `CREATE_USERS_TABLE` and in a new `USERS_ADDED_COLUMNS` mapping, which converges through the existing `_add_missing_columns()` in a third pass placed right after `CREATE_USERS_TABLE`. `User` and `_row_to_user` carry the two values. A new `set_user_limits()` updates only the columns it is given, using a sentinel so "leave alone" and "set to NULL" stay distinct. `Identity` stays frozen and gains `break_glass`, `token_budget_daily` and `requests_per_minute`, all with defaults. Only `resolve()` sets them: `break_glass=True` on the `ADMIN_TOKEN` path, and the two overrides from the row `find_user_by_token_hash` already reads, so there is no extra round trip. `scripts/manage_users.py` gains `set-limits`, and `list-users` prints both limits, with `default` for NULL. Nothing reads the new `Identity` fields yet (STORY-010, STORY-013).

## User Story

As a platform operator
I want to set one user's token budget or request rate from the CLI
So that a heavy user does not require a configuration change for everyone

## Story Reference

- Story file: `.agents/stories/PRD-013-audit-and-usage-limits/STORY-008-per-user-overrides.md`
- PRD: `.agents/PRDs/PRD-013-audit-and-usage-limits/PRD.md` (sections 4, 6.6, 6.8, 6.12, 7 F7, 10)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `app/db` (schema, dataclass, user CRUD), `app/services/identity.py`, `scripts/manage_users.py`, tests |
| Story | STORY-008 |
| PRD | PRD-013 |
| Epic Branch | `epic/PRD-013-audit-and-usage-limits` (commit directly on this branch) |
| Depends on | none (STORY-007 settings are already done but are not read here) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`. This story has no UI surface, so no skill applies (the story's Technical Notes say the same) | — |

---

## Patterns to Follow

### Added-columns mapping (third table, same mechanism)
```python
# SOURCE: app/db/models.py:261  (CHAT_MESSAGES_ADDED_COLUMNS, with its long rationale comment above it)
CHAT_MESSAGES_ADDED_COLUMNS = {"history_trimmed": "INTEGER"}
```

### Convergence pass placed after its table's CREATE
```python
# SOURCE: app/db/database.py:699-711
    check_database_reachable()
    with _session() as conn:
        conn.execute(CREATE_AUDIT_LOGS_TABLE)
        _add_missing_columns(conn, "audit_logs", AUDIT_LOGS_ADDED_COLUMNS)
        conn.execute(CREATE_AUDIT_LOGS_DEDUP_INDEX)
        conn.execute(CREATE_USERS_TABLE)
        conn.execute(CREATE_USERS_TOKEN_HASH_INDEX)
        ...
        conn.execute(CREATE_CHAT_MESSAGES_TABLE)
        _add_missing_columns(conn, "chat_messages", CHAT_MESSAGES_ADDED_COLUMNS)
```

### Row mapper + single-column UPDATE returning bool
```python
# SOURCE: app/db/database.py:1476-1483, 1577-1585
def _row_to_user(row: _Row) -> User:
    return User(user_id=row["user_id"], role=row["role"], token_hash=row["token_hash"],
                active=bool(row["active"]), created_at=row["created_at"])

def set_user_token_hash(user_id: str, token_hash: str) -> bool:
    with _session() as conn:
        cursor = conn.execute("UPDATE users SET token_hash = ? WHERE user_id = ?", (token_hash, user_id))
        return cursor.rowcount == 1
```

### CLI subcommand + error handling
```python
# SOURCE: scripts/manage_users.py:57-63 (unknown user -> stderr "Error: no user ...", return 1)
def _deactivate_user(args: argparse.Namespace) -> int:
    init_db()
    if not deactivate_user(args.user_id):
        print(f"Error: no user with user_id '{args.user_id}'.", file=sys.stderr)
        return 1
    print(f"Deactivated user '{args.user_id}'.")
    return 0
```

### Tests
```python
# SOURCE: tests/test_manage_users_cli.py:156-160
def test_deactivate_user_unknown_user_exits_nonzero(temp_db, capsys):
    exit_code = main(["deactivate-user", "--user-id", "ghost"])
    assert exit_code == 1
    assert "no user" in capsys.readouterr().err

# SOURCE: tests/test_manage_users_cli.py:41-48 (argparse rejection -> SystemExit, nothing written)
    with pytest.raises(SystemExit) as exc_info:
        main(["create-user", "--user-id", "eve", "--role", "superuser"])
    assert exc_info.value.code != 0

# SOURCE: tests/test_db.py:424-468 (legacy-schema fixture), 3226-3263 (migrate test),
#         3267-3333 (ordering + no-ALTER-on-fresh tests via _RecordingConnection/_install),
#         2228-2269 (mapping shape / declared-in-CREATE / NOT NULL-needs-DEFAULT twins)
```

| Category | File:Lines | Pattern |
|----------|------------|---------|
| SCHEMAS | `app/db/models.py:150-165, 236-261` | Column declared in CREATE **and** in an `*_ADDED_COLUMNS` mapping, with a rationale comment |
| MIGRATION | `app/db/database.py:699-711, 714-767` | `_add_missing_columns(conn, table, mapping)` after the table's CREATE; tolerates a duplicate column from a concurrent boot |
| NAMING | `app/db/database.py:1566-1585` | `verb_user_thing(user_id, ...) -> bool` with `rowcount == 1` |
| ERRORS | `scripts/manage_users.py:57-63` | `Error: ...` to stderr, `return 1`; argparse `choices`/`type` failures → `SystemExit(2)` |
| DATACLASS | `app/db/models.py:416-422` | New optional fields go **after** existing ones so positional construction keeps working |
| TESTS | `tests/test_identity.py:22-90`, `tests/test_manage_users_cli.py`, `tests/test_db.py` | `temp_db` / `uninitialized_db` + `db_connect` fixtures |

---

## Design Notes

1. **Pass position.** `_add_missing_columns(conn, "users", USERS_ADDED_COLUMNS)` goes immediately after `conn.execute(CREATE_USERS_TABLE)` and before `CREATE_USERS_TOKEN_HASH_INDEX`. The reason is the one `chat_messages` has: on a fresh database, `PRAGMA table_info(users)` before the CREATE reports no columns, and the pass would ALTER a table that does not exist. The index does not read the new columns, so placing the pass before it is a matter of tidiness, not correctness.
2. **Sentinel.** Use a module-level `_UNCHANGED = object()` in `database.py`. `set_user_limits(user_id, *, token_budget_daily=_UNCHANGED, requests_per_minute=_UNCHANGED) -> bool` builds `SET` only from the arguments that are not `_UNCHANGED`, so `None` writes NULL. Column names come from a fixed tuple, never from caller strings. With no column passed it raises `ValueError`, because that is a programming error; the CLI never reaches it (Note 4). It returns `rowcount == 1`, so an unknown user returns `False` and writes nothing.
3. **Value parsing in the CLI, not the DB layer.** Use an argparse `type=_limit_value` that returns `None` for `default` (case-insensitive) and an `int` ≥ 1 for a number. Anything else raises `argparse.ArgumentTypeError`, which becomes `SystemExit(2)` with a message on stderr. That happens before `init_db()`, so nothing is written (AC3). It accepts only the word `default`, not `unlimited`: per PRD 6.6, `unlimited` belongs to the role settings, and an override is either a number or "use the role's".
4. **"Leave alone" in argparse.** Both flags use `default=argparse.SUPPRESS`, so an omitted flag is absent from `vars(args)` and is never passed through. Giving neither flag is an error: call `parser.error("set-limits needs --token-budget and/or --requests-per-minute")`, which exits 2 and writes nothing.
5. **Identity.** Append `break_glass: bool = False`, `token_budget_daily: Optional[int] = None` and `requests_per_minute: Optional[int] = None` after `role`. `Identity(user_id, role)` and `Identity("ana", "user") == Identity("ana", "user")` keep working. `resolve()` returns `Identity(user_id="admin", role="admin", break_glass=True)` on the `ADMIN_TOKEN` path, leaving the overrides at `None`. The user path passes `user.token_budget_daily` and `user.requests_per_minute` and leaves `break_glass` False, even when the role is `admin`.
6. **`list-users` format.** Append two tab-separated fields: `user_id\trole\tactive\tcreated_at\t<budget>\t<rpm>`. Print `default` when a value `is None`; use the `is None` check rather than `or`.

## Risks

| Risk | Mitigation |
|------|-----------|
| `tests/test_identity.py:63, 78, 90` assert `resolve(ADMIN_TOKEN) == Identity("admin", "admin")`, which fails once `break_glass=True` | Update all three to `Identity(user_id="admin", role="admin", break_glass=True)`. AC5 asks for exactly this change |
| `tests/test_migrate_to_turso_cli.py:179` pins `_ddl_columns(CREATE_USERS_TABLE)` to five names | Add the two new names. `scripts/migrate_to_turso.py:240-266` already handles a source that lacks them: it leaves them out of the INSERT, so the destination default (NULL) applies. No script change |
| The race test `test_two_init_db_calls_racing_on_history_trimmed_both_converge` (`tests/test_db.py:4306`) gates every `PRAGMA table_info` on a barrier. A third pass adds a third crossing | Both threads run the same path, so the crossings stay symmetric. Run the test explicitly in Task 7. Also update its docstring ("twice, once per table" becomes three times) |
| `test_init_db_issues_no_alter_when_schema_is_current` and the "one bootstrap `_session()`" assertions | The new pass reuses the same connection and issues no ALTER in steady state. Both should pass unchanged; run them to confirm |
| `_row_to_user` reads `row["token_budget_daily"]` on a `users` table that was never migrated | Every production read path runs `init_db()` first (`app/main.py` lifespan, `chat_ui` import, every CLI command). No test builds a hand-written legacy `users` table today (grep found none), so plain indexing is safe and matches the other mappers |
| The `Identity` fields could be read before STORY-010 exists | Nothing reads them in this story, by design. Grep after implementing should show no reader outside `identity.py` and tests |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/models.py` | UPDATE | Declare the two columns in `CREATE_USERS_TABLE`; add `USERS_ADDED_COLUMNS` with a rationale comment; add `User.token_budget_daily` and `User.requests_per_minute` |
| `app/db/database.py` | UPDATE | Import `USERS_ADDED_COLUMNS`; add the third `_add_missing_columns` pass plus an `init_db` docstring paragraph; extend `_row_to_user`; add `_UNCHANGED` and `set_user_limits()` |
| `app/services/identity.py` | UPDATE | Add three `Identity` fields; `resolve()` sets them |
| `scripts/manage_users.py` | UPDATE | `set-limits` subcommand, `_limit_value` type, and two `list-users` fields |
| `tests/test_db.py` | UPDATE | Mapping-shape tests, a pre-limits `users` fixture and its migrate test, ordering test, no-ALTER-on-fresh test, `set_user_limits` unit tests, race docstring |
| `tests/test_identity.py` | UPDATE | Break-glass expectations, override carry-through, admin-role user test, default-construction test |
| `tests/test_manage_users_cli.py` | UPDATE | `set-limits` cases and the `list-users` limits columns |
| `tests/test_migrate_to_turso_cli.py` | UPDATE | Pinned users column list gains two names |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Schema and dataclass

- **File**: `app/db/models.py`
- **Action**: UPDATE
- **Implement**:
  - Add `token_budget_daily INTEGER,` and `requests_per_minute INTEGER` to `CREATE_USERS_TABLE`, after `created_at`.
  - After `CREATE_USERS_TOKEN_HASH_INDEX`, add `USERS_ADDED_COLUMNS = {"token_budget_daily": "INTEGER", "requests_per_minute": "INTEGER"}`. Its comment should cover: the third mapping (PRD-013 STORY-008, Section 6.6); declared in both places, for the reason the audit mapping gives; nullable with no default on purpose, since NULL means "use the role's limit" and is the true value for every existing user; additive only; nothing reads it until STORY-010.
  - Append `token_budget_daily: Optional[int] = None` and `requests_per_minute: Optional[int] = None` to `User`, after `created_at`, with a short comment.
- **Mirror**: `app/db/models.py:236-261` (`CHAT_MESSAGES_ADDED_COLUMNS` and its comment)
- **Validate**: `python -c "from app.db.models import USERS_ADDED_COLUMNS, User; print(User('a','user','h'))"`

### Task 2: Convergence and mapper

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - Import `USERS_ADDED_COLUMNS`.
  - In `init_db()`, insert `_add_missing_columns(conn, "users", USERS_ADDED_COLUMNS)` on the line after `conn.execute(CREATE_USERS_TABLE)` (Design Note 1).
  - Add a docstring paragraph: "PRD-013 STORY-008 makes `users` the third table on this path ... after `CREATE_USERS_TABLE` for the reason the `chat_messages` pass gives".
  - Extend `_row_to_user` with both fields.
- **Mirror**: `app/db/database.py:672-711`
- **Validate**: `pytest tests/test_db.py -q -k "init_db or added_columns"`

### Task 3: `set_user_limits`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Below `set_user_token_hash`, add `_UNCHANGED = object()` and `set_user_limits(user_id, *, token_budget_daily=_UNCHANGED, requests_per_minute=_UNCHANGED) -> bool`, following Design Note 2. Build `assignments` from the fixed pairs `(("token_budget_daily", token_budget_daily), ("requests_per_minute", requests_per_minute))`, skipping `_UNCHANGED`. Raise `ValueError` if the result is empty. Run one `UPDATE users SET a = ?, b = ? WHERE user_id = ?` and return `cursor.rowcount == 1`. The docstring covers the sentinel versus `None`, that values are not validated here (the CLI owns parsing), and that the next `resolve()` sees the change (PRD 6.6).
- **Mirror**: `app/db/database.py:1577-1585`
- **Validate**: covered by Task 6 tests

### Task 4: Identity fields and `resolve()`

- **File**: `app/services/identity.py`
- **Action**: UPDATE
- **Implement**: Follow Design Note 5. Extend the class docstring: `break_glass` is True only for the `ADMIN_TOKEN` credential (PRD 6.8); the overrides come from the `users` row that `resolve()` already reads (PRD 6.6), with no extra round trip; the break-glass identity has no row, so its overrides are `None`; nothing reads the fields until STORY-010 and STORY-013.
- **Mirror**: existing `resolve()` at `app/services/identity.py:46-63`
- **Validate**: `pytest tests/test_identity.py -q` (three admin assertions are expected to fail until Task 6)

### Task 5: CLI `set-limits` and `list-users`

- **File**: `scripts/manage_users.py`
- **Action**: UPDATE
- **Implement**:
  - Import `set_user_limits`.
  - `_limit_value(raw: str) -> Optional[int]`: `default` maps to `None`. Otherwise `int(raw)`; on `ValueError`, raise `ArgumentTypeError(f"expected a whole number ≥ 1 or 'default', got '{raw}'")`. A value below 1 raises `ArgumentTypeError(f"must be at least 1 or 'default', got {value}")`.
  - Add a `_LIMIT_FLAGS` mapping from `dest` to column.
  - `_set_limits(args)`: collect `changes` from `vars(args)` for `token_budget_daily` and `requests_per_minute`. Call `init_db()`. If `set_user_limits(args.user_id, **changes)` is false, print `Error: no user with user_id '...'.` to stderr and return 1. Otherwise print `Set limits for '<id>': token budget <v|default>, requests per minute <v|default>`, showing only the flags that were passed, and return 0.
  - Parser: `set-limits` with `--user-id` (required), `--token-budget` (`dest="token_budget_daily"`, `type=_limit_value`, `default=argparse.SUPPRESS`, `metavar="N|default"`) and `--requests-per-minute` (`dest="requests_per_minute"`, same). The "neither flag" check (Design Note 4) runs inside `main` after `parse_args`, or in `_set_limits` with `parser.error`. Pick the one that keeps `_set_limits` testable through `main()`.
  - `_list_users`: append `\t{_limit_text(user.token_budget_daily)}\t{_limit_text(user.requests_per_minute)}`, where `_limit_text(v)` returns `"default" if v is None else str(v)`.
- **Mirror**: `scripts/manage_users.py:57-63, 77-99`
- **Validate**: `python scripts/manage_users.py set-limits --help`

### Task 6: Tests

- **Files**: `tests/test_db.py`, `tests/test_identity.py`, `tests/test_manage_users_cli.py`, `tests/test_migrate_to_turso_cli.py`
- **Action**: UPDATE
- **Implement**:
  - **test_db.py** (AC1):
    - `test_users_added_columns_carries_two_nullable_limits`: the mapping equals the expected dict, both appear in `CREATE_USERS_TABLE`, and there is no NOT NULL or DEFAULT.
    - `test_every_users_added_column_is_also_declared_in_the_create`, the twin of `:2243`.
    - `test_users_added_columns_declaring_not_null_also_declare_a_default`, the twin of `:2252`.
    - Fixture `_create_pre_user_limits_database(connect, url)`: `audit_logs`, `chat_sessions` and `chat_messages` from current constants; `users` as the five-column legacy DDL plus the token-hash index; two seeded users.
    - `test_init_db_migrates_a_pre_user_limits_database`: both columns exist, both seeded rows read `None` on both fields through `get_user`, and the other fields are preserved.
    - `test_init_db_adds_the_user_limit_columns_after_creating_the_table`: in the `_RecordingConnection` statement order, `CREATE_USERS_TABLE` comes before the ALTER.
    - Extend `test_init_db_adds_no_..._alter_to_a_fresh_database`, or add a users twin.
    - `set_user_limits` unit tests: setting one column leaves the other unchanged; `None` clears to NULL; an unknown user returns `False`; no arguments raises `ValueError`.
    - Update the race-test docstring.
  - **test_identity.py** (AC2, AC5):
    - Update `:63`, `:78` and `:90` to expect `break_glass=True`.
    - Add `test_resolve_admin_token_sets_break_glass_and_no_overrides`.
    - Add `test_resolve_admin_role_user_token_is_not_break_glass`.
    - Add `test_resolve_carries_the_users_limit_overrides`, which inserts a user and calls `set_user_limits(..., token_budget_daily=5_000_000)`.
    - Add `test_identity_two_positional_args_still_construct`, checking the defaults are `False`/`None`/`None`.
  - **test_manage_users_cli.py** (AC2–AC4):
    - `set-limits --token-budget 5000000`: the row is updated, `requests_per_minute` is unchanged (pre-set it to 30 first to prove it), and `resolve` on the token from create-user's stdout returns `token_budget_daily=5000000`.
    - `default` clears each column.
    - Parametrize `0`, `-5` and `abc` → `SystemExit` with a non-zero code, the message on stderr, and the row unchanged.
    - An unknown user exits 1 with `no user` and creates no row.
    - Neither flag → `SystemExit` with a non-zero code.
    - `list-users` shows `default\tdefault` for a fresh user and the numbers after `set-limits`.
  - **test_migrate_to_turso_cli.py:179**: add `"token_budget_daily", "requests_per_minute"` to the expected list.
- **Mirror**: the test sources listed in Patterns
- **Validate**: `pytest tests/test_db.py tests/test_identity.py tests/test_manage_users_cli.py tests/test_migrate_to_turso_cli.py -q`

### Task 7: Full regression

- **Action**: run only
- **Validate**:
  - `pytest tests/ -q`, the whole suite. Watch in particular `test_two_init_db_calls_racing_*`, `test_init_db_issues_no_alter_when_schema_is_current`, `tests/test_rbac.py` and `tests/test_chat_sessions.py:1677`.
  - `grep -rn "token_budget_daily\|requests_per_minute\|break_glass" app chat_ui` should show readers only in `identity.py`, `database.py`, `models.py` and `config.py` (STORY-007's settings), with none in the pipeline.

---

## End-to-End Tests

- [ ] On a scratch DB (`DATABASE_URL=file:./tmp_s008.db`): `python scripts/manage_users.py create-user --user-id dana --role user`, then `set-limits --user-id dana --token-budget 5000000`. Exit 0, and `list-users` shows `dana ... 5000000\tdefault`
- [ ] `set-limits --user-id dana --requests-per-minute 30`, then `--token-budget default`. `list-users` shows `default\t30`
- [ ] `set-limits --user-id dana --token-budget 0` / `abc` / `--user-id ghost --token-budget 5` exit non-zero with a message, and `list-users` is unchanged
- [ ] Booting against a DB created before this story (an existing dev DB) adds both columns. `list-users` shows `default\tdefault` for every existing user
- [ ] `python -c "from app.services.identity import resolve; from app.config import settings; print(resolve(settings.ADMIN_TOKEN))"` shows `break_glass=True, token_budget_daily=None, requests_per_minute=None`

---

## Validation

```bash
pytest tests/test_db.py tests/test_identity.py tests/test_manage_users_cli.py tests/test_migrate_to_turso_cli.py -q
pytest tests/ -q
python scripts/manage_users.py set-limits --help
```

---

## Acceptance Criteria

(Copied from story `STORY-008`)

- [ ] Given a `users` table created before this story, when `init_db()` runs, then `token_budget_daily INTEGER` and `requests_per_minute INTEGER` exist, both NULL on every existing row, converged through a new `USERS_ADDED_COLUMNS` mapping and the existing `_add_missing_columns`.
- [ ] Given `python scripts/manage_users.py set-limits --user-id dana --token-budget 5000000`, when it runs, then Dana's row has `token_budget_daily=5000000`, her `requests_per_minute` is unchanged, and `resolve(dana_token)` returns an `Identity` with `token_budget_daily=5000000`.
- [ ] Given `--token-budget default` or `--requests-per-minute default`, when it runs, then that column is set to NULL; given a value below 1, a non-number, or an unknown user, then the command exits non-zero with a message and writes nothing.
- [ ] Given `list-users`, when it runs, then each line shows both limits, printing `default` for NULL.
- [ ] Given `resolve(settings.ADMIN_TOKEN)`, when it returns, then the identity has `break_glass=True` and both overrides `None`; given a user token whose role is `admin`, then `break_glass` is `False`.
- [ ] All tasks completed
- [ ] Full `pytest tests/` passes
- [ ] Follows existing patterns (added-columns convergence, `-> bool` user setters, CLI stderr/exit-code style)
