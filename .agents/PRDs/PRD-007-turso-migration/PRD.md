---
id: PRD-007
slug: turso-migration
title: Turso / libSQL Migration
status: draft
base_branch: main
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-01
updated: 2026-09-01
---

## 1. Executive Summary

Harness IA stores its entire persistent state — the `audit_logs` compliance trail and the `users` identity store from PRD-005 — in a single local SQLite file, reached through Python's stdlib `sqlite3` from one module, `app/db/database.py`. That file lives in a Docker named volume (`harness_data`), which makes the audit trail an artifact of one container's filesystem: it survives restarts, but it is bound to one host, one disk, and one running instance. Two consequences block the roadmap. First, **persistence across deployments is a volume-management concern rather than a database guarantee** — there is no managed backup, no point-in-time recovery, and a volume lost or recreated takes the compliance record with it. Second, **the deployment cannot scale past one instance**: a SQLite file cannot be safely shared by concurrent writers across processes on different hosts, so `POST /query` and the Reflex chat UI are permanently pinned to a single container.

This PRD replaces the local SQLite file with **Turso (libSQL) as a remote database, accessed over the network**. The `.db` file is eliminated entirely — not shadowed by an embedded replica, not kept as a fallback path. `DATABASE_URL` stops naming a filesystem path and starts naming a libSQL endpoint; the `harness_data` volume is removed from `docker-compose.yml`; `harness_ai.db` is deleted from the repository root and gitignored.

The migration is unusually well-scoped for this codebase, and one fact governs the whole effort: **all database access is confined to one 356-line module**. `app/db/database.py` holds 22 call sites of `get_connection()`; outside it, `sqlite3` appears exactly twice, both as exception types (`app/services/duplicate_checker.py:32`, `scripts/manage_users.py:37`). There is no ORM — every statement is plain SQL with `?` placeholders, which is exactly the dialect libSQL speaks. No `SELECT` in the codebase needs rewriting, and the schema (`INTEGER PRIMARY KEY AUTOINCREMENT`, `TEXT`, `CREATE UNIQUE INDEX`, `ALTER TABLE ADD COLUMN`) is compatible as-is.

The real work is therefore not translating SQL. It is **paying for the fact that every database call is now a network round trip**. Today the module opens a fresh connection per operation — microseconds against a local file, a TCP/TLS handshake against a remote endpoint. The admin console's summary reads ten separate figures sequentially (`chat_ui/chat_ui/admin_state.py:229`, `_READS`), `GET /stats` reads nine (`app/routers/admin.py:71-84`), and `top_pii_entities()` pulls every PII-bearing row into memory to count entities in Python. Under remote-pure access those patterns degrade from invisible to user-visible. The MVP therefore includes: a **shared, reused client** replacing connection-per-operation; a **batched read path** for the summary fan-out; and an **aggregate-in-SQL rewrite** of `top_pii_entities()`. Multi-instance operation adds one more requirement the single-file design never needed — a **safe concurrent `init_db()`**, since N instances now race to run the same additive `ALTER TABLE` migration against one shared database at startup.

## 2. Mission

Make the audit trail a durable, managed database that any number of application instances can share, rather than a file that belongs to one container.

Core principles:

- **One seam, one module.** The migration changes `app/db/database.py` and nothing else that touches SQL. The 22 public functions keep their names, signatures, and return types, so `app/routers/`, `app/services/`, `chat_ui/`, and `scripts/` see an unchanged contract. Where a caller must change (the batched summary read), it is a deliberate, named exception, not a leak.
- **The file is gone, not hidden.** No local `.db`, no embedded replica, no silent fallback to a filesystem path when the network is unavailable. A configuration that would have opened a file is a startup error, not a degraded mode. A fallback that silently writes audit rows to a local file no one reads is worse than a failure.
- **Network cost is designed for, not discovered.** Every read path that issues more than one statement is either batched or justified in writing. "It was fast against a local file" stops being an argument.
- **The audit trail's integrity survives the move.** Existing rows are migrated, verified by count and by content, and the cutover is reversible until the verification passes. A compliance record that is truncated by its own migration has failed at its only job.
- **Concurrency becomes a real condition.** Multi-instance is the point of this work, so schema migration, credential uniqueness, and duplicate detection are all evaluated under concurrent access rather than assumed safe from single-process habit.
- **Tests stay hermetic and stay green.** 19 test files across 27 sites pin `DATABASE_URL` to a temporary `sqlite:///` path. They must keep running offline, per-test isolated, and without a Turso account — against a local libSQL server, not a file and not the production database.

## 3. Target Users

