---
story: STORY-001
prd: PRD-007
slug: libsql-driver-spike
title: "Spike: verify the six risky libSQL client behaviors and record the driver decision"
type: SPIKE
complexity: MEDIUM
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-01
---

# Plan: Six behaviors, one endpoint, one decision record

## Summary

Stand up a local libSQL server, point a pinned Python client at it, and answer the six questions PRD Section 8 names as the ones where the libSQL Python clients "differ precisely where this codebase is sensitive": named-column row access, commit semantics without `with sqlite3.Connection`, `lastrowid`, `rowcount`, `PRAGMA table_info`, and batch execution. Each answer is produced by a throwaway script that is **run but not committed**; what gets committed is one decision record at `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md` naming the chosen client, its exact pinned version, and a yes/no plus reproducible evidence for each of the six — including, for any behavior that comes back **no**, the workaround the later story must adopt. The record also settles the local dev-server workflow (start command, port, teardown), which PRD Section 12 lists as a Phase 1 deliverable and which [[STORY-003]] and [[STORY-006]] both build on. Nothing under `app/`, `chat_ui/`, or `scripts/` is touched — this story produces knowledge and a document, and the final task proves that with `git diff main --stat`.

Pre-research has already narrowed the candidate field and surfaced two facts the spike must confirm or refute rather than discover late. First, `libsql-client-py` and `libsql-experimental` are both **deprecated and archived** (the former archived 2025-06-11), superseded by `libsql` — so the field is effectively `libsql` with `turso-serverless` as the fallback, and pinning a dead package is not an option. Second, the `libsql` documentation's own cursor example prints `(1234567890, 'System started')` — a **tuple**, not a mapping. If that holds, Behavior 1 is a **no**, and it is a `no` that touches 22 call sites plus `_row_to_audit_log()` and `_row_to_user()`. Finding that in this story is the entire point of this story.

## User Story

As a maintainer
I want the libSQL Python client chosen on evidence rather than assumption
So that the storage swap in [[STORY-006]] does not discover mid-rewrite that the driver cannot express something `app/db/database.py` depends on.

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-001-libsql-driver-spike.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 8 (Technology Stack, "Driver selection is a Phase 1 deliverable, not an assumption"), Section 12 Phase 1, Section 14 Risk 1 (silent write loss) and Risk 4 (test-suite migration)

## Metadata

| Field | Value |
|-------|-------|
| Type | SPIKE |
| Complexity | MEDIUM |
| Systems Affected | `.agents/reports/PRD-007-turso-migration/` (CREATE, one file). **No** `app/`, **no** `chat_ui/`, **no** `scripts/`, **no** `tests/`, **no** `requirements.txt`. |
| Story | STORY-001 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

**Dependency check**: `depends_on: []`. Nothing blocks this story; it is the first story of the epic. `blocks: [STORY-005, STORY-006]` — both are `todo`, so no downstream work is waiting on a partial answer. Cleared to proceed.

**Branch check**: `epic/PRD-007-turso-migration` **does not exist yet** — `git branch -a` shows epics for PRD-001 through PRD-006 only. Task 0 creates it from `main`.

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `.agents/skills/frontend-design` | Read in full. Scoped by its own `description` to "distinctive, intentional visual design when building new UI or reshaping an existing one" — aesthetic direction, typography, layout. This story renders no UI and emits no user-facing string. | **none** |

`.agents/skills/` was listed and contains exactly one skill directory, `frontend-design`. Its `SKILL.md` was read in full; it governs visual design work and nothing in this story is visual. The story frontmatter's `skills: []` is therefore correct, and this table records that the scan happened rather than that it found nothing to scan. No skill rule constrains any task below.

---

## Prior Research (carried into the tasks, not a substitute for them)

Everything in this section was established while planning and is written down so the spike **confirms or refutes** it against a live endpoint instead of rediscovering it. None of it is evidence for the decision record — only a run against a real endpoint is.

