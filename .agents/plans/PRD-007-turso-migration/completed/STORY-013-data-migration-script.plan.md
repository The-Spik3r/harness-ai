---
story: STORY-013
prd: PRD-007
slug: data-migration-script
title: "scripts/migrate_to_turso.py: copy audit_logs and users with verification and a rollback point"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-02
---

# Plan: scripts/migrate_to_turso.py — copy `audit_logs` and `users` with verification and a rollback point

## Summary

Add one new CLI script, `scripts/migrate_to_turso.py`, that copies every row of `audit_logs` and `users` out of a legacy SQLite `.db` file into the Turso database `DATABASE_URL` names, then proves the copy landed intact before it says so. It reads the source through stdlib `sqlite3` opened **read-only** and writes the destination through `app.db.database.get_connection()` — the one process-wide libSQL client, never a second one — inserting `audit_logs.id` explicitly so `GET /audit/{id}` keeps addressing the same rows. Because the driver has no batch API (STORY-001 §2.6) and `executemany` has never been exercised against this endpoint, rows go over the wire as chunked multi-row `INSERT ... VALUES (...),(...)` statements: one statement per chunk, provably, using only `execute()`. Verification is three-layered — per-table counts, a full row-by-row content comparison over the destination's column list, and an accessor-level read-back through `get_audit_log()` covering every row that carries a value in the seven columns PRD Section 5 story 4 names. Any mismatch names the table, the id, and the column, and exits non-zero. The destination must be empty or the script refuses; the source file is opened read-only and its SHA-256 is printed before and after, so the rollback point PRD Section 7.5 promises is a fact the operator reads on their own terminal rather than a claim in a document. Deleting the source is **not** here — that is STORY-014.

## User Story

As a compliance admin
I want every existing audit row copied into Turso and verified
So that the historical record is not silently truncated by the move that was supposed to protect it

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-013-data-migration-script.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 5 story 4, Section 7.5, Section 11, Section 12 Phase 4, Section 14 Risk 2
- Decision record (governs the write mechanism): `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md` §2.2, §2.6, §3.2

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | `scripts/` (new CLI), test suite. **No change to `app/`, `chat_ui/`, or any existing script.** |
| Story | STORY-013 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` holds only `frontend-design`, whose `description` scopes it to "distinctive, intentional visual design when building new UI". This story is a CLI tool that renders nothing. The story's Technical Notes reach the same conclusion independently. No skill applies. | none |

---

## The two constraints that shape this plan

**1. There is no batch API, and `executemany` is unproven here.** From STORY-001 §2.6, re-pasted into `app/db/database.py:872-900`:

```
dir(connection) = ['close','commit','cursor','execute','executemany','executescript',
                   'in_transaction','isolation_level','rollback','sync']
has conn.batch: False        has conn.execute_batch: False
conn.execute('stmt1; stmt2; stmt3')            -> [(5,)]     <- only statement 1
batch containing SELECT * FROM no_such_table   -> [(5,)]     <- NO ERROR RAISED
```

`executemany` exists on the driver but is used **nowhere in this repo**, so it is unverified against the endpoint — and the same document proves this driver can report success for a statement it never ran. The story's "batch the inserts" is therefore satisfied by a **chunked multi-row `INSERT ... VALUES (?,…),(?,…)`**: a single statement carrying N rows, issued through the same `execute()` every one of the 22 public functions uses, so it inherits behavior that is already proven rather than behavior that is merely documented. Task 4 measures `executemany` as a possible improvement and records the result; nothing here depends on it.

**2. The `_Connection` block is the transaction, and it rolls back.** `app/db/database.py:212-221`:

```python
    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self._client.commit()
        else:
            self._client.rollback()
        return False
```

Both tables are copied inside **one** `with get_connection() as conn:` block. A failure at chunk 40 of 50, or on the `users` copy after `audit_logs` succeeded, therefore leaves the destination **empty**, not half-populated — which is what makes "refuse a non-empty destination" a workable policy instead of a trap. STORY-001 §2.2 proved the rollback is real when read back through a fresh client (`rows after rollback (fresh client): 0`).

---

## Patterns to Follow

### CLI shape — argparse, `main(argv)` returning an int

```python
# SOURCE: scripts/manage_users.py:1-8, 100-107
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
...
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":
    sys.exit(main())
