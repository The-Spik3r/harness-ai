---
story: STORY-015
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-015-readme-and-deployment-docs.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: PENDING
status: COMPLETE
completed: 2026-09-02
---

# Implementation Report — STORY-015: README: correct the persistence claim, the env table, and document multi-instance deployment

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-015-readme-and-deployment-docs.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `PENDING`

## Summary

One committed file changed: `README.md`, +105/−11. The two lines the story names were the smallest part
of it. The persistence claim at `:177` and the `DATABASE_URL` row at `:214` are corrected, four more
places that still asserted SQLite are corrected, a new `## Persistence & Deployment` section carries
the multi-instance bound, the resilience statement and the migration-tool documentation, and
`## Running Tests` is rewritten around the local libSQL dev server.

**Three defects were found by executing the README rather than reading it, and none of them was in the
plan.** The documented in-container test command needed a *third* override, not two. The whole-suite
run is green — the "known failures" the epic has been carrying are not what the index says they are.
And following the Docker quickstart verbatim against a genuinely fresh database **does not produce a
serving application**, because the RBAC bootstrap guard kills the container before `create-user` can
run. Each was fixed in the README and each is recorded below with the command that proved it.

A fourth finding is operational rather than documentary, and it is the most serious thing here: the
`STREAM_EXPIRED` issue the index tracks as a test-suite annoyance **reproduces in the running
application**, where it presents as a permanent `500` on every database-touching request. See Finding 4.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Duplicate `TURSO_AUTH_TOKEN` removed; trailing newline restored | `.env.example` | ✅ |
| 2 | Architecture diagram: two `SQLite` labels → `Turso` | `README.md` | ✅ |
| 3 | Features table and Roadmap "Shipped" de-SQLite'd | `README.md` | ✅ |
| 4 | `Requirements`: database named; `libsql` wheel range verified against PyPI | `README.md` | ✅ |
| 5 | Quickstart — Local: the two new required variables | `README.md` | ✅ |
| 6 | Quickstart — Docker: same, plus `--build` and `env_file` notes | `README.md` | ✅ |
| 7 | `:177` persistence claim replaced | `README.md` | ✅ |
| 8 | New `## Persistence & Deployment` section + TOC entry | `README.md` | ✅ |
| 9 | Env table: `DATABASE_URL`, `TURSO_AUTH_TOKEN`, `DB_BOOTSTRAP_ENABLED` | `README.md` | ✅ |
| 10 | `## Running Tests` rewritten around the dev server | `README.md` | ✅ |
| 11 | Every command and error string executed and captured | — | ✅ |
| 12 | README followed end to end against a fresh database | — | ✅ (split, see AC 5) |
| 13 | `grep` gate + structural read-through | — | ✅ |
| 14 | Three new Troubleshooting entries + stale-image case | `README.md` | ✅ |

## The error strings, captured rather than reconstructed