**Platform / DevOps Engineer** — Owns the deployment. Today they must treat the `harness_data` Docker volume as the system of record and cannot run a second instance behind a load balancer. Needs a database that outlives any container, a connection contract expressible as env vars, and a startup that fails loudly on misconfiguration rather than silently creating an empty database. Technical level: high; comfortable with Docker, TLS, and connection strings.

**Security / Compliance Admin** — Consumes the audit trail via `/audit`, `/stats`, and the admin console. Their requirement is unchanged by this PRD and constrains it: no audit row may be lost, altered, or made unreadable by the migration, and the PII, RBAC, duplicate, and pattern telemetry (PRD-003, PRD-005) must read back identically. Also gains managed backup and recovery, which the file never offered. Technical level: comfortable with REST APIs and env vars.

**End User (Employee)** — Uses the chat UI. Must not notice the migration except as improved availability. The added per-request latency (one duplicate-check read, one audit write) sits inside a request already dominated by the OpenRouter call, so it must stay imperceptible. Technical level: non-technical to technical.

**Integrating Developer / Maintainer** — Works inside `app/db/`. Needs the module's public contract to be stable, the error taxonomy to be explicit (the migration invalidates three `except sqlite3.*` clauses), and the test suite to remain runnable offline on a laptop with no Turso credentials. Technical level: high.

## 4. MVP Scope

### In Scope

