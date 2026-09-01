---
story: STORY-001
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-001-libsql-driver-spike.plan.md
epic_branch: epic/PRD-007-turso-migration
decision: libsql==0.1.11
status: DECIDED
completed: 2026-09-01
---

# Driver Decision Record — STORY-001

**Verified against**: `ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67` (image built 2026-08-23), primary node, `http://…:8080`
**Client under test**: `libsql==0.1.11` on CPython 3.11.16
**Method**: a throwaway harness (Appendix) using `app/db/models.py`'s DDL and `app/db/database.py`'s SQL verbatim. Every answer below is a pasted observation, not a reading of the documentation. All results were reproduced a second time against a freshly recreated, empty server.

## 1. Decision

**Adopt `libsql` pinned to `0.1.11`.** The `requirements.txt` line STORY-006 will add:

```
libsql==0.1.11
```

It is the only actively maintained client with the required topology. It answers three of the six behaviors cleanly, answers a fourth (commit) in a way that **preserves the module's existing `with`-block idiom**, and fails two — named-column access and batch execution — with workarounds that were *proven to run against this endpoint*, not merely proposed. Section 3 records them.

The spike did **not** benchmark `turso-serverless` as a fallback. The plan gated that on `libsql` failing a behavior with no acceptable workaround, and that gate was not reached.

## 2. The six behaviors

| # | Behavior | Answer | Evidence | Consequence |
|---|---|---|---|---|
| 1 | Named-column row access | **NO** | rows are `<class 'tuple'>`; no `row_factory` | 22 call sites + both mappers need a wrapper — §3.1 |
| 2 | Commit without explicit `commit()` | **QUALIFIED YES** | `with conn:` **commits**; bare `execute` and `close()` **lose the row** | The module's idiom survives; the danger is any code that drops it — §3.2 |
| 3 | `lastrowid` on AUTOINCREMENT | **YES** | `1, 2, 3`, confirmed by fresh-client `SELECT id` | `insert_audit_log()` works unchanged |
| 4 | `rowcount` on UPDATE | **YES** | `1` on hit, `0` on miss, never `-1` | `deactivate_user()` / `set_user_token_hash()` work unchanged |
| 5 | `PRAGMA table_info` | **YES, with a caveat** | statement supported; **`Cursor` is not iterable** | `database.py:45` iterates the cursor — must use `.fetchall()` — §3.3 |
| 6 | Batch / multi-statement | **NO** | no `batch()`; `executescript()` returns `None`; multi-statement `execute()` returns only statement 1 **and swallows errors** | STORY-010 must use one SELECT, not a client batch — §3.4 |

### 2.1 Named-column row access — NO

```
hasattr(conn,'row_factory'): False
  set row_factory then fetch: RAISED builtins.AttributeError:
      'builtins.Connection' object has no attribute 'row_factory'
type(row) = <class 'tuple'>
  repr = (1, '2026-09-01T00:00:00Z', 'u1', 'laptop', 'h1', 'preview', 'rh', 'rprev',
          'gpt-4', 42, 0, None, 1, None, 1, 0, 'PERSON,EMAIL_ADDRESS', 'user', None)
  row.keys():         RAISED builtins.AttributeError: 'tuple' object has no attribute 'keys'
  row['timestamp']:   RAISED builtins.TypeError: tuple indices must be integers or slices, not str
  row[1] positional:  OK -> '2026-09-01T00:00:00Z'
aliased aggregate row = (1,)
  row['n']:           RAISED builtins.TypeError: tuple indices must be integers or slices, not str
```

There is no `sqlite3.Row` equivalent and no `row_factory` hook. **However, `cursor.description` is populated** — and, critically, for *both* shapes the module relies on:

```
SELECT *      -> POPULATED: ['id', 'timestamp', 'user_id', 'device', 'prompt_hash',
   'prompt_preview', 'response_hash', 'response_preview', 'model_used', 'tokens_used',
   'was_duplicate_blocked', 'suspicious_pattern', 'success', 'error_message',
   'pii_detected_input', 'pii_detected_output', 'pii_entities', 'role', 'denied_permission']
aliased agg   -> POPULATED: ['n']
```

**Blast radius**: 22 `get_connection()` call sites, `_row_to_audit_log()` (19 named reads), `_row_to_user()` (5), and `_add_missing_columns()`'s `row["name"]`.

### 2.2 Commit semantics — QUALIFIED YES *(the headline result)*

Four cases, each written by its own process and its own client, then read back by a **third process constructing a fresh client**. A same-client read-back was never used as evidence — Risk 1 is precisely that such a read can be served from client-side state.

