# Persistence & deployment

Where Harness AI keeps state, what is stored and who can read it, what multi-instance deployment does and does not yet cover, and how to migrate off a legacy SQLite file.

← Back to the [README](../README.md).

---

## Persistence & Deployment

### Where state lives

All five tables the harness owns — `audit_logs`, `users`, `chat_sessions`, `chat_messages` and `usage_daily` (one usage counter row per user per UTC day) — live in a [Turso](https://turso.tech) (libSQL) database, reached over the network. There is no database file in the repository, in the image, or in the compose stack, and there is no local-file fallback: a `sqlite:` `DATABASE_URL` is a startup error rather than a file, deliberately, because a local database written to an ephemeral container layer is read by nobody and backed up by nobody.

To provision one: create a database, take its `libsql://<database>-<org>.turso.io` URL and an auth token, and put both in `.env` as `DATABASE_URL` and `TURSO_AUTH_TOKEN`. Any libSQL endpoint works — the local dev server on `http://` is the same contract without the token.

### What is stored, and who can read it

**This release changed what the harness holds at rest, and that is worth reading before you deploy it.** Until now the durable store held a prompt hash and truncated previews. `chat_messages` holds **the prompt as the user typed it** and **the response as PII redaction released it**. **No raw model output reaches `chat_messages`** — what the model returned before masking never enters a transcript; it survives only where it always has, as the 500-character `audit_logs` preview this release did not touch. The prompt, though, is stored in full and unmasked, and that is a real widening over the previous release rather than a detail.

**Only the author reads a transcript.** Ownership is a required parameter on every session and message function in `app/db/database.py`, re-checked on every read rather than trusted from the client; `chat_messages` carries no `user_id` of its own, so reads and deletes scope through a subselect on `chat_sessions`. A `session_id` belonging to someone else is refused at `POST /query` with a `403`, and returns an empty transcript through every other path — the same answer as a session that does not exist, so the id space cannot be probed. **There is no admin path to a transcript**: `GET /audit` gains a `session_id` and nothing more, and the admin console renders no transcript at all.

**`audit_logs` is unchanged.** It still stores the prompt hash and the 500-character raw previews it always did, and it gained exactly one column, `session_id`. Nothing about the audit trail's contents moved in this release. PRD-013 later added eight metadata columns — ingress, message count, the token split, two flags, a conversation key and the usage limit — and no content: no new preview and no new text. See [`GET /audit`](api.md#get-audit-requires-auditreadall-or-auditreadown).

**`CHAT_HISTORY_ENABLED=false` is a supported configuration, not a degraded mode.** With it off, no transcript row is written and none is read, the session rail is *absent* rather than empty, and the chat behaves exactly as it did before this release — same image, same code path, no fork to maintain. It is the configuration for a deployment that must not hold prompt text at rest. `POST /query` is unaffected either way: it never wrote a transcript, and with the flag off a supplied `session_id` is still recorded on the audit row as a label. The switch governs the transcript, not the audit column.

**Deleting a chat removes the transcript and leaves the audit record intact.** The session and its messages go together in one transaction. `audit_logs` is append-only and is not touched, so the `session_id` on those rows is left pointing at a conversation that no longer exists — deliberately. That is what preserves the evidence of what was asked when a user tidies their list, and the confirmation dialog says so in the user's own words rather than the schema's.

**No retention or expiry exists.** A transcript persists until its owner deletes it. A deployment holding prompt text will eventually want a TTL; there is none today, and `audit_logs` has none either.

### Multiple instances

Several application instances may now share one database. That is what this migration bought: the audit trail is no longer an artifact of one container's filesystem, and `init_db()` converges correctly when instances start against the same database simultaneously, rather than racing each other through the schema migration.

**This is proven rather than assumed.** `tests/test_two_instance_smoke.py` starts two application processes against one database and asserts that a chat written through the first is served, in full, by the second — the transcript included. Sessions were the last piece of state that lived only in one process's memory, and they no longer do.

**What is still not included.** The database blocker is gone; the deployment topology is not built:

- **No load balancer or health-check configuration** is provided or documented here.
- **No Reflex websocket session affinity.** The chat UI holds a websocket per session, so placing instances behind a round-robin balancer without sticky sessions is not a supported configuration today.

Treat multi-instance as *unblocked*, not *delivered*.

### The database is a hard dependency of every request

With the local file gone, every `POST /query` makes network round trips it never used to. With [usage limits](features.md#usage-limits) on, the default, there are five statements per request — the identity read, the usage gate, the duplicate check, the usage charge and the audit write — about 16 ms of it (p50, same-host dev server) for the two usage statements; with `USAGE_LIMITS_ENABLED=false` there are three. Retry, circuit-breaker, and offline-buffering behavior are deliberately outside the current scope, which has a consequence worth knowing before you size a deployment rather than during an incident: **a transient database outage fails requests instead of degrading them.** Endpoints that previously could not fail on storage now can.

There is no exception for the duplicate check. A storage failure during the duplicate lookup returns `500`, and the query never reaches the model — the check fails closed, as `tests/test_query_router.py::test_duplicate_check_storage_failure_returns_500` asserts. An earlier version of this section said the opposite; the code never did. Letting a failed check through would turn every database outage into a window with no duplicate control, which would be a security decision, not a resilience detail. The usage gate fails closed the same way, for the same reason: a counter it cannot read is a `500`, never an unlimited request. Its charge, written after the model has answered, fails open instead — the answer is returned, the failure is logged at `ERROR`, and the audit row keeps the token counts. Resilience work is the first item on the roadmap beyond this migration.

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