All three quoted in the README's Troubleshooting section were produced by running the code, in a
`python:3.11`-based image (this host cannot run the project's Python — see Finding 5).

`DATABASE_URL=sqlite:///harness_ai.db`:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
DATABASE_URL
  Value error, DATABASE_URL must name a libSQL endpoint, not a file. Replace the 'sqlite:' URL with
  'libsql://<database>-<org>.turso.io' (or 'http://127.0.0.1:8080' for the local dev server). PRD-007
  removed the file fallback deliberately: a local database file is written to an ephemeral container
  layer, read by nobody, and backed up by nobody.
```

`DATABASE_URL=libsql://example-org.turso.io` with `TURSO_AUTH_TOKEN=`:

```
  Value error, TURSO_AUTH_TOKEN is required when DATABASE_URL names a remote endpoint (libsql:// or
  https://). The local libSQL dev server on http:// takes no token.
```

A reachable scheme with nothing listening, on `--network none`:

```
app.db.errors.DatabaseUnreachableError: Cannot reach the database at http://127.0.0.1:9999. The
application will not start: PRD-007 removed the local-file fallback deliberately, so there is nothing
to degrade to. Check DATABASE_URL and that the endpoint is reachable from this host. Driver said:
Hrana: `http error: `error trying to connect: tcp connect error: Connection refused (os error 111)``
```

Identical to the text STORY-008 specified and STORY-014 recorded. No drift.

## Findings

### 1. The documented test command needed a third override — and then the suite is fully green

STORY-014's Finding 2 identified two variables. Running the two-variable command produced **two
failures**:

```
FAILED tests/test_config.py::test_local_dev_server_without_a_token_is_accepted
FAILED tests/test_config.py::test_https_is_remote_even_though_it_starts_like_http
2 failed, 1111 passed, 20 skipped in 47.51s
```

Both are the same environment-inheritance family as Finding 1, one variable over: those tests construct
`Settings()` to assert that a local `http://` endpoint is accepted *without* a token and that `https://`
is rejected *for lacking* one. `env_file: .env` supplies a real `TURSO_AUTH_TOKEN`, which makes both
assertions false. Adding `-e TURSO_AUTH_TOKEN=`:

```
1113 passed, 20 skipped, 1 warning in 46.86s
```

The README documents all three overrides with a sentence each explaining what it defends against.

### 2. The epic's recorded "known failures" are not what the index says

The index describes two collection errors and a whole-suite `STREAM_EXPIRED`. Measured here:

| Run | Result |
|---|---|
| `pytest tests/` (whole suite, one process) | **1113 passed, 20 skipped, 0 failed** |
| `pytest tests/test_pii_badge.py` (alone) | collection error, `'chat_ui.chat_ui' is not a package` |
| `pytest tests/test_db.py` | 97 passed |

So the collection error fires **only when those modules are run in isolation** — a whole-suite
collection imports `chat_ui.chat_ui` as a package first and both modules then pass. And `STREAM_EXPIRED`
did **not** reproduce in a whole-suite run at all. The README states this accurately rather than
repeating the inherited claim; the index's paragraph is now the stale one.

### 3. 🔴 The Docker quickstart, followed verbatim against a fresh database, does not serve

This is what AC 5 exists to catch, and it caught something. On a genuinely empty database the README's
order is `up -d --build` → `create-user` → `curl /health`. The first `up` starts the app, the RBAC
bootstrap guard finds no users, and the container **exits**:

```
app.services.authz.RbacNotBootstrappedError: RBAC_ENABLED=true but no active users exist.
[ERROR] Unexpected exit from worker-1
```

`create-user` then succeeds — it runs in a throwaway container of its own — but the service is dead, so
the documented `curl http://localhost:8000/health` returns nothing:

```
$ docker ps -a --filter name=harness-ai-harness-ai-1 --format '{{.Status}}'
Exited (1) 50 seconds ago
```

The README now carries a second `docker-compose up -d` in the quickstart block and a paragraph
explaining why the first boot is expected to exit on a new database. This defect predates PRD-007 — the
same ordering would have failed on a fresh SQLite file — but AC 5 is what made anyone run it.

### 4. 🔴 `STREAM_EXPIRED` is not only a test problem — it breaks the running application

The index tracks the idle Hrana stream as a suite-level annoyance. It is not. After the app container
booted and sat through its spaCy model load, the first `POST /query` returned `500`:

```
StorageError: Hrana: `api error: `status=400 Bad Request,
body={"message":"The stream has expired due to inactivity","code":"STREAM_EXPIRED"}``
  File "/app/app/db/database.py", line 1117, in find_user_by_token_hash
```

**It does not recover.** Two further requests failed identically, and a `docker-compose restart` did
not clear it. The database itself was fine throughout — a short-lived process against the same endpoint
read the same rows instantly:

```
audit rows: 0
user resolves: admin
```

The difference is process lifetime, not database state: a `down`/`up` followed by a request issued the
moment `/health` went green succeeded on the first try (`audit_id: 1`). So the failure mode is
**idle-then-request on a long-lived shared client**, and every identity resolution goes through it.

This was demonstrated against the local libSQL dev server; STORY-014's `POST /query` against remote
Turso worked, so the idle window may differ per endpoint. Either way, PRD Section 13's resilience item
is no longer only about transient outages — it is about a client that stops working after sitting
still. **This needs its own story, and it is more urgent than its current filing suggests.** Not fixed
here: this story's blast radius is documentation.

### 5. This host still cannot run the project's Python — now with the exact range

STORY-014 recorded "no wheel for Python 3.14 on Windows". The PyPI file list for `libsql==0.1.11`:

| Platform | CPython wheels published |
|---|---|
| Windows (`win_amd64`) | 3.9, 3.10, 3.11, 3.12, 3.13 |
| macOS | 3.10, 3.11, 3.12, 3.13 |
| Linux (`manylinux_2_17_x86_64`) | 3.8 – 3.14, plus PyPy 3.10/3.11 |

`cp314` exists but is **Linux-only**, which is exactly why this Windows host on 3.14 falls back to the
Rust sdist. The README's `Requirements` bullet now states this range instead of a bare `Python 3.9+`.
Every Python step in this story ran in a container, as in STORY-014.

### 6. The `.env.example` duplicate was an uncommitted edit, so the fix leaves no diff

`TURSO_AUTH_TOKEN` appeared twice, the second time as a bare key with no explanation, and the file
lacked a trailing newline. Both came from an **uncommitted** working-tree change, so removing them
restored the file to its committed state and `git diff .env.example` is now empty. The story's blast
radius is therefore one committed file, not two. Recorded because "no diff" and "not done" look
identical in a commit.

### 7. Handoffs checked and found already correct

STORY-013 forwarded a "no `GET /audit/{id}` route" correction. The README never claimed one —
`### GET /audit` is documented as a list endpoint carrying `audit_id`, which is accurate. No edit was
needed; recorded so the handoff is closed rather than silently dropped.

## End-to-End Verification

Every check in the plan's E2E section, executed.

| # | Check | Result |
|---|-------|--------|
| 1 | Dev server starts from the README's `docker run` line **verbatim** | ✅ `HTTP 200` on `/health` |
| 2 | Whole suite against it | ✅ **1113 passed, 20 skipped, 0 failed** |
| 3 | README's in-container command, verbatim | ✅ 1113 passed; `test_db.py` alone → 97 passed |
| 4 | `sqlite:` `DATABASE_URL` → `ValueError` | ✅ captured verbatim |
| 5 | Remote endpoint, no token → `ValueError` | ✅ captured verbatim |
| 6 | Unreachable endpoint → `DatabaseUnreachableError` | ✅ captured verbatim |
| 7 | README quickstart end to end, fresh database | ✅ see AC 5 below |
| 8 | `grep -rn "sqlite\|harness_data\|harness_ai.db" README.md` | ✅ 8 hits, all justified below |
| 9 | TOC anchors, tables, code fences | ✅ 29/29 anchors resolve; 46 fences balanced |

### AC 5, answered honestly in two halves

No Turso CLI is installed on this host, and provisioning a database on the operator's Turso account is
not something this story should do unilaterally. The plan pre-committed to a split rather than a
substitution, and that is what happened:

**Half A — a genuinely fresh database, full README flow.** A brand-new, empty libSQL server, then the
Docker quickstart executed by reading only the README (`.env` was backed up first and restored
byte-identically afterwards):

```
health           {"status":"ok"}
create-user      Created user 'admin' with role 'admin'.
POST /query      {"status":"SUCCESS","response":"Ok","audit_id":1,"model_used":"openai/gpt-4o",
                  "tokens_used":15,"pii_redacted":false,"pii_entities_masked":[]}
GET /audit       {"total":1,"queries":[{"audit_id":1,"user_id":"admin", ...}]}
GET /stats       {"total_queries":1,"unique_users":1,"success_rate":"100.0%", ...}
```

`audit_id: 1` is the proof the database was actually fresh. This half is what exposed Finding 3.

**Half B — the remote `libsql://` path.** `.env` restored to the operator's real Turso endpoint, stack
brought up, authenticated reads served:

```
remote-path health 200 after 6s
GET /audit   total rows: 17   ids: [17, 16, ..., 2, 1]
GET /stats   {"total_queries":17,"blocked_duplicates":5,"unique_users":5,"success_rate":"82.4%", ...}
```

**No write was made to the production database.** STORY-014 already proved `POST /query` against it
(`audit_id: 17`), and repeating it would add a row to a compliance record to prove something already
recorded. The 17 rows are intact and unchanged.

So AC 5 is met as: *from-zero flow proven against a fresh database, remote Turso path proven to boot and
serve.* Not a single run against a fresh **Turso** database, and this report says so rather than
implying otherwise.

### The `grep` gate, with every hit justified

8 hits, 0 unintentional:

| Line | Hit | Why it is deliberate |
|---|---|---|
| 155 | `sqlite:` URL is a startup error | Quickstart — the error **is** the feature |
| 228 | same rule, stated in full | `Persistence & Deployment` — explains why there is no fallback |
| 250 | "Migrating an existing **SQLite** deployment" | Names what you migrate *from* — the sanctioned historical reference |
| 252 | legacy `harness_ai.db` | Same subsection: what the script reads |
| 255–256 | `--source harness_ai.db` | The script's real CLI, from its own docstring |
| 274 | `sqlite:` value is a startup error | Env table, `DATABASE_URL` row |
| 485 | Troubleshooting entry for that error | The message an operator will actually see |
| 494 | `sqlite3.connect` in a stale-image traceback | Describes a pre-migration image's failure |

`grep -n "named volume" README.md` → 0 hits.

## Validation Results

| Check | Result |
|-------|--------|
| Full test suite (documented command) | ✅ 1113 passed, 20 skipped, 0 failed |
| `tests/test_db.py` | ✅ 97 passed |
| `docker compose config` | ✅ parses; no `volumes` key, no `sqlite:` string |
| `grep` gate | ✅ 8 hits, each justified |
| `named volume` | ✅ 0 hits |
| TOC anchors | ✅ 29/29 resolve |
| Markdown tables | ✅ consistent column counts (one escaped `\|` is pre-existing Roadmap content) |
| Code fences | ✅ 46, balanced |
| Architecture diagram alignment | ✅ labels sit outside the box border; unaffected |
| Fresh-database E2E | ✅ `/health`, `create-user`, `POST /query`, `/audit`, `/stats` |
| Remote Turso E2E | ✅ boots, serves authenticated reads, 17 rows intact |
| `.env` restored after the E2E run | ✅ byte-identical to backup |
| Blast radius | ✅ `git diff --stat` names `README.md` + this story's `.agents/` artifacts |

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `README.md` | UPDATE | +105/−11 |
| `.env.example` | UPDATE (net zero) | Uncommitted duplicate removed — restores the committed state, see Finding 6 |

## Deviations from Plan

1. **A third test-command override.** The plan specified `HARNESS_TEST_LIBSQL_URL` and `DATABASE_URL`;
   measurement showed `TURSO_AUTH_TOKEN=` is also required (Finding 1).
2. **The "Known failures" paragraph was rewritten, not written.** The plan had it repeat the index's
   claim. Executing the suite showed the claim is wrong (Finding 2), so the README documents the
   measured behavior instead. This is the plan's Task 10 being overruled by its own Task 11, which is
   the order those tasks exist in.
3. **Two edits the plan did not contain**, both forced by Finding 3: a second `docker-compose up -d` in
   the Docker quickstart, and a note that pairing the stack with a host-run dev server needs
   `host.docker.internal`.
4. **AC 5 executed as a documented split** rather than one fresh-Turso run — the fallback the plan
   pre-committed to, exercised for the stated reason (no CLI, and not this story's call to provision on
   the operator's account).
5. **`.env.example`'s net diff is zero** (Finding 6), so the plan's "exactly two files" AC resolves to
   one committed file plus a reverted stray edit.
6. **The leak warning was proved with a decoy, not with production.** To verify the README's claim that
   omitting `DATABASE_URL` lets a test run reach the database `.env` names, a second dev server was
   seeded with 3 rows and used as the inherited value. The result — `assert 3 == 1` at
   `tests/test_db.py:1816` — is the same mechanism STORY-014 saw as `assert 17 == 1`, established
   without a second production read.

## Tests Written

None. This story changes documentation only and adds no Python. Its verification is the E2E table
above, executed against a real application and a real database. Findings 3 and 4 name defects that need
tests, in the stories that fix them.

## Acceptance Criteria

- [x] `README.md:177`'s named-volume claim is replaced: state lives in Turso, no volume is involved, container lifecycle does not affect the audit history
- [x] The env table documents `DATABASE_URL` as a required libSQL endpoint with no default, and `TURSO_AUTH_TOKEN` beside it as a required secret for remote endpoints (`DB_BOOTSTRAP_ENABLED` added too)
- [x] Multi-instance guidance states instances may share one database and names what was **not** delivered — load balancing, health checks, Reflex websocket session affinity
- [x] The test instructions give the local libSQL server command and state that no Turso account is needed
- [x] The setup instructions were followed end to end against a fresh database and the application served a query — as a documented split; the fresh-database half returned `audit_id: 1`
- [x] The `grep` gate returns only deliberate references, each listed with its justification
- [x] The in-container pytest command is documented **and works** — 1113 passed — with the three overrides and the reason for each
- [x] All tasks completed
- [x] Blast radius is one committed file plus this story's `.agents/` artifacts
- [x] Follows existing patterns