```

`main()` takes `argv` and handlers **return** an int rather than calling `sys.exit`, which is the only reason `tests/test_manage_users_cli.py` can drive the CLI in-process. This script keeps that property.

### Error reporting — stderr, `Error:`, return 1

```python
# SOURCE: scripts/manage_users.py:40-43
    except IntegrityError:
        print(f"Error: a user with user_id '{args.user_id}' already exists.", file=sys.stderr)
        return 1
```

`tests/test_manage_users_cli.py:66` pins `captured.out == ""` on the error path — nothing goes to stdout before an error. This script inherits that discipline.

### Writing — one transaction, explicit ids

```python
# SOURCE: app/db/database.py:525-558 (insert_audit_log)
INSERT INTO audit_logs (
    timestamp, user_id, device, prompt_hash, prompt_preview, ...
) VALUES (?, ?, ?, ?, ?, ...)
```

Note what is *absent*: `id`. `insert_audit_log()` deliberately lets AUTOINCREMENT assign it, so **this script cannot reuse it** — AC 2 requires the id to come from the source. The script issues its own INSERT whose column list is the reconciled source columns plus `id`.

### Reading back for verification — the real accessors

```python
# SOURCE: app/db/database.py:611-618
def get_audit_log(audit_id: int) -> Optional[AuditLog]:
    with _session() as conn:
        row = conn.execute("SELECT * FROM audit_logs WHERE id = ?", (audit_id,)).fetchone()
```

AC 8 asks for read-back "through `get_audit_log(...)`" specifically, not through raw SQL — so the verification uses the function the compliance surface actually calls.

### Schema introspection — `PRAGMA table_info`, by name

```python
# SOURCE: app/db/database.py:517
existing = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
```

The same idiom, run against the **source** with `sqlite3`, is what makes AC 9 (an older-schema source) a handled case rather than a crash.

### Test module — in-process `main([...])`, `temp_db`, `capsys`

```python
# SOURCE: tests/test_manage_users_cli.py:11, 17-18
from scripts.manage_users import main
def test_create_user_prints_token_exactly_once_with_recovery_warning(temp_db, capsys):
    exit_code = main(["create-user", "--user-id", "ana", "--role", "user"])
```

`temp_db` is the initialized destination; the autouse `_never_the_configured_database` fixture (`tests/conftest.py:129`) empties it first. `tmp_path` is used **only** for the source `.db` file — it is the one genuine file in this story, and `tests/conftest.py:9-16` is explicit that a `Path` must never stand in for the database URL.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `scripts/migrate_to_turso.py` | CREATE | The migration CLI: read-only source open, schema reconciliation, chunked copy in one transaction, three-layer verification, rollback statement. |
| `tests/test_migrate_to_turso_cli.py` | CREATE | AC 10's six named cases plus id preservation, source immutability, `token_hash` integrity, AC 8 read-back, AUTOINCREMENT continuation, batching, and dry-run. |
| `.agents/reports/PRD-007-turso-migration/STORY-013-data-migration-script.report.md` | CREATE | The run against the real `harness_ai.db`, the `sqlite3` exception ruling STORY-014 needs, and the `executemany` finding. |

**No file is modified.** Nothing under `app/`, `chat_ui/`, or `scripts/manage_users.py` changes — `get_connection()` is already public ("Public because thirteen test modules open one directly", `app/db/database.py:226`) and needs no widening.

---

## Design

### 1. CLI surface

```
python scripts/migrate_to_turso.py --source harness_ai.db [--batch-size 50]
                                   [--verify-sample 50] [--dry-run]
