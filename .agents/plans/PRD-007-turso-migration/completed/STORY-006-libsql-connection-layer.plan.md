---
story: STORY-006
prd: PRD-007
slug: libsql-connection-layer
title: "Swap app/db/database.py onto a shared libSQL client, preserving all 22 public signatures"
type: REFACTOR
complexity: HIGH
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-01
---

# Plan: Swap `app/db/database.py` onto a shared libSQL client

## Summary

Replace `sqlite3` inside `app/db/database.py` with `libsql==0.1.11` while keeping every public
name, signature and return type identical, so the ~40 call sites across routers, services, the
chat UI and the CLI need no edits. The whole swap lands behind one chokepoint: `get_connection()`
stops constructing a `sqlite3.Connection` per call and starts handing out a thin wrapper over a
**cached libSQL client** (one handshake per thread, not per call), whose cursors are iterable and
whose rows answer both `row["timestamp"]` and `(count,) = row`. That wrapper is what lets the 22
functions, both row mappers, `_add_missing_columns()`'s `PRAGMA table_info` loop, and thirteen
test modules survive untouched. `_translated()` gains a libSQL arm — every SQL failure arrives as
a bare `builtins.ValueError` carrying a Hrana-wrapped message (STORY-001 §3.5) — and `_session()`
commits **explicitly** rather than inheriting a context manager's semantics (PRD Risk 1's
mitigation). `tests/conftest.py` flips from `tmp_path` SQLite files to a session-scoped local
libSQL server with a per-test schema reset, so every test still gets an isolated, empty database,
offline and account-free.

## User Story

As a maintainer
I want `app/db/database.py` running on libSQL with an unchanged public surface
So that the ~40 call sites need no edits and the migration stays confined to one module

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-006-libsql-connection-layer.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md`
- **Driver decision record (read before writing a line)**:
  `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md`

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (driver swap, behavior-preserving) |
| Complexity | HIGH — atomic, cannot be split (story Technical Notes) |
| Systems Affected | `app/db/`, test infrastructure, dependency pin, CI |
| Story | STORY-006 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds one skill, `frontend-design`, whose `SKILL.md` description scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story touches no UI. | none |

The story's `skills:` frontmatter is empty and the scan of `.agents/skills/` confirms it. No skill
constrains this work.

---

## Patterns to Follow

### The public surface that must not move

```python
# SOURCE: app/db/database.py:29-31 -- the chokepoint, and the only thing being replaced
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn
```

`get_connection` is **not** private and **not** optional: thirteen test modules import it and use
`with get_connection() as conn:` plus `conn.execute(...).fetchone()` with named-column access
(`tests/test_db.py:43`, `:167`, `:855`; `tests/test_chat_state.py:57`;
`tests/test_query_router.py:47`; `tests/test_integration.py:38`;
`tests/test_pii_dedup_isolation.py:62`; `tests/test_pii_redaction_integration.py:56`;
`tests/test_query_pipeline_authorization.py:18`; `tests/test_rbac.py:56`;
`tests/test_conftest_fixtures.py:82`). The name survives; its body and return type change.

### Error translation — the one seam that knows the driver

```python
# SOURCE: app/db/database.py:50-67
@contextmanager
def _translated() -> Iterator[None]:
    """Driver exceptions in, app.db.errors exceptions out.

    The single seam in the codebase where sqlite3's exception hierarchy is known.
    STORY-006 rewrites this body and nothing else has to change.
    """
    try:
        yield
    except sqlite3.IntegrityError as exc:
        raise IntegrityError(_constraint_of(exc), str(exc)) from exc
    except sqlite3.OperationalError as exc:
        ...
```

STORY-004 wrote that docstring as a promise to this story. Honour it: `app/db/errors.py` is not
edited — its module docstring already states "this module deliberately imports no driver, so
STORY-006 replaces the client underneath it without touching a line of it."

### Session semantics

```python
# SOURCE: app/db/database.py:69-79
@contextmanager
def _session() -> Iterator[sqlite3.Connection]:
    with _translated():
        conn = get_connection()
        with conn:
            yield conn