```
FRESH-CLIENT READ-BACK (separate process, separate client):
  no_commit    -> LOST
  commit       -> DURABLE
  with_block   -> DURABLE
  close_only   -> LOST
  raw rows present: ['commit', 'with_block']
```

`with conn:` **does** carry the commit-on-exit semantic. This is the construct every one of the module's 22 functions already uses, so PRD Risk 1's worst case — "INSERTs return successfully and the data is never persisted" — **does not fire for the code as written**. Two ways it still fires, and both must be guarded:

- A write executed *without* the `with` block is silently lost. There is no error, no warning.
- **`close()` does not imply commit.** A shared, long-lived client (PRD Pattern 1) closed at shutdown with an uncommitted write loses it.

Supporting facts:

```
conn.autocommit:      ABSENT (no such attribute)
conn.in_transaction:  False
conn.rollback():      present, returns None
rows after rollback (fresh client): 0     <- rollback is real, not a no-op
```

### 2.3 `lastrowid` — YES

```
type(conn.execute(...)) = <class 'builtins.Cursor'>     <- `cursor = conn.execute(...)` still valid
insert 0: cursor.lastrowid = 1 (type int)
insert 1: cursor.lastrowid = 2 (type int)
insert 2: cursor.lastrowid = 3 (type int)
conn.lastrowid (connection-level): ABSENT               <- cursor-level only
fresh-client SELECT id -> [(1, 'row0'), (2, 'row1'), (3, 'row2')]
lastrowid [1, 2, 3] == actual ids [1, 2, 3]: True
RETURNING id fallback: OK -> (4,)                       <- available, not needed
```

`insert_audit_log()` (`database.py:84`) and `GET /audit/{id}` need no change.

### 2.4 `rowcount` — YES

```
deactivate_user     HIT : rowcount = 1   (== 1 -> True)
   rowcount after commit: 1              <- stable across commit
deactivate_user     MISS: rowcount = 0   (== 1 -> False)
set_user_token_hash HIT : rowcount = 1
set_user_token_hash MISS: rowcount = 0
```

The three-way contract holds: `1` on a hit, `0` on a miss, never `-1`. `deactivate_user()` and `set_user_token_hash()` keep returning correct booleans, and `scripts/manage_users.py` keeps reporting a typo'd `user_id`.

### 2.5 `PRAGMA table_info` — YES, with a caveat that breaks the current line

The statement is fully supported over the remote endpoint, and the five `ALTER TABLE ADD COLUMN` migrations apply correctly against an old-schema table:

```
existing before = ['device','error_message','id','model_used','prompt_hash','prompt_preview',
                   'response_hash','response_preview','success','suspicious_pattern',
                   'timestamp','tokens_used','user_id','was_duplicate_blocked']
  ALTER TABLE audit_logs ADD COLUMN pii_detected_input INTEGER NOT NULL DEFAULT 0: OK
  ALTER TABLE audit_logs ADD COLUMN pii_detected_output INTEGER NOT NULL DEFAULT 0: OK
  ALTER TABLE audit_logs ADD COLUMN pii_entities TEXT: OK
  ALTER TABLE audit_logs ADD COLUMN role TEXT: OK
  ALTER TABLE audit_logs ADD COLUMN denied_permission TEXT: OK
all five present: True (missing=set())
```

`INTEGER NOT NULL DEFAULT 0` is accepted, so `AUDIT_LOGS_ADDED_COLUMNS` needs no edit. **The caveat**: the cursor cannot be iterated, which is exactly what `database.py:45` does.

```
list(conn.execute('PRAGMA table_info(audit_logs)')):
    RAISED builtins.TypeError: 'builtins.Cursor' object is not iterable

# via fetchall() it works:
PRAGMA via fetchall(): OK, rows = 19
  first row repr : (0, 'id', 'INTEGER', 0, None, 1)
  type           : <class 'tuple'>
  description    : (('cid',…), ('name',…), ('type',…), ('notnull',…), ('dflt_value',…), ('pk',…))
  row['name']    : RAISED builtins.TypeError: tuple indices must be integers or slices, not str
  mapped name    : id        <- description-based mapping works on PRAGMA rows too
```

PRAGMA rows are tuples like every other row, but `description` is populated for them, so the §3.1 wrapper covers this case as well. The table-valued form also works, if ever preferred:

```
SELECT name FROM pragma_table_info('audit_logs'): OK -> ['id','timestamp',…,'denied_permission']
```