```

- **`--source` (required)** — path to the legacy `.db` file. It is a CLI argument and **cannot** be a `DATABASE_URL`: `app/config.py:76-98` rejects any `sqlite:` URL outright, which is exactly the guarantee PRD Section 2 wanted ("a configuration that would have opened a file is a startup error").
- **The destination is `settings.DATABASE_URL` + `TURSO_AUTH_TOKEN`**, not a flag — the same contract every other entry point uses, so there is no second way to name a database and no way for the two to disagree. The endpoint is echoed through `app.db.database._safe_endpoint()`, which already strips an in-URL token (`:291-313`); re-implementing that redaction is how a token ends up in a terminal scrollback.
- **`--batch-size`** — rows per `INSERT` statement, default **50**. `audit_logs` copies at most 19 columns, so 50 rows is 950 bound parameters, under the conservative `SQLITE_MAX_VARIABLE_NUMBER` of 999 an older libSQL build may still enforce. Exposed so an operator can tune it, defaulted so they need not.
- **`--verify-sample`** — how many rows the AC 8 accessor read-back covers, default **50**, `0` meaning all. See §5.
- **`--dry-run`** — read the source, check every precondition, report the plan, write nothing. Exists so an operator can rehearse against the real production endpoint without touching it.

No subcommands: `manage_users.py` has four verbs, this has one. `_build_parser()` still follows its shape (`prog=`, long flags, `set_defaults(func=...)`) so the two scripts read alike.

### 2. Reading the source without touching it (AC 6)

```python
uri = f"file:{Path(args.source).resolve().as_posix()}?mode=ro"
source = sqlite3.connect(uri, uri=True)
source.row_factory = sqlite3.Row
```

Three layers, because AC 6 covers "success, failure, **or interruption**":

1. **`mode=ro`.** The connection cannot issue a write, so no code path in this script — including one that dies halfway — can mutate the file. This is enforcement, not intention.
2. **SHA-256 before and after.** Hashed at open, hashed again in the `finally` block, both printed. Equal is the proof; unequal is a hard failure with a non-zero exit, even on an otherwise successful run.
3. **Hot-journal refusal.** If `{source}-wal` or `{source}-journal` exists and is non-empty, SQLite would want to recover it — a write — before reading. The script refuses with the checkpoint instruction rather than opening. A read-only open of a hot-WAL database can also fail obscurely; refusing first turns that into a sentence an operator can act on.

The source is opened **once**, read for the copy and again for verification, and closed in a `finally`.

### 3. Schema reconciliation (AC 9)

```
source_columns = {row["name"] for row in source.execute("PRAGMA table_info(audit_logs)")}
dest_columns   = the 19 columns of CREATE_AUDIT_LOGS_TABLE, from app/db/models.py
```

- **`copied = dest_columns ∩ source_columns`**, in `dest_columns` order. The copy names every column explicitly on both sides. This is not stylistic: the real `harness_ai.db` has `pii_entities, role, denied_permission` appended by `ALTER TABLE`, so its column *order* differs from `CREATE_AUDIT_LOGS_TABLE`. A positional `SELECT *` copy would shift values into the wrong columns and still report matching counts — precisely the failure AC 3 exists to catch.
- **`dest_columns − source_columns`** (an older file predating PRD-003/PRD-005) → omitted from the INSERT, so the destination applies its own DDL default. Reported by name: `note: source lacks role, denied_permission -> destination defaults applied`. Verification then expects the default, not an absent source value.
- **`source_columns − dest_columns`** → **refuse**. A column the current schema has no home for means the source is not the database this script was written against, and silently dropping data is not an option in a compliance migration.
- **A source with no `audit_logs` table at all** → refuse; that is not a harness database. A source whose `audit_logs` lacks `id` → refuse; AC 2 is unsatisfiable without it.
- **A source with no `users` table** (older than PRD-005) → **not** an error. Reported as `users: absent in source, 0 rows`, verified as 0, and the run proceeds.

### 4. The copy

One transaction, both tables, ascending `id`:

```python
with get_connection() as conn:          # commit on clean exit, rollback on any exception
    for chunk in _chunks(audit_rows, args.batch_size):
        placeholders = ", ".join(["(" + ", ".join("?" * len(copied)) + ")"] * len(chunk))
        conn.execute(
            f"INSERT INTO audit_logs ({', '.join(copied)}) VALUES {placeholders}",
            tuple(value for row in chunk for value in row),
        )
    ...same for users...
