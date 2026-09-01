---
story: STORY-006
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-006-libsql-connection-layer.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: PENDING
status: COMPLETE
completed: 2026-09-01
---

# Implementation Report — STORY-006: Swap `app/db/database.py` onto a shared libSQL client

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-006-libsql-connection-layer.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `PENDING`

## Summary

`app/db/database.py` now speaks libSQL. `sqlite3` is gone from the module, `_db_path()` with it, and
`get_connection()` — the single chokepoint all 22 public functions run through — hands back a thin
wrapper over one **process-wide client** instead of constructing a connection per call. All 22
public signatures are byte-identical to `main` apart from `get_connection()`'s return annotation,
which is the change the story asked for. **No file under `app/routers/`, `app/services/` or
`scripts/` was touched**, so the ~40 call sites needed no edits.

Three private classes carry the compatibility. `_Row` restores named column access on rows the
driver returns as bare tuples, using the `description` the driver does populate, while staying
unpackable as a sequence. `_Cursor` makes the driver's non-iterable cursor iterable and maps its
rows. `_Connection` keeps `with get_connection() as conn:` meaning a transaction and commits
**explicitly** on exit rather than inheriting the driver's context manager — PRD Risk 1's stated
mitigation. `_translated()` recognises libSQL failures by their `Hrana:` message wrapper, because
every SQL error arrives as a bare `builtins.ValueError` with no hierarchy to catch, and re-raises
anything unrecognised so a genuine `ValueError` from our own code is never swallowed.
`app/db/errors.py` was not edited, exactly as STORY-004 designed for.

`tests/conftest.py` flipped from `tmp_path` SQLite files to the local libSQL dev server, with
per-test isolation coming from a schema reset instead of a fresh filename.

## The finding that changed the design

The plan's D1 specified a **per-thread client cache** as the "safe under either answer" default,
because neither STORY-001 nor upstream documentation answered thread-safety. Task 1 measured it,
twice, against the pinned server with eight threads writing concurrently:

| Shape | Result |
|---|---|
| One client shared by 8 threads | **SAFE** — 0 errors, 200/200 rows durable via a fresh client, exact per-thread counts |
| One client per thread (the plan's default) | **UNSAFE** — 7 of 8 threads raised `TRANSACTION_TIMEOUT`; only 29–31 of 200 rows survived |

Independent clients contend for the database's single writer; one shared client serializes its own
callers and never contends. **The plan's defensive default was the dangerous option** — it would
have produced precisely the silent write loss PRD Risk 1 exists to prevent. The implementation uses
the single process-wide client the acceptance criterion literally asks for, and
`chat_ui/chat_ui/admin_state.py`'s `asyncio.to_thread` reads are safe against it by measurement
rather than by assumption.

The same finding was applied back to the test fixtures: `_reset_database()` and `db_connect` were
first written to open their own raw client, which is the pattern just shown to be unsafe. Both now
go through `get_connection()`, so a test process holds exactly one client. The full suite got
faster (43s → 37s) and its three-run variance disappeared.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Answer thread-safety, `auth_token` spelling, live error messages | throwaway probe (not committed) | ✅ |
| 2 | Pin the driver | `requirements.txt` | ✅ |
| 3 | Flip the fixtures onto the local libSQL server | `tests/conftest.py` | ✅ |
| 4 | The swap: client, `_Row`/`_Cursor`/`_Connection`, `get_connection()` | `app/db/database.py` | ✅ |
| 5 | The libSQL arm of `_translated()` | `app/db/database.py` | ✅ |
| 6 | The tests reaching past the public surface | `tests/test_db.py`, `tests/test_conftest_fixtures.py` | ✅ |
| 7 | Comments the swap made false, and the three subprocess probes | `chat_ui/chat_ui/admin_state.py`, 3 test modules | ✅ |
| 8 | Give CI a database | `.github/workflows/ci.yml` | ✅ |
| 9 | Full suite + durability proof through a fresh client | — | ✅ |

## Task 1 findings (the probe, in full)

**Thread-safety** — reproduced twice, verdicts above.

**`auth_token`** — signature is
`connect(database, timeout=5.0, isolation_level=..., _check_same_thread=True, _uri=False, sync_url=None, sync_interval=None, offline=False, auth_token='', encryption_key=None)`.
`auth_token=''` and a non-empty token are both accepted against the local server; `authToken` and
`token` raise `TypeError`. Note `timeout` defaults to **5.0 seconds** — that is the fuse on the
contention above.

**Error surface** — every failure is `builtins.ValueError` (mro: `ValueError → Exception →
BaseException`), and every message begins `Hrana:`, including a server that is not running:

| Failure | Message | `_MISSING_RELATION` | `_CONSTRAINT` |
|---|---|---|---|
| duplicate PK `users.user_id` | `SQLite error: UNIQUE constraint failed: users.user_id`, `SQLITE_CONSTRAINT` | — | ✅ `users.user_id` |
| duplicate UNIQUE `token_hash` | `SQLite error: UNIQUE constraint failed: users.token_hash`, `SQLITE_CONSTRAINT` | — | ✅ `users.token_hash` |
| missing table | `SQLite error: no such table: …`, `SQLITE_UNKNOWN` | ✅ | — |
| duplicate ADD COLUMN | `SQLite error: duplicate column name: …`, `SQLITE_UNKNOWN` | — | — |
| syntax error | `SQL input error: near "SELCT"…`, `SQL_INPUT_ERROR` | — | — |
| wrong parameter count | `cursor error: … ARGS_INVALID …` | — | — |
| server unreachable | `http error: … Connection refused` (**no `code:` field**) | — | — |

Both regexes at `app/db/database.py:41-42` survived verbatim, as their comment predicted. The
unreachable case is why the driver-shape guard is `Hrana:` and not `code:`.

## Validation Results

| Check | Result |
|-------|--------|
| Backend import (`from app.main import app`) | ✅ OK |
| Full suite | ✅ 1046 passed, 16 failed — **the same 16 that fail on the committed tree** |
| Regressions | ✅ none (failure sets diffed, byte-identical) |
| Suite determinism | ✅ 5 consecutive full runs, identical results |
| E2E | ✅ 10/10 |
| libsql wheel resolves (not sdist) | ✅ `libsql-0.1.11-cp311-cp311-manylinux_2_17_x86_64…whl` |
| 22 public signatures vs `main` | ✅ 22 on both; only `get_connection`'s return annotation differs |
| Callers outside `app/db/` modified | ✅ none |
| Code-level `sqlite3` under `app/`, `chat_ui/`, `scripts/` | ✅ zero (AST) |
| STORY-002 characterization tests | ✅ pass, unmodified (files untouched by this story) |

**The 16 pre-existing failures.** Measured properly rather than assumed: the story's work was
stashed, the committed tree run in the same container against the same server, and the failure list
captured. It is **identical** — 16 failed / 1044 passed before, 16 failed / 1046 passed after (the
+2 are this story's new tests). All 16 are provenance guards from PRD-006 (`test_untouched_app.py`)
and PRD-005/007 (`test_pii_dedup_isolation.py`, `test_pii_redaction_integration.py`) that compare
against pinned baselines earlier stories on this epic already moved past. Note this is **one more
than the 7 the plan expected**: the plan took its baseline from STORY-001's report, which measured
`main`; the extra ones were added by STORY-002/004/005 committing to the epic branch.

## E2E Results

| # | Check | Result |
|---|---|---|
| 1 | Pinned libsql-server healthy | ✅ 200 in 1s |
| 2 | Full suite, no failures beyond pre-existing | ✅ |
| 3 | `insert_audit_log` in process A, read back in process B with a **new** client | ✅ id 1 returned, same row, all 19 columns incl. `pii_entities`, `denied_permission` |
| 4 | `deactivate_user` hit/miss | ✅ `True` / `False`, `active=0` durable from a fresh client |
| 5 | `set_user_token_hash` hit/miss | ✅ `True` / `False`, `token_hash='rotated'` durable from a fresh client |
| 6 | `init_db()` over a pre-PII 14-column table | ✅ 19 columns via a fresh client, five added, row preserved with defaults |
| 7 | `find_user_by_token_hash` with no `users` table → `None` (401, not 500) | ✅ STORY-002 test, unmodified |
| 8 | `manage_users.py create-user` twice → usable CLI error | ✅ "a user with user_id 'e2e-dup' already exists.", exit 1, no traceback |
| 9 | Unreachable endpoint | ✅ `StorageError`, no bare `ValueError` escapes `app/db/` |
| 10 | `import app.db.database` does not connect | ✅ lazy; boot-time reachability stays STORY-008's guard |

Phases 3–6 were run as **separate processes** constructing their own clients. A same-client
read-back was never accepted as evidence.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/db/database.py` | UPDATE | +274/−… (the swap) |
| `tests/conftest.py` | UPDATE | +190/−… |
| `tests/test_db.py` | UPDATE | +86 |
| `tests/test_conftest_fixtures.py` | UPDATE | +67 |
| `.github/workflows/ci.yml` | UPDATE | +30 |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | +17 (docstring only) |
| `tests/test_admin_shell.py` | UPDATE | +14 |
| `tests/test_render_invariants.py` | UPDATE | +11 |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | +10 |
| `requirements.txt` | UPDATE | +1 |
| `app/db/errors.py` | UNCHANGED | — |
| `app/db/models.py` | UNCHANGED | — |

536 insertions, 164 deletions across 10 files.

`app/db/models.py` needed **no change**, as the story predicted: the DDL
(`INTEGER PRIMARY KEY AUTOINCREMENT`, `TEXT`, `CREATE UNIQUE INDEX`, `ALTER TABLE ADD COLUMN`,
`INTEGER NOT NULL DEFAULT 0`) is libSQL-compatible as-is, verified by E2E 6 building the schema and
migrating a legacy table end to end.

## Deviations from Plan

1. **D1 inverted: one process-wide client, not a per-thread cache.** The plan's "safe default" was
   measured to be the unsafe option (7/8 threads losing writes). See "The finding that changed the
   design". This is the deviation that mattered; everything else is small.
2. **The test fixtures also hold one client.** `_reset_database()` and `db_connect` were written per
   the plan with their own raw client, then changed to route through `get_connection()` once the
   same contention reasoning was applied to them. `db_connect` stays "raw" in the sense its
   docstring always meant — the SQL is the test's and `init_db()` never ran — but it is no longer a
   separate client.
3. **A third fixture-contract test needed rewriting**, not the two the plan named.
   `test_the_url_is_not_the_configured_default` asserted `temp_db != os.environ["DATABASE_URL"]`,
   which the endpoint model makes unfailable in the other direction. Its surviving claims are
   asserted instead: `DATABASE_URL` has no default, and the suite runs on a plain-`http` local
   endpoint that STORY-005's validator makes unreachable for any Turso database. All three keep
   their names — `test_no_pre_epic_test_function_was_removed_or_renamed` fails on a rename.
4. **`grep -rn "sqlite3" app/ chat_ui/ scripts/` is not literally empty** (plan D7, anticipated).
   Five hits remain, all **docstring prose**: two in `app/db/errors.py` explaining what
   `StorageError` stands in for, and three in `app/db/database.py` naming what each wrapper replaces.
   The code-level invariant — no import, no reference — is zero and is verified by AST, which is the
   instrument STORY-002 adopted for exactly this reason (its report, Deviation 1). Rewriting
   `errors.py`'s prose would delete the reasoning that justifies the module; the mentions are
   accurate history, not stale code.
5. **`.github/workflows/ci.yml` was changed**, a file outside the story's stated list. Without a
   libsql-server service container CI has no database and every storage test fails on the next push.
   Flagged in the plan as Task 8 and called out here again.
6. **One unexplained slow run.** The first full-suite run reported 26 failed / 236 errors in 96s;
   every run since (eight of them, before and after the one-client fixture change) reports the same
   16 failures in ~38s. It was the first run to import `chat_ui` in a cold container over a Windows
   bind mount and did one-time work. It is **not reproduced** and I am not claiming a root cause —
   recording it because it is the kind of thing that comes back.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_db.py` | `test_the_shared_client_is_reused_across_calls` (Pattern 1, asserted by identity — a module that quietly rebuilds passes every other test); `test_the_shared_client_is_rebuilt_when_the_database_url_changes` (the cache key must include the URL, or one test's reads come from another's database) |

Rewritten rather than added (names preserved): `test_init_db_issues_no_alter_when_schema_is_current`
(recording proxy replaces `sqlite3`'s `set_trace_callback`, which the libSQL connection has no
equivalent of), `test_find_user_by_token_hash_raises_when_the_failure_is_not_a_missing_table`
(induces the driver's real `Hrana:`-wrapped `ValueError`), and the three fixture-contract tests in
`tests/test_conftest_fixtures.py`.

Per-test isolation was already covered by the existing pair
`test_isolation_first_test_writes_a_row` / `test_isolation_second_test_sees_an_empty_database`,
which now proves the reset rather than `tmp_path`; the plan's suggested extra test for it would
have duplicated them.

## Acceptance Criteria

- [x] `_db_path()` and the `sqlite3`-based `get_connection()` are gone, replaced by a process-wide client constructed once and reused — and, contrary to the plan, genuinely process-wide, because per-thread was measured to lose writes
- [x] All 22 public signatures identical to `main` (only `get_connection`'s return annotation moved); no caller outside `app/db/` modified
- [x] `row["timestamp"]`, `row["n"]`, `row["model_used"]` still work; both mappers map their full field sets including the `bool(...)` coercions and the five PRD-003/PRD-005 columns
- [x] Every `INSERT`/`UPDATE`/`ALTER` durably committed, verified through a **separate, freshly constructed client in a separate process**
- [x] `insert_audit_log(entry)` returns the new `audit_logs.id`; `get_audit_log(that_id)` retrieves the same row
- [x] `deactivate_user` / `set_user_token_hash` return `True` on a hit and `False` on a miss
- [x] `tests/conftest.py` provisions a local libSQL server database; every test gets an empty one; no test reads or writes a `.db` file
- [x] Full suite passes with no network access and no Turso account (local container, no token)
- [x] STORY-002 characterization tests pass **unmodified**
- [x] `grep -rn "sqlite3" app/ chat_ui/ scripts/` — zero code-level hits (AST-verified); five docstring-prose mentions remain by decision, see Deviation 4
- [x] `requirements.txt` carries `libsql==0.1.11`
- [x] No test function removed or renamed
- [x] Out of scope and untouched: `init_db()` concurrency (STORY-007), `top_pii_entities()` aggregation (STORY-009), batched reads (STORY-010)

## Notes for the next stories

- **STORY-007** (concurrent `init_db()`): the duplicate-`ADD COLUMN` failure is
  `ValueError: Hrana: … "SQLite error: duplicate column name: <col>", code: "SQLITE_UNKNOWN"`,
  which `_translated()` currently turns into a plain `StorageError` — `SQLITE_UNKNOWN` is shared
  with "no such table", so the code cannot be the discriminator and the message must be.
- **STORY-008** (startup guard): `_shared_client()` is lazy — importing `app.db.database` connects
  to nothing, so an unreachable endpoint surfaces at first use, not at import. The guard has to
  reach the database deliberately.
- **The five-second `timeout` default** on `libsql.connect` is the fuse behind every contention
  failure seen here. Anything that adds a second client to a process should expect it.