**Duplicate `ADD COLUMN`** — collected for STORY-007, which must treat this as success rather than a startup crash:

```
builtins.ValueError: Hrana: `stream error: `Error {
    message: "SQLite error: duplicate column name: pii_detected_input",
    code: "SQLITE_UNKNOWN" }`
```

### 2.6 Batch execution — NO

The full public surface, pasted:

```
dir(connection) = ['close','commit','cursor','execute','executemany','executescript',
                   'in_transaction','isolation_level','rollback','sync']
dir(cursor)     = ['arraysize','close','description','execute','executemany','executescript',
                   'fetchall','fetchmany','fetchone','lastrowid','rowcount']
has conn.batch: False        has conn.execute_batch: False
has conn.executescript: True has conn.executemany: True
```

- **No `batch()`.** The archived `libsql-client` had one; `libsql` does not.
- **`executemany`** is one statement with many parameter sets. It does not answer this AC and must not be mistaken for a yes.
- **`executescript()` returns `None`** — results are unreachable. Usable for DDL, useless for the summary fan-out.
- **Multi-statement `execute()` is worse than unsupported — it is misleading.** It returns only the first statement's result, and a batch containing a bad statement reported *success*:

```
conn.execute('stmt1; stmt2; stmt3')            -> [(5,)]     <- only statement 1
batch containing SELECT * FROM no_such_table   -> [(5,)]     <- NO ERROR RAISED
```

Per-statement results and per-statement error attribution are therefore **both unavailable**. PRD Risk 6 is real and cannot be solved with a client-side batch API.

**The fallback works and is faster.** One `SELECT` with scalar subqueries, measured against this endpoint:

```
10 sequential statements:            16.3 ms  (19.1 ms on the repeat run)
1 combined scalar-subquery SELECT:    1.7 ms  ( 1.9 ms on the repeat run)
combined description = ['total_recorded','blocked_duplicates','blocked_suspicious',
                        'unique_users','successful','pii_detected']
```

Roughly a 10× improvement, and `description` gives each figure its own column name — so per-figure attribution survives. See §3.4.

## 3. Workarounds required

### 3.1 Named-column access → a `description`-based mapping wrapper  → **STORY-006**

Proven against the endpoint:

```python
cur = conn.cursor()
cur.execute("SELECT * FROM audit_logs LIMIT 1")
names = [c[0] for c in cur.description]
mapped = dict(zip(names, cur.fetchone()))
mapped['timestamp']          # -> '2026-09-01T00:00:00Z'
mapped['denied_permission']  # -> None
# aliased aggregate:
mapped['n']                  # -> 1
```

STORY-006 should wrap rows in a small mapping type at the `get_connection()` seam so `row["..."]` keeps working. Because `description` is populated for `SELECT *`, **the 22 call sites and both mappers can stay untouched** — the column order does *not* have to be pinned to the DDL, which was the bad outcome the plan flagged. Note the wrapper must also cover `.keys()` if any caller uses it (none do today) and must apply to PRAGMA rows (§3.3).

### 3.2 Commit → keep the `with` block, and commit before close  → **STORY-006**

The existing `with get_connection() as conn:` idiom is durable and must be preserved deliberately rather than by accident. Two additions:

- Any write that leaves the `with` block — likely once a **shared** client replaces connection-per-operation (PRD Pattern 1) — needs an explicit `conn.commit()`. Note that a shared client changes the shape of this: `with conn:` on a process-wide client is a transaction boundary, not a connection lifetime.
- The shutdown path must `commit()` **before** `close()`; close alone discards.
- Per PRD Risk 1's mitigation, every write function's test must read back through a **fresh** client.

### 3.3 `PRAGMA` cursor iteration → `.fetchall()`  → **STORY-006**

`database.py:45` reads:

```python
existing = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
```

Both halves break: the cursor is not iterable, and `row["name"]` fails on a tuple. It becomes:

```python
cur = conn.cursor()
cur.execute("PRAGMA table_info(audit_logs)")
names = [c[0] for c in cur.description]
existing = {dict(zip(names, r))["name"] for r in cur.fetchall()}
```

— or simply `{r[1] for r in cur.fetchall()}`, since `name` is column 1 of a PRAGMA row and that ordering is fixed by SQLite. With the §3.1 wrapper in place, the original line survives with only `.fetchall()` added.

### 3.4 No batch → one SELECT, and it can carry all ten figures  → **STORY-010**, **STORY-009**

`json_group_array` is available on this endpoint, which lets the four list-valued reads join the six counts in the **same single round trip**. Verified:

```
8-figure single round trip OK in 1.7 ms
 columns: ['total_recorded','blocked_duplicates','blocked_suspicious','unique_users',
           'successful','pii_detected','top_models','top_users']
 values : (6, 0, 0, 3, 6, 6, '["gpt-4","claude-3"]', '["u2","u1","u0"]')