```

- **`id` is in `copied`** — it is both a `dest_column` and a `source_column`, so it copies like any other. AC 2 costs nothing extra; what costs something is *not* doing it.
- **Ascending `id` order** (`ORDER BY id`) so `sqlite_sequence` climbs monotonically and ends at `MAX(id)`. Verified locally: inserting explicit ids `7, 30` into an `INTEGER PRIMARY KEY AUTOINCREMENT` column leaves `sqlite_sequence.seq = 30`, and the next natural insert returns `31`. Task 6 re-verifies this **against the libSQL endpoint** rather than trusting a different engine, and repairs the sequence explicitly if the endpoint does not maintain it.
- **Placeholders are positional `?` only.** Named placeholders were not among STORY-001's six verified behaviors (`app/db/database.py:895-897`), so this plan does not use them.
- **`users.token_hash` copies as an opaque value** — no re-hashing, no normalization, no `strip()`. It is a SHA-256 digest produced by `app/services/identity.py`, and the only correct transformation is none.

### 5. Verification — three layers, in order

Run **after** the transaction commits, so every read observes durable state. Each layer names the table and the check on failure.

| Layer | What it proves | Mechanism |
|---|---|---|
| **A. Counts** | Nothing was dropped or duplicated | `SELECT COUNT(*)` on both sides, per table. Reported as `audit_logs: 1274 source -> 1274 destination` whether or not it matches. |
| **B. Content** | The values are the same, in the same rows | Both sides fully selected over `copied`, ordered by primary key (`id`; `user_id` for `users`), zipped and compared cell by cell. Reports the first mismatches as `audit_logs id=418 column=pii_entities source='PERSON,EMAIL_ADDRESS' destination='PERSON'`, capped at 20 lines so a systematic failure does not scroll the real message away. Columns absent from the source are compared against the destination's declared default instead. |
| **C. Accessor read-back** | The compliance surface returns what the console will show | `get_audit_log(id)` for a bounded sample, compared against an `AuditLog` built from the source row. |

**Why B and C both exist.** B is exhaustive and cheap — two bulk selects — and covers every column of every row, which is what "compares row content, not only counts" (AC 3) asks for. C is narrow and expensive — one round trip per row — but it is the only layer that exercises `_row_to_audit_log()`'s `bool()` coercions and the `SELECT *` path `GET /audit/{id}` actually uses, which is what AC 8 asks for by name. Neither substitutes for the other.

**The sample is not random.** It is: the lowest id, the highest id, and **every row carrying a non-default value in any of `pii_entities`, `role`, `denied_permission`, `pii_detected_input`, `pii_detected_output`** — the seven columns PRD Section 5 story 4 names — until `--verify-sample` is reached. Rows with nothing interesting in them are the ones layer B already covers well; rows carrying PII telemetry are the ones AC 8 was written about. `--verify-sample 0` covers every row, for an operator who wants exhaustive accessor-level proof and will pay for it.

Two further checks, both cheap:

- **Id set equality** (AC 2): `set(source ids) == set(destination ids)`, asserted as its own named check so a renumbering failure reports as *"audit_logs: id preservation failed"* and not as 1,274 content mismatches.
- **`token_hash` integrity** (AC 7): `SELECT COUNT(*), COUNT(DISTINCT token_hash) FROM users` must agree, and `idx_users_token_hash` must be present in the destination's `sqlite_master`. A copy that landed while the unique index was missing would look fine until the next `insert_user()`.

### 6. Refusing a non-empty destination (AC 5)

Checked **before** anything is written: if `audit_logs` or `users` holds any row, print the counts, name the table, and return 1. No `--force`, no `--reset-destination`.

That is a deliberate omission. The alternative — a flag that empties a populated audit table — is a foot-gun aimed at the exact asset this epic exists to protect, and "genuinely idempotent" is not available either, since an idempotent upsert on `audit_logs` would have to decide what to do about an id that exists with *different* content. The retry path is instead structural: §4's single transaction means a failed copy leaves the destination empty and immediately re-runnable. The one case that does leave rows behind is a *committed* copy whose verification then failed, and for that the script prints the explicit recovery — the two `DELETE` statements to run, and the reminder that the source is still authoritative — rather than performing it.

### 7. The rollback statement (AC 6, PRD 7.5)

Every run — success or failure — ends with a block on stdout:

```
Source      harness_ai.db
            sha256 3f9c…a12b  (unchanged)
            8 audit_logs rows, 0 users rows
Destination http://127.0.0.1:8080
            8 audit_logs rows, 0 users rows
Verified    counts OK · content OK · id preservation OK · read-back OK (8 of 8 sampled)
Rollback    The source file was opened read-only and is unmodified. It remains
            authoritative until you delete it, which is a separate step (STORY-014).