### The candidate field

| Package | Latest | Status | Why it is / is not a candidate |
|---|---|---|---|
| **`libsql`** | **0.1.11** | Active — `tursodatabase/libsql-python` | **Primary candidate.** Successor to both deprecated clients. Rust-backed, `sqlite3`-compatible DB-API surface, documented `commit()`, `cursor.rowcount`, `cursor.lastrowid`, `cursor.description`, `executemany`. Speaks `libsql://`, `https://`, and `http://`. |
| `libsql-client` | 0.3.1 | **Archived 2025-06-11** | Had exactly what this codebase wants — a `batch()` returning one `ResultSet` per statement, with named row access. Disqualified by being dead: PRD Section 8 requires an exact pin, and pinning an archived package is a liability, not a decision. Worth reading for its API shape only. |
| `libsql-experimental` | 0.0.55 | **Deprecated** | Superseded by `libsql`. Not a candidate. |
| **`turso-serverless`** | **0.1.0** | Active | **Fallback candidate only.** Pure-Python DB-API 2.0 over HTTP — no compiled wheel, which sidesteps the toolchain problem below. Counted against it: version 0.1.0, and it targets Turso Cloud rather than a self-hosted libSQL server. Evaluate **only** if `libsql` fails a behavior with no acceptable workaround (Task 10). |
| `pyturso` | 0.7.2 | Active | **Not a candidate.** In-process/embedded database. PRD Section 4 rejects any local-file read path outright: "the file is being eliminated, not relocated." |

### The Python-version trap

`libsql` 0.1.11 ships 23 artifacts. Wheel coverage matters here because there is no pure-Python fallback:

- `cp311`: `manylinux_2_17_x86_64` ✅, `win_amd64` ✅, macOS x86_64 + arm64 ✅
- `cp314`: `manylinux_2_17_x86_64` only — **no `win_amd64`**

The Dockerfile builds on `python:3.11` (`Dockerfile:2`, `Dockerfile:29`), so the deployment target is covered. **The development host runs Python 3.14.4 on Windows**, where `pip download libsql==0.1.11` falls back to `libsql-0.1.11.tar.gz` and would require a Rust toolchain to build. This is verified, not speculative — the sdist fallback was observed during planning. Task 2 therefore runs the spike under Python **3.11**, matching the Dockerfile, and the decision record must state the wheel-coverage constraint so [[STORY-006]] and CI are not surprised by it.

### The local dev server

`ghcr.io/tursodatabase/libsql-server` run as a primary node, listening on `8080`, no auth token required locally. Docker 29.7.2 is available on this host and the repo already ships a `docker-compose.yml`, so this adds no new class of tooling. This satisfies the three non-negotiables PRD Section 7.6 places on the test infrastructure: offline after the image pull, no Turso account, structurally incapable of reaching production.

### What the docs already suggest per behavior

| # | Behavior | Documented signal | Spike must settle |
|---|---|---|---|
| 1 | Named-column access | Example prints a **tuple**; `cursor.description` exists | Is there a `row_factory`? If not, `description`-based mapping is the workaround |
| 2 | Commit semantics | `conn.commit()` shown explicitly for remote; "Commit changes to remote database" | Does a write **without** `commit()` survive a **fresh client**? Does `with conn` commit? |
| 3 | `lastrowid` | `cursor.lastrowid` documented | Correct against `INTEGER PRIMARY KEY AUTOINCREMENT` over the network? |
| 4 | `rowcount` | `cursor.rowcount` documented for DML | Correct for a **0-row** `UPDATE`, not only a 1-row one? |
| 5 | `PRAGMA table_info` | Not documented either way | Supported over the remote endpoint at all, and in what row shape? |
| 6 | Batch | `executemany` = one statement, many params | Is there a **multi-statement** batch? `executemany` does **not** answer [[STORY-010]] |

---

## Patterns to Follow

### The row access this spike is testing (the thing that must keep working)