```

Per-figure error attribution is preserved because each figure is a named column, so `_READS`' ten `READ_LABEL_*` entries can map one-to-one onto columns rather than onto statements. `len(_READS) == 10` need not change.

**STORY-009** (`top_pii_entities` aggregated in SQL) is also unblocked — a recursive CTE splits the comma-separated `pii_entities` and aggregates server-side, verified:

```
recursive CTE split of pii_entities: OK -> [('PERSON', 6), ('EMAIL_ADDRESS', 3)]
```

### 3.5 Bonus: the exception surface is a bare `ValueError`  → **STORY-004**

Not one of the six, but collected while the endpoint was up because STORY-004 cannot be designed without it. **Every** SQL error arrives as `builtins.ValueError` carrying a Hrana-wrapped message. There is no exception hierarchy; `libsql.Error` exists but is not what gets raised.

```
duplicate PRIMARY KEY user_id   ValueError: … "UNIQUE constraint failed: users.user_id",  code: "SQLITE_CONSTRAINT"
duplicate UNIQUE token_hash     ValueError: … "UNIQUE constraint failed: users.token_hash", code: "SQLITE_CONSTRAINT"
SELECT from missing users table ValueError: … "no such table: users",                     code: "SQLITE_UNKNOWN"
duplicate ADD COLUMN            ValueError: … "duplicate column name: …",                 code: "SQLITE_UNKNOWN"
```

Consequences STORY-004 must absorb:

- `except sqlite3.IntegrityError` cannot be replaced by an exception *type* — the two duplicate cases share `SQLITE_CONSTRAINT` and are distinguishable only by the message naming `users.user_id` vs `users.token_hash`. `scripts/manage_users.py:37` must still tell them apart.
- **`SQLITE_UNKNOWN` is not diagnostic** — missing-table and duplicate-column share it. The 401-not-500 behavior at `database.py:289` must therefore match on the message text `no such table`, not on a code.
- Catching bare `ValueError` risks swallowing genuine programming errors. The parsing belongs in one place in `app/db/errors.py`, and nowhere else.

## 4. Local libSQL dev-server workflow

Reproducible, offline after the initial pull, no Turso account, and structurally unable to reach production.

```bash
# start
docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
  ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67

# ready when this returns 200
curl -sf http://127.0.0.1:8080/health

# teardown -- no volume is mounted, so this destroys the data with it
docker rm -f harness-libsql-dev
```

- **Endpoint**: `http://127.0.0.1:8080`. `DATABASE_URL=http://127.0.0.1:8080`, `TURSO_AUTH_TOKEN` unset — a local primary requires no token.
- **Ports**: HTTP `8080`; the container also opens gRPC on `5001` (unused here).
- **Isolation**: mount **no** volume. The server starts empty, and `docker rm -f` leaves nothing. For per-test isolation, STORY-003 should drop and recreate the schema per test, or run one container per test session; the container starts in ~2 s.
- **Pin the digest, not `:latest`.** `sha256:6dd3eb27…` is the image used for every result in this document.

## 5. Environment constraints

**`libsql` is a compiled extension with no pure-Python fallback**, so wheel coverage is a hard constraint, not a detail. For 0.1.11 (23 artifacts published):

| Python | Linux x86_64 | Windows amd64 | macOS x86_64 / arm64 |
|---|---|---|---|
| cp311 | ✅ | ✅ | ✅ / ✅ |
| cp314 | ✅ | ❌ | — |

- **Deployment is safe**: `Dockerfile:2` and `:29` build on `python:3.11`, and the install here resolved `libsql-0.1.11-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` — a wheel, not the sdist.
- **This development host cannot install it natively.** It runs Python 3.14.4 on Windows, where there is no `win_amd64` wheel; `pip` falls back to `libsql-0.1.11.tar.gz` and needs a Rust toolchain. The entire spike was therefore run inside a `python:3.11` container, which is the fallback the plan specified.
- **Action for STORY-003 and CI**: pin CI to Python 3.11, or run the suite in the project image. A developer on Python 3.12/3.13 should check wheel coverage before assuming a local `pip install` works.

## 6. Rejected alternatives