```

The story asks for this in the script's own output, not only in documentation, and it is the last thing printed for a reason: it is the sentence that tells the operator what state they are in.

### 8. The `sqlite3` exception, stated rather than assumed

The story asks whether PRD Section 11's *"No module outside `app/db/` imports `sqlite3` or any driver module"* is meant to except this script. **It is, and it is already in writing** — STORY-014's AC 6:

> Given `grep -rn "sqlite" app/ chat_ui/ docker-compose.yml Dockerfile`, when it runs, then there are no hits in any production path. `scripts/migrate_to_turso.py` is the one documented exception (it reads the legacy file by design); if it is excluded, say so explicitly.

Note that STORY-014's grep does not scan `scripts/` at all, while PRD Section 11's functional requirement does. The reconciliation is that this script is a **one-time operational tool, not a production code path** — it is never imported by the application, it runs once per deployment, and it exists precisely to read the file the rest of the system no longer may. The script's module docstring states this in full, and Task 10 records it in the report so STORY-014 does not have to rediscover it.

### Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | A positional copy silently shifts values between columns — the real `harness_ai.db` has a different column *order* than `CREATE_AUDIT_LOGS_TABLE`, and counts would still match. | Every statement names its columns; never `SELECT *` against the source. Task 8's content test builds a source with the ALTER-appended order and asserts per-column equality. |
| 2 | Explicit ids leave `sqlite_sequence` behind `MAX(id)`, so the first post-migration `insert_audit_log()` collides — history preserved, next write broken. | Ascending-id insert, then an explicit `sqlite_sequence` check and repair (Task 6), then a test that performs a real `insert_audit_log()` after migrating and asserts the new id is `MAX(id) + 1` (Task 9d). |
| 3 | The multi-row `INSERT` exceeds the endpoint's bound-parameter limit on a large history and fails mid-run. | `--batch-size 50` = 950 parameters, under the conservative 999 ceiling. Task 4 exercises a chunk count > 1 against the live endpoint. A failure rolls the whole transaction back (constraint 2), so it cannot half-populate. |
| 4 | Verification reads through the same client that wrote, so client-side state could confirm a write that never landed — PRD Risk 1's shape. | The verification reads run **after** `__exit__` commits, and Task 9e re-reads through a **fresh** client by resetting `app.db.database._client` (the key-based cache at `:57-63` reconstructs on demand), as STORY-001 §2.2 required of every write. |
| 5 | A hot `-wal` sidecar makes a read-only open either fail obscurely or require a recovery write, breaking AC 6. | Detected and refused before opening, with the checkpoint instruction (Task 3). |
| 6 | The AC 8 read-back at one round trip per row makes a real migration unusably slow if it is exhaustive by default. | Layer B is exhaustive and bulk; layer C is bounded by `--verify-sample`, biased toward the rows carrying PII telemetry, and can be opened to all with `0`. What was actually checked is printed in the summary (`read-back OK (50 of 1274 sampled)`) so the operator is never misled. |
| 7 | Suite-wide `STREAM_EXPIRED` (the open issue in the PRD index) makes a whole-suite run flaky and could be misread as a defect in this story. | Validate with `pytest tests/test_migrate_to_turso_cli.py` as its own process, as every story since STORY-006 has. Do not chase it here. |

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Confirm the dev endpoint is up

- **File**: — (environment)
- **Action**: RUN
- **Implement**: Start the pinned libSQL dev server from STORY-001 §4 if it is not already running. It is the only endpoint the suite talks to and it takes no token.
- **Validate**:
  ```bash
  curl -sf http://127.0.0.1:8080/health || docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
    ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67
  ```

### Task 2: The script skeleton, parser, and the `sqlite3` exception docstring

- **File**: `scripts/migrate_to_turso.py`
- **Action**: CREATE
- **Implement**: The `REPO_ROOT` bootstrap, imports, `_build_parser()` with `--source` (required), `--batch-size` (int, default 50), `--verify-sample` (int, default 50), `--dry-run` (store_true), and `main(argv)` returning an int. One handler function, no subcommands. Take the destination column list from `app/db/models.py` rather than re-typing it — derive it from `CREATE_AUDIT_LOGS_TABLE` / `CREATE_USERS_TABLE`, or declare it beside a comment pointing at `models.py`; do not let two column lists drift.
- **Module docstring must record**: that this is the **one sanctioned `import sqlite3` outside `app/db/`** (§8, quoting STORY-014's AC 6), why the exception is sound (a one-time operational tool, never imported by the application), that the destination comes from `settings` and the source from the CLI because `app/config.py:76-98` forbids a `sqlite:` URL, and that deleting the source belongs to STORY-014.
- **Mirror**: `scripts/manage_users.py:1-28` (bootstrap, imports, a module constant with a "why here" comment), `:76-107` (parser + `main`).
- **Validate**: `python scripts/migrate_to_turso.py --help` prints the four flags; `python scripts/migrate_to_turso.py` exits non-zero on the missing `--source`.

### Task 3: Read-only source open, hot-journal refusal, and the SHA-256 fingerprint

- **File**: `scripts/migrate_to_turso.py`
- **Action**: UPDATE
- **Implement**: `_open_source(path)` → resolves the path, refuses a missing file, refuses a non-empty `-wal`/`-journal` sidecar with the checkpoint instruction, hashes the file (SHA-256, chunked read), and opens `sqlite3.connect(f"file:{path}?mode=ro", uri=True)` with `row_factory = sqlite3.Row`. A `_fingerprint(path)` helper returns `(sha256, size)`. The `finally` in `main()` re-fingerprints and fails the run if it changed, on every exit path.
- **Rationale to state in the code**: AC 6 covers success, failure **and** interruption, so `mode=ro` is the enforcement and the hash is the proof; a comment saying "we don't write to it" would be neither.
- **Validate**:
  ```bash
  python -c "
  import sqlite3
  c = sqlite3.connect('file:harness_ai.db?mode=ro', uri=True)
  print(c.execute('SELECT COUNT(*) FROM audit_logs').fetchone())
  try:
      c.execute('CREATE TABLE x (a)')
  except Exception as e:
      print('write refused:', type(e).__name__, e)"
  ```
  Expect the count and a refused write.

### Task 4: Schema reconciliation and the chunked copy

- **File**: `scripts/migrate_to_turso.py`
- **Action**: UPDATE
- **Implement**: `_reconcile(source, table)` implementing §3 — intersection in destination order, the refusal cases, the absent-`users` case, and a returned record of which columns were defaulted. Then `_copy(conn, ...)` building the chunked multi-row `INSERT` of §4 inside the single `with get_connection() as conn:` block, both tables, `audit_logs ORDER BY id`. `--dry-run` returns before that block is entered.
- **Mirror**: `app/db/database.py:517` (the `PRAGMA table_info` idiom), `:525-558` (an explicit-column INSERT).
- **Docstring must record**: that a real ALTER-migrated source has a different column order than `CREATE_AUDIT_LOGS_TABLE`, so the column names are load-bearing (Risk 1); that the driver has no batch API (STORY-001 §2.6) and `executemany` is unexercised in this repo, so one statement per chunk through `execute()` is the mechanism.
- **Also**: measure `executemany` once against the endpoint and record the result for Task 10 — whether it is one round trip or N. It is not adopted in this story either way; the note is for whoever next needs bulk writes.
- **Validate**: dry-run first, then a real copy into the dev endpoint:
  ```bash
  python scripts/migrate_to_turso.py --source harness_ai.db --dry-run
  DATABASE_URL=http://127.0.0.1:8080 python scripts/migrate_to_turso.py --source harness_ai.db --batch-size 3
  ```
  Expect 8 rows copied in 3 statements, exit 0.

### Task 5: The non-empty-destination refusal

- **File**: `scripts/migrate_to_turso.py`
- **Action**: UPDATE
- **Implement**: `init_db()` first (it is also the reachability guard, `app/db/database.py:454-478`), then count both destination tables. Any non-zero → print the counts and the table at fault to stderr, return 1, write nothing. On the committed-but-unverified path, print the two `DELETE` statements as the recovery, per §6.
- **Rationale to state in the code**: why there is no `--force` (§6) — the single transaction is the retry path, and a flag that empties an audit table is the wrong tool to ship beside one.
- **Mirror**: `scripts/manage_users.py:57-60` (the stderr + `return 1` shape).
- **Validate**: run Task 4's copy twice; the second run must exit 1, name `audit_logs`, print nothing to stdout before the error, and leave the destination at 8 rows.

### Task 6: `sqlite_sequence` continuation, verified at the endpoint

- **File**: `scripts/migrate_to_turso.py`
- **Action**: UPDATE
- **Implement**: After the copy commits, read `SELECT seq FROM sqlite_sequence WHERE name = 'audit_logs'` from the destination. If it is absent or below `MAX(id)`, set it explicitly (`INSERT OR REPLACE INTO sqlite_sequence(name, seq) VALUES ('audit_logs', ?)`) and say so in the output. If it already matches, say that too — the operator should know which happened.
- **Rationale to state in the code**: local SQLite updates the sequence on an explicit-id insert (verified: ids `7, 30` → `seq = 30`, next natural id `31`); this repairs the case where the endpoint does not, rather than assuming parity with a different engine.
- **Validate**:
  ```bash
  python -c "
  from app.db.database import get_connection
  with get_connection() as c:
      print(c.execute(\"SELECT name, seq FROM sqlite_sequence\").fetchall())
      print(c.execute('SELECT MAX(id) AS m FROM audit_logs').fetchone()['m'])"
  ```
  The two must agree.

### Task 7: The three verification layers and the summary block

- **File**: `scripts/migrate_to_turso.py`
- **Action**: UPDATE
- **Implement**: `_verify_counts`, `_verify_content`, `_verify_ids`, `_verify_read_back`, `_verify_token_hashes` per §5, each **returning** a list of failure strings rather than raising, so all checks run and the operator sees every problem in one pass instead of one per re-run. Then the §7 summary block, printed on every exit path, and `return 1` if any check produced a failure. Mismatch lines are capped at 20 with an `… and N more` trailer.
- **Mirror**: `app/db/database.py:611-618` and `:575-608` for the read-back path; `app/db/errors.py`'s docstring style for stating what a check exists to protect.
- **Validate**: re-run Task 4's copy against a fresh endpoint and confirm the summary reads `counts OK · content OK · id preservation OK · read-back OK`; then corrupt one destination cell by hand and confirm a re-verify names the table, the id and the column.

### Task 8: Tests — the six AC 10 cases

- **File**: `tests/test_migrate_to_turso_cli.py`
- **Action**: CREATE
- **Implement**: A `_make_source(tmp_path, ...)` helper building a legacy `.db` with stdlib `sqlite3` — the ALTER-appended column order of the real file (Risk 1), non-contiguous ids, rows carrying `pii_entities`, `role` and `denied_permission`, and a `users` row. Then the six cases AC 10 names, in this order: **(a)** clean copy — exit 0, counts equal, every column equal; **(b)** id preservation — ids `3, 7, 100` survive and `get_audit_log(100)` resolves; **(c)** non-empty destination — refuses, exit 1, `captured.out == ""`, destination row count unchanged; **(d)** count mismatch — monkeypatch the script's copy helper to drop the last chunk, assert exit 1 and that the message names `audit_logs` and the failed check; **(e)** older-schema source — a source lacking `role` and `denied_permission` copies successfully and those columns read back as `None`; **(f)** empty source — exit 0, `0 -> 0`, and the output says plainly that there was nothing to migrate.
- **Mirror**: `tests/test_manage_users_cli.py:17-70` (in-process `main([...])`, `temp_db`, `capsys`, the stdout/stderr split); `tests/test_db.py`'s pre-migration schema builders for the hand-rolled legacy table.
- **Validate**: `python -m pytest tests/test_migrate_to_turso_cli.py -q`

### Task 9: Tests — the integrity guarantees the ACs turn on

- **File**: `tests/test_migrate_to_turso_cli.py`
- **Action**: UPDATE
- **Implement**: **(a)** AC 6 — the source's SHA-256 is unchanged after a successful run **and** after a failed one (force a failure mid-copy), and a write through the script's own connection is refused; **(b)** AC 7 — `token_hash` values are byte-identical, `find_user_by_token_hash(hash)` resolves the migrated user, and inserting a second user with a duplicate `token_hash` still raises `IntegrityError` (the unique index survived); **(c)** AC 8 — for every seeded row, `get_audit_log(id)` returns an `AuditLog` whose five `AUDIT_LOGS_ADDED_COLUMNS` plus `role` and `denied_permission` equal the source, including a multi-entity `pii_entities` string and a row where all seven are `NULL`/default; **(d)** Risk 2 — after migrating ids `3, 7, 100`, a real `insert_audit_log(...)` returns `101`; **(e)** Risk 4 — the content verification is re-run after resetting `app.db.database._client` to `None`, so the read-back crosses a **fresh** client; **(f)** content mismatch with **matching counts** exits 1 and names the column — AC 3's stated reason for existing; **(g)** batching — with `--batch-size 2` over 5 rows, a recording proxy over `get_connection()` observes exactly 3 `INSERT INTO audit_logs` statements; **(h)** `--dry-run` writes nothing and exits 0.
- **Mirror**: `tests/test_db.py:109-150` (the `_RecordingConnection` proxy idiom) for (g); `tests/conftest.py:81-103` for reaching the destination without opening a second client.
- **Validate**: `python -m pytest tests/test_migrate_to_turso_cli.py -q` — Tasks 8 and 9 all green.

### Task 10: Run it against the real `harness_ai.db` and write the report

- **File**: `.agents/reports/PRD-007-turso-migration/STORY-013-data-migration-script.report.md`
- **Action**: CREATE
- **Implement**: Run the script for real against the repo-root `harness_ai.db` (8 `audit_logs` rows, 0 `users` rows as of 2026-09-02) into the dev endpoint, and paste the verbatim output — including the summary block — into the report. Record: the per-table counts; the source SHA-256 before and after; the §8 ruling on PRD Section 11 versus STORY-014's AC 6, stated as an answer to the question the story asked; the `executemany` measurement from Task 4; whether the endpoint maintained `sqlite_sequence` on its own or needed the Task 6 repair; and an explicit note that **the source file has not been deleted and must not be until STORY-014**.
- **Mirror**: the existing reports in `.agents/reports/PRD-007-turso-migration/`.
- **Validate**: the report contains real pasted output, not a description of it.

### Task 11: Full validation and the untouched-application proof

- **File**: —
- **Action**: RUN
- **Implement**: Run the new suite and the storage suites, then prove from the diff that nothing outside `scripts/` and `tests/` moved.
- **Validate**:
  ```bash
  python -m pytest tests/test_migrate_to_turso_cli.py -q
  python -m pytest tests/test_db.py -q
  python -m pytest tests/test_manage_users_cli.py -q
  git status --porcelain                     # only the three new files
  git diff main --stat -- app/ chat_ui/      # must print nothing
  grep -rn "sqlite3" app/ chat_ui/ scripts/  # only scripts/migrate_to_turso.py
  ```
  Run each suite as its own process — the whole-suite `STREAM_EXPIRED` issue in the PRD index is pre-existing and not this story's (Risk 7).

---

## End-to-End Tests

- [ ] `python scripts/migrate_to_turso.py --help` documents all four flags
- [ ] `--dry-run` against the real `harness_ai.db` reports 8 `audit_logs` rows and 0 `users` rows and writes nothing (destination count still 0 afterwards)
- [ ] A real run into an empty dev endpoint exits 0 and prints `counts OK · content OK · id preservation OK · read-back OK`
- [ ] `GET /audit/{id}` served from the migrated database returns the same row for the same id it returned from the file — start the app against the endpoint and compare one id end to end
- [ ] A second run against the now-populated endpoint exits 1, names `audit_logs`, and prints nothing to stdout
- [ ] `sha256sum harness_ai.db` is identical before and after every one of the runs above
- [ ] After the migration, `python scripts/manage_users.py create-user --user-id smoke --role user` succeeds against the same endpoint — the `users` copy did not break the unique index
- [ ] After the migration, one `POST /query` writes an audit row whose id is `MAX(migrated id) + 1`

## Validation

```bash
python -m pytest tests/test_migrate_to_turso_cli.py -q
python -m pytest tests/test_db.py tests/test_manage_users_cli.py -q
python scripts/migrate_to_turso.py --source harness_ai.db --dry-run
grep -rn "sqlite3" app/ chat_ui/ scripts/
git diff main --stat -- app/ chat_ui/
```

## Acceptance Criteria

(Copied from story `STORY-013`)

- [ ] Given a source `.db` file and a target Turso database, when the script runs, then all rows of `audit_logs` and `users` are copied.
- [ ] Given `audit_logs`, when rows are copied, then their `id` values are **preserved**, not regenerated.
- [ ] Given a completed copy, when the script verifies, then it reports source and destination row counts **per table** and compares row content, not only counts.
- [ ] Given any mismatch in count or content, when the script finishes, then it exits non-zero and says which table and which check failed.
- [ ] Given a non-empty destination, when the script is run, then it either refuses outright or is genuinely idempotent.
- [ ] Given the source `.db` file, when the script completes by any path — success, failure, or interruption — then it is unmodified.
- [ ] Given the `users` table, when it is copied, then `token_hash` values transfer intact and the unique index on them holds afterward.
- [ ] Given all five `AUDIT_LOGS_ADDED_COLUMNS` plus `role` and `denied_permission`, when rows are read back through `get_audit_log(...)`, then PII entities, roles, and denied permissions match the source exactly.
- [ ] Given a source database missing some added columns, when the script runs, then it handles the case explicitly rather than crashing.
- [ ] Given the script, when it is tested, then coverage includes: a clean copy, id preservation, a non-empty destination, a count mismatch, an older-schema source, and an empty source.
- [ ] All tasks completed
- [ ] `tests/test_migrate_to_turso_cli.py` and `tests/test_db.py` pass
- [ ] No file under `app/` or `chat_ui/` is modified
- [ ] `grep -rn "sqlite3" app/ chat_ui/ scripts/` hits `scripts/migrate_to_turso.py` and nothing else
- [ ] Follows existing patterns