```python
# SOURCE: app/db/database.py:26-29
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn
```

```python
# SOURCE: app/db/database.py:135-144  -- named access on an aliased aggregate
def count_audit_logs(user_id: Optional[str] = None) -> int:
    with get_connection() as conn:
        ...
        row = conn.execute("SELECT COUNT(*) AS n FROM audit_logs").fetchone()
        return row["n"]
```

```python
# SOURCE: app/db/database.py:101-122  -- 19 named reads in one mapper
def _row_to_audit_log(row: sqlite3.Row) -> AuditLog:
    return AuditLog(
        id=row["id"],
        timestamp=row["timestamp"],
        ...
        denied_permission=row["denied_permission"],
    )
```

`SELECT *` plus name access means Behavior 1 cannot be answered "positionally is fine" without also fixing the column order to the DDL — record that consequence if the answer is no.

### The implicit commit this spike is testing

```python
# SOURCE: app/db/database.py:51-84  -- no explicit commit anywhere in the module
def insert_audit_log(entry: AuditLog) -> int:
    with get_connection() as conn:
        cursor = conn.execute("INSERT INTO audit_logs (...) VALUES (?, ...)", (...))
        return cursor.lastrowid
```

Every write in the module inherits its durability from `with sqlite3.Connection`. There is **no** `conn.commit()` call in all 356 lines. That is Risk 1 in one sentence.

### The `rowcount` and `PRAGMA` contracts

```python
# SOURCE: app/db/database.py:337-345
def deactivate_user(user_id: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("UPDATE users SET active = 0 WHERE user_id = ?", (user_id,))
        return cursor.rowcount == 1
```

```python
# SOURCE: app/db/database.py:45  -- runs inside init_db(); a failure here is a failure to boot
existing = {row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)")}
```

`rowcount == 1` is a three-way contract: `1` on a hit, `0` on a miss, and never `-1`. The `PRAGMA` read compounds Behaviors 1 and 5 — it needs both `PRAGMA` support *and* `row["name"]`.

### The DDL the spike runs against

```sql
-- SOURCE: app/db/models.py:4-26 (audit_logs) and :52-60 (users)
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    ...
)
```

The spike uses `CREATE_AUDIT_LOGS_TABLE` and `CREATE_USERS_TABLE` **verbatim** by importing `app.db.models` — reading them is not a modification, and a hand-retyped schema would test the wrong thing.

### Report frontmatter shape

```markdown
# SOURCE: .agents/reports/PRD-006-admin-console/STORY-001-audit-row-model.report.md:1-9
---
story: STORY-001
prd: PRD-006
plan: .agents/plans/.../STORY-001-....plan.md
epic_branch: epic/PRD-006-admin-console
commit: 577a285
status: COMPLETE
completed: 2026-08-28
---
```