- [ ] Replace stdlib `sqlite3` with a libSQL client in `app/db/database.py`; the module's 22 public functions keep their names, signatures, and return types
- [ ] `DATABASE_URL` accepts libSQL endpoints (`libsql://`, `https://`, `http://` for the local dev server); a `sqlite:///` value becomes a startup error with a message naming the replacement
- [ ] New `TURSO_AUTH_TOKEN` setting in `app/config.py`, required when the endpoint is remote, unused for the local dev server
- [ ] **Shared, reused client** replacing per-operation connection creation — one handshake per process, not one per query
- [ ] Row access by column name preserved: the module's `row["..."]` reads and both `_row_to_audit_log()` / `_row_to_user()` mappers keep working over the libSQL result shape
- [ ] Explicit commit semantics replacing reliance on `with sqlite3.Connection` — every `INSERT` / `UPDATE` / `ALTER` verified to durably commit
- [ ] `insert_audit_log()` keeps returning the new row id; `deactivate_user()` and `set_user_token_hash()` keep returning affected-row booleans
- [ ] Error taxonomy: a module-owned exception surface replacing the three `except sqlite3.*` clauses at `app/db/database.py:289`, `app/services/duplicate_checker.py:32`, and `scripts/manage_users.py:37`, with behavior preserved at each site
- [ ] **Concurrency-safe `init_db()`**: N instances starting simultaneously against one database must converge on the correct schema without a crash or a partially applied migration
- [ ] `_add_missing_columns()` schema introspection verified against the remote endpoint (`PRAGMA table_info` is executed during startup, so a failure here is a failure to boot)
- [ ] **Batched summary read**: the ten sequential reads in `chat_ui/chat_ui/admin_state.py` `_READS` and the nine in `GET /stats` collapse into a single round trip, preserving per-figure error attribution
- [ ] **`top_pii_entities()` aggregated in SQL** — it currently transfers every PII-bearing row to count entities client-side
- [ ] **Data migration**: a script that copies existing `audit_logs` and `users` rows from a `.db` file into Turso, with count and content verification and a documented rollback point
- [ ] Test infrastructure: all 19 test files run offline against a local libSQL server with per-test isolation, replacing the 27 `sqlite:///{tmp_path}` fixtures
- [ ] `docker-compose.yml`: remove the `harness_data` volume and the `DATABASE_URL: sqlite:////app/data/harness_ai.db` environment entry; add the Turso connection env vars
- [ ] Remove `harness_ai.db` from the repository root; gitignore `*.db`
- [ ] `requirements.txt` gains the libSQL client (the first dependency in `app/db/`'s history that is not stdlib)
- [ ] README updates: `DATABASE_URL` row in the env table (`README.md:214`), the persistence claim at `README.md:177`, and a multi-instance deployment note
- [ ] Startup guard: the application fails fast and loudly if the database is unreachable or the token is missing, rather than booting into a broken state

### Out of Scope

- [ ] Embedded replicas or any local-file read path — explicitly rejected; the file is being eliminated, not relocated
- [ ] An ORM or query builder — the module stays plain parameterized SQL
- [ ] Async database access — every caller (`app/routers/*.py`, `chat_ui/`, `scripts/`) is synchronous today and stays synchronous; see Section 6
- [ ] Schema redesign, new tables, new columns, or new indexes beyond what the current schema declares
- [ ] Any change to duplicate detection, pattern detection, PII redaction, or RBAC *behavior* — only their storage layer moves
- [ ] Multi-region or edge replica placement
- [ ] Actually running multiple instances in production — this PRD removes the *database* blocker; deployment topology (load balancer, Reflex websocket session affinity) is separate work
- [ ] Connection pooling beyond what the chosen client provides natively
- [ ] Retry, circuit-breaker, or offline-queue behavior for transient network failure — noted as a Future Consideration, deliberately excluded from MVP
- [ ] Migrating any state other than `audit_logs` and `users`

## 5. User Stories

**1.** As a **Platform Engineer**, I want the audit trail stored in Turso rather than a Docker volume, so that redeploying, recreating, or moving the container cannot destroy the compliance record.
> *Example:* `docker compose down -v` today deletes the entire audit history. After this PRD it deletes nothing — the volume no longer exists and the data lives in Turso.

**2.** As a **Platform Engineer**, I want to run more than one application instance against the same database, so that the harness can be scaled and load-balanced.
> *Example:* Two containers both accept `POST /query`. A duplicate prompt sent to instance A is detected by instance B within the detection window, because both read the same `audit_logs` table.

**3.** As a **Platform Engineer**, I want the app to fail immediately and legibly when the database is unreachable or `TURSO_AUTH_TOKEN` is missing, so that a misconfigured deployment never serves traffic while silently dropping audit rows.
> *Example:* Starting with an expired token exits with a message naming the setting, not a 500 on the first user query.

**4.** As a **Compliance Admin**, I want every existing audit row to be present and byte-identical after the migration, so that the historical record is not silently truncated by the move.
> *Example:* The migration script reports the source and destination row counts for both tables and refuses to declare success on any mismatch; PII entities, roles, and `denied_permission` values read back unchanged.

**5.** As a **Compliance Admin**, I want the admin console to load in roughly the time it does today, so that the audit register stays usable after the storage layer moves across a network.
> *Example:* The console's ten summary figures (`_READS`) arrive in one round trip. If the database is unreachable, each figure still reports its own failure using its existing `READ_LABEL_*` copy rather than blanking the page.

**6.** As an **End User**, I want the chat to feel as responsive as it does today, so that the storage change is invisible to me.
> *Example:* `run_query(...)` adds one duplicate-check read and one audit write per request — two round trips inside a request already waiting on OpenRouter.

**7.** As a **Maintainer**, I want the full test suite to run offline with no Turso account and no shared state between tests, so that development does not require network access or risk touching production data.
> *Example:* `pytest tests/` on a laptop in airplane mode passes, exactly as it does today with `tmp_path` SQLite files.

**8.** As a **Maintainer**, I want `app/db/database.py`'s public contract unchanged, so that the call sites across routers, services, chat UI, and the CLI need no edits.
> *Example:* `count_audit_logs(user_id=...)` still returns an `int`; `find_user_by_token_hash(...)` still returns `Optional[User]` and still folds a missing `users` table into "no match" (`app/db/database.py:289`), preserving the 401-not-500 login behavior PRD-005 specified.

## 6. Core Architecture & Patterns

### Current shape

```
app/routers/admin.py ─┐
app/routers/query.py  ├─→ app/db/database.py ─→ sqlite3 ─→ ./harness_ai.db  (Docker volume)
app/services/*.py     │      (22 × get_connection)
chat_ui/**/*.py       │
scripts/manage_users.py ┘
```

### Target shape

```
app/routers/admin.py ─┐
app/routers/query.py  ├─→ app/db/database.py ─→ libSQL client ══(network)══→ Turso
app/services/*.py     │   (one shared client;
chat_ui/**/*.py       │    same 22 public functions)
scripts/manage_users.py ┘

tests ─→ local libSQL dev server (no file, no network)
scripts/migrate_to_turso.py ─→ one-time .db → Turso copy
```

The seam is unchanged. `app/db/database.py` was already the only module that knows how data is stored; this PRD changes what is behind that boundary and leaves the boundary itself in place.

### Pattern 1 — Shared client, not connection-per-operation

Today every one of the 22 public functions calls `get_connection()`, which constructs a fresh `sqlite3.Connection`. Against a file this is nearly free. Against a remote endpoint each construction is a TCP + TLS handshake, so the cost model inverts: a single admin console load would pay ten handshakes. `get_connection()` is replaced by a process-wide client created once and reused, with the connection lifecycle owned by `app/db/database.py` alone. Because the function is already the single chokepoint, this is a change to one function body, not to 22 call sites.

### Pattern 2 — Synchronous throughout

Every consumer is synchronous: `app/routers/admin.py:30` and `:70` and `app/routers/query.py:16` are plain `def` endpoints (FastAPI runs those in a threadpool, so blocking I/O is already the expected shape), `run_query(...)` at `app/services/query_pipeline.py:45` is `def`, `chat_ui/chat_ui/admin_state.py` reads synchronously, and `scripts/manage_users.py` is a CLI. **The MVP uses the libSQL client's synchronous interface.** Adopting the async client would force `async` through all 22 database functions and every caller — a change an order of magnitude larger than the migration itself, for no benefit in a codebase whose endpoints are already threadpool-dispatched.

### Pattern 3 — The batched read is the one deliberate caller change

`_READS` at `chat_ui/chat_ui/admin_state.py:229` is a ten-entry table of `(field, label, callable, kwargs)` consumed by the loop at `:1018`; `GET /stats` at `app/routers/admin.py:71-84` performs the same fan-out with nine direct calls. Both must collapse to one round trip. The constraint is that `_READS` exists to give each figure **its own failure label** (`READ_LABEL_*`) so a partial failure names the read that broke, and `tests/test_admin_shell.py` asserts `len(_READS) == 10`. A naive batch destroys that attribution. The design must therefore batch the statements while keeping the per-figure result and error mapping intact. This is the only place where the migration is permitted to change code outside `app/db/`.

### Pattern 4 — Aggregate in the database, not in Python

`top_pii_entities()` currently issues `SELECT pii_entities FROM audit_logs WHERE pii_entities IS NOT NULL` and counts comma-separated entities in a Python dict. That transfers the entire PII-bearing history over the network on every admin console load and every `GET /stats`. It is rewritten to aggregate in SQL, returning at most `limit` rows.

### Pattern 5 — Concurrency-safe startup migration

`init_db()` runs `CREATE TABLE IF NOT EXISTS`, then `_add_missing_columns()` (a `PRAGMA table_info` read followed by conditional `ALTER TABLE ADD COLUMN`), then the users table and unique index. Under one process against one file this is trivially safe. Against a shared database with N instances booting together, the read-then-alter sequence is a race: two instances can both observe a column as missing and both attempt to add it. The MVP makes this convergent — the losing instance must treat "column already exists" as success, not as a startup crash.

### Pattern 6 — Errors owned by the module

Three sites catch stdlib SQLite exceptions and will stop matching:

| Site | Catches | Behavior that must survive |
|---|---|---|
| `app/db/database.py:289` | `sqlite3.OperationalError` | Missing `users` table → "no match" → **401, not 500** (PRD-005 §9) |
| `app/services/duplicate_checker.py:32` | `sqlite3.Error` | Storage failure degrades the duplicate check without failing the query |
| `scripts/manage_users.py:37` | `sqlite3.IntegrityError` | Duplicate `user_id` / `token_hash` reported as a usable CLI error |

`app/db/` exports its own error surface so callers never import a driver-specific exception type again. Each of the three behaviors is pinned by a test before the driver changes.

### Directory structure (delta only)

```
app/
  config.py                    # + TURSO_AUTH_TOKEN, DATABASE_URL semantics change
  db/
    database.py                # rewritten internals, identical public surface
    errors.py                  # NEW — module-owned exception surface
    models.py                  # unchanged (schema DDL is libSQL-compatible as-is)
  routers/admin.py             # /stats fan-out → batched read
chat_ui/chat_ui/admin_state.py # _READS fan-out → batched read
scripts/
  manage_users.py              # exception import only
  migrate_to_turso.py          # NEW — one-time data migration + verification
tests/
  conftest.py                  # NEW/extended — libSQL dev-server fixture
docker-compose.yml             # − harness_data volume, − sqlite DATABASE_URL
README.md                      # env table, persistence claim, multi-instance note
harness_ai.db                  # DELETED
```

## 7. Tools / Features

### 7.1 Connection layer (`app/db/database.py`)

Replaces `_db_path()` + `get_connection()`. Parses `DATABASE_URL` as a libSQL endpoint, attaches `TURSO_AUTH_TOKEN` when the endpoint is remote, constructs the client once per process, and reuses it. A `sqlite:///` URL raises at startup with a message naming the correct replacement rather than falling back to a file.

### 7.2 Error surface (`app/db/errors.py`)

A small set of exceptions raised by `app/db/`: an integrity violation (duplicate `user_id` / `token_hash`), a missing-relation condition, and a general storage error. Each of the three current catch sites is rewritten against these. No consumer imports the driver.

### 7.3 Batched summary read

One database function returning all ten summary figures in a single round trip, consumed by both `GET /stats` (`app/routers/admin.py:71`) and `_READS` (`chat_ui/chat_ui/admin_state.py:229`). The per-figure `READ_LABEL_*` error attribution and the `len(_READS) == 10` invariant are preserved.

### 7.4 `top_pii_entities()` rewrite

Same signature, same ordering semantics (descending frequency, capped at `limit`), aggregation moved into SQL. `chat_ui/chat_ui/admin_copy.py:317` documents that the visible cap comes from the read's own `limit` — that contract holds.

### 7.5 Migration script (`scripts/migrate_to_turso.py`)

One-time copy of `audit_logs` and `users` from a `.db` file into a Turso database. Requirements: idempotent or explicitly refusing to run against a non-empty destination; preserves `audit_logs.id` values (the audit trail is referenced by id via `GET /audit/{id}`); reports source and destination counts per table; verifies content, not only counts; exits non-zero on any mismatch. Documented rollback: the source `.db` file is untouched and remains authoritative until verification passes.

### 7.6 Test infrastructure

A pytest fixture that provisions a local libSQL server and hands each test an isolated, empty database, replacing the 27 `monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db_path}")` sites across 19 files. Two of those files launch subprocesses with `DATABASE_URL` in the environment (`tests/test_admin_shell.py:709`, `tests/test_chat_ui_startup_guard.py:65`) and need the endpoint passed the same way. Non-negotiable properties: runs offline, requires no Turso account, and cannot reach a production database.

### 7.7 Startup guard

`init_db()` is called at import time by `chat_ui/chat_ui` (noted at `tests/test_admin_shell.py:697`), which makes database reachability a boot-time condition. The guard turns an unreachable endpoint or a missing token into an immediate, legible failure.

## 8. Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| Language | Python 3.11 (Dockerfile) | unchanged |
| API | FastAPI + uvicorn | unchanged; endpoints stay `def` (threadpool) |
| UI | Reflex 0.9.6.post1 | unchanged |
| **Database** | **Turso (libSQL), remote** | replaces the local SQLite file entirely |
| **Driver** | **libSQL Python client, synchronous interface** | new dependency in `requirements.txt`; first non-stdlib dependency in `app/db/` |
| Local dev / CI database | local libSQL server | no `.db` file, no network, no account |
| Config | pydantic-settings | `DATABASE_URL` semantics change; `TURSO_AUTH_TOKEN` added |
| PII | presidio-analyzer, presidio-anonymizer, spacy | unchanged |
| Tests | pytest, pytest-asyncio | unchanged; fixtures rewritten |
| Packaging | Docker + Caddy, single port | `harness_data` volume removed |

**Driver selection is a Phase 1 deliverable, not an assumption.** The libSQL Python ecosystem offers more than one client, and they differ precisely where this codebase is sensitive: named-column row access, `with`-block commit semantics, `lastrowid`, `rowcount`, `PRAGMA` support, and batch execution. Phase 1 verifies these against a real endpoint before any production code is rewritten (Section 12).

Version pinning: the driver is pinned to an exact version in `requirements.txt`, consistent with `reflex==0.9.6.post1`.

## 9. Security & Configuration

### Authentication to the database

The database moves from a file protected by container filesystem permissions to a network endpoint protected by a bearer token. `TURSO_AUTH_TOKEN` joins `OPENROUTER_API_KEY` and `ADMIN_TOKEN` as a required production secret, supplied through the same `env_file` mechanism `docker-compose.yml` already uses. It is never logged, never echoed in error messages, and never committed. The connection is TLS for any remote endpoint; a plaintext `http://` endpoint is permitted only for the local development server.

### Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | *(none — no file fallback)* | libSQL endpoint. A `sqlite:///` value is a startup error. |
| `TURSO_AUTH_TOKEN` | Yes (remote) | `""` | Bearer token for the Turso database. Unused against the local dev server. |

All other settings in `app/config.py` are unchanged. Note that `DATABASE_URL` loses its current default of `sqlite:///harness_ai.db` — a default that silently creates a local file is exactly the failure mode this PRD removes.

The Dockerfile's build stage sets `DATABASE_URL=sqlite:///:memory:` as a build-time placeholder so that importing `chat_ui.chat_ui` during `reflex export` passes Pydantic validation. That placeholder must be updated, and the build must not require a live database.

### In scope (security)

- Database credential handled as a secret, on par with existing secrets
- TLS for all remote database traffic
- `harness_ai.db` removed from the repository and `*.db` gitignored — a database file containing real audit rows and `users` token hashes must never be committable
- Test infrastructure structurally incapable of reaching a production database
- The 401-not-500 credential-resolution behavior at `app/db/database.py:289` preserved verbatim; PRD-005 §9 treats it as a credential-enumeration control, not a convenience

### Out of scope (security)

- Rotating or managing Turso tokens beyond reading one from the environment
- Database-level row encryption or field-level encryption of `prompt_preview` / `response_preview`
- Network egress restrictions or IP allowlisting to the database
- Changes to `ADMIN_TOKEN`, per-user RBAC tokens, or any PRD-005 authorization behavior

## 10. API Specification

**No public API changes.** Every endpoint keeps its path, method, auth, request shape, and response schema:

| Endpoint | Auth | Change |
|---|---|---|
| `POST /query` | Bearer (per-user, PRD-005) | None. Adds two network round trips internally (duplicate check read, audit write). |
| `GET /audit` | Bearer + `audit:read:*` | None. Scoping behavior unchanged. |
| `GET /audit/{id}` | Bearer + `audit:read:*` | None. Requires `audit_logs.id` preservation through migration. |
| `GET /stats` | Bearer + `stats:read` | Response schema identical; internally one batched read instead of nine. |
| `GET /health` | None | Extended only if a database-reachability signal is added; response shape stays backward compatible. |

The one deliberate behavioral difference: when the database is unreachable, endpoints that previously could not fail on storage now can. Each failure mode is mapped to a defined status code and, where an existing degradation path exists (`app/services/duplicate_checker.py:32`), that path is preserved rather than replaced by a 500.

## 11. Success Criteria

### MVP definition

The application runs against a remote Turso database with no `.db` file anywhere in the repository, the image, or the compose stack; all existing audit rows have been migrated and verified; the full test suite passes offline; and two application instances can run concurrently against the same database without corruption or lost audit rows.

### Functional requirements

- [ ] `app/db/database.py`'s 22 public functions keep their names, signatures, and return types
- [ ] No module outside `app/db/` imports `sqlite3` or any driver module
- [ ] `grep -rn "sqlite" app/ chat_ui/ scripts/` returns no production code paths
- [ ] `harness_ai.db` is deleted from the repository; `*.db` is gitignored
- [ ] `docker-compose.yml` declares no `harness_data` volume and no `sqlite:///` `DATABASE_URL`
- [ ] A `sqlite:///` `DATABASE_URL` produces a startup error naming the correct replacement, never a file
- [ ] A missing or invalid `TURSO_AUTH_TOKEN` fails at startup, not on first request
- [ ] `init_db()` converges correctly when N instances start simultaneously against the same database
- [ ] `_add_missing_columns()` applies the five `AUDIT_LOGS_ADDED_COLUMNS` correctly against a remote endpoint and is a no-op on a current schema
- [ ] `insert_audit_log()` returns the new row id; `deactivate_user()` and `set_user_token_hash()` return `True` only when exactly one row changed
- [ ] `insert_user()` raises a module-owned integrity error on a duplicate `user_id` or `token_hash`, and `scripts/manage_users.py` reports both cases distinguishably
- [ ] `find_user_by_token_hash()` against a database with no `users` table returns `None` → **401, not 500**
- [ ] `duplicate_checker` still degrades gracefully on a storage failure instead of failing the query
- [ ] `GET /stats` and the admin console summary each issue **one** round trip for all ten figures
- [ ] Per-figure `READ_LABEL_*` error attribution survives batching; `len(_READS) == 10` still holds (`tests/test_admin_shell.py`)
- [ ] `top_pii_entities()` aggregates in SQL and transfers at most `limit` rows
- [ ] Migration script reports per-table source and destination counts, verifies content, preserves `audit_logs.id`, and exits non-zero on any mismatch
- [ ] All 19 affected test files pass offline with per-test isolation and no Turso account
- [ ] `README.md:177` (persistence claim) and `README.md:214` (env table) are corrected; multi-instance deployment is documented
- [ ] The Docker build succeeds without a reachable database

### Quality indicators

- Admin console load time with a warm client is within a small constant of today's, not a multiple of it
- Added `POST /query` latency is bounded by two round trips and is negligible against the OpenRouter call
- No new dependency in `app/db/` beyond the single pinned libSQL client
- Every behavior listed in Section 6, Pattern 6 is pinned by a test written **before** the driver swap

## 12. Implementation Phases

### Phase 1 — Driver verification and behavior pinning (no production code changes)

**Goal:** Establish which client is used and prove the six risky behaviors before rewriting anything.

**Deliverables:**
- A spike verifying, against a real libSQL endpoint: named-column row access, commit semantics without `with sqlite3.Connection`, `lastrowid` on insert, `rowcount` on update, `PRAGMA table_info`, and batch execution
- Driver decision recorded with evidence for each of the six
- Local libSQL dev-server workflow documented and reproducible
- Characterization tests pinning the three exception behaviors (Section 6, Pattern 6) **against current SQLite**, so the driver swap is measured against a green baseline

**Validation:** All six behaviors answered yes/no with evidence; new characterization tests pass on `main` unchanged.

### Phase 2 — Storage layer swap

**Goal:** `app/db/database.py` runs on libSQL with an unchanged public surface.

**Deliverables:**
- Connection layer: shared client, `DATABASE_URL` parsing, `TURSO_AUTH_TOKEN`, no file fallback
- `app/db/errors.py` and the three rewritten catch sites
- Row mapping, commit semantics, `lastrowid` / `rowcount` handling
- Concurrency-safe `init_db()`
- Test fixture rewrite across 19 files (27 sites), including the two subprocess-environment cases
- Startup guard

**Validation:** Full suite green against a local libSQL server; the Phase 1 characterization tests still pass; no `sqlite3` import outside tests.

### Phase 3 — Network-cost remediation

**Goal:** Remove the read patterns that only made sense against a local file.

**Deliverables:**
- Batched summary read serving both `GET /stats` and `_READS`, with per-figure error attribution preserved
- `top_pii_entities()` aggregated in SQL
- Measured round-trip counts for an admin console load and a `POST /query`

**Validation:** Admin console and `/stats` each issue one round trip for the summary; `tests/test_admin_shell.py`, `tests/test_stats_router.py`, `tests/test_admin_state.py`, and `tests/test_summary.py` pass with their assertions about rendered output unchanged.

### Phase 4 — Data migration and cutover

**Goal:** Move the existing audit trail, delete the file, and prove multi-instance operation.

**Deliverables:**
- `scripts/migrate_to_turso.py` with verification and a documented rollback point
- `docker-compose.yml` without the `harness_data` volume; Dockerfile build placeholder updated
- `harness_ai.db` deleted; `*.db` gitignored
- README corrections (`:177`, `:214`) and a multi-instance deployment note
- A two-instance smoke test against one database: concurrent writes, cross-instance duplicate detection, no lost audit rows

**Validation:** Migrated row counts and content match; two instances run concurrently without corruption; `docker compose down -v` destroys no data.

## 13. Future Considerations

- **Resilience**: retry with backoff, a circuit breaker, and a bounded local buffer so that a transient database outage degrades rather than drops audit rows. Deliberately out of MVP scope, but the most valuable follow-up — remote-pure access makes the database a hard dependency of every request.
- **Actual multi-instance deployment**: load balancer, health checks, and Reflex websocket session affinity. This PRD removes the database blocker only.
- **Read replicas / edge placement** if read latency from the deployment region proves material.
- **Indexes for the audit trail**: `audit_logs` has no index on `prompt_hash` or `timestamp` today. The duplicate check (`find_duplicate_timestamp`) filters on both and currently scans. Cheap against a small local file, less so at volume over a network — worth measuring once real data is in Turso.
- **Retention and archival**: a growing audit table now has a real cost profile and a real query cost. Retention policy is a compliance decision, not a technical one, and belongs in its own PRD.
- **External analytics access** to the audit trail (dashboards, exports) now that the data is reachable outside the application process.
- **Database-level backup verification** as a scheduled, tested procedure rather than an assumed platform feature.

## 14. Risks & Mitigations

**Risk 1 — Silent write loss from changed commit semantics.** *(Highest severity.)* Every write in the module relies on `with sqlite3.Connection` committing on exit. If the libSQL client's context manager does not carry that semantic, `INSERT`s return successfully and the data is never persisted — and because `insert_audit_log()` is fire-and-forget from the pipeline's perspective, the failure is invisible until someone reads an empty audit trail.
> **Mitigation:** Phase 1 verifies commit semantics explicitly before any rewrite. Phase 2 makes commits explicit rather than inherited from a context manager. Every write function gets a test that reads the row back through a **fresh** client.

**Risk 2 — Audit data lost or altered during migration.** The audit trail is the product; a truncated or reordered migration is an unrecoverable compliance failure. `GET /audit/{id}` means `audit_logs.id` values must be preserved, not regenerated.
> **Mitigation:** The source `.db` is never mutated and remains authoritative until verification passes. The script verifies counts and content per table, preserves ids explicitly, refuses a non-empty destination, and exits non-zero on any mismatch. The file is deleted only after verification, in a separate step from the copy.

**Risk 3 — Concurrent `init_db()` corrupts or fails the schema migration.** The read-then-`ALTER` sequence in `_add_missing_columns()` is a race the single-file design never faced. N instances booting together can each observe a column as missing; the losers crash at startup or, worse, leave the schema partially migrated. Because `init_db()` runs at import time, this presents as a container that will not boot.
> **Mitigation:** Phase 2 treats "column already exists" as success rather than an error, so concurrent runs converge. Validated by a test that starts multiple `init_db()` calls concurrently against one empty database, and again against a schema missing a subset of `AUDIT_LOGS_ADDED_COLUMNS`.

**Risk 4 — Test-suite migration is larger than the production change.** 19 files and 27 sites depend on `sqlite:///{tmp_path}`, and two spawn subprocesses with `DATABASE_URL` in the environment. If the replacement fixture is slow, flaky, network-dependent, or leaks state between tests, it undermines the safety net the whole migration depends on — and a suite that needs a live account is a permanent tax on every future change.
> **Mitigation:** The dev-server fixture is a Phase 1 deliverable, proven before production code changes. Requirements are explicit and testable: offline, per-test isolated, no account. Suite wall-clock time is measured before and after; a material regression is a design failure to be fixed, not accepted.

**Risk 5 — The database becomes a hard dependency of every request, with no fallback.** Remote-pure access is the chosen topology, and MVP scope excludes retry and buffering. A transient network failure that a local file could never produce now fails user requests, and Section 10 notes that endpoints which previously could not fail on storage now can.
> **Mitigation:** Accepted deliberately for the MVP and stated plainly rather than papered over. Every failure mode is mapped to a defined status code; the existing degradation path in `duplicate_checker` is preserved; the startup guard prevents booting into a broken state. Resilience is the first Future Consideration and should be scheduled immediately after this epic, not indefinitely.

**Risk 6 — Batching breaks the admin console's partial-failure UX.** `_READS` exists so each of the ten figures reports its own failure with its own `READ_LABEL_*` copy; `tests/test_admin_shell.py` pins `len(_READS) == 10`, and the copy in `chat_ui/chat_ui/admin_copy.py` is written against per-read semantics. Collapsing ten reads into one round trip can turn ten legible partial failures into one blank page.
> **Mitigation:** Per-figure result and error mapping is an explicit acceptance criterion of Phase 3, not an implementation detail. The existing admin tests are treated as the specification and must pass with their assertions unchanged.

## 15. Appendix

### Related documents

- `.agents/PRDs/PRD-001-harness-ia/PRD.md` — original SQLite audit schema and the "no new dependencies, stdlib only, portable" principle this PRD knowingly departs from
- `.agents/PRDs/PRD-003-pii-redaction/PRD.md` — `pii_detected_input`, `pii_detected_output`, `pii_entities` columns; `top_pii_entities()` semantics
- `.agents/PRDs/PRD-005-rbac/PRD.md` — `users` table, additive migration mechanism, and the 401-not-500 credential-resolution requirement (§9)
- `.agents/PRDs/PRD-006-admin-console/PRD.md` — `_READS`, `READ_LABEL_*` partial-failure copy, and the admin register the batched read must not regress

### Key code references

| Concern | Location |
|---|---|
| All database access | `app/db/database.py` (356 lines, 22 × `get_connection()`) |
| Schema DDL and additive columns | `app/db/models.py` |
| Driver exception coupling | `app/db/database.py:289`, `app/services/duplicate_checker.py:32`, `scripts/manage_users.py:37` |
| `/stats` fan-out (9 reads) | `app/routers/admin.py:71-84` |
| Admin console fan-out (10 reads) | `chat_ui/chat_ui/admin_state.py:229` (`_READS`), consumed at `:1018` |
| Client-side PII aggregation | `app/db/database.py`, `top_pii_entities()` |
| Test `DATABASE_URL` fixtures | 19 files, 27 sites; subprocess cases at `tests/test_admin_shell.py:709`, `tests/test_chat_ui_startup_guard.py:65` |
| Deployment persistence | `docker-compose.yml` (`harness_data`), `Dockerfile` (build placeholder), `README.md:177`, `README.md:214` |

### Dependencies

- A Turso account and database provisioned before Phase 4 cutover (Phases 1–3 need only the local libSQL dev server)
- A locally runnable libSQL server available to developers and CI

### Skills referenced

`.agents/skills/` was scanned as required. It contains one skill, `frontend-design`, whose description scopes it to visual design of new or reshaped UI (aesthetic direction, typography, layout). This PRD changes no rendered output — the admin console's copy, figures, and error labels are explicitly constrained to remain unchanged (Risk 6, Phase 3 validation). No skill applies to this product domain, so no skill rules are cited in Sections 6, 8, 9, or 11.

**Skills referenced:** none applicable