```

### Rows, as the driver actually returns them

```
# SOURCE: .agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md §2.1
type(row) = <class 'tuple'>
row['timestamp']: RAISED builtins.TypeError: tuple indices must be integers or slices, not str
# but description IS populated, for SELECT * and for aliased aggregates:
SELECT *    -> ['id', 'timestamp', ..., 'denied_permission']
aliased agg -> ['n']
```

```python
# SOURCE: driver decision §3.1 -- proven against the endpoint
cur = conn.cursor()
cur.execute("SELECT * FROM audit_logs LIMIT 1")
names = [c[0] for c in cur.description]
dict(zip(names, cur.fetchone()))["timestamp"]
```

### Tests

```python
# SOURCE: tests/test_db.py:156-176 -- the shape every db test takes
def test_init_db_migrates_pre_pii_database(uninitialized_db, db_connect):
    _create_pre_pii_database(db_connect, uninitialized_db)
    init_db()
    with get_connection() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
    assert {"pii_detected_input", "pii_detected_output", "pii_entities"} <= columns
```

Note the **iteration over a cursor** and the **named access on a PRAGMA row** — both of which the
raw driver refuses (decision record §2.5). The wrapper must restore both, or this test and
`app/db/database.py:95` break together.

```python
# SOURCE: tests/conftest.py:130-140 -- the fixture seam STORY-003 built for this story
@pytest.fixture
def database_url(tmp_path, monkeypatch) -> str:
    url = _url_for(tmp_path, "test.db")
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    return url
```

---

## Design

### D1 — Client lifetime: cached per (thread, URL), not per call, not one global

PRD Pattern 1 requires "a process-wide client created once and reused"; the story's Technical Notes
require confirming thread-safety first, because `chat_ui/chat_ui/admin_state.py:1018` reaches these
functions through `asyncio.to_thread(...)` and FastAPI dispatches its `def` endpoints to a
threadpool. **The decision record does not answer thread-safety** — it was not one of the six
behaviors — and upstream documents no guarantee. So Task 1 answers it empirically, the same way
STORY-001 answered everything else, and the answer selects between two pre-designed shapes:

- **Default (safe under either answer): a per-thread cache.** `threading.local()` holding
  `(url, auth_token, client)`. One handshake per worker thread instead of one per call — which is
  the cost model Pattern 1 exists to fix (a ten-read console load pays at most one handshake, not
  ten) — and thread-confined, which is what `sqlite3` connections were.
- **If Task 1 proves the client safe under concurrent use**: collapse to a single module-level
  client behind the same `_client()` accessor. No caller changes; the diff stays inside one
  function.

The cache key **must include the current `DATABASE_URL`**. Every test repoints
`settings.DATABASE_URL` through `monkeypatch` on a constructed `Settings` instance
(`tests/conftest.py:120`), so a client cached without regard to the URL would serve test N+1 from
test N's endpoint. This is the single easiest way to make the whole suite lie.

### D2 — `get_connection()` returns a wrapper, and the wrapper is the whole trick

Three small private classes in `app/db/database.py`:

| Class | Answers | Why it must exist |
|---|---|---|
| `_Row` | `row["timestamp"]`, `row[0]`, `(count,) = row`, `len(row)`, `.keys()` | Rows are plain tuples (§2.1). `_row_to_audit_log()`'s 19 named reads, `_row_to_user()`'s 5, `row["n"]` in seven counters, and `tests/test_conftest_fixtures.py:158`'s `(count,) = ...fetchone()` all have to keep working. Model it on `sqlite3.Row`: mapping **and** sequence. |
| `_Cursor` | `__iter__`, `fetchone`/`fetchall`/`fetchmany`, `lastrowid`, `rowcount`, `description` | The driver's `Cursor` is **not iterable** (§2.5) yet `app/db/database.py:95` and four tests iterate one. Wrapping restores it and maps every row through `_Row` using `description`. |
| `_Connection` | `execute`, `cursor`, `commit`, `rollback`, `close`, `__enter__`/`__exit__` | Keeps `with get_connection() as conn:` meaning a transaction, not a connection lifetime — and `close()` must be a **no-op** on the shared client (§3.2: "close() does not imply commit", and closing a shared client would strand every other caller). |

`lastrowid` and `rowcount` pass straight through: verified `1,2,3` and `1`/`0`-never-`-1`
(§2.3, §2.4), so `insert_audit_log()`, `deactivate_user()` and `set_user_token_hash()` need no
logic change.

### D3 — Commit explicitly (PRD Risk 1)

`with conn:` on the raw client *is* durable (§2.2), but PRD Risk 1's mitigation is explicit:
"Phase 2 makes commits explicit rather than inherited from a context manager." So
`_Connection.__exit__` calls `commit()` on success and `rollback()` on an exception, and
`_session()` keeps its shape. Two traps the decision record proved are live: a write outside any
`with` block is **silently lost**, and `close()` discards uncommitted work.

### D4 — `_translated()` matches on message shape, not on exception type

Every SQL error is a bare `builtins.ValueError` (§3.5); there is no hierarchy, and `libsql.Error`
exists but is not what gets raised. Catching bare `ValueError` unconditionally would swallow
genuine programming errors, so translate only what looks like a driver error:

| Message contains | Becomes |
|---|---|
| `constraint failed: <name>` | `IntegrityError(constraint, message)` — the existing `_CONSTRAINT` regex already matches `UNIQUE constraint failed: users.user_id` |
| `no such table: <name>` | `MissingRelationError(relation, message)` — the existing `_MISSING_RELATION` regex already matches |
| any other Hrana/SQLite-shaped failure (`Hrana:`, `SQLite error:`, a `code: "SQLITE_…"` field) | `StorageError(message)` |
| anything else | re-raised untouched |

The two regexes at `app/db/database.py:41-42` survive verbatim — their comment already predicted
this ("libSQL is SQLite-derived and emits the same text, so STORY-006 re-verifies these two
patterns rather than replacing the approach"). Task 1 re-verifies them against live messages.

### D5 — Test isolation: one session-scoped server, schema reset per test

The decision record §4 gives two options and recommends this one: "For per-test isolation,
STORY-003 should drop and recreate the schema per test, or run one container per test session."

- A session fixture resolves the endpoint from `HARNESS_TEST_LIBSQL_URL` (default
  `http://127.0.0.1:8080`), health-checks it, and **fails with the exact `docker run` line from
  §4** if it is unreachable. No silent skip: a suite that quietly stops testing storage is worse
  than a red one.