| Candidate | Verdict | Reason |
|---|---|---|
| `libsql-client` 0.3.1 | Rejected | Repository **archived 2025-06-11**. It had exactly the `batch()` returning per-statement `ResultSet`s with named row access that would have answered Behaviors 1 and 6 outright — which is painful, but PRD Section 8 requires an exact pin and pinning a dead package trades a known workaround for an unknown liability. |
| `libsql-experimental` 0.0.55 | Rejected | Deprecated, superseded by `libsql`. |
| `pyturso` 0.7.2 | Rejected | In-process / embedded database. PRD Section 4 rejects any local-file read path: "the file is being eliminated, not relocated." Wrong topology, not a close call. |
| `turso-serverless` 0.1.0 | Not evaluated | Pure-Python DB-API 2.0 over HTTP, so it would sidestep §5's wheel constraint entirely — genuinely attractive on that axis. Not benchmarked because the plan gated it on `libsql` failing a behavior with **no** acceptable workaround, and every failure here had one that ran. Worth revisiting only if §5 becomes painful in CI. |

## 7. Reproducing this

The harness was scratch and is not in the repository, per the story's constraint that this work produce "knowledge and a document, not production code". Recreate it as follows.

```bash
docker network create harness-spike-net
docker run -d --name harness-libsql-dev --network harness-spike-net -p 8080:8080 \
  -e SQLD_NODE=primary \
  ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
docker run -d --name harness-spike --network harness-spike-net python:3.11 sleep infinity
docker exec harness-spike pip install libsql==0.1.11
# make app/db/models.py importable inside the container as app.db.models, then:
docker exec -e PYTHONPATH=/spike -e LIBSQL_URL=http://harness-libsql-dev:8080 \
  -w /spike harness-spike python spike_libsql.py
```

The commit check must be run as separate processes — this is the part that is easy to get wrong, and getting it wrong invalidates the answer:

```bash
R="docker exec -e PYTHONPATH=/spike -e LIBSQL_URL=http://harness-libsql-dev:8080 -w /spike harness-spike python spike_libsql.py"
$R --write setup
for c in no_commit commit with_block close_only; do $R --write $c; done
$R --fresh-client     # a THIRD process, constructing its own client
```

The essential probes, condensed:

```python
import libsql
conn = libsql.connect("http://127.0.0.1:8080")

# B1 -- rows are tuples; description is the way back to names
row = conn.execute("SELECT * FROM audit_logs LIMIT 1").fetchone()   # -> tuple
cur = conn.cursor(); cur.execute("SELECT * FROM audit_logs LIMIT 1")
dict(zip([c[0] for c in cur.description], cur.fetchone()))["timestamp"]

# B2 -- write in one process, read in another with a NEW client
with conn: conn.execute(INSERT, params)     # DURABLE
conn.execute(INSERT, params)                # LOST unless commit()
conn.execute(INSERT, params); conn.close()  # LOST

# B3/B4
cur = conn.execute(INSERT, params); cur.lastrowid          # 1, 2, 3
cur = conn.execute("UPDATE users SET active=0 WHERE user_id=?", ("ghost",)); cur.rowcount  # 0

# B5 -- fetchall(), not iteration
cur = conn.cursor(); cur.execute("PRAGMA table_info(audit_logs)"); cur.fetchall()

# B6 -- no batch; one SELECT instead
[n for n in dir(conn) if not n.startswith('_')]
conn.execute("SELECT (SELECT COUNT(*) FROM audit_logs) AS total_recorded, ...").fetchone()
```

## 8. Acceptance criteria

- [x] Named-column row access answered — **NO**, tuples; `description`-based mapping proven viable; 22-call-site + two-mapper blast radius stated (§2.1, §3.1)
- [x] Commit durability answered through a **separate, freshly constructed client in a separate process** — `with` block DURABLE, bare execute and `close()` LOST (§2.2)
- [x] `lastrowid` answered — **YES**, cursor-level, confirmed against fresh-client reads (§2.3)
- [x] `rowcount` answered for one-row and zero-row UPDATEs as literal values — `1` and `0` (§2.4)
- [x] `PRAGMA table_info` answered — **supported**; rows are tuples; cursor not iterable (§2.5)
- [x] Batch execution answered — no API, round-trip cost measured, per-statement results and errors both unavailable (§2.6)
- [x] Decision record names the chosen client, exact pinned version, and yes/no + evidence for all six, including workarounds (§1–§3)
- [x] `git diff main --stat` shows no file modified under `app/`, `chat_ui/`, or `scripts/`
- [x] Local dev-server workflow documented and reproducible (§4)
- [x] No production code written; no dependency added to `requirements.txt` by this story
