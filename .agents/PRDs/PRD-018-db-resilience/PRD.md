---
id: PRD-018
slug: db-resilience
title: Database Resilience — Retry, Circuit Breaker and Buffered Audit Writes
status: draft
base_branch: main
epic_branch: epic/PRD-018-db-resilience
created: 2026-11-16
updated: 2026-11-16
---

## 1. Executive Summary

Since PRD-007 the database is a network endpoint, and [docs/deployment.md:46-50](../../../docs/deployment.md) says plainly what that costs: *"a transient database outage fails requests instead of degrading them."* Every request makes three to five round trips to Turso/libSQL (identity read, usage admit, duplicate lookup, usage charge, audit write), plus the `action_decisions` batch on a `/v1` tool response and the transcript writes in the chat UI. Each statement that fails raises `StorageError` and nothing retries it. PRD-014 measured what "transient" looks like here: single TCP connections stall for 7–21 s, ending in `STREAM_EXPIRED` (the server's ~10 s stream window passed) or `tcp connect error ... (os error 10060)` ([spike](../../spikes/PRD-014-docker-network-stalls.md)). The production defence, the idle probe in `_shared_client()` ([app/db/database.py:83-132](../../../app/db/database.py)), only proves a client *before* it is lent. A stream that dies during a statement reaches `_translated()` ([app/db/database.py:592-628](../../../app/db/database.py)), which drops the client and re-raises **without retrying, on purpose**: by then the caller's block has already run inside `_session()`'s transaction, and a replay from there "could replay half of it".

This PRD keeps that rule and adds three things around it. **(1) Retry at the unit of work.** Each storage function becomes a callable that can be run again from the start on a fresh client. Whether it *is* run again depends on two facts: what kind of failure happened (the request never left, the server refused the stream, or the outcome is unknown), and whether the statement can be replayed safely. Reads and idempotent writes are retried. A non-idempotent write (`admit_usage`, `charge_usage`, `append_chat_message`) is retried only when the failure proves it did not run. Audit writes become idempotent through a client-minted `write_id` with a unique index. **(2) A process-local circuit breaker.** After repeated infrastructure failures it stops sending traffic to a database that is down and fails fast with `StorageUnavailableError`, a subclass of `StorageError`. Every fail-closed arm already catches that type, so **an open breaker refuses requests. It never waves one through.** The ingresses return `503` with `Retry-After` instead of an unexplained `500`. **(3) A durable local journal for audit writes.** An audit row (and its `action_decisions`) that cannot land after its retries is appended and fsynced to an on-disk journal, then drained into the database once it answers again. The gate checks are never buffered.

**MVP goal:** with fault injection on the `db` suite, a single `STREAM_EXPIRED` or `tcp connect error` on any statement of a request is absorbed and the request succeeds. A non-idempotent statement whose outcome is unknown is never replayed. With the database down, every ingress refuses with `503` (on `/v1`, an OpenAI error object `storage_unavailable`), nothing reaches the upstream, and a request that was already in flight when the outage began still returns its answer, its audit row drained later, exactly once. With the database healthy, every pipeline response and every pinned test is unchanged.

## 2. Mission

Ride out a storage blip without weakening a single control, and never lose an audit row to one.

Core principles:

- **Replay only what is provably safe.** A retry is a second execution. It is allowed when the first one provably did not happen, or when a second one changes nothing. "Probably fine" is not a retry rule (D2, D3).
- **Retry the whole unit, never the tail of one.** The retry boundary is the start of a `_session()` block, on a fresh client. `_translated()` keeps its no-retry contract unchanged (D1).
- **A breaker refuses, it never admits.** Open means `StorageUnavailableError`, a `StorageError`, so the duplicate check and the usage gate fail closed through the arms they already have (D7).
- **Evidence before release.** A response is released only when its audit row (and, for tools, its decisions) is committed to the database *or* fsynced to the journal. Memory is not evidence (D9, D13).
- **Gates read live data or refuse.** Nothing is buffered on the way in: identity, admission and duplicate lookups are never answered from a cache, the journal or a guess (D15).
- **Measure the driver, don't assume it.** Every classification rule rests on driver text captured live. The PRD's open questions about `libsql==0.1.11` are answered by a spike before any retry code lands (STORY-001).

## 3. Target Users

**Platform Operator.** Runs one or more instances against Turso. Today a 2-second network blip shows up as a burst of `500`s, and a sustained outage is indistinguishable from an application bug. They need blips to go unnoticed, outages to read as `503 storage unavailable` with a `Retry-After`, and a status page that says "breaker open since 14:02:11, 3 audit entries journaled" without opening a shell.

**Security/Compliance Admin.** The audit trail is PRD-001's founding property. They need a guarantee that no answered request goes unrecorded because of a storage hiccup, that the duplicate window and the usage limits keep holding during one, and a written account of the one residual gap (a duplicate resent to a *different* instance while a row is still in this instance's journal, Section 9.2 T4).