- The existing autouse fixture `_never_the_configured_database` becomes the reset: drop every table
  and index in the database, then point `settings.DATABASE_URL` at the endpoint. pytest
  instantiates autouse fixtures first, so every test — including the six that never asked for a
  database — starts empty.
- **What this costs, stated plainly**: `database_url_factory` can no longer mint *distinct* URLs,
  because one sqld instance without namespaces serves one database. Its two contract tests in
  `tests/test_conftest_fixtures.py` (`test_factory_yields_a_distinct_url_on_every_call`,
  `test_factory_does_not_patch_this_process_settings`) assert distinctness and must be rewritten —
  **keeping their names**, because `tests/test_pii_redaction_integration.py:353`'s census guard
  fails on a removed or renamed test function. What replaces the guarantee: the three subprocess
  probes (`tests/test_admin_shell.py:697`, `tests/test_render_invariants.py:260`,
  `tests/test_chat_ui_startup_guard.py:66`) each run inside a test whose reset has already fired,
  so each still sees an empty database — which is all any of them needs (the RBAC guard probe in
  particular needs the `users` table to hold no admin).
- **Rejected: namespace-per-test** (`--enable-namespaces` plus
  `POST /v1/namespaces/<ns>/create`, addressed as `http://<ns>.localhost:8080`). It would preserve
  distinct URLs, but the client reaches a namespace by *hostname*, and `<ns>.localhost` does not
  resolve inside a Debian-based container (Docker's embedded DNS returns NXDOMAIN; only
  systemd-resolved hosts answer wildcard `.localhost`). That makes the suite pass on one machine
  and fail on another — the opposite of what the AC "offline and account-free are non-negotiable
  properties" protects. Revisit only if proven to resolve in both the container and CI.

### D6 — `CHILD_SETTINGS_PREAMBLE` and `TEST_DATABASE_URL_ENV` are deleted

`tests/conftest.py:63-77` says so in its own comment: they exist only because STORY-005's validator
rejects the `sqlite:///` URL a child process would construct for itself, so the real URL had to
travel in a second variable. Once the fixtures mint real libSQL endpoints, `DATABASE_URL` carries
them directly and both symbols go. `child_db_env(url)` stays (three call sites) and returns
`{"DATABASE_URL": url}`; the three modules drop `CHILD_SETTINGS_PREAMBLE` from their imports and
their `_CHECK_SCRIPT` concatenations. None of the three is in
`test_pii_redaction_integration.py`'s `_PRE_EPIC_UNTOUCHED_TESTS`, so they may be edited.

### D7 — The `grep sqlite3` acceptance criterion, precisely