The decision record is not an implementation report — it carries `status: DECIDED` and a `decision:` field naming the pinned client — but it lives in the same directory and keeps the same `story` / `prd` / `plan` / `epic_branch` keys so the index and the workflow can find it.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md` | CREATE | The one committed artifact: chosen client, exact pin, six answers with evidence, workarounds, dev-server workflow |
| `.agents/stories/PRD-007-turso-migration/STORY-001-libsql-driver-spike.md` | UPDATE | Phase 5 — `plan`, `status`, `report`, `updated` |
| `.agents/PRDs/PRD-007-turso-migration/index.md` | UPDATE | Phase 5 — status + plan link |
| *scratchpad* `spike_libsql.py` | CREATE (**not committed**) | The throwaway harness. Lives in the scratchpad directory, never in the repo |

**Explicitly not changed**: `app/**`, `chat_ui/**`, `scripts/**`, `tests/**`, `requirements.txt`, `docker-compose.yml`, `Dockerfile`. Task 12 proves it.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 0: Create the epic branch

- **File**: — (git)
- **Action**: CREATE
- **Implement**: `git checkout main && git checkout -b epic/PRD-007-turso-migration`. It does not exist yet. All 16 stories of PRD-007 commit here; there is no per-story branch.
- **Note**: the untracked `.agents/PRDs/PRD-007-turso-migration/` and `.agents/stories/PRD-007-turso-migration/` directories in the working tree come along with the checkout and are committed on this branch, not on `main`.
- **Validate**: `git rev-parse --abbrev-ref HEAD` prints `epic/PRD-007-turso-migration`; `git log -1 --oneline` matches `main`'s tip (`d91168b`).

### Task 1: Start the local libSQL dev server and prove it is reachable

- **File**: — (environment)
- **Action**: RUN
- **Implement**:
  ```bash
  docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
    ghcr.io/tursodatabase/libsql-server:latest
  ```
  No auth token is required against a local primary. The endpoint for every later task is `http://127.0.0.1:8080`. **Do not** mount a volume — each spike run wants a clean database, and the teardown must leave nothing behind.
- **Record for the decision record**: the exact image reference **including the resolved digest** (`docker inspect --format '{{index .RepoDigests 0}}'`), the start command, the port, and the teardown (`docker rm -f harness-libsql-dev`). [[STORY-003]] and [[STORY-006]] consume this verbatim; `:latest` without a digest is not reproducible.
- **Validate**: `curl -sf http://127.0.0.1:8080/health` (or `/v2`) returns success, and `docker logs harness-libsql-dev` shows the primary listening on 8080.

### Task 2: Pin the client under Python 3.11 and record wheel coverage

- **File**: — (scratch venv, outside the repo)
- **Action**: RUN
- **Implement**: create a throwaway venv on **Python 3.11** — matching `Dockerfile:2` (`FROM python:3.11`) — and `pip install libsql==0.1.11`. The host's default Python is 3.14.4, for which **no `win_amd64` wheel exists**; installing there falls back to the sdist and needs a Rust toolchain. If a local 3.11 is unavailable, run the whole spike inside `python:3.11` in Docker on the same Docker network as the server, and use `http://harness-libsql-dev:8080` as the endpoint.
- **Record**: whether the install resolved a **wheel** or the **sdist** (`pip install -v` names the artifact), and the cp311 platform coverage. PRD Section 8 requires an exact pin; the pin is meaningless if it cannot be installed on the CI and deployment platforms.
- **Validate**: `python -c "import libsql; print(libsql.__file__)"` succeeds and `pip freeze | grep -i libsql` prints `libsql==0.1.11`.

### Task 3: Write the spike harness

- **File**: `{scratchpad}/spike_libsql.py` — **scratch only, never committed**
- **Action**: CREATE
- **Implement**: one script, six independently-runnable checks, each printing a labelled verdict line plus the raw repr of what it observed. Requirements:
  - Reads the endpoint from an env var, defaulting to `http://127.0.0.1:8080`.
  - Imports `CREATE_AUDIT_LOGS_TABLE`, `CREATE_USERS_TABLE`, `AUDIT_LOGS_ADDED_COLUMNS` from `app.db.models` rather than retyping the DDL. Import only — `app/db/models.py` is not edited.
  - Every check prints **the observed value**, not just pass/fail. `assert` alone produces no evidence; the decision record needs the repr.
  - A `--fresh-client` mode that constructs a **brand-new** client and reads, used by Task 5.
  - Catches and prints the exception **type and module** on failure — a behavior that raises is evidence, and the exception's identity is what [[STORY-004]]'s error surface will be built from.
- **Mirror**: the DDL and the statements come from `app/db/database.py` — use its actual SQL text (the `INSERT INTO audit_logs (...)` at `:53-62`, the `UPDATE users SET active = 0 ...` at `:343`, the `PRAGMA table_info(audit_logs)` at `:45`), not simplified stand-ins. A spike that tests `CREATE TABLE t (a, b)` has tested nothing about this codebase.
- **Validate**: `python spike_libsql.py --help` runs; the script is under the scratchpad path and `git status --porcelain` in the repo shows it nowhere.

### Task 4: Behavior 1 — named-column row access (AC 1)

- **File**: `{scratchpad}/spike_libsql.py`
- **Action**: RUN
- **Implement**: insert one `audit_logs` row, then probe, in order: (a) does `conn.row_factory = ...` exist and take effect; (b) does a fetched row support `row["timestamp"]`; (c) does `row["n"]` work on `SELECT COUNT(*) AS n` (the aliased-aggregate case, used by six functions); (d) what is `type(row)` and does it support `.keys()`; (e) is `cursor.description` populated with column names for both `SELECT *` and the aliased aggregate.
- **Expected to be a `no`** — the client's own documented example prints a bare tuple. Do not stop there. If subscripting fails, record the **workaround** and prove it runs: a mapping row factory built from `cursor.description`, wrapping every result before it reaches `_row_to_audit_log()` / `_row_to_user()`. Note explicitly whether `description` is populated for `SELECT *`, because that determines whether the 22 call sites can stay untouched or must be rewritten positionally against a fixed column order.
- **Blast radius to state in the record**: 22 call sites, `_row_to_audit_log()` (19 named reads), `_row_to_user()` (5).
- **Validate**: the record carries a yes/no, `type(row)`, the repr of a fetched row, and — if no — a runnable workaround snippet.

### Task 5: Behavior 2 — commit semantics, verified through a fresh client (AC 2) — **highest severity**

- **File**: `{scratchpad}/spike_libsql.py`
- **Action**: RUN
- **Implement**: four cases, each written by one client and read back by a **separately constructed** client in a **separate process invocation** (`--fresh-client`):
  1. `conn.execute(INSERT ...)` and **nothing else** — no commit, no close. Does the row survive?
  2. `conn.execute(INSERT ...)` then `conn.commit()`.
  3. `with conn: conn.execute(INSERT ...)` — does the context manager carry the `sqlite3` commit-on-exit semantic? This is the exact construct all 22 functions use.
  4. `conn.execute(INSERT ...)` then `conn.close()` — does close imply commit?
- **The read-back must not reuse the writing client, and must not be an in-process or in-memory shortcut.** The story is explicit and Risk 1 is why: a same-client read can be served from client-side state and would report a commit that never happened. Running the read as a separate process invocation is the cheapest way to make that impossible to get wrong by accident.
- **Also record**: whether the client is autocommit by default, and whether `rollback()` is available and effective — [[STORY-013]]'s migration script will want it.
- **Consequence to state**: if case 3 is a `no`, every one of the module's writes silently loses data on swap, and [[STORY-006]] must add an explicit commit to each. That is the single most valuable sentence this spike produces.
- **Validate**: four cases, four recorded outcomes, each with the fresh-client read result pasted in.

### Task 6: Behavior 3 — `lastrowid` on AUTOINCREMENT insert (AC 3)

- **File**: `{scratchpad}/spike_libsql.py`
- **Action**: RUN
- **Implement**: against `audit_logs` (`id INTEGER PRIMARY KEY AUTOINCREMENT`, `app/db/models.py:6`), insert three rows in sequence and record `cursor.lastrowid` after each. Check it is present, non-`None`, monotonically 1/2/3, and — via a fresh-client `SELECT id` — that it names the row actually written. Also record whether `lastrowid` reads off the **cursor** or the **connection**, and whether `conn.execute(...)` returns a cursor at all (the module does `cursor = conn.execute(...)` at `:53` and `:342`; if `execute` returns something else, that is a shape change on its own).
- **Workaround to record if unsupported**: `RETURNING id`, which libSQL inherits from SQLite ≥3.35 — but verify it against this endpoint rather than assuming.
- **Consequence**: `insert_audit_log()` returns `cursor.lastrowid` (`:84`) and `GET /audit/{id}` depends on it.
- **Validate**: three ids recorded, each confirmed against a fresh-client read.

### Task 7: Behavior 4 — `rowcount` for one-row and zero-row updates (AC 4)

- **File**: `{scratchpad}/spike_libsql.py`
- **Action**: RUN
- **Implement**: insert one `users` row. Then run `UPDATE users SET active = 0 WHERE user_id = ?` twice: once with the existing `user_id` (expect `rowcount == 1`), once with a `user_id` that does not exist (expect `rowcount == 0`). Record both raw values. Then repeat for `UPDATE users SET token_hash = ? WHERE user_id = ?` (`set_user_token_hash`, `:352-355`).
- **The zero-row case is the one that matters.** Some drivers report `-1` for "unknown", which would make `cursor.rowcount == 1` return `False` correctly but for the wrong reason — and would silently break any later `!= 0` reading. Record the literal value, not a boolean.
- **Also record**: whether `rowcount` is meaningful **before** a commit, since Behavior 2 may force a commit in between.
- **Consequence**: `deactivate_user()` and `set_user_token_hash()` both `return cursor.rowcount == 1`, and `scripts/manage_users.py` reports a typo'd `user_id` off that `False`.
- **Validate**: four literal `rowcount` values recorded (two statements × hit/miss).

### Task 8: Behavior 5 — `PRAGMA table_info` over the remote endpoint (AC 5)

- **File**: `{scratchpad}/spike_libsql.py`
- **Action**: RUN
- **Implement**: create `audit_logs` **without** the five `AUDIT_LOGS_ADDED_COLUMNS` (an old-schema simulation — this is what `_add_missing_columns()` exists for), then:
  1. Execute `PRAGMA table_info(audit_logs)`. Is it accepted over the wire at all? Record the exception type and module if not.
  2. Is the result **iterable directly** from `conn.execute(...)`? Line 45 iterates the cursor without `fetchall()`.
  3. Does each row support `row["name"]`? This compounds Behavior 1 — record it separately, because `PRAGMA` results may have a different shape from a `SELECT`.
  4. Run the real `_add_missing_columns()` sequence: `ALTER TABLE audit_logs ADD COLUMN {name} {ddl}` for each of the five, using the DDL from `AUDIT_LOGS_ADDED_COLUMNS` verbatim — including `INTEGER NOT NULL DEFAULT 0`, which SQLite only accepts because of the `DEFAULT`.
  5. Re-run the `PRAGMA` and confirm all five now appear.
  6. Record what happens on a **duplicate** `ADD COLUMN` — the exception's type, module, and message. [[STORY-007]] needs exactly this to make concurrent `init_db()` converge, and it is free to collect now.
- **Fallback to record if `PRAGMA` is unsupported**: `SELECT ... FROM pragma_table_info('audit_logs')` (the table-valued function form), which some remote protocols accept where the bare statement is rejected.
- **Consequence**: this runs inside `init_db()`, which `chat_ui/chat_ui` calls at import time. A failure here is a container that will not boot.
- **Validate**: the record states supported yes/no, the row shape, the five ALTERs applied, and the duplicate-column exception identity.

### Task 9: Behavior 6 — batch / multi-statement execution (AC 6)

- **File**: `{scratchpad}/spike_libsql.py`
- **Action**: RUN
- **Implement**: the question is **several different statements in one round trip**, not one statement with many parameter sets. Probe in this order and record each:
  1. Is there a `conn.batch(...)` / `execute_batch` / `executescript`? Enumerate the actual surface — `[n for n in dir(conn) + dir(cur) if not n.startswith('_')]` — and paste it into the record.
  2. `executemany` — confirm it is same-statement-only. It does **not** answer this AC; record why so the next reader does not mistake it for a yes.
  3. If a batch API exists: submit the **ten real summary statements** (`COUNT(*)`, `COUNT(*) WHERE was_duplicate_blocked = 1`, `COUNT(*) WHERE suspicious_pattern IS NOT NULL`, `COUNT(DISTINCT user_id)`, `COUNT(*) WHERE success = 1`, the PII count, `top_models`, `top_users`, `top_pii_entities`, `list_audit_logs`) and record: how are **per-statement results** returned (order, shape, name access)? What happens on a **per-statement error** — does one bad statement fail the whole batch, and can the failure be attributed to its statement?
  4. Count the round trips. If the client offers no observable count, measure wall-clock for 10 statements batched vs. 10 sequential against the local server and record both.
- **Per-statement error attribution is not optional.** PRD Risk 6: `_READS` exists so each of the ten figures reports its own failure via its own `READ_LABEL_*`, and `tests/test_admin_shell.py` pins `len(_READS) == 10`. A batch API that collapses ten legible failures into one opaque one is a **partial** yes, and must be recorded as such.
- **If there is no multi-statement batch at all**: say so plainly and record the fallback for [[STORY-010]] — a single `SELECT` with ten scalar subqueries in one row, which needs no client batch API and preserves per-figure mapping by column name. Note that it makes Behavior 1's answer load-bearing a second time.
- **Validate**: the record answers all four sub-questions; `dir()` output for connection and cursor is pasted in full.

### Task 10: Candidate comparison and the decision

- **File**: — (analysis)
- **Action**: RUN
- **Implement**: assemble the six answers. If `libsql==0.1.11` passes all six, or fails only with workarounds that are cheap and local to `app/db/database.py`, **it is the choice** — it is the only actively maintained client with the required topology, and the alternatives are archived, pre-1.0, or the wrong shape. Record that reasoning rather than leaving the pin unjustified.
  Re-run the failing checks against `turso-serverless==0.1.0` **only** if `libsql` fails a behavior with no acceptable workaround. Its being pure-Python (no wheel constraint) is a genuine advantage worth a paragraph either way; its `0.1.0` version and Turso-Cloud orientation are the counterweight.
  If **no** candidate can satisfy Behavior 2 (commit) or Behavior 5 (`PRAGMA`), do not paper over it: that is a finding that changes PRD Section 12's phasing, and it goes to the top of the decision record.
- **Validate**: the record names one client and one exact version, with the reasoning and the rejected alternatives written down.

### Task 11: Write the decision record

- **File**: `.agents/reports/PRD-007-turso-migration/STORY-001-driver-decision.md`
- **Action**: CREATE
- **Implement**: `mkdir -p .agents/reports/PRD-007-turso-migration` first. Frontmatter follows the report shape at `.agents/reports/PRD-006-admin-console/STORY-001-audit-row-model.report.md:1-9`, with `status: DECIDED` and an added `decision:` field. Sections, in order:
  1. **Decision** — one sentence. Client name, exact pinned version, the `requirements.txt` line as it will be written by [[STORY-006]].
  2. **The six behaviors** — a table (`# | Behavior | Answer | Evidence | Consequence`) with yes / no / partial, followed by one subsection per behavior carrying the actual observed output. **Paste the reprs.** A record that says "works" without the value it saw is not evidence.
  3. **Workarounds required** — one entry per `no` or `partial`, each naming the story that must adopt it ([[STORY-006]] for row access and commits, [[STORY-007]] for the duplicate-column exception, [[STORY-010]] for batching). This section is the whole reason the story says "do not stop at no".
  4. **Local dev-server workflow** — image reference **with digest**, start command, port, teardown, and how a test gets an isolated empty database. This is the Phase 1 deliverable [[STORY-003]] and [[STORY-006]] consume.
  5. **Environment constraints** — the cp311/cp314 wheel coverage and the Python 3.14-on-Windows sdist fallback, stated as a constraint on CI and on developer machines.
  6. **Rejected alternatives** — `libsql-client` (archived 2025-06-11), `libsql-experimental` (deprecated), `pyturso` (embedded; PRD forbids a local file), `turso-serverless` (or the reason it won, if it did).
  7. **Reproducing this** — the spike script inline in a fenced block, so the run is repeatable even though the file was never committed.
- **Validate**: every one of the eight story ACs maps to a section; each of the six has a yes/no/partial and a pasted observation; the pinned version is exact.

### Task 12: Prove no production code moved (AC 8)

- **File**: — (verification)
- **Action**: RUN
- **Implement**: `git diff main --stat` and confirm the only changed paths are under `.agents/`. Also `git status --porcelain` to confirm the spike script and the scratch venv are outside the repo, not merely untracked. Then commit on `epic/PRD-007-turso-migration`.
- **Validate**: `git diff main --stat -- app/ chat_ui/ scripts/` is **empty**; `git diff main --stat` lists only `.agents/` paths.

---

## End-to-End Tests

- [ ] `docker run ... ghcr.io/tursodatabase/libsql-server:latest` starts and `http://127.0.0.1:8080` answers a health probe
- [ ] `pip install libsql==0.1.11` on Python 3.11 resolves a **wheel** (not the sdist) and `import libsql` succeeds
- [ ] The spike creates `audit_logs` and `users` from `app/db/models.py`'s DDL **verbatim** against the remote endpoint, with no SQL edits
- [ ] A write followed by a read from a **separately constructed client in a separate process** returns the expected durability answer for all four commit cases
- [ ] The five `AUDIT_LOGS_ADDED_COLUMNS` apply via `ALTER TABLE` and appear in a subsequent `PRAGMA table_info`
- [ ] A duplicate `ADD COLUMN` produces a recorded exception type, module, and message
- [ ] `docker rm -f harness-libsql-dev` leaves no container and no volume
- [ ] Re-running the spike from a clean container reproduces every recorded answer

## Validation

```bash
# dev server up
docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
  ghcr.io/tursodatabase/libsql-server:latest
docker inspect --format '{{index .RepoDigests 0}}' harness-libsql-dev   # pin this in the record
curl -sf http://127.0.0.1:8080/health

# client pinned, on 3.11
python -c "import sys, libsql; print(sys.version)"
pip freeze | grep -i libsql          # -> libsql==0.1.11

# the spike
python "{scratchpad}/spike_libsql.py"

# nothing under production code moved
git diff main --stat -- app/ chat_ui/ scripts/ tests/ requirements.txt   # -> empty
git diff main --stat                                                     # -> only .agents/

# teardown
docker rm -f harness-libsql-dev
```

## Acceptance Criteria

(Copied from story `STORY-001`)

- [ ] Named-column row access answered — `row["timestamp"]` / `row["n"]` subscripting, or positional mapping — with the 22-call-site and two-mapper blast radius stated (Task 4)
- [ ] Commit durability answered by reading back through a **separate, freshly constructed client**; a same-client read-back is not accepted as evidence (Task 5)
- [ ] `lastrowid` on `INTEGER PRIMARY KEY AUTOINCREMENT` answered — retrievable, and how (Task 6)
- [ ] `rowcount` answered for an `UPDATE` matching exactly one row **and** one matching zero rows, as literal values (Task 7)
- [ ] `PRAGMA table_info(audit_logs)` answered — supported over the remote endpoint, and the row shape (Task 8)
- [ ] Batch execution answered — API presence, round-trip cost, per-statement results, and per-statement errors (Task 9)
- [ ] A decision record is committed naming the chosen client, its **exact pinned version**, and a yes/no plus evidence for each of the six, including workarounds for anything unsupported (Tasks 10–11)
- [ ] `git diff main --stat` shows no file modified under `app/`, `chat_ui/`, or `scripts/` (Task 8 of the story; Task 12 here)
- [ ] Local libSQL dev-server workflow documented and reproducible — start, port, teardown (Tasks 1, 11)
- [ ] All tasks completed
- [ ] No production code written; no new dependency added to `requirements.txt` by this story