**Integrating Developer (`/v1` client).** OpenAI SDKs retry `5xx` on their own. They need a storage outage to be a standard, retryable OpenAI error object with a `Retry-After` the SDK can honour, not a plain-text `Internal Server Error` (today's response when the identity read fails, Section 6.7).

**Chat user.** Today a storage failure during sign-in or at the start of a send escapes the handler. At `chat_ui/chat_ui/state.py:967` `resolve(token)` runs after `pending` is set (`:962`) and before the `try`/`finally` that clears it (`:995`), so the composer stays locked. They need a clear bubble ("the harness's database is unavailable, nothing was sent") and a composer that unlocks.

## 4. MVP Scope

### In Scope

**Characterization (spike)**
- [ ] Capture the driver's verbatim error text, and *which call raised it* (`connect`, `execute`, `fetchone`, `commit`), for: connection refused, connect timeout, `docker pause` mid-statement (read timeout), container restart mid-transaction (`invalid baton`), idle expiry (`STREAM_EXPIRED`)
- [ ] Answer, against the dev server: does `libsql==0.1.11` open an implicit transaction for DML on a remote endpoint (is an `INSERT` durable before `commit()`)? Does `commit()` issue a request when no transaction is open? Does a write from a fresh client, after a stream was abandoned mid-transaction, wait, fail with `TRANSACTION_TIMEOUT`, or succeed?

**Classification and retry (`app/db/database.py`, `app/db/errors.py`)**
- [ ] `_classify(exc, phase) -> FailureClass`, a pure function over the message text and the failing call (D2)
- [ ] `_unit_of_work(name, kind, fn)`: runs `fn(conn)` in a fresh `_session()`, retries per D3/D5, reports to the breaker
- [ ] Every operational function in `database.py` declares its kind (`READ`, `IDEMPOTENT`, `NON_IDEMPOTENT`) and runs through `_unit_of_work` (Section 6.3)
- [ ] `StorageUnavailableError(StorageError)`: retry budget exhausted on an infrastructure class, or breaker open. Carries `retry_after_seconds`

**Idempotent audit writes (D4)**
- [ ] `audit_logs.write_id TEXT` and `action_decisions.write_id TEXT`, each with a `UNIQUE` index, on the `_add_missing_columns()` path. `action_decisions` becomes the fourth table on it
- [ ] `insert_audit_log` and `insert_action_decisions` use `INSERT ... ON CONFLICT(write_id) DO NOTHING` and read the id back by `write_id`
- [ ] `log_query` mints the `write_id` (`uuid4`) and stamps the `timestamp` once, before the first attempt

**Circuit breaker (D6, D7)**
- [ ] `app/services/circuit_breaker.py: CircuitBreaker`, a small reusable class: thresholds passed in, injected clock, pluggable half-open probe, `force_open(seconds)`, `status() -> BreakerStatus` (Section 6.5)
- [ ] Storage holds exactly one instance per process, `closed → open → half_open → closed`, counting only infrastructure-class operation failures
- [ ] Half-open probe: one `SELECT 1` on a fresh client, under `_client_lock`, never through `get_connection()` (the `_proved()` rule, [app/db/database.py:145-151](../../../app/db/database.py))
- [ ] `check_database_reachable()` and `init_db()` bypass retry and breaker (boot stays loud, D17)

**Ingress mapping (D8)**
- [ ] `require_identity`: `StorageUnavailableError` → `HTTPException(503, Retry-After)`, never 401
- [ ] `POST /query`: `DuplicateCheckError` / `UsageLimitError` / `ChatSessionError` caused by `StorageUnavailableError` → `503` with fixed text. Non-transient causes keep today's `500`
- [ ] `/v1`: new fault code `storage_unavailable` (503, `api_error`, retryable) in `_FAULTS`; `503` in `_HTTP_ERRORS`; `Retry-After` on both
- [ ] Chat UI: `resolve()` moved inside the `try`/`finally` in `_do_send`; sign-in maps a storage failure to a notice; a `storage_unavailable` detail string with no driver text

**Audit journal (D9–D14)**
- [ ] `app/db/audit_journal.py`: append-and-fsync JSON Lines, per-process file under `AUDIT_BUFFER_DIR`, exclusive OS lock, per-line checksum, torn-tail recovery, adoption of unlocked journals at boot
- [ ] Bounds: `AUDIT_BUFFER_MAX_BYTES`. Admission headroom check at pipeline entry. Fail closed when a row can be neither written nor journaled
- [ ] Drainer thread: FIFO, one transaction per entry, idempotent by `write_id`, resolves `action_decisions.audit_id` from the audit row's `write_id`
- [ ] Duplicate overlay: `check_duplicate` also consults this process's journaled rows under the same predicate as `find_duplicate_timestamp`
- [ ] A response whose success row is only journaled carries `audit_id: null` and `audit_ref: <write_id>` (D14)

**Observability (D16)**
- [ ] Structured logs for every breaker transition, exhausted retry, journal append, drain and torn tail
- [ ] `GET /storage/status` (`stats:read`): breaker state, counters, journal depth
- [ ] Admin console: a Storage panel reading the same snapshot

**Deployment and docs**
- [ ] `docker-compose.yml`: a named volume for `AUDIT_BUFFER_DIR`, which reverses the "No volume" comment for the journal only
- [ ] `docs/deployment.md` "hard dependency" section rewritten; `docs/roadmap.md` first two resilience boxes ticked; `.env.example`; `docs/api.md` 503 rows

### Out of Scope

- [ ] Provider (OpenRouter) resilience and fallback: **PRD-022**
- [ ] Websocket session affinity for the chat UI behind a load balancer: **PRD-019**
- [ ] Buffering any gate read or `admit_usage`, or serving one from a cache (D15)
- [ ] Buffering `charge_usage` or transcript writes (D15, Open decision O5)
- [ ] Interrupting a stalled driver call: `libsql==0.1.11` exposes no timeout this repo has verified, and abandoning a call on the shared client is unsafe (Risk 2)
- [ ] Booting without a reachable database (D17)
- [ ] A shared, cross-instance breaker or journal
- [ ] Encrypting the journal at rest (Section 13)
- [ ] Prometheus or any new metrics dependency (D16)

## 5. User Stories

1. **As a platform operator, I want a single dead stream mid-request absorbed, so that a blip is not a 500.**
   *Example:* the duplicate lookup's `execute` gets `Hrana: api error: status=400 Bad Request, body={"message":"The stream has expired due to inactivity","code":"STREAM_EXPIRED"}`. `_translated()` drops the client as today. `_unit_of_work` sees `DEAD_STREAM` on a `READ`, waits ~50 ms and re-runs the lookup on a fresh client, and the request is answered. One `INFO` line records `retry op=find_duplicate_timestamp class=dead_stream attempt=2`.

2. **As a security admin, I want an open breaker to refuse rather than skip the duplicate check, so that an outage is not a window without controls.**
   *Example:* the database has been down for 30 s and the breaker is open. A `POST /query` with the break-glass token (resolved without the database) reaches step 4. `find_duplicate_timestamp` raises `StorageUnavailableError` without a network call, `check_duplicate` turns it into `DuplicateCheckError`, and the router returns `503 {"detail": "Storage unavailable: the request was not sent to the model."}` with `Retry-After: 7`. The upstream is never called.

3. **As a platform operator, I want `admit_usage` never replayed after an ambiguous failure, so that a user is not charged two attempts for one.**
   *Example:* `admit_usage`'s `execute` raises a read timeout after the request was sent (`OUTCOME_UNKNOWN`). The increment may have landed, so the statement is not retried. The gate fails closed with `503`, and the client's own retry is the next counted attempt. Had it been `tcp connect error` (`NOT_SENT`), the admit would have been retried.

4. **As a compliance admin, I want an answer that was already paid for to keep its audit row through an outage, so that the trail has no hole.**
   *Example:* a `/v1` request is admitted and passes the duplicate check at 14:02:09. The upstream takes 4 s, and the database goes down at 14:02:11. At 14:02:13 the success row fails three attempts. It is journaled (`write_id=7f3c…`, fsynced), and the client gets its completion with `harness.audit_id: null`, `harness.audit_ref: "7f3c…"`. At 14:03:40 the breaker closes, the drainer inserts the row with its original `timestamp` of 14:02:13, and `GET /storage/status` shows `journal.entries: 0`.

5. **As a security admin, I want a tool response released only when its decisions are durably recorded, so that PRD-017's "no release without the decision rows" still holds.**
   *Example:* the success row lands but `insert_action_decisions` exhausts its retries. The decisions (with `audit_id` known) are journaled and fsynced, then the calls are released. If the journal append also fails (disk full), the response is refused exactly as PRD-017 D8 does today: `mark_audit_log_failed`, `ActionAuditError`, `500 internal_error`, nothing released.

6. **As a security admin, I want a resend of a just-answered prompt still held while its row sits in the journal, so that buffering does not open a duplicate bypass on the same instance.**
   *Example:* the success row for key `k` is journaled. The database recovers, and the same user resends before the drain reaches that entry. `find_duplicate_timestamp` finds nothing, the journal overlay finds `k` at 14:02:13, and the response is `QueryBlockedDuplicateResponse(first_query_at="2026-11-16T14:02:13Z")`.

7. **As an `/v1` integrator, I want an outage to look like an OpenAI 503, so that my SDK backs off and retries on its own.**
   *Example:* `HTTP/1.1 503`, `Retry-After: 7`, body `{"error":{"message":"Storage is unavailable; the request was not sent to the model.","type":"api_error","param":null,"code":"storage_unavailable"}}`, no `x-should-retry` header (retryable, the PRD-015 D7 rule).

8. **As a platform operator, I want to see breaker state and journal depth, so that I know whether I am looking at a blip, an outage or a backlog.**
   *Example:* `GET /storage/status` with `ADMIN_TOKEN` during an outage returns `{"breaker":{"state":"open","since":"2026-11-16T14:02:12Z","consecutive_failures":5,"last_failure_class":"not_sent","retry_after_seconds":7},"journal":{"entries":3,"bytes":8410,"max_bytes":67108864,"oldest_timestamp":"2026-11-16T14:02:13Z","draining":false},"counters":{...}}`.

## 6. Core Architecture & Patterns

### 6.1 Where the pieces sit

```
ingress (auth dependency / ChatState / pipeline)
  └─ app/db/database.py public function           e.g. find_duplicate_timestamp(user_id, key, since)
       └─ _unit_of_work(name, kind, fn)            NEW: the retry boundary
            ├─ breaker.before()                    open → StorageUnavailableError, no network
            ├─ attempt i: with _session() as conn: return fn(conn)
            │     └─ _translated()                 UNCHANGED: classifies, drops a dead client, re-raises, never retries
            ├─ on StorageError: cls = _classify(exc, phase); retryable(cls, kind)?
            │     yes and budget left → backoff, attempt i+1 (fresh client: _translated() dropped it)
            │     no → breaker.record(cls); raise (StorageUnavailableError if cls is infrastructure)
            └─ success → breaker.record_success()

audit write path (log_query / action_audit.record)
  └─ write_id minted, timestamp stamped once
       ├─ _unit_of_work(IDEMPOTENT)                retried on every infrastructure class
       └─ exhausted or breaker open → audit_journal.append(entry); fsync → return JournaledRef
                                                   append failed → AuditUnavailableError (fail closed)

drainer thread (started in both lifespans)
  └─ breaker closed and journal non-empty → oldest entry → one transaction → checkpoint
```

### 6.2 Failure taxonomy (D2)

The driver raises a bare `ValueError` prefixed `Hrana:` for everything ([app/db/database.py:388-393](../../../app/db/database.py)), so classification reads the message text, as `_is_dead_stream()` already does ([:421-433](../../../app/db/database.py)). It also reads **which call raised**, because the same text means different things on `execute` and on `commit`.

| Class | Evidence | Did the statement run? | Examples (verbatim where already captured) |
|---|---|---|---|
| `NOT_SENT` | connect-phase failure | **No.** No request reached the server | `http error: error sending request for url (http://127.0.0.1:1/v2/pipeline): ... Connection refused` ([:514-515](../../../app/db/database.py)); `tcp connect error ... (os error 10060)` / `(os error 110)` (PRD-014 spike); DNS failure |
| `DEAD_STREAM` | `_DEAD_STREAM` markers ([:418](../../../app/db/database.py)) **on `execute`/`fetch*`** | **No.** The server refused the baton, so this request was not executed, and any uncommitted earlier work on that stream is gone with it | `STREAM_EXPIRED`; `Received an invalid baton` |
| `OUTCOME_UNKNOWN` | the request may have been sent and its response lost: read timeout, connection reset, a dead-stream marker **on `commit`**, any `Hrana:` text the classifier does not recognise | **Unknown** | captured by STORY-001 (`docker pause` mid-statement) |
| `STATEMENT` | `IntegrityError`, `MissingRelationError`, duplicate column, SQL error | Ran and was refused, deterministically | `UNIQUE constraint failed: users.token_hash`; `no such table: users` |

Rules:
- **Unrecognised text is `OUTCOME_UNKNOWN`, never `NOT_SENT`.** That way a classifier miss costs a retry that did not happen, never a replay that did.
- **`STATEMENT` failures are never retried and never count toward the breaker.** `_translated()` already classifies them first ([:609-612](../../../app/db/database.py)), and STORY-024 AC 3 keeps a working client cached on a constraint violation. A breaker that opened on `UNIQUE constraint failed` would turn a correctly refused write into an outage.
- **A dead-stream marker on `commit` is `OUTCOME_UNKNOWN`** until STORY-001 proves that `commit()` on an expired stream means "not committed". If the driver autocommits DML (open question 1), the `INSERT` may already have landed.
- The `phase` comes from a thin wrapper inside `_Connection`, which records the last driver call before re-raising. Same object, same message, so `_translated()` and `_is_dead_stream()` behave exactly as now (the PRD-014 `_RecordedClient` rule).

### 6.3 Statement kinds and the per-request classification (D3)

| Kind | Retried on | Why |
|---|---|---|
| `READ` | `NOT_SENT`, `DEAD_STREAM`, `OUTCOME_UNKNOWN` | Running a `SELECT` twice changes nothing |
| `IDEMPOTENT` | `NOT_SENT`, `DEAD_STREAM`, `OUTCOME_UNKNOWN` | A second run leaves the same state, by construction (a key, or a value-setting `UPDATE`) |
| `NON_IDEMPOTENT` | `NOT_SENT`, `DEAD_STREAM` on `execute` only | A second run would apply the effect twice, so it is retried only when the first provably did not run |

Every statement a request can issue, in pipeline order:

| # | Statement | Call site | Kind | Retry | If it still fails |
|---|---|---|---|---|---|
| 1 | Identity read `find_user_by_token_hash` ([database.py:1564-1587](../../../app/db/database.py)) | `identity.resolve` ([identity.py:83](../../../app/services/identity.py)) from `require_identity` ([middleware/auth.py:17](../../../app/middleware/auth.py)), `ChatState.login` (`state.py:311`) and `_do_send` (`:967`) | `READ` | all infra | **503**, never 401. Break-glass `ADMIN_TOKEN` resolves with no read ([identity.py:78-81](../../../app/services/identity.py)) |
| 2 | Session ownership `get_chat_session` via `chat_sessions.owns` | `/query` with `session_id` ([routers/query.py:115](../../../app/routers/query.py)) | `READ` | all infra | 503 (today 500 via `ChatSessionError`) |
| 3 | History `list_chat_messages` | `chat_history.assemble` in `_do_send` | `READ` | all infra | today's degraded arm: notice, send unchanged |
| 4 | **Usage admit** `admit_usage` ([:1740-1758](../../../app/db/database.py)): `INSERT ... ON CONFLICT DO UPDATE SET requests = requests + 1 ... RETURNING` | `usage_limits.admit` ([usage_limits.py:159-162](../../../app/services/usage_limits.py)) | `NON_IDEMPOTENT` | `NOT_SENT`, `DEAD_STREAM`@execute | **fail closed**, 503. A replay after `OUTCOME_UNKNOWN` could count the attempt twice (O3) |
| 5 | **Duplicate lookup** `find_duplicate_timestamp` ([:857-899](../../../app/db/database.py)) | `check_duplicate` ([duplicate_checker.py:33](../../../app/services/duplicate_checker.py)) | `READ` | all infra | **fail closed**, 503 |
| 6 | Refusal and flag rows `insert_audit_log` ([:802-854](../../../app/db/database.py)) | `_deny` ([query_pipeline.py:288](../../../app/services/query_pipeline.py)), steps 2c, 3, 4, 5, 6, 7, 8 error arms; `/query` foreign-session refusal ([query.py:118](../../../app/routers/query.py)) | `IDEMPOTENT` (after D4) | all infra | **journal** (D9) |
| 7 | **Usage charge** `charge_usage` ([:1761-1782](../../../app/db/database.py)): `UPDATE ... SET input_tokens = input_tokens + ?` | step 7b ([query_pipeline.py:804-811](../../../app/services/query_pipeline.py)) | `NON_IDEMPOTENT` | `NOT_SENT`, `DEAD_STREAM`@execute | **fail open**, as today (`usage_limits.py:214-227`). A replay could double-charge. The audit row's token columns stay the record |
| 8 | Success row `insert_audit_log` | step 8 ([query_pipeline.py:893-918](../../../app/services/query_pipeline.py)) | `IDEMPOTENT` | all infra | **journal**, response released with `audit_ref` (D14) |
| 9 | `insert_action_decisions` ([:2253-2302](../../../app/db/database.py)), one transaction of N `INSERT`s | `action_audit.record` ([query_pipeline.py:925](../../../app/services/query_pipeline.py)) | `IDEMPOTENT` (after D4) | all infra | **journal**, with the audit row or alone (D13) |
| 10 | `mark_audit_log_failed` ([:902-917](../../../app/db/database.py)): `UPDATE ... SET success = 0, error_message = ?` | PRD-017 D8 arm ([query_pipeline.py:937](../../../app/services/query_pipeline.py)) | `IDEMPOTENT` (sets fixed values) | all infra | best effort, as today |
| 11 | `create_chat_session` ([:1865-1895](../../../app/db/database.py)): `INSERT` with a Python-minted `uuid4` primary key | `_do_send` lazy create | `IDEMPOTENT` (key) | all infra; on a retry, `IntegrityError(chat_sessions.session_id)` means the first attempt landed and counts as success | today's arm: the turn is sent unattached |
| 12 | `append_chat_message` ([:2077-2177](../../../app/db/database.py)): `AUTOINCREMENT`, no natural key | `_append_and_persist` (`state.py:867`) | `NON_IDEMPOTENT` | `NOT_SENT`, `DEAD_STREAM`@execute | today's `TRANSCRIPT_NOT_SAVED_NOTICE`. A replay could show the bubble twice on reload |
| 13 | `touch_chat_session` ([:1980-1993](../../../app/db/database.py)): `SET updated_at = now` | `_append_and_persist` | `IDEMPOTENT` | all infra | today's `SESSION_ORDER_STALE_NOTICE` |
| 14 | `get_chat_session` re-read after touch | `_append_and_persist` | `READ` | all infra | same notice |

Admin, CLI and summary reads (`summary_snapshot`, `usage_snapshot`, `list_*`, `count_*`) are `READ`. The `users` writes in `scripts/manage_users.py` keep their `IntegrityError` contract. `insert_user` is `NON_IDEMPOTENT`: a replay that hit `UNIQUE constraint failed: users.user_id` after `OUTCOME_UNKNOWN` would misreport a created user as a duplicate. The update writes (`deactivate_user`, `set_user_token_hash`, `set_user_limits`, `rename_chat_session`) are `IDEMPOTENT`. `delete_chat_session` is `IDEMPOTENT` (deleting twice deletes once).

**Why the unit is the whole block.** `insert_action_decisions` is several statements in one transaction ([:2256-2262](../../../app/db/database.py)). A `DEAD_STREAM` on row *k* means the server dropped the stream, and rows 1..k−1 went with it, uncommitted. Replaying statement *k* alone would commit a batch missing its head. Replaying the block from row 1 on a fresh client is correct, and with `write_id` it is correct even if the first attempt did commit.

### 6.4 Idempotent audit writes (D4)

```sql
-- AUDIT_LOGS_ADDED_COLUMNS gains:  "write_id": "TEXT"
CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_logs_write_id ON audit_logs(write_id);
-- ACTION_DECISIONS_ADDED_COLUMNS (new mapping): "write_id": "TEXT"   -- "<batch uuid>:<index>"
CREATE UNIQUE INDEX IF NOT EXISTS idx_action_decisions_write_id ON action_decisions(write_id);

INSERT INTO audit_logs (..., write_id) VALUES (..., ?) ON CONFLICT(write_id) DO NOTHING;
SELECT id FROM audit_logs WHERE write_id = ?;          -- same transaction; the id whether this attempt or an earlier one inserted it
```

- Nullable, no default, no backfill: every existing row reads `NULL`, and SQLite's `UNIQUE` admits any number of `NULL`s. Pre-PRD rows are untouched (the PRD-013 STORY-002 precedent).
- The index sits on the line after `_add_missing_columns(conn, "audit_logs", ...)`, for the reason `CREATE_AUDIT_LOGS_DEDUP_INDEX` does ([database.py:673-679](../../../app/db/database.py)). `action_decisions` gets an added-columns pass after `CREATE_ACTION_DECISIONS_TABLE`, for the reason the `chat_messages` pass gives ([:681-692](../../../app/db/database.py)).
- `log_query` ([audit_logger.py:73-107](../../../app/services/audit_logger.py)) already stamps `timestamp` once per call. It now mints `write_id` there too, so every attempt, the journal entry and the drain all carry the same pair. **A late row keeps the time the event happened, not the time it landed.**
- `ON CONFLICT ... DO NOTHING` with a `RETURNING` clause returns no row on conflict, so the id is read back with a `SELECT` rather than `RETURNING`. `RETURNING` itself is verified on this driver ([:1698-1712](../../../app/db/database.py)); `DO NOTHING` is not, and STORY-002 verifies it.

### 6.5 The circuit breaker (D6, D7)

```
closed ──(5 consecutive operations failed on an infrastructure class)──▶ open
open ──(10 s elapsed)──▶ half_open ──(probe SELECT 1 on a fresh client succeeds)──▶ closed
                              └──(probe fails)──▶ open (another 10 s)
```

- **Process-local.** One breaker per process, matching the one client per process ([database.py:90-97](../../../app/db/database.py)). Instances do not share state (sharing it would need the database). In a Reflex deployment the FastAPI app is mounted into the same process, so `/query`, `/v1` and the chat UI share one breaker.
- **Counts operations, not attempts.** An operation that exhausted its retries is one failure. A `STATEMENT` failure, and a `NON_IDEMPOTENT` operation refused retry on `OUTCOME_UNKNOWN`, also leave the count unchanged: the first says nothing about reachability, and the second is counted once, as the failure it is.
- **Open is fail fast, not fail open.** `_unit_of_work` raises `StorageUnavailableError(retry_after_seconds=...)` before touching `_shared_client()`. It is a `StorageError`, so `check_duplicate` ([duplicate_checker.py:34-35](../../../app/services/duplicate_checker.py)) and `admit` ([usage_limits.py:161-162](../../../app/services/usage_limits.py)) turn it into their fail-closed errors with no code change. `find_user_by_token_hash`'s `MissingRelationError` arm ([database.py:1583](../../../app/db/database.py)) does not match it, so an outage can never read as a bad credential (the PRD-007 STORY-004 rule).
- **Half-open admits one probe, not one request.** The probe is the breaker's own `SELECT 1`, issued under `_client_lock` on a new client, as `_proved()` does. While it runs, other callers still get `StorageUnavailableError`, so a recovering database meets one statement, not a herd.
- **Constants, not settings** (`_BREAKER_FAILURE_THRESHOLD = 5`, `_BREAKER_OPEN_SECONDS = 10.0`), on the `_IDLE_PROBE_AFTER_SECONDS` precedent ([:78-80](../../../app/db/database.py)): *"a deployment knob whose wrong value silently restores the defect is not a knob worth having."* (O6) They are the storage instance's arguments, not the class's defaults.

**The primitive is a class; storage is one instance of it.** The state machine is written once, in `app/services/circuit_breaker.py`, so PRD-022 can hold one per upstream provider without a second implementation:

```python
@dataclass(frozen=True)
class BreakerStatus:
    state: Literal["closed", "open", "half_open"]
    since: str                          # UTC _TIMESTAMP_FORMAT, last transition
    consecutive_failures: int
    last_failure_class: Optional[str]   # storage: a D2 class name; PRD-022: its fault kind
    retry_after_seconds: Optional[int]  # None while closed; >= 1 otherwise

class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int, open_seconds: float,
                 clock: Callable[[], float] = time.monotonic,
                 probe: Optional[Callable[[], bool]] = None) -> None: ...
    def before(self) -> None              # raises BreakerOpen(retry_after_seconds) while open
    def record_success(self) -> None      # closes from half_open; resets the count
    def record_failure(self, failure_class: str) -> None
    def force_open(self, seconds: float) -> None   # open now for `seconds`, whatever the count
    def status(self) -> BreakerStatus
```

- **Probe is pluggable.** With a `probe` callable, half-open runs it once (holding the breaker's own lock so only one runs) and closes or reopens on its result, while every other caller still gets `BreakerOpen`. That is storage's mode: its probe is `SELECT 1` on a fresh client under `_client_lock`, as described above. With `probe=None`, half-open admits exactly one live caller as the probe, and the others get `BreakerOpen` until that caller records success or failure. That is PRD-022's mode. Both modes share the rest of the state machine.
- **`force_open(seconds)`** is unused by storage. PRD-022 needs it for a provider that answers `401` (its D12). It exists in the class so the two never fork.
- **Injected clock.** The state machine takes `clock` (monotonic by default), so the breaker tests advance time without sleeping. The `since` timestamp is wall-clock UTC and is only ever displayed. `BreakerStatus` contains no lock, client or callable, so it can be serialized as is.
- **Storage wiring.** `database.py` builds one module-level `_storage_breaker = CircuitBreaker("storage", _BREAKER_FAILURE_THRESHOLD, _BREAKER_OPEN_SECONDS, probe=_probe_fresh_client)`. `_unit_of_work` calls `before()` / `record_success()` / `record_failure(cls)`, and `database` translates `BreakerOpen` into `StorageUnavailableError(retry_after_seconds=...)`. `storage_status().breaker` is `_storage_breaker.status()`. Storage behaviour, numbers and tests are exactly as specified in this section. The class extraction adds no behaviour of its own.

### 6.6 Retry budget (D5)

`_RETRY_MAX_ATTEMPTS = 3`. Backoff before attempt 2 is uniform(0, 50 ms), before attempt 3 uniform(0, 200 ms) (full jitter). `_RETRY_START_DEADLINE_SECONDS = 2.0`: no new attempt *starts* more than 2 s after the first one started. **A deadline cannot shorten an attempt already running.** A stalled call returns when the driver gives up (21 s for the Windows connect timeout in PRD-014's evidence), and the shared client serializes its callers ([:90-97](../../../app/db/database.py)), so one stall delays every concurrent statement in the process. Retry does not fix stalls. It fixes what a stall leaves behind (Risk 2).

Why so small: the observed failures are a dead client on a working server, and `_translated()` has already dropped that client, so attempt 2 on a fresh client succeeds or fails within one round trip. A budget large enough to wait out an outage would hold pipeline workers (`PIPELINE_MAX_WORKERS = 32`, [config.py:260](../../../app/config.py)) hostage. The breaker covers outages.

### 6.7 What each ingress returns (D8)

| Situation | `POST /query` | Chat UI | `/v1/chat/completions` |
|---|---|---|---|
| Identity read unavailable | `503 {"detail":"Storage unavailable"}`, `Retry-After` (today: Starlette's plain-text 500, since `StorageError` is not an `HTTPException`) | sign-in: `login_error` notice. Send: `internal_error` bubble with fixed detail, composer unlocked (today: unhandled, `pending` stuck) | `503`, `storage_unavailable` via `_HTTP_ERRORS[503]` (today: plain-text 500, not an OpenAI object) |
| Admit or duplicate lookup unavailable | `503 {"detail":"Storage unavailable: the request was not sent to the model."}`, `Retry-After` (today `500` with driver text in `detail`, [query.py:31-37](../../../app/routers/query.py)) | `internal_error` bubble, fixed detail (today `detail=str(exc)`, driver text) | `503`, `storage_unavailable`, retryable, `Retry-After` (today `500 internal_error`, [v1.py:208-209](../../../app/routers/v1.py)) |
| Same, non-transient cause (`MissingRelationError`, e.g. the dropped table in `test_duplicate_check_storage_failure_returns_500`) | **unchanged `500`** | unchanged | unchanged `500 internal_error` |
| Success row journaled | `200`, `audit_id: null`, `audit_ref` | `audit_id` NULL on the transcript row | `200`, `harness.audit_id: null`, `harness.audit_ref`; `X-Harness-Audit-Ref` instead of `X-Harness-Audit-Id`; `id: "chatcmpl-harness-ref-<write_id>"` |
| Row neither written nor journaled (`AuditUnavailableError`) | `503`, nothing released | `internal_error` bubble | `503 storage_unavailable` (tools: PRD-017's `500 internal_error`, unchanged) |
| Journal above admission headroom (D10) | `503`, before step 2, no row | `internal_error` bubble | `503 storage_unavailable` |
| Post-commit (streamed) fault | — | — | SSE `error` event `storage_unavailable`, as `_sse_events` does for any fault ([v1.py:254-281](../../../app/routers/v1.py)) |

`Retry-After` is the integer seconds until the breaker's next half-open (minimum 1), or `1` when the breaker is closed and only this operation's budget ran out. 503 bodies never carry driver text. The driver text goes to the log through `_redacted()` ([database.py:491-506](../../../app/db/database.py)). Non-transient 500s keep today's `detail`, so existing assertions stand.

The streamed commit rule (PRD-015 Section 6.4) is unaffected. Every read that can fail closed runs before step 7, so a storage refusal always keeps its real status. Only the step 8 writes run after commit, and those journal instead of failing.

### 6.8 The audit journal (D9–D12)

**What it actually absorbs.** During a hard outage the identity read fails for every user token, and the duplicate check fails for every request that gets past it. So the only rows a hard outage writes are (a) the step 8 rows of requests already past step 4 when it began, and (b) rows written before step 4 by break-glass requests: `_deny`, step 2c, step 3. The journal is a seam for the in-flight tail and for blips longer than the retry budget, not a store-and-forward queue for traffic. That is why it can be small, and why filling it is a real anomaly worth failing closed on.

**Format.** `AUDIT_BUFFER_DIR/audit-journal-<host>-<pid>-<boot uuid>.jsonl`. One line per entry:

```json
{"v":1,"write_id":"7f3c…","appended_at":"2026-11-16T14:02:13Z",
 "audit":{"timestamp":"2026-11-16T14:02:13Z","user_id":"alice","dedup_key":"…","success":true, "...": "every AuditLog field"},
 "audit_id":null,
 "decisions":[{"write_id":"7f3c…:0","tool_call_id":"call_1","decision":"deny", "...": "every ActionDecisionRow field but audit_id"}],
 "sha256":"<of the line without this field>"}
```

`audit` is `null` when only the decisions are journaled (`audit_id` then known). A drained entry is never rewritten in place. The drainer records a checkpoint (byte offset) in a sidecar file, and compacts the journal when it is fully drained.

**Durability.** `append` writes the line, `flush()` and `os.fsync()`, and returns only after both. The caller releases the response only after `append` returns (D13). At boot, a line whose checksum fails is a torn tail from a crash mid-append. That write was never acknowledged, so no response was released on it. It is logged at `ERROR` and discarded.

**Ownership and multi-instance.** Each process holds an exclusive OS lock on its own file (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows). At boot, the drainer *adopts* every journal in the directory whose lock it can take, which covers a restart (new pid) and a crashed sibling sharing the volume. A file locked by a live process is left to that process. Instances that do not share a volume never see each other's journals, and each drains its own.

**Bounds (D10).** `AUDIT_BUFFER_MAX_BYTES` (default 64 MiB). An append that would exceed it fails, so the write is neither committed nor journaled. That is `AuditUnavailableError`, and the request **fails closed**: nothing is released without a record (O1, Section 9.2 T5). To keep that from ever hitting a request that has already paid for an upstream call, the pipeline checks **admission headroom** at entry, before step 2: if `journal.bytes > MAX_BYTES − PIPELINE_MAX_WORKERS × 64 KiB`, the request is refused with 503 before anything runs (and writes no row, since there is no room for one). Every worker in flight therefore has room for its rows.

**Drain (D11).** A daemon thread started in `app/main.py`'s lifespan and in `chat_ui/chat_ui/chat_ui.py`'s lifespan task (the two places `pipeline_executor.shutdown` is registered, [pipeline_executor.py:13-19](../../../app/services/pipeline_executor.py)), never at import, so a non-`db` test never meets it (PRD-014 D2). While the breaker is closed and the journal is non-empty, it takes the oldest entry and runs one `_unit_of_work(IDEMPOTENT)` transaction: insert the audit row (`ON CONFLICT DO NOTHING`), select its id by `write_id`, insert the decisions with that id (`ON CONFLICT DO NOTHING`). Then it advances the checkpoint. A crash between commit and checkpoint replays the entry, and `write_id` makes the replay a no-op. A drain failure feeds the breaker like any other operation. New writes go straight to the database once it answers. They do not queue behind the backlog, because the backlog is what keeps rows invisible to the duplicate lookup on other instances. **Consequence, stated:** a drained row's `id` is later than rows written after it. `/audit` orders by `timestamp` ([database.py:996-1007](../../../app/db/database.py)), and nothing orders `audit_logs` by `id`.

**Duplicate overlay (D12).** The journal keeps an in-memory index of its pending audit rows. `check_duplicate` ([duplicate_checker.py:29-39](../../../app/services/duplicate_checker.py)) consults it **after** the database lookup succeeds and **only if** that found nothing, applying the exact predicate of `find_duplicate_timestamp` ([database.py:885-898](../../../app/db/database.py)): same `user_id` and `dedup_key`, `timestamp >= cutoff`, `success`, not `was_duplicate_blocked`, `denied_permission IS NULL`, `pattern_action` not `flag`, `limit_exceeded IS NULL`. The overlay never stands in for the database. A failed lookup still fails closed. A row is removed from the index once its drain commits. A `db` test pins the parity between the overlay predicate and the SQL.

### 6.9 Directory structure (files touched)

```
app/
├── config.py                      # AUDIT_BUFFER_DIR, AUDIT_BUFFER_MAX_BYTES (+ validators)
├── db/
│   ├── errors.py                  # StorageUnavailableError, AuditUnavailableError
│   ├── models.py                  # write_id columns, two unique indexes, ACTION_DECISIONS_ADDED_COLUMNS
│   ├── database.py                # _classify, _unit_of_work, breaker, phase tracking; every op declares its kind
│   └── audit_journal.py           # NEW: append/fsync, lock, adopt, checkpoint, overlay index, drainer
├── middleware/auth.py             # StorageUnavailableError → 503
├── routers/query.py               # 503 arms
├── routers/v1.py                  # storage_unavailable fault, _HTTP_ERRORS[503], Retry-After, audit_ref header
├── routers/admin.py               # GET /storage/status
├── services/circuit_breaker.py    # NEW: CircuitBreaker, BreakerStatus, BreakerOpen (reused by PRD-022)
├── services/audit_logger.py       # write_id, journal fallback, returns AuditRef
├── services/duplicate_checker.py  # overlay after the DB lookup
├── services/query_pipeline.py     # headroom check at entry; step 8 + record() under D13
├── services/v1_translate.py       # STORAGE_UNAVAILABLE in _FAULTS
├── models/schemas.py, v1_schemas.py  # audit_id Optional, audit_ref
└── main.py                        # drainer start/stop
chat_ui/chat_ui/state.py, copy.py, admin_state.py, chat_ui.py   # resolve() inside try; copy; Storage panel; drainer
docker-compose.yml, .env.example, docs/deployment.md, docs/roadmap.md, docs/api.md, docs/features.md
tests/test_db_resilience_*.py      # NEW (Section 12)
```

### 6.10 Patterns followed

- **One seam for the driver's failure shape.** Classification lives beside `_translated()` in `database.py`. No consumer learns a driver string (PRD-007 Section 7.2).
- **Subclass, don't widen.** `StorageUnavailableError(StorageError)` reaches every existing `except StorageError` arm. Narrow arms (`MissingRelationError`) stay narrow.
- **Module constants for behaviour whose wrong value restores a defect** (PRD-008 STORY-024). Settings only for deployment facts (a directory, a disk budget).
- **Docstrings carry the why and the measurement**, house style.
- **Characterize before changing.** The driver questions are answered by STORY-001 before any classifier rule is written.

## 7. Tools/Features

### F1 — Driver characterization spike
Section 4's capture list and the three open questions, against `harness-libsql-dev` from inside `harness-test-net` (the PRD-014 D5 recipe, so port-forwarding stalls do not muddy the result). Output: `.agents/spikes/PRD-018-driver-failure-surface.md`, a table of (fault, call that raised, verbatim text, landed?). STORY-002 turns it into classifier fixtures.

### F2 — Classifier and unit of work
`_classify(exc, phase)` (pure, unit-tested from F1's strings) and `_unit_of_work(name, kind, fn)`. All public operational functions in `database.py` move their `with _session() as conn:` body into a local function passed to it, with their signatures unchanged.

### F3 — `write_id` migration and idempotent inserts
Section 6.4. `insert_audit_log(entry)` reads `entry.write_id`. `AuditLog` and `ActionDecisionRow` gain a defaulted `write_id: Optional[str] = None`, so every positional constructor keeps working.

### F4 — Circuit breaker
Section 6.5: the reusable `CircuitBreaker` class with an injected clock and a pluggable probe, and the single storage instance wired into `_unit_of_work`.

### F5 — Ingress mapping
Section 6.7, plus the chat UI `pending` fix.

### F6 — Audit journal and drainer
Section 6.8.

### F7 — Release under a journaled record
`log_query` returns `AuditRef(audit_id: Optional[int], write_id: str)`. Step 8 uses it. `record()` gets the ref, and journals decisions keyed to the audit `write_id` when `audit_id` is `None`.

### F8 — Status endpoint and admin panel
Section 10. The admin console's panel reads `storage_status()` in-process, like the other panels, so it needs no network call.

### F9 — Docs and deployment
`docs/deployment.md`: the "hard dependency" section becomes "What a database outage does": the classification table, the 503s, the journal and its volume, and the residual gap. Compose volume `harness-audit-buffer:/var/lib/harness/audit-buffer`.

## 8. Technology Stack

| Component | Version | Role here |
|---|---|---|
| Python | 3.11 | `os.fsync`, `fcntl` / `msvcrt` locking, `threading` (drainer), `uuid` (already imported in `database.py`) |
| `libsql` | 0.1.11 (pinned, `requirements.txt:13`) | unchanged. Behaviour characterized by F1, never patched |
| libSQL server | `ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb27…` (dev), Turso (prod) | unchanged |
| FastAPI / Starlette | unpinned, as today | `Retry-After` header on `HTTPException` / `JSONResponse` |
| Reflex | 0.9.6.post1 | chat UI and admin console changes |
| pytest | 9.1.x | `db` marker (PRD-014), fault-injecting client proxy |

**No new dependencies.** No retry or breaker library (`tenacity`, `pybreaker`): the logic that matters is classification, which no library knows, and the breaker is about forty lines with a clock. No metrics library (D16).

## 9. Security & Configuration

### 9.1 Authentication & authorization
Unchanged. `GET /storage/status` requires `stats:read` ([authz.py:14](../../../app/services/authz.py)). During an outage, user tokens cannot be resolved, so only `ADMIN_TOKEN` (break-glass, resolved with no read) reaches the endpoint. That is break-glass's purpose. A 503 from the identity read is never a 401: a real outage must not read as a bad credential (PRD-007 STORY-004).

### 9.2 Threat reasoning

| # | Threat | Treatment |
|---|---|---|
| T1 | **The breaker becomes a bypass.** An open breaker skips the duplicate check or the usage gate "to stay available" | Open raises `StorageUnavailableError`, a `StorageError`, into the existing fail-closed arms (D7). A test asserts the upstream stub is never called while the breaker is open, on all three ingresses |
| T2 | **Half a transaction replayed** | The retry boundary is the start of the block, on a fresh client. `_translated()` never retries (D1). Multi-statement blocks are idempotent by `write_id` |
| T3 | **Counters inflated by replay.** `admit_usage` counts an attempt twice, `charge_usage` charges twice | Both `NON_IDEMPOTENT`: retried only on `NOT_SENT` / `DEAD_STREAM`@execute (D3). Unrecognised text is `OUTCOME_UNKNOWN` |
| T4 | **Duplicate bypass through the journal.** A journaled row is invisible to `find_duplicate_timestamp` | Same instance: the overlay (D12). **Residual:** a resend that lands on a *different* instance before this one drains is not held. Its window is the drain lag, bounded by the outage. A per-user rate limit still applies, and the resend reaches the model once more at most per instance. Accepted and documented |
| T5 | **Unrecorded release** | Release requires commit or fsync (D13). Journal full or failing → `AuditUnavailableError` → refused. Headroom (D10) keeps in-flight requests clear of this |
| T6 | **Journal discloses audit content.** `prompt_preview` is the raw final turn, pre-redaction ([query_pipeline.py:346](../../../app/services/query_pipeline.py), [audit_logger.py:78](../../../app/services/audit_logger.py)), now on local disk | Directory created `0700`, files `0600` (POSIX). Compacted to zero bytes once drained. Contents never logged (only `write_id`, `user_id`, counts). The compose volume is named and not bind-mounted. Encryption at rest is Section 13 |
| T7 | **Journal tampering.** Someone with write access to the volume plants rows | Out of scope: such a person already has the host. The per-line `sha256` detects corruption, not forgery. Stated |
| T8 | **Journal-fill denial of service** | During an outage only break-glass requests reach the pipeline (Section 6.8), so a user token cannot fill it. Full → fail closed, which during an outage changes nothing |
| T9 | **Driver text reaches clients.** Today `detail=str(exc)` carries `Hrana: ...` to `/query` and the chat bubble | The new 503 bodies and bubble use fixed text. Driver text is logged through `_redacted()` |
| T10 | **Retry storm on a recovering database** | Full jitter, three attempts, one half-open probe per process |
| T11 | **Outage hides a revocation.** A revoked token keeps working because identity is "cached during the outage" | No identity cache: the read fails closed (D15) |

### 9.3 Configuration

| Variable | Default | Validation | Purpose |
|---|---|---|---|
| `AUDIT_BUFFER_DIR` | `./var/audit-buffer` (compose: `/var/lib/harness/audit-buffer`, a named volume) | created at boot if missing. Not writable → startup error naming the setting | Journal location |
| `AUDIT_BUFFER_MAX_BYTES` | `67108864` (64 MiB) | ≥ `PIPELINE_MAX_WORKERS × 65536 × 2` | Journal capacity (D10) |

Constants, deliberately not settings: `_RETRY_MAX_ATTEMPTS = 3`, `_RETRY_START_DEADLINE_SECONDS = 2.0`, `_BREAKER_FAILURE_THRESHOLD = 5`, `_BREAKER_OPEN_SECONDS = 10.0`, `_JOURNAL_ENTRY_RESERVE_BYTES = 65536`.

### 9.4 Out of scope (security)
Encrypting the journal; signing journal entries; cross-instance duplicate visibility of journaled rows; provider failover (PRD-022).

## 10. API Specification

**New fault on `/v1`** (`v1_translate._FAULTS`):

| `code` | status | `type` | retryable | headers |
|---|---|---|---|---|
| `storage_unavailable` | 503 | `api_error` | yes (no `x-should-retry`) | `Retry-After: <s>` |

**`POST /query` 503:**
```http
HTTP/1.1 503 Service Unavailable
Retry-After: 7
{"detail": "Storage unavailable: the request was not sent to the model."}
```

**Journaled success (`/query`):** `{"status":"success","response":"…","audit_id":null,"audit_ref":"7f3c2a…","model_used":"…",…}`. `audit_ref` is present on every success, and equals the row's `write_id`. `audit_id` stays an integer whenever the row committed, which is every healthy request, so a client that reads only `audit_id` sees no change outside an outage.

**`GET /storage/status`** (`stats:read`):
```json
{"instance": "web-1:4120",
 "breaker": {"state": "closed|open|half_open", "since": "2026-11-16T14:02:12Z",
             "consecutive_failures": 0, "last_failure_class": "dead_stream", "retry_after_seconds": null},
 "journal": {"entries": 0, "bytes": 0, "max_bytes": 67108864, "headroom_bytes": 2097152,
             "oldest_timestamp": null, "draining": false, "adopted_files": 0},
 "counters": {"retries": {"find_duplicate_timestamp:dead_stream": 3},
              "exhausted": {"admit_usage:outcome_unknown": 1},
              "breaker_opens": 1, "journal_appended": 4, "journal_drained": 4, "torn_tail_discarded": 0}}
```
Counters reset on restart: they are process-local and in memory, not a metrics backend. The endpoint makes no database call. `/health` is unchanged (`{"status":"ok"}`, no storage), so a load balancer does not take every instance out of rotation during a database outage, where they would still be answering 503s with `Retry-After` correctly.

**Internal API:**
```python
class StorageUnavailableError(StorageError):  retry_after_seconds: int
class AuditUnavailableError(StorageError): ...
database._unit_of_work(name: str, kind: Kind, fn: Callable[[_Connection], T]) -> T
database.storage_status() -> StorageStatus          # .breaker: BreakerStatus, .journal, .counters
circuit_breaker.CircuitBreaker(name, failure_threshold, open_seconds, clock=time.monotonic, probe=None)
  .before() / .record_success() / .record_failure(cls) / .force_open(seconds) / .status() -> BreakerStatus
audit_logger.log_query(...) -> AuditRef            # was -> int
action_audit.record(decisions, identity, audit_ref: AuditRef, session_id=None)
audit_journal.append(entry) -> None                 # returns after fsync, raises AuditUnavailableError
audit_journal.pending_duplicate(user_id, dedup_key, since) -> Optional[str]
```

## 11. Success Criteria

### MVP definition
- [ ] A single `DEAD_STREAM` or `NOT_SENT` fault injected on any one of statements 1–14 (Section 6.3) of a request is absorbed: the response equals the fault-free response, and exactly one row per expected row lands
- [ ] An `OUTCOME_UNKNOWN` fault injected *after* `admit_usage` / `charge_usage` / `append_chat_message` executed is never replayed: `usage_daily.requests` and the token columns move by exactly one call's worth
- [ ] Breaker open: every ingress returns its Section 6.7 response, the upstream stub records zero calls, and no non-audit row is written
- [ ] In-flight request across an outage: the response is released, the row is journaled, and after recovery exactly one row with the original `timestamp` and `write_id` exists (`SELECT COUNT(*) ... WHERE write_id = ?` is 1), including when the process is killed between drain commit and checkpoint
- [ ] With the database healthy, every pipeline response body is byte-identical to `main`, and the full suite passes with no pinned assertion changed except those a story names

### Functional requirements
- [ ] `_classify` has a table test over every verbatim string in F1's report and in `database.py`'s comments. Unknown `Hrana:` text → `OUTCOME_UNKNOWN`. A non-`Hrana:` `ValueError` propagates untouched
- [ ] `STATEMENT` failures are never retried, never trip the breaker, and leave the client cached (STORY-024 AC 3 still passes)
- [ ] `_translated()`'s docstring and behaviour are unchanged. A test asserts it still re-raises without a second `execute`
- [ ] `init_db()` against an unreachable endpoint fails as fast as today (`test_init_db_fails_fast_against_an_unreachable_endpoint` unchanged)
- [ ] `test_duplicate_check_storage_failure_returns_500` passes unchanged (`MissingRelationError` is non-transient)
- [ ] Identity read unavailable → 503 on all three ingresses, never 401. On `/v1`, an OpenAI error object
- [ ] Chat UI: a storage failure in `resolve()` during a send leaves `pending == False`
- [ ] Journal: append returns only after fsync (asserted with a patched `os.fsync`). A torn last line is discarded with an `ERROR`. A second process cannot lock a held file. An orphaned file is adopted and drained
- [ ] Journal full → `AuditUnavailableError` → nothing released. Headroom refusal happens before step 2 and calls no upstream
- [ ] Overlay predicate parity with `find_duplicate_timestamp`: a `db` test writes each excluded row shape to both and asserts both answer the same
- [ ] Tools: decisions journaled with the audit row resolve to the drained row's `id`; journal unavailable → PRD-017 D8 path unchanged
- [ ] `GET /storage/status` makes zero driver calls (asserted with PRD-014's guard in a non-`db` test)

### Quality indicators
- [ ] Healthy-path overhead: p50 added latency per request under 0.5 ms (no extra round trip; measured with `scripts/measure_usage_latency.py`'s method)
- [ ] Three in-network `-m db` runs (`scripts/test-db-in-network.sh`) green
- [ ] Every exhausted retry and breaker transition produces exactly one log line, with no SQL, no parameters and redacted driver text

## 12. Implementation Phases

### Phase 1 — Measure the driver (Story 1)
**Goal:** replace the three open questions and the `OUTCOME_UNKNOWN` examples with captured facts.
**Deliverables:** F1 spike report. Classifier fixtures.
**Validation:** each Section 6.2 row cites a captured string and the call that raised it. If commit-on-expired-stream proves "not committed", the `DEAD_STREAM`@commit rule may move to `NOT_SENT` by an orchestrator decision recorded here.

### Phase 2 — Retry safely (Stories 2–4)
**Goal:** blips absorbed, nothing replayed unsafely.
**Deliverables:** `_classify`, `_unit_of_work`, phase tracking, kinds on every function, `write_id` migration and idempotent inserts.
**Validation:** fault-injection suite (below) for statements 1–14. Full suite green.

### Phase 3 — Fail fast and say so (Stories 5–7)
**Goal:** outages are 503s with `Retry-After` on every ingress.
**Deliverables:** breaker, `StorageUnavailableError`, ingress mapping, chat UI fixes, `/v1` fault code.
**Validation:** breaker-open tests per ingress, upstream stub uncalled.

### Phase 4 — Never lose a row (Stories 8–11)
**Goal:** audit rows survive an outage and land exactly once.
**Deliverables:** journal, drainer, overlay, headroom, `AuditRef` and response fields, PRD-017 path.
**Validation:** kill-and-restart drain test. Overlay parity. Journal-full test.

### Phase 5 — Visible and documented (Stories 12–13)
**Deliverables:** `/storage/status`, admin panel, logs audit, docs, compose volume, roadmap.

**Testing approach (all phases), consistent with PRD-014:**
- **Pure, non-`db`:** `_classify` table, breaker state machine with an injected clock, retry loop over fake `fn`s, journal on `tmp_path` (append, fsync, torn tail, lock, adopt, capacity), Section 6.7 mappings with the pipeline stubbed. PRD-014's guard proves these issue no driver calls.
- **`db` with fault injection:** a `_FaultyClient` proxy installed by monkeypatching `libsql.connect`, built on PRD-014's `_RecordedClient` forwarding pattern. A script says "on the Nth `execute` whose SQL starts with `INSERT INTO usage_daily`, raise `ValueError(<captured text>)` **before** forwarding (`NOT_SENT` / `DEAD_STREAM`) or **after** forwarding (`OUTCOME_UNKNOWN`: the effect landed, the response was lost)". The "after" mode is the only honest way to test that a landed effect is not replayed.
- **`db` against real faults (opt-in, `--run-chaos`):** `http://127.0.0.1:1` for connection refused, and `docker restart harness-libsql-dev` under a live process for `invalid baton` (the STORY-024 capture method). Excluded from the default run because they take seconds and need Docker control.
- The drainer is started only by the lifespans, so no non-`db` test meets a background thread that touches storage.

## 13. Future Considerations

- **Driver-level timeouts** if a future `libsql` exposes them, so a stalled call can be cut short and retried (Risk 2).
- **Idempotent transcripts:** a `write_id` on `chat_messages` would move `append_chat_message` to `IDEMPOTENT`.
- **A charge ledger** (`usage_charges` keyed by audit `write_id`) so `charge_usage` becomes idempotent and journal-able, and `usage_daily` reconcilable from it.
- **Journal encryption at rest**, with a key from the environment.
- **Cross-instance duplicate visibility** for journaled rows (closing T4's residual), if the drain lag ever proves material.
- **Readiness endpoint** distinct from `/health`, for orchestrators that should stop routing to an instance whose breaker is open, once PRD-019's load-balancer topology exists.
- **Provider fallback**: PRD-022, which can reuse this PRD's breaker for the upstream.

## 14. Risks & Mitigations

| # | Risk | Likelihood / Impact | Mitigation |
|---|---|---|---|
| 1 | **Misclassification replays a landed write** | Low / High | Unknown text is `OUTCOME_UNKNOWN`. `DEAD_STREAM` counts only on `execute`/`fetch*`. Every rule comes from F1's captured text. The "after forwarding" fault mode tests each non-idempotent statement |
| 2 | **Stalls are not fixed.** A 7–21 s stall still costs the request (and blocks the shared client) before any retry runs | High / Medium | Stated, not hidden (Section 6.6). The retry fixes the dead client a stall leaves. The breaker stops a sustained stall from repeating per request. Driver timeouts are Section 13 |
| 3 | **An abandoned stream holds the write lock**, so a fresh client's retried write hits `TRANSACTION_TIMEOUT` (PRD-007 STORY-006's five-second default) | Medium / Medium | F1 measures it (open question 3). If confirmed, `TRANSACTION_TIMEOUT` is `NOT_SENT` (the write was refused, not applied) and counts within the 2 s budget, or the budget is revisited with the data |
| 4 | **The journal makes the container stateful** (compose says "No volume ... the container is stateless") | Certain / Medium | Named volume in compose. Docs state the journal is empty in steady state. A missing or unwritable directory is a startup error, not silent loss. O1 records the trade-off |
| 5 | **`audit_id: null` breaks a client** that assumes an integer | Low / Medium | Only during an outage, only for in-flight requests. `audit_ref` is always present. O2 records the alternative (withhold the response) |
| 6 | **Overlay drifts from the SQL predicate** as later PRDs add exclusions | Medium / High | The parity test fails on any new exclusion added to one side only. Both live next to each other with a cross-reference comment |
| 7 | **The drainer competes with live traffic** for the single client | Low / Low | One entry per transaction, yields between entries, only while the breaker is closed |

## 15. Appendix

### Decisions

| # | Decision |
|---|---|
| D1 | **Retry boundary = the start of a `_session()` block**, re-invoked as a callable on a fresh client. `_translated()` keeps its no-retry contract and its docstring |
| D2 | **Four failure classes** (`NOT_SENT`, `DEAD_STREAM`, `OUTCOME_UNKNOWN`, `STATEMENT`), from message text *and* the failing call. Unrecognised → `OUTCOME_UNKNOWN`. Dead stream on `commit` → `OUTCOME_UNKNOWN` until F1 proves otherwise |
| D3 | **Three statement kinds.** `READ` and `IDEMPOTENT` retried on every infrastructure class. `NON_IDEMPOTENT` (`admit_usage`, `charge_usage`, `append_chat_message`, `insert_user`) only when the failure proves it did not run |
| D4 | **`write_id` (uuid4) + `UNIQUE` index + `ON CONFLICT DO NOTHING`** on `audit_logs` and `action_decisions`, minted once in `log_query` / `record()` with the timestamp |
| D5 | **Budget: 3 attempts, full jitter (≤ 50 ms, ≤ 200 ms), no attempt starts after 2 s.** Module constants. The deadline cannot cut a running call |
| D6 | **Process-local breaker**: opens after 5 consecutive infrastructure-failed operations, 10 s open, one `SELECT 1` half-open probe on a fresh client under `_client_lock`. `STATEMENT` failures never count. Built as a reusable `CircuitBreaker` class (thresholds passed in, injected clock, pluggable probe, `force_open`, `BreakerStatus`). Storage holds exactly one instance |
| D7 | **Open = `StorageUnavailableError(StorageError)`.** The existing fail-closed arms refuse. Nothing is waved through |
| D8 | **503 + `Retry-After` for transient/unavailable storage on every ingress**: `/v1` `storage_unavailable` (503, `api_error`, retryable), identity read never 401, fixed bodies without driver text. Non-transient causes keep today's 500 |
| D9 | **Audit journal on local disk**: JSON Lines, fsync per append, one file per process under an exclusive lock, orphan adoption at boot, torn-tail discard |
| D10 | **Bounded by `AUDIT_BUFFER_MAX_BYTES`. Full → fail closed** (`AuditUnavailableError`, nothing released). Admission headroom (`PIPELINE_MAX_WORKERS × 64 KiB`) checked at pipeline entry, so a paid answer is never withheld for lack of space |
| D11 | **Drain**: daemon thread from the lifespans, FIFO, one idempotent transaction per entry, checkpoint after commit. New writes go direct when healthy. `id` order ≠ time order for drained rows |
| D12 | **Duplicate overlay** over this process's journaled rows, same predicate, consulted only after a successful DB lookup that found nothing. Cross-instance gap accepted (T4) |
| D13 | **PRD-017 D8 restated**: "recorded" means committed *or* fsynced to the journal, audit row and decisions in one entry when the row is journaled. Release allowed then. Neither possible → today's fail-closed path |
| D14 | **Journaled success**: `audit_id: null`, `audit_ref: <write_id>` on every success. `/v1` `X-Harness-Audit-Ref` and `chatcmpl-harness-ref-<write_id>` |
| D15 | **Not buffered and not cached**: identity, ownership, history, admit, duplicate reads, the charge (stays fail-open), transcripts. A storage-unavailable refusal writes no audit row (today's contract) |
| D16 | **Observability without a dependency**: structured logs, `GET /storage/status` (`stats:read`, no DB call), an admin console Storage panel, in-memory counters. `/health` unchanged |
| D17 | **Boot unchanged**: `init_db()` / `check_database_reachable()` bypass retry and breaker and still refuse to start without a database. The journal is drained only after a successful boot |
| D18 | **Testing**: pure tests non-`db`; a `_FaultyClient` proxy with before/after-forward modes for `db` tests; real-fault tests opt-in (`--run-chaos`) |

### Open decisions (proposed default)

These are the calls the user may reasonably make differently. Each has a default the stories will implement unless overruled.

- **O1 — Journal on disk, not in memory.** *Default: disk.* Memory would keep the container stateless but lose rows on a crash during an outage, which breaks "never lost". Disk needs a volume and puts raw prompt previews on it (T6).
- **O2 — Release a response whose success row is only journaled.** *Default: release, with `audit_id: null` + `audit_ref`.* Alternative: withhold it (fail closed), which keeps `audit_id: int` but costs the user an answer already paid for and makes the journal useful only for refusal rows.
- **O3 — `admit_usage` is not retried after `OUTCOME_UNKNOWN`.** *Default: not retried, fail closed with 503.* Alternative: retry and accept at most one over-counted attempt per retry. That error is in the fail-closed direction and would absorb more blips.
- **O4 — `/v1` storage faults become `503 storage_unavailable`.** *Default: yes.* Alternative: keep PRD-015 D7's `500 internal_error` (retryable) for byte compatibility, adding only `Retry-After`.
- **O5 — The usage charge is not journaled.** *Default: not journaled, stays fail-open.* A replayed charge needs an idempotency key (Section 13's ledger). Until then the audit row's token columns are the record (PRD-013 T8).
- **O6 — Retry and breaker parameters are module constants.** *Default: constants* (PRD-008 precedent). Alternative: settings, for operators on high-latency links.
- **O7 — A storage-unavailable refusal writes no audit row.** *Default: none*, as today for `DuplicateCheckError` / `UsageLimitError` ([v1.py:225-227](../../../app/routers/v1.py)). Journaling one per refused request during an outage would turn the journal into a traffic log and fill it.
- **O8 — Does the journal count as "recorded" for a decision written *before* an action is executed?** *Not resolved here: needs the user's call.* D13 lets a fsynced journal entry stand in for a committed `action_decisions` write. That is defensible for PRD-017's step 8, where the harness *releases* calls to a client after the model produced them. PRD-023 T9 ("executed but not recorded") requires the opposite for the MCP gateway's pre-forward decision write: the harness itself forwards the call, and PRD-023 says this PRD's offline buffering "must not apply to the pre-forward write". The two conflict if D13 is read as a general rule. Options: (a) scope D13 explicitly to PRD-017's post-response release, so any pre-execution decision write must commit to the database or fail closed (consistent with PRD-023 T9); (b) let the journal satisfy pre-forward writes too, for availability, and amend PRD-023 T9; (c) leave the journal opt-in per call site, with pre-forward sites opting out. *Proposed default, pending the user:* (a). The journal API gives no call site a way to journal a pre-forward write, and PRD-023's gateway calls the non-journaling `insert_action_decisions` path directly.

### Evidence (verified against `main` @ `2253871`)

- `_shared_client()` probes a client idle ≥ `_IDLE_PROBE_AFTER_SECONDS = 5.0` before lending it, and replaces a dead one once ([app/db/database.py:80, 83-132, 135-174](../../../app/db/database.py)).
- `_translated()` invalidates a dead stream and re-raises `StorageError`, without retrying ([:592-628](../../../app/db/database.py)). `_session()` is `_translated()` around a committing `_Connection` ([:631-642](../../../app/db/database.py), [:351-356](../../../app/db/database.py)).
- `check_database_reachable()` runs only from `init_db()` and classifies unreachable vs auth ([:567-589](../../../app/db/database.py)).
- `insert_audit_log` is a plain `INSERT` returning `lastrowid`. `audit_logs.id` is `INTEGER PRIMARY KEY AUTOINCREMENT` with no other unique key ([:802-854](../../../app/db/database.py), [app/db/models.py:4-40](../../../app/db/models.py)).
- `admit_usage` and `charge_usage` are increment statements ([:1719-1782](../../../app/db/database.py)). `admit` fails closed, `charge` fails open ([app/services/usage_limits.py:13-20, 159-162, 214-227](../../../app/services/usage_limits.py)).
- `check_duplicate` turns `StorageError` into `DuplicateCheckError` ([app/services/duplicate_checker.py:32-35](../../../app/services/duplicate_checker.py)).
- No `log_query` call in `run_conversation` is guarded. A failing success-row write propagates as a raw `StorageError` after the upstream answered and the charge ran ([app/services/query_pipeline.py:804-811, 893-918](../../../app/services/query_pipeline.py)). `/query`'s chain does not catch it ([app/routers/query.py:27-41](../../../app/routers/query.py)), and on `/v1` it is outside `_PIPELINE_FAULTS` ([app/routers/v1.py:111-117](../../../app/routers/v1.py)).
- PRD-017 D8: `record()` failure → `mark_audit_log_failed` best effort → `ActionAuditError` → `/v1` 500 `internal_error` ([query_pipeline.py:923-946](../../../app/services/query_pipeline.py), [v1.py:198-212](../../../app/routers/v1.py), [v1_translate.py:719-724](../../../app/services/v1_translate.py)).
- `require_identity` calls `resolve()`, which calls `find_user_by_token_hash` with no storage handling ([app/middleware/auth.py:14-20](../../../app/middleware/auth.py), [app/services/identity.py:69-92](../../../app/services/identity.py)). `/v1`'s handlers cover `HTTPException` and `RequestValidationError` only ([v1.py:489-501](../../../app/routers/v1.py)).
- Chat UI: `pending = True` at `chat_ui/chat_ui/state.py:962`, `resolve(token)` at `:967`, `try` at `:995`. Login `resolve()` at `:311` is unguarded. The internal-error arms put `str(exc)` in `detail` (`:1175-1196`).
- `QuerySuccessResponse.audit_id: int` ([app/models/schemas.py:80](../../../app/models/schemas.py)); `/v1` `audit_id: int` and `chat_completion_id(audit_id)` ([app/models/v1_schemas.py:26-33, 173](../../../app/models/v1_schemas.py)); `X-Harness-Audit-Id` ([v1.py:250](../../../app/routers/v1.py)).
- `/health` returns `{"status": "ok"}` and touches no storage ([app/main.py:39-41](../../../app/main.py)). No metrics library in `requirements.txt`.
- `docker-compose.yml` declares no volume, on purpose ("the container is stateless").
- PRD-014 stall evidence: 21.05 s `tcp connect error` (`os error 10060`), then `STREAM_EXPIRED` on the reused client, and 0 in-network stalls over 143,461 calls ([spike](../../spikes/PRD-014-docker-network-stalls.md)). `_reset_database()`'s one dead-stream retry is safe because its statements are idempotent `DROP ... IF EXISTS` (`tests/conftest.py:254-284`), which is this PRD's rule in miniature.

### Assumptions (to be confirmed by STORY-001 or STORY-002)

- The `OUTCOME_UNKNOWN` driver texts (read timeout, connection reset) are not yet captured anywhere in this repo.
- Whether `libsql==0.1.11` autocommits DML against a remote endpoint, and whether `commit()` is a network call when no transaction is open.
- Whether a stream abandoned mid-transaction holds the write lock until the server expires it.
- `INSERT ... ON CONFLICT(write_id) DO NOTHING` behaves on the pinned driver as SQLite documents (only `DO UPDATE ... RETURNING` is verified, [database.py:1698-1712](../../../app/db/database.py)).
- `libsql.connect` is called with `(url, auth_token=...)` only ([database.py:127, 173](../../../app/db/database.py)). No client-side timeout is configured, and whether the driver offers one is unverified.

### Tentative story breakdown (to be generated by `/create-stories`)

| # | Story | Type | Size |
|---|---|---|---|
| 1 | Driver failure-surface spike (F1) | spike | small |
| 2 | `_classify` + phase tracking + fixtures | technical | small |
| 3 | `_unit_of_work` and kinds on every `database.py` function | technical | medium |
| 4 | `write_id` columns, indexes, idempotent audit and decision inserts | technical | medium |
| 5 | `CircuitBreaker` class (reusable), the storage instance, `StorageUnavailableError` | technical | medium |
| 6 | Ingress mapping: `/query`, `require_identity`, `/v1` fault code | feature | medium |
| 7 | Chat UI: `resolve()` inside the send's `try`, login notice, fixed copy | feature | small |
| 8 | Audit journal: append/fsync, lock, adopt, torn tail, bounds | technical | medium |
| 9 | Drainer and lifespan wiring | technical | medium |
| 10 | `AuditRef`, journaled release, PRD-017 D13 path, response fields | feature | medium |
| 11 | Duplicate overlay and headroom check | technical | small |
| 12 | `GET /storage/status` and admin Storage panel | feature | small |
| 13 | Docs, compose volume, `.env.example`, roadmap, in-network regression runs | docs | small |

### Related documents

- PRD-007 (Turso migration): one client per process (STORY-006: 169/200 writes lost to `TRANSACTION_TIMEOUT` with a client per thread), the error surface (STORY-004), the boot guard (STORY-008)
- PRD-008 STORY-024: the idle probe, dead-stream invalidation, the "no knob" rule
- PRD-009: the duplicate predicate (D1, D3, F5) the overlay must match
- PRD-013: usage gate fail-closed (T7), charge fail-open (T8), D9
- PRD-014: the stall evidence, the `db` marker and guard, the recorder pattern, the in-network recipe
- PRD-015: `/v1` fault table (D7), the stream commit rule (Section 6.4)
- PRD-017: D8, `record()` and fail-closed release (T5)
- PRD-019 (websocket affinity) and PRD-022 (provider fallback): the rest of the roadmap's resilience track, out of scope here

### Cross-PRD consumers of this PRD

- **PRD-022 (provider fallback)** reuses `CircuitBreaker`, one instance per upstream provider, with this PRD's numbers as its defaults (its Section 6.10, O10). It uses `probe=None` (the next live request is the probe) and `force_open(seconds)` for a provider answering `401`. Its `GET /providers/status` returns one `BreakerStatus` per provider, shaped like `storage_status().breaker`.
- **PRD-019 (multi-instance deployment)**: `/ready` reads `storage_status().breaker.state` (its D5). It never records a failure or success on the breaker, and it keeps this PRD's 503 + `Retry-After` intact through the balancer. So `BreakerStatus.state` and `retry_after_seconds` are a contract with PRD-019, not an internal detail.
- **PRD-023 (MCP and skills)**: its T9 requires that the MCP pre-forward decision write is **not** satisfied by the journal. This conflicts with a general reading of D13. The tension is recorded as Open decision O8 and is not resolved here.
- [docs/deployment.md — The database is a hard dependency of every request](../../../docs/deployment.md), [docs/roadmap.md — Next up: resilience](../../../docs/roadmap.md)

### Dependencies

- Depends on: PRD-007, PRD-013, PRD-014, PRD-017 (all done)
- Blocks: none hard. PRD-019's `/ready` and PRD-022's provider breakers consume `storage_status()` and `CircuitBreaker`. PRD-022's STORY-001 extracts the class itself if this PRD has not landed it yet

Skills referenced: none (`.agents/skills/` holds only `frontend-design`, which does not apply. The admin Storage panel follows the existing admin console's components).
