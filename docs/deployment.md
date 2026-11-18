# Persistence & deployment

Where Harness AI keeps state, what is stored and who can read it, what a database outage does, what multi-instance deployment does and does not yet cover, and how to migrate off a legacy SQLite file.

← Back to the [README](../README.md).

---

## Persistence & Deployment

### Where state lives

All five tables the harness owns — `audit_logs`, `users`, `chat_sessions`, `chat_messages` and `usage_daily` (one usage counter row per user per UTC day) — live in a [Turso](https://turso.tech) (libSQL) database, reached over the network. There is no database file in the repository, in the image, or in the compose stack, and there is no local-file fallback: a `sqlite:` `DATABASE_URL` is a startup error rather than a file, deliberately, because a local database written to an ephemeral container layer is read by nobody and backed up by nobody. The one local state is the [audit journal](#what-a-database-outage-does): empty while the database is reachable, it holds audit rows only during an outage and lives on a named volume in the compose stack.

To provision one: create a database, take its `libsql://<database>-<org>.turso.io` URL and an auth token, and put both in `.env` as `DATABASE_URL` and `TURSO_AUTH_TOKEN`. Any libSQL endpoint works — the local dev server on `http://` is the same contract without the token.

### What is stored, and who can read it

**This release changed what the harness holds at rest, and that is worth reading before you deploy it.** Until now the durable store held a prompt hash and truncated previews. `chat_messages` holds **the prompt as the user typed it** and **the response as PII redaction released it**. **No raw model output reaches `chat_messages`** — what the model returned before masking never enters a transcript; it survives only where it always has, as the 500-character `audit_logs` preview this release did not touch. The prompt, though, is stored in full and unmasked, and that is a real widening over the previous release rather than a detail.

**Only the author reads a transcript.** Ownership is a required parameter on every session and message function in `app/db/database.py`, re-checked on every read rather than trusted from the client; `chat_messages` carries no `user_id` of its own, so reads and deletes scope through a subselect on `chat_sessions`. A `session_id` belonging to someone else is refused at `POST /query` with a `403`, and returns an empty transcript through every other path — the same answer as a session that does not exist, so the id space cannot be probed. **There is no admin path to a transcript**: `GET /audit` gains a `session_id` and nothing more, and the admin console renders no transcript at all.

**`action_decisions` is a table of its own.** The action policy engine (PRD-016) is called by `/v1` for every tool call while `V1_TOOLS_ENABLED=true` (PRD-017), and the table stays empty with the flag off. One row per tool call is written, allowed calls included: the tool, the decision, the rule, every classification, a hash of the arguments and a preview of up to 500 characters of them. **That preview can hold up to 500 characters of a denied secret read (T10)**; URL userinfo and query values are masked first, everything else is raw, and nothing in the API or the console shows it. The rows link to `audit_logs` by a nullable `audit_id`, the request's row, with no foreign key. No retention exists, as with `audit_logs`.

**`audit_logs` is unchanged.** It still stores the prompt hash and the 500-character raw previews it always did, and it gained exactly one column, `session_id`. Nothing about the audit trail's contents moved in this release. PRD-013 later added eight metadata columns — ingress, message count, the token split, two flags, a conversation key and the usage limit — and no content: no new preview and no new text. See [`GET /audit`](api.md#get-audit-requires-auditreadall-or-auditreadown).

**`CHAT_HISTORY_ENABLED=false` is a supported configuration, not a degraded mode.** With it off, no transcript row is written and none is read, the session rail is *absent* rather than empty, and the chat behaves exactly as it did before this release — same image, same code path, no fork to maintain. It is the configuration for a deployment that must not hold prompt text at rest. `POST /query` is unaffected either way: it never wrote a transcript, and with the flag off a supplied `session_id` is still recorded on the audit row as a label. The switch governs the transcript, not the audit column.

**Deleting a chat removes the transcript and leaves the audit record intact.** The session and its messages go together in one transaction. `audit_logs` is append-only and is not touched, so the `session_id` on those rows is left pointing at a conversation that no longer exists — deliberately. That is what preserves the evidence of what was asked when a user tidies their list, and the confirmation dialog says so in the user's own words rather than the schema's.

**No retention or expiry exists.** A transcript persists until its owner deletes it. A deployment holding prompt text will eventually want a TTL; there is none today, and `audit_logs` has none either.

### Multiple instances

Two application instances can share one database behind a sticky, health-checked balancer (PRD-019). `docker-compose.yml`, the single-instance stack, is unchanged; `docker-compose.lb.yml` ships the two-instance topology. This section describes what shipped and what is not covered.

**Proven in two ways.** `tests/test_two_instance_smoke.py` starts two application processes against one database and asserts that a chat written through the first is served, in full, by the second. `tests/test_two_instance_balancer.py` puts a real Caddy in front of two instances. An opt-in Docker E2E, `tests/e2e/test_lb_docker.py`, covers stickiness, killing an instance and a rolling restart against the real compose stack (see [Testing](testing.md)); it is not part of CI.

#### Topology

```
client --> lb (caddy 2.11.7, :$PORT) --+--> harness-a (in-container Caddy -> backend :8001) --+
                                       |                                                      +--> shared Turso
                                       +--> harness-b (in-container Caddy -> backend :8001) --+
```

Start it from the repo root:

```bash
LB_COOKIE_SECRET=$(openssl rand -hex 32) docker compose -f docker-compose.lb.yml up -d
```

- The balancer config is `deploy/lb/Caddyfile`; the Caddy image is pinned by digest in `docker-compose.lb.yml`. The instances publish nothing; the `lb` service publishes `${PORT:-8000}`.
- The file declares `name: harness-ai-lb`, so this stack has its own compose project and its own `harness-audit-buffer` volume. `docker compose down -v` of one stack therefore cannot destroy the other's audit journal. Before you run `down -v` on either, check that `GET /storage/status` shows `journal.entries == 0`: undrained entries are lost with the volume.
- The two instances share that volume: each process locks its own journal file, and a journal left by a killed instance is adopted by its sibling or replacement (PRD-018).
- `LB_COOKIE_SECRET` is required: compose refuses to start without it (Caddy itself would accept an empty value silently). Only the balancer reads it; nothing in `app/` does.
- The Caddyfile names the services `harness-a` and `harness-b`, so `--scale` is not supported.

#### Affinity and failover

The balancer pins a client to an instance with a signed cookie, `harness_lb` (`lb_policy cookie harness_lb`, signed with `LB_COOKIE_SECRET`). The chat UI's websocket and its per-session state live on one instance, so every request of a session must reach the same one.

- The cookie is `Path=/; HttpOnly; SameSite=Lax`. It has **no `Secure` attribute** and it is a **session cookie** (no expiry): it ends when the browser closes. Its value is 64 hex characters. Terminate TLS in front of the balancer (see "TLS and the port" below).
- If the pinned instance dies or becomes unready, another instance answers and the cookie is re-set. The user sees the sign-in gate once, because the session token is per-instance disk state, then the transcript reloads from the database. **The answer that was in flight is lost.**
- Only the cookie policy is tested. IP-hash and round-robin affinity are not supported.

#### Probes

| Path | Meaning | Used by |
|---|---|---|
| `/health` | Liveness. Ignores the drain flag. | The image `HEALTHCHECK` (`Dockerfile`, every 10 s) and compose `service_healthy` |
| `/ready` | Readiness. `503` with `{"status":"not_ready","reason":"draining"}` while the drain file (`DRAIN_FILE`) exists; otherwise `200` with `{"status":"ready","breaker":"closed"}`; `503` with reason `breaker_open` and a `Retry-After` while PRD-018's breaker is open. It never moves the breaker: a `SELECT 1` bounded by `READY_DB_TIMEOUT_SECONDS`, and no call at all while the breaker is not closed. | The balancer's active health check (`health_uri /ready`) |
| `/storage/status` | Storage and journal detail; needs `stats:read`. | Operators; not for the balancer |

The balancer probes every `health_interval 5s` with a `health_timeout 3s` and expects `200`. Passive health uses `fail_duration 30s` and counts connection failures only; an instance answering `503` is handled by the active probe. Keep `READY_DB_TIMEOUT_SECONDS` (default 2.0, at most 10) below the 3 s health timeout.

#### Timeouts

Every hop must be longer than `OPENROUTER_TIMEOUT_SECONDS` + 30 s, so the balancer never cuts a model call before the application gives up on it. With the default of 120 s that is 150 s.

| Hop | Value | Rule |
|---|---|---|
| `response_header_timeout` | `150s` | `OPENROUTER_TIMEOUT_SECONDS` (120) + 30 s |
| `dial_timeout` | `3s` | connecting to an instance |
| `lb_try_duration` | `5s` | how long the balancer waits for a healthy upstream |
| `health_timeout` | `3s` | above `READY_DB_TIMEOUT_SECONDS` |
| `stream_close_delay` | `5m` | keeps websockets open across a config reload |

If you raise `OPENROUTER_TIMEOUT_SECONDS`, raise `response_header_timeout` in `deploy/lb/Caddyfile` with it. **With a third-party balancer** instead of this one: a 150 s read/idle timeout, no response buffering (SSE and websockets must stream), a health check on `/ready` whose timeout is above `READY_DB_TIMEOUT_SECONDS`, and cookie affinity. Only the shipped Caddyfile is tested.

#### What a client sees when the balancer cannot serve

With no healthy instance the balancer answers `503` after about 5 s (`lb_try_duration`) with `Retry-After: 10`, the breaker interval of PRD-018. `/v1/*` gets an OpenAI-shaped error body (`type: api_error`, `code: service_unavailable`); other paths get `{"detail":"Service unavailable"}`. An instance's own `503` (a storage outage, with its own `Retry-After`) passes through untouched. A request that reached an instance is never replayed to another (there is no `retry_match`), because `/query` and `/v1` calls are not idempotent; only connection failures are retried. The balancer does not compress responses and writes no access log, both to stay out of the streaming path.

#### Rolling restart

`scripts/rolling_restart.sh` replaces the instances one at a time without dropping a request the balancer already routed. **Build first**: the script never builds, and `--force-recreate` reuses the existing image, so new code needs an explicit build.

```bash
docker compose -f docker-compose.lb.yml build
scripts/rolling_restart.sh [-f COMPOSE_FILE]... [-p PROJECT]
```

For each instance, in order: check that every other instance answers `/ready` 200; touch the drain file so `/ready` turns 503 and the balancer stops routing new requests there; wait for that 503; sleep the drain window; recreate the instance and wait for `/ready` 200. Nothing starts unless every instance is ready first.

- **Drain window** = `2 * health_interval` + `DRAIN_SECONDS`. The health interval is parsed from `deploy/lb/Caddyfile` (5 s, so 10 s). `DRAIN_SECONDS` defaults to `OPENROUTER_TIMEOUT_SECONDS` + 10, and that timeout is read from your shell environment, else from inside the first instance container (`.env` reaches the containers through `env_file`, not your shell), else 120. Fractions round up.
- Tunables (environment): `POLL_SECONDS` (2), `DRAIN_WAIT_SECONDS` (30, how long `/ready` may take to turn 503), `READY_TIMEOUT_SECONDS` (180, how long a replacement may take to turn 200).
- `-f` may repeat (an overlay on the base file); `-p` names the compose project. Without `-f` the script targets `docker-compose.lb.yml`.
- The audit journal does not block a restart: the volume survives the recreate and the new process adopts what is left (PRD-018).

| Exit | Meaning |
|---|---|
| 0 | done |
| 1 | usage or configuration error |
| 2 | refused: an instance is not ready (also checked before each drain) |
| 3 | the drain never took effect; undone, nothing recreated |
| 4 | a replacement never became ready; the other instance was not touched and still serves |

#### TLS and the port

The image is built with `PORT`, and the in-image routing listens on it. Over plain HTTP the balancer must publish that same `$PORT`, which the compose file does. Behind TLS on 443 the constraint disappears: terminate TLS in front of the balancer. The cookie carries no `Secure` attribute, so do not expose the balancer to browsers over plain HTTP outside a trusted network.

#### Not supported, and not verified

- `REFLEX_REDIS_URL` set: it silently switches Reflex to Redis, which is untested here. Leave it unset.
- `--scale` of the instance services; IP-hash or round-robin affinity.
- Not verified in isolation: websocket pass-through, and `stream_close_delay` across a config reload. The Docker E2E covers stickiness, a killed instance and a rolling restart end to end.

**Security.** `docker compose config` prints the values from `.env`, including `TURSO_AUTH_TOKEN` and `ADMIN_TOKEN`: do not paste its output into a ticket or a chat.

### What a database outage does

With the local file gone, every `POST /query` makes network round trips it never used to. With [usage limits](features.md#usage-limits) on, the default, there are five statements per request — the identity read, the usage gate, the duplicate check, the usage charge and the audit write — about 16 ms of it (p50, same-host dev server) for the two usage statements; with `USAGE_LIMITS_ENABLED=false` there are three. This section says what the harness does when one of them fails (PRD-018). The short version: a blip is ridden out with a retry, a sustained outage is refused fast with a `503` and a `Retry-After`, and the one write that can be postponed, the audit row, goes to a local journal and is drained when the database is back. **No gate ever answers from a cache, the journal or a guess.**

**What is retried.** Every storage call runs as one unit and is retried only when the failure says whether the statement ran. Failures are sorted into four classes in `app/db/database.py`, beside `_translated()`, which itself never retries:

| Class | What it is | Did the statement run? | Retried? |
|---|---|---|---|
| `NOT_SENT` | The connection was refused (`tcp connect error`), or a stream was found dead on `commit` | No | Yes, every call |
| `DEAD_STREAM` | The stream was already closed when `execute` or a fetch ran | No | Yes, every call |
| `OUTCOME_UNKNOWN` | A reset, a timeout, an unrecognised `Hrana:` error, a server restart window (`503` or `404`) | Unknown | Reads and idempotent writes only |
| `STATEMENT` | A constraint, a syntax error, a missing table: the database answered | Yes, it was refused | Never, and it does not count toward the breaker |

The calls that are not idempotent (`admit_usage`, `charge_usage`, `append_chat_message`, `insert_user`) are retried only on `NOT_SENT` and on a `DEAD_STREAM` at `execute`, because repeating one that actually ran would count it twice. The audit writes are idempotent: each carries a `write_id` minted by the client and is inserted with `ON CONFLICT(write_id) DO NOTHING`, so a replay after an unknown outcome cannot write a second row. The budget is three attempts, full-jitter backoff of at most 50 ms and then 200 ms, and no new attempt starts once 2 s have passed. These are constants in the code, not settings. The deadline cannot shorten an attempt that is already running (see "What is still not covered").

**The circuit breaker.** Five consecutive operations that end in an infrastructure failure open a breaker, per process. While it is open, every storage call is refused at once, with no round trip, for 10 s; then one probe goes through, and its result closes or reopens it. **An open breaker refuses; it never admits.** Identity, the usage gate and the duplicate check fail closed, as they did before: a database that cannot be read does not turn into an unlimited, unchecked request. There is no cache of identity or of anything a gate reads. The break-glass `ADMIN_TOKEN` resolves without a database read, so it still works during an outage; a user's token cannot, because their identity read fails closed. The usage *charge*, written after the model has answered, fails open: the answer is returned, the failure is logged at `ERROR`, and the audit row keeps the token counts.

**What a client sees.** A request refused because of the database gets the same fixed copy on every ingress. The driver's own text is logged (redacted) and never sent.

| Ingress | A storage outage | Notes |
|---|---|---|
| `POST /query` | `503` with `{"detail": "Storage unavailable"}` when the identity read fails; `503` with `{"detail": "Storage unavailable: the request was not sent to the model."}` when the session check, the usage gate or the duplicate check fails | Always with `Retry-After`. A cause that is not an outage (a `STATEMENT` error) keeps the `500` and its detail |
| `POST /v1/chat/completions` | `503`, `type: api_error`, `code: storage_unavailable`, with `Retry-After` | Retryable: there is no `x-should-retry: false`, so the OpenAI SDKs retry it. Like every `/v1` error it carries `"harness": null` |
| Chat UI | The chat's fixed "internal error" bubble, composer unlocked; sign-in shows a storage notice instead of "invalid token" | Never the driver text. A journaled row shows `audit pending` in the footer |

`Retry-After` is in whole seconds, at least 1: the time to the breaker's next probe, or 1 when the breaker is closed and only the retry budget ran out. A failure after a `/v1` stream has started is one SSE `error` event with no `Retry-After`, since the headers are gone; every gate runs before the stream starts, so today that case is not reachable. The duplicate check's storage failure used to be a plain `500`, asserted by `tests/test_query_router.py::test_duplicate_check_storage_failure_returns_500`; that holds now only for a non-transient cause, and an outage is the `503` above. The fail-closed contract is unchanged: the query never reaches the model, and a check that could not run is never skipped, because that would turn every outage into a window with no duplicate control, a security decision and not a resilience detail.

**The audit journal.** When the audit row of an answer already produced cannot be written, it is appended to a journal file and the answer is released, instead of failing a request the model has already been paid for. This applies only to that post-response write. A write the request needs *before* it executes anything (the action decisions on `/v1`) never uses the journal: if it cannot be recorded, the request is refused.

- **Where.** `AUDIT_BUFFER_DIR` (default `./var/audit-buffer`; in compose `/var/lib/harness/audit-buffer`, the named volume `harness-audit-buffer`) and `AUDIT_BUFFER_MAX_BYTES` (default 64 MiB; it must be at least `PIPELINE_MAX_WORKERS` × 65536 × 2, 4 MiB at the default, or startup stops and names the setting). See [Configuration](configuration.md).
- **What it holds.** The row exactly as it would have been written, including `prompt_preview` (up to 500 raw characters). The directory is `0700` and the files `0600` on POSIX; contents are never logged. It is **not encrypted or signed**: protect the volume as you protect the database. It is empty in steady state, and a drained file is compacted to zero bytes.
- **Files.** One per process, `audit-journal-<host>-<pid>-<boot uuid>.jsonl`: each append is fsynced, each line carries a sha256, and each file holds an exclusive OS lock while its process lives. At startup an instance adopts any sibling file whose lock is free (its own previous run, or a crashed sibling on a shared volume). Instances that do not share a volume drain only their own.
- **A torn tail** (the last line corrupt, or without its newline: a crash mid-append) is discarded with one `ERROR`. A corrupt line that is *not* the last, or a line whose checksum is valid but that cannot be decoded, holds the whole file back: it is left on disk untouched, not adopted, with one `ERROR`, and counted in `held_back_files`. A drained entry that fails for a reason that is not an outage is held back for the life of the process (`held_back_entries`). Held-back data is never retried by that process; inspect the file before touching it, and do not delete it blindly.
- **Draining.** A daemon thread, started only by the two lifespans (the API's and the chat UI's), writes the entries oldest first, one idempotent transaction each, and only while the breaker is closed; an instance with no traffic recovers through the breaker's single probe. New writes go straight to the database. The original timestamp is kept.
- **A drained row's `id` is not time order.** The id is assigned when the row is written, so a drained row's `id` is later than rows written after the outage began. **Order by `timestamp`**; `GET /audit` does.
- **A full journal, or one that cannot be written,** fails the request closed with a `503`. Before running a request the harness also checks that the journal has headroom for it (one 64 KiB reserve per pipeline worker); without it the request is refused with `Retry-After: 1` before it reaches the model.
- **What the answer says.** A journaled success is a `200` released with `audit_id: null` and an `audit_ref` (the row's `write_id`); on `/v1` the `X-Harness-Audit-Id` header is replaced by `X-Harness-Audit-Ref` and the `id` reads `chatcmpl-harness-ref-<write_id>`. `audit_ref` is present on every success. If the row could be neither written nor journaled, nothing is released: the answer is a `503` (the chat UI says "The harness could not record this answer.").
- **The duplicate check** consults the journal after the database lookup has succeeded and found nothing, so a conversation whose row is still in the journal is held as a duplicate. A lookup that failed still fails closed.

**Seeing it.** `GET /storage/status` (`stats:read`; the break-glass token works) answers from memory with no database call, so it works with the breaker open: breaker state, journal size and age, and the process's counters. The admin console shows the same at `/admin/storage`. `/health` is unchanged. Counters are per process and reset on restart. See [`GET /storage/status`](api.md#get-storagestatus-requires-statsread).

**What is still not covered.** Stated, not hidden:

- **A resend that lands on another instance** before the first has drained is not held as a duplicate: the journal index is local to a process (residual threat T4). The window is the drain lag.
- **Stalls are not fixed.** The driver has no read timeout. A call to a database that accepts the connection and then goes silent returns only when the driver gives up (7-21 s measured), and the shared client serialises callers behind it. Retry fixes what a stall leaves behind and the breaker stops it repeating, but the 2 s deadline cannot shorten an attempt in flight.
- **On a Windows host a refused connect takes about 2 s**, so the deadline allows one attempt there. Linux refuses in milliseconds and gets the three.
- **`delete_chat_session` is idempotent**, so if the first attempt's commit landed but its reply was lost, the retry finds nothing and returns "not found": the data is right, and the message may read wrongly for a delete that worked.
- **Four chat UI calls** (reloading the session list, selecting, renaming and deleting a chat) still resolve identity outside the storage handling and fall back to the generic error.
- **`docker compose down -v` destroys undrained journal entries.** Check that `journal.entries` is `0` in `GET /storage/status` before removing the volume.
- **The journal is not encrypted or signed** (T6, T7), and there is **no provider failover**: an OpenRouter outage still fails requests (see the [roadmap](roadmap.md)).

**What it costs when nothing is wrong.** The retry and breaker code adds about **0.04 ms** (p50, four storage calls per request) against a local file database, which is within noise. Over the Docker Desktop dev server the same comparison read +0.80 ms inside a 1.70 ms spread, because each write there costs about 180 ms of volume commit: the 0.5 ms budget **cannot be resolved** at that noise floor, and the result is reported as unresolvable, not as a pass. The fault suite behind the behaviour above is `tests/test_db_resilience_*.py`; the opt-in chaos test that restarts a real server is described in [Testing](testing.md).

### Migrating an existing SQLite deployment

If you are upgrading a deployment that still holds a legacy `harness_ai.db`, `scripts/migrate_to_turso.py` copies `audit_logs` and `users` out of that file and into the database `DATABASE_URL` names.

```bash
python scripts/migrate_to_turso.py --source harness_ai.db --dry-run   # reports counts, writes nothing
python scripts/migrate_to_turso.py --source harness_ai.db             # copies, then verifies
```

Four properties matter when you run it:

- **The source file is opened read-only and is never modified.** It stays authoritative until verification passes, and the script never deletes it — that is your decision, afterwards.
- **A non-empty destination is refused, and there is no `--force`.** One file, one run. If your rows are spread across several files, only one of them can be copied.
- **Verification is not optional.** The script checks per-table counts, compares every row by column name, confirms `audit_logs.id` values are preserved rather than regenerated, and reads a sample back through the application's own accessors. Any mismatch exits non-zero.
- **Delete the source only after a clean run.** If the live database is inside a Docker volume rather than in the repository, extract it from the volume first — the file in your working tree may not be the one your deployment has been writing to.

---