`grep -rn "sqlite3" app/ chat_ui/ scripts/` will still hit **prose**: four historical mentions in
`app/db/errors.py`'s docstrings ("Before this module existed…", "It stands in for `sqlite3.Error`")
and one in `chat_ui/chat_ui/admin_state.py:981`. STORY-002 hit this exact wall and resolved it the
same way (its report, Deviation 1: "The greps were too blunt: they match the word `sqlite3` in
docstring prose… The AST check verifies the real invariant"). This plan therefore:

1. Makes the **code-level** claim true and checks it by AST: no `import sqlite3` and no `sqlite3.`
   reference under `app/`, `chat_ui/chat_ui/`, `scripts/`.
2. Fixes the one comment the swap makes **factually false** — `chat_ui/chat_ui/admin_state.py:981-982`
   ("Every function in `app/db/database.py` opens its own `sqlite3` connection… and a connection
   cannot cross threads"). After this story it reaches a shared client; the per-call offload stays
   correct but for a new reason, and the docstring must say the new one.
3. Leaves `app/db/errors.py`'s historical prose alone — it is accurate history, and rewriting it
   would delete the reasoning that justifies the module. **Recorded as a deliberate deviation from
   the AC's literal wording** in the report.

### D8 — Environment reality (blocks local validation, not the design)

`libsql` is a compiled extension with **no Windows wheel for Python 3.14** (decision record §5),
and this development host is Windows on Python 3.14.4. Every validation command below therefore
runs inside `python:3.11`, exactly as STORY-001 did. **`docker` is installed here but the daemon is
not currently running** (`docker ps` → "failed to connect… dockerDesktopLinuxEngine"). Starting
Docker Desktop is a prerequisite for Task 1 and every validation step after it.

CI already pins Python 3.11 (`.github/workflows/ci.yml:18`) and installs from `requirements.txt`,
so the wheel resolves there. What CI lacks is a database: it needs the pinned libsql-server as a
service container. Adding it is not optional — without it every storage test fails on the next
push — so it is Task 8, flagged as a file outside the story's stated list.

### Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `requirements.txt` | UPDATE | add `libsql==0.1.11` (exact pin, decision record §1) |
| `app/db/database.py` | UPDATE | the swap: client cache, `_Row`/`_Cursor`/`_Connection`, `_translated()` libSQL arm, explicit commit, `_db_path()`/`_SQLITE_PREFIX` deleted |
| `tests/conftest.py` | UPDATE | endpoint fixture + per-test schema reset; `db_connect` returns a raw libSQL client; `CHILD_SETTINGS_PREAMBLE`/`TEST_DATABASE_URL_ENV` deleted |
| `tests/test_conftest_fixtures.py` | UPDATE | the two factory-contract tests re-stated against the endpoint model (names kept) |
| `tests/test_db.py` | UPDATE | two tests that reach for `sqlite3` internals: `set_trace_callback` and the `_LockedConnection` raising `sqlite3.OperationalError` |
| `tests/test_admin_shell.py` | UPDATE | drop `CHILD_SETTINGS_PREAMBLE` (import + concatenation + stale comment) |
| `tests/test_render_invariants.py` | UPDATE | same |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | same |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | docstring only: the per-call offload's reason changes from "a connection cannot cross threads" to the shared client's actual rule |
| `.github/workflows/ci.yml` | UPDATE | libsql-server service container + `DATABASE_URL`, so the suite has a database in CI |
| `app/db/errors.py` | UNCHANGED | STORY-004 built it to survive this story untouched |
| `app/db/models.py` | UNCHANGED | DDL verified libSQL-compatible as-is (§2.5); if it needs a change, that is a report finding |

**No file under `app/routers/`, `app/services/`, or `scripts/` is touched.** If a task tempts you
to edit one, stop — that is the signal the wrapper is incomplete.

### Dependency order

1 (verify) → 2 (pin) → 3 (test infrastructure) → 4 (the swap) → 5 (errors) → 6 (the three
sqlite3-internal tests) → 7 (comments/probes) → 8 (CI) → 9 (full suite + durability proof).
Tasks 3 and 4 are the atomic pair: the suite is red between them and green only after both.

### Risks + mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Silent write loss** (PRD Risk 1, highest severity). A lost `insert_audit_log()` is invisible until someone reads an empty audit trail. | Explicit `commit()` in `_Connection.__exit__` (D3), plus Task 9's read-back through a **separate, freshly constructed client** for every write function. Never accept a same-client read as evidence. |
| R2 | The client is not thread-safe and a module-level singleton corrupts state under the console's `asyncio.to_thread` reads. | Task 1 answers it; the per-thread cache (D1) is correct under either answer, so the swap is never blocked on the result. |
| R3 | A cached client outlives a `monkeypatch`ed `DATABASE_URL`, and the whole suite silently tests one database. | Cache key includes the URL (D1). Task 6 adds a fixture-contract test that two different URLs yield two different clients. |
| R4 | `close()` on the shared client from a caller strands every other caller. | `_Connection.close()` is a no-op with a docstring saying why; the real client is closed only at process exit, and only after `commit()` (§3.2). |
| R5 | Hidden `sqlite3`-shaped assumptions in tests beyond the three found. | Task 9 runs the **full** suite, not the db subset, and compares the failure list against the 7 pre-existing failures recorded in STORY-001's report. |
| R6 | The per-test reset misses an object (e.g. an index) and state leaks between tests. | Reset drops from `sqlite_master` for both `table` and `index` types, and a fixture-contract test writes a row in one test and asserts an empty table in the next. |
| R7 | Scope creep into STORY-007/009/010. | `init_db()` concurrency, `top_pii_entities()` aggregation and batched reads are explicitly **out**. Duplicate-`ADD COLUMN` still crashes after this story; that is STORY-007's job, and decision record §2.5 already captured the error text for it. |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Answer the two open driver questions before touching production code

- **File**: none (throwaway probe, not committed — the same constraint STORY-001 worked under)
- **Action**: VERIFY
- **Implement**: Start the pinned dev server and a `python:3.11` probe container (decision record
  §4/§7 has the exact commands). Answer, by pasted observation:
  1. **Thread-safety**: N threads sharing one `libsql` client, each running a mixed read/insert
     loop against `audit_logs`; then the same with a client per thread. Record whether the shared
     case raises, corrupts, or deadlocks. This selects between D1's two shapes.
  2. **`auth_token` keyword**: confirm the exact spelling `libsql.connect(url, auth_token=...)`
     against the local server (it takes no token, so assert the call is *accepted*), since
     `TURSO_AUTH_TOKEN` has no local endpoint to prove itself against.
  3. **Live error messages**: re-raise the four failures from §3.5, confirm the two existing regexes
     (`no such table: (\w+)`, `constraint failed: ([\w.]+)`) still match, and capture the shape a
     non-matching driver error takes (for D4's third row).
- **Mirror**: `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md` §7 — the
  harness recipe is written out there; reuse it rather than inventing one.
- **Validate**: three answers written into the story report's "Driver findings" section, each with
  pasted output. Nothing under `app/` changed yet: `git status --short app/` is empty.

### Task 2: Pin the driver

- **File**: `requirements.txt`
- **Action**: UPDATE
- **Implement**: add `libsql==0.1.11` — the exact pin decision record §1 names. Exact `==`,
  matching the file's existing `reflex==0.9.6.post1` style; PRD Section 8 requires an exact pin.
- **Mirror**: `requirements.txt:9`
- **Validate**: `docker run --rm -v "$PWD":/w -w /w python:3.11 pip install -r requirements.txt`
  resolves a `cp311` **wheel** for libsql, not the sdist (grep the log for
  `libsql-0.1.11-cp311-cp311-manylinux`).

### Task 3: Flip `tests/conftest.py` onto the local libSQL server

- **File**: `tests/conftest.py`
- **Action**: UPDATE
- **Implement**:
  - Delete `_SQLITE_PREFIX`, `_url_for`, `_path_from_url`, `TEST_DATABASE_URL_ENV`,
    `CHILD_SETTINGS_PREAMBLE`, and the `import sqlite3` / `from pathlib import Path` lines that go
    dead with them.
  - Add a session fixture resolving the endpoint from `HARNESS_TEST_LIBSQL_URL` (default
    `http://127.0.0.1:8080`), health-checked once; on failure, `pytest.exit` with the `docker run`
    command from decision record §4 in the message.
  - Add `_reset(url)`: connect a raw client, `SELECT name, type FROM sqlite_master WHERE type IN
    ('table','index') AND name NOT LIKE 'sqlite_%'`, `DROP` each (indexes first), commit.
  - `_never_the_configured_database` (autouse) calls `_reset` then patches `settings.DATABASE_URL`
    at the endpoint. `database_url` / `temp_db` / `uninitialized_db` keep their exact names, still
    return a `str` URL, and `temp_db` still calls `init_db()`.
  - `database_url_factory` returns the endpoint (D5); its docstring states plainly what changed and
    why, replacing the `mktemp` uniqueness claim.
  - `db_connect(url)` returns a **raw** `libsql.connect(url)` — still deliberately raw, still
    bypassing `app.db.database`, so `test_db.py`'s pre-migration schema builders keep building a
    shape `init_db()` would not produce.
  - Rewrite the module docstring: it currently promises "STORY-006 changes the two private helpers
    below and nothing else in `tests/`". That turned out to be false, and the file should say what
    is true.
- **Mirror**: `tests/conftest.py:110-165` for fixture shape and docstring density; endpoint and
  teardown commands from decision record §4.
- **Validate**: with the server up,
  `docker run --rm --network harness-libsql-net -v "$PWD":/w -w /w -e DATABASE_URL=http://harness-libsql-dev:8080 -e HARNESS_TEST_LIBSQL_URL=http://harness-libsql-dev:8080 -e OPENROUTER_API_KEY=test-key -e ADMIN_TOKEN=test-token python:3.11 sh -c "pip install -q -r requirements.txt && pytest tests/test_conftest_fixtures.py -q"`.
  At this point only the two factory tests Task 6 rewrites may fail — the isolation and
  URL-string tests must already pass.

### Task 4: The swap — `app/db/database.py`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - `import libsql`; delete `import sqlite3`, `_SQLITE_PREFIX`, `_db_path()`.
  - `_client()`: per-thread cache keyed on `(settings.DATABASE_URL, settings.TURSO_AUTH_TOKEN)`,
    constructing `libsql.connect(url)` locally and `libsql.connect(url, auth_token=token)` when the
    token is non-empty. Docstring states the handshake cost model (PRD Pattern 1) and the
    thread-confinement reason (D1), citing Task 1's answer.
  - `_Row`, `_Cursor`, `_Connection` per D2. `_Cursor` builds its name→index map once from
    `description` and returns `None` from `fetchone()` on an empty result (every caller checks
    `if row is None`).
  - `_Connection.__exit__`: `commit()` on success, `rollback()` on exception, and **return False**
    so exceptions propagate. `close()` is a documented no-op.
  - `get_connection() -> _Connection` — public name unchanged, return annotation now the wrapper.
  - `_session()` and `init_db()` keep their bodies. `_add_missing_columns()` keeps its
    `{row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}` line **unchanged** —
    the wrapper is what makes it legal again (§3.3).
  - `_row_to_audit_log(row: _Row)` / `_row_to_user(row: _Row)`: annotation only. **No body edits.**
  - **No `SELECT`, `INSERT`, `UPDATE` or `ALTER` text is edited.** Every statement already uses `?`
    placeholders. If you find yourself rewriting SQL, stop and ask why (story Technical Notes).
- **Mirror**: the module's own structure — private helpers above public functions, docstrings that
  carry the reason rather than the mechanic.
- **Validate**: `pytest tests/test_db.py -q` in the container: green except the tests Task 5 and
  Task 6 own.

### Task 5: The libSQL arm of `_translated()`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: per D4 — catch `ValueError`, classify by message using the two **existing** regexes
  plus a driver-shape guard, re-raise anything unrecognized untouched. Update `_constraint_of`'s
  annotation (its argument is now a `ValueError`) and the comment block at `:34-39`, which was
  written as a prediction and can now state Task 1's verified result. `app/db/errors.py` is **not**
  edited.
- **Mirror**: `app/db/database.py:50-67` — same contextmanager, same three outcomes, same
  `raise … from exc` chaining.
- **Validate**: `pytest tests/test_db.py -k "error or integrity or missing or token_hash" -q`, then
  `pytest tests/test_duplicate_checker.py tests/test_manage_users_cli.py tests/test_query_router.py tests/test_identity.py tests/test_auth_dependencies.py -q`
  — the STORY-002 characterization tests must pass **unmodified**.

### Task 6: The tests that reach past the public surface

- **Files**: `tests/test_db.py`, `tests/test_conftest_fixtures.py`
- **Action**: UPDATE
- **Implement**:
  - `test_init_db_issues_no_alter_when_schema_is_current` (`tests/test_db.py:100-117`) uses
    `conn.set_trace_callback` — a CPython-only hook the libSQL connection does not have (§2.6 lists
    its entire surface). Replace the traced connection with a recording proxy over
    `get_connection()` that appends the SQL passed to `.execute()`. The assertion ("no ALTER on a
    current schema") is unchanged; only the instrument moves. **Keep the test name.**
  - `test_find_user_by_token_hash_raises_when_the_failure_is_not_a_missing_table`
    (`tests/test_db.py:1067-1100`) has `_LockedConnection.execute` raise
    `sqlite3.OperationalError("database is locked")`, which the new `_translated()` will not match.
    Raise the driver's real shape instead — a `ValueError` carrying the Hrana-wrapped text captured
    in Task 1 — so the test keeps pinning "a non-missing-table failure surfaces as `StorageError`,
    not as a silent 401". **Keep the test name.**
  - `test_factory_yields_a_distinct_url_on_every_call` and
    `test_factory_does_not_patch_this_process_settings` (`tests/test_conftest_fixtures.py:126-144`):
    restate against the endpoint model per D5, keeping both names (the census guard at
    `tests/test_pii_redaction_integration.py:353` fails on a removed or renamed test function). The
    first now asserts the factory yields the endpoint every probe can reach and that a probe starts
    empty; the second keeps its real claim — the factory does not mutate this process's `settings`.
    Docstrings must say what was traded and why.
  - Add one test for R3 (two different `DATABASE_URL`s yield two different clients) and one for R6
    (a row written in one test is absent in the next).
- **Mirror**: `tests/test_conftest_fixtures.py:1-14` — its module docstring is the model for
  explaining a contract change rather than quietly weakening one.
- **Validate**: `pytest tests/test_db.py tests/test_conftest_fixtures.py -q` fully green.

### Task 7: Comments the swap made false, and the three subprocess probes

- **Files**: `chat_ui/chat_ui/admin_state.py`, `tests/test_admin_shell.py`,
  `tests/test_render_invariants.py`, `tests/test_chat_ui_startup_guard.py`
- **Action**: UPDATE
- **Implement**:
  - `admin_state.py:980-984`: the paragraph justifying the per-call `asyncio.to_thread` offload says
    every database function "opens its own `sqlite3` connection… and a connection cannot cross
    threads". After this story the client is shared and thread-confined by `_client()`. The offload
    stays per-call — rewrite the *reason*, change no code. This is the only file outside `app/db/`
    and `tests/` this story touches, and it touches a docstring.
  - The three probe modules: drop `CHILD_SETTINGS_PREAMBLE` from the `from tests.conftest import`
    line and from the `_CHECK_SCRIPT` / `_PAGES_CHECK_SCRIPT` concatenation, and replace the "two
    variables rather than one" comments (`test_admin_shell.py:704`,
    `test_chat_ui_startup_guard.py:68`, `test_render_invariants.py:271`) with what is now true:
    `DATABASE_URL` carries the endpoint directly, because it validates.
- **Mirror**: `tests/conftest.py:63-77` — the comment that predicted this deletion; it is the
  explanation to invert.
- **Validate**:
  `pytest tests/test_admin_shell.py tests/test_render_invariants.py tests/test_chat_ui_startup_guard.py -q`
  (these spawn subprocesses; they are slow, and they are the ones that catch a broken child
  environment). Then the AST check from D7: no `import sqlite3` and no `sqlite3.` attribute
  reference anywhere under `app/`, `chat_ui/chat_ui/`, `scripts/`.

### Task 8: Give CI a database

- **File**: `.github/workflows/ci.yml`
- **Action**: UPDATE
- **Implement**: add a `services:` entry running the **digest-pinned** libsql-server from decision
  record §4 with `SQLD_NODE=primary`, port 8080 published, and a health check; set
  `DATABASE_URL: http://127.0.0.1:8080` (plus `OPENROUTER_API_KEY` / `ADMIN_TOKEN` placeholders if
  the run does not already have them) on the test step. Python stays at 3.11 — the wheel constraint
  from §5 is now load-bearing, so say so in a comment.
- **Mirror**: `.github/workflows/ci.yml:13-25` — keep the existing step shape and ordering.
- **Validate**: `git diff .github/workflows/ci.yml` reviewed by eye, and the digest in the file is
  character-identical to
  `sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67`. Real proof arrives on
  push.

### Task 9: The full suite, and the durability proof that is the point of the story

- **File**: none (verification)
- **Action**: VERIFY
- **Implement**:
  - Full suite in the container against the dev server. Compare the failure list to the **7
    pre-existing failures** recorded in STORY-001's report (six `test_untouched_app.py` provenance
    guards plus one `test_chat_state.py` assertion, all failing on `main` and unrelated to this
    epic). Any eighth failure is this story's.
  - **Durability, through a fresh client** (PRD Risk 1): for `insert_audit_log`, `insert_user`,
    `deactivate_user`, `set_user_token_hash` and `init_db`'s `ALTER`, write in one process and read
    back in a **second process constructing its own client**. A same-client read-back is not
    evidence — decision record §2.2's methodology is the standard to meet.
  - Re-verify `insert_audit_log()` returns the new `audit_logs.id` and `get_audit_log(that_id)`
    retrieves the same row; and that the zero-row `deactivate_user` / `set_user_token_hash` cases
    return `False` (the case that regresses silently, §2.4).
  - Signature diff: `git diff main -- app/db/database.py` reviewed for any changed `def` line
    outside the private helpers; `git diff main --stat -- app/routers/ app/services/ scripts/` is
    empty.
- **Validate**: the commands in the Validation section below.

---

## End-to-End Tests

- [ ] Start the pinned libsql-server; `curl -sf http://127.0.0.1:8080/health` returns 200
- [ ] Full suite in `python:3.11` against that endpoint: no failures beyond the 7 pre-existing ones
- [ ] Write `insert_audit_log(...)` in process A; read it back in process B with a **new** client — row present, ids equal
- [ ] `insert_user` → `deactivate_user(existing)` is `True`, `deactivate_user("ghost")` is `False`; verified from a fresh client
- [ ] `set_user_token_hash(existing, h)` is `True`, `set_user_token_hash("ghost", h)` is `False`
- [ ] Against a database with a pre-PII `audit_logs` table, `init_db()` adds all five columns and the pre-existing row survives with defaults (`tests/test_db.py:156`)
- [ ] `find_user_by_token_hash` against a database with no `users` table returns `None` (401 path, not 500) — STORY-002 test, unmodified
- [ ] `scripts/manage_users.py create` twice reports a usable duplicate error rather than a traceback — STORY-002 test, unmodified
- [ ] Kill the server, run one storage test: the failure is a `StorageError`, not a `ValueError` escaping `app/db/`
- [ ] `python -c "import app.db.database"` in the container does **not** connect (the client is lazy; import-time failure is STORY-008's guard, not an accident here)

## Validation

```bash
# 0. Prerequisite: Docker Desktop running (it is currently not -- see D8)
docker network create harness-libsql-net
docker run -d --name harness-libsql-dev --network harness-libsql-net -p 8080:8080 \
  -e SQLD_NODE=primary \
  ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
curl -sf http://127.0.0.1:8080/health

# 1. Full suite, Python 3.11, no network beyond the local server
docker run --rm --network harness-libsql-net -v "$PWD":/w -w /w \
  -e DATABASE_URL=http://harness-libsql-dev:8080 \
  -e HARNESS_TEST_LIBSQL_URL=http://harness-libsql-dev:8080 \
  -e OPENROUTER_API_KEY=test-key -e ADMIN_TOKEN=test-token \
  python:3.11 sh -c "pip install -q -r requirements.txt && pytest -q"

# 2. The AC greps
grep -rn "sqlite3" app/ chat_ui/chat_ui/ scripts/ --include=*.py            # prose only -- see D7
grep -rn "import sqlite3\|sqlite3\." app/ chat_ui/chat_ui/ scripts/ --include=*.py   # must be empty
grep -n "libsql==0.1.11" requirements.txt

# 3. No call site moved
git diff main --stat -- app/routers/ app/services/ scripts/                 # must be empty

# 4. Teardown (no volume is mounted, so this destroys the data with it)
docker rm -f harness-libsql-dev && docker network rm harness-libsql-net
```

## Acceptance Criteria

(Copied from story STORY-006)

- [ ] `_db_path()` and the `sqlite3`-based `get_connection()` are gone, replaced by a client constructed once and reused (per thread — D1, PRD Section 6 Pattern 1)
- [ ] All 22 public signatures identical to `main`; no caller outside `app/db/` modified
- [ ] Column access by name still works (`row["timestamp"]`, `row["n"]`, `row["model_used"]`); `_row_to_audit_log()` and `_row_to_user()` map their full field sets including the `bool(...)` coercions and the five PRD-003/PRD-005 columns
- [ ] Every `INSERT`/`UPDATE`/`ALTER` is durably committed, verified by reading back through a **separate, freshly constructed client**
- [ ] `insert_audit_log(entry)` returns the new `audit_logs.id`; `get_audit_log(that_id)` retrieves the same row
- [ ] `deactivate_user` / `set_user_token_hash` return `True` on a hit and `False` on a miss
- [ ] `tests/conftest.py` provisions a local libSQL server database; every test gets an isolated, empty database; no test reads or writes a `.db` file
- [ ] Full suite passes with no network access and no Turso account
- [ ] The STORY-002 characterization tests pass **unmodified**
- [ ] `grep -rn "sqlite3" app/ chat_ui/ scripts/` — code-level hits are zero; four historical docstring mentions in `app/db/errors.py` remain by decision (D7), recorded as a deviation
- [ ] `requirements.txt` carries `libsql==0.1.11`
- [ ] All tasks completed
- [ ] No test function removed or renamed (`test_pii_redaction_integration.py::test_no_pre_epic_test_function_was_removed_or_renamed` stays green)
- [ ] Out of scope and untouched: `init_db()` concurrency (STORY-007), `top_pii_entities()` aggregation (STORY-009), batched reads (STORY-010)
