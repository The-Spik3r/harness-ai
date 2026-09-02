---
story: STORY-014
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-014-deployment-cutover.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: fd9ab85
status: COMPLETE
completed: 2026-09-02
---

# Implementation Report — STORY-014: Cutover: remove the `harness_data` volume, the build placeholder, and `harness_ai.db`

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-014-deployment-cutover.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `fd9ab85`

## Summary

Two committed files changed and two database files were deleted. `docker-compose.yml` lost its
`environment:` block, its `harness_data` mount and the top-level `volumes:` key, so `DATABASE_URL` and
`TURSO_AUTH_TOKEN` now arrive through the same `env_file: .env` that already carried
`OPENROUTER_API_KEY` and `ADMIN_TOKEN`. The Dockerfile's builder placeholder became
`DATABASE_URL=http://127.0.0.1:8080` plus `DB_BOOTSTRAP_ENABLED=false`, which un-breaks an image build
that STORY-005 had left red and satisfies PRD Section 11's build-without-a-database requirement.

**The data this cutover was actually protecting was not in the repository.** The
`harness-ai_harness_data` volume held **16 `audit_logs` rows and 1 `users` row** (latest
`2026-09-01T03:23:35Z`), against 8 rows in the repo-root `harness_ai.db` that STORY-013 rehearsed with
and 6 more in a shadow `chat_ui/harness_ai.db`. That file was extracted and checksummed first, migrated
into the operator's real Turso database, verified through the script and again through the application
and the admin console, and only then were the repository files deleted.

Unlike STORY-013's rehearsal, **this ran against production Turso**
(`libsql://harness-ai-tobiaspasinato.aws-us-east-2.turso.io`). The stack boots against it, `POST /query`
returned `audit_id: 17` continuing straight on from the migrated id 16, and the admin console renders
all 17 rows and all ten summary figures.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Volume database extracted and checksummed to an archive outside the tree | — | ✅ |
| 2 | Migration run against production Turso; source SHA-256 unchanged | — | ✅ |
| 3 | Migrated data verified through the application surface | — | ✅ |
| 4 | `environment:`, the mount and the `volumes:` key removed | `docker-compose.yml` | ✅ |
| 5 | Builder placeholder + `DB_BOOTSTRAP_ENABLED=false` | `Dockerfile` | ✅ |
| 6 | Both `.db` files deleted; ignore rules and git history confirmed | — | ✅ |
| 7 | Both local `.env` files repointed (pulled forward — Task 2 depended on it) | `.env`, `chat_ui/.env` | ✅ |
| 8 | Build proved to need no database, by controlled comparison | — | ✅ |
| 9 | `docker compose down -v` proved to destroy nothing | — | ✅ |
| 10 | Stack, `POST /query` and the admin console exercised against Turso | — | ✅ |
| 11 | `sqlite` sweep, with every exception named | — | ✅ |
| 12 | In-container pytest checked; findings routed to STORY-015 | — | ✅ |
| 13 | Suite module-by-module; blast radius proved | — | ✅ |

## The migration, pasted verbatim

Source: the file extracted from the `harness-ai_harness_data` volume, archived at
`C:/Users/tobip/harness-ai-prd007-cutover-archive/volume-harness_ai.db`
(`sha256 08ad5f62fd1893a07febd1aa8bd014733853d626fa37191d911ad80eaead42a9`).

```
Dry run -- nothing was written.
  audit_logs: 16 row(s), 19 column(s) copied
  users: 1 row(s), 5 column(s) copied
  destination: libsql://harness-ai-tobiaspasinato.aws-us-east-2.turso.io, empty
```

```
Source      /archive/volume-harness_ai.db
            sha256 08ad5f62fd1893a07febd1aa8bd014733853d626fa37191d911ad80eaead42a9  (unchanged)
            16 audit_logs row(s), 1 users row(s)
Destination libsql://harness-ai-tobiaspasinato.aws-us-east-2.turso.io
            16 audit_logs row(s), 1 users row(s)
            audit_logs AUTOINCREMENT sequence: already correct at 16
Copied      17 row(s) in 2 statement(s)
Verified    counts OK · content OK · id preservation OK · read-back OK (4 of 16 sampled) · token_hash OK
Rollback    The source file was opened read-only and is unmodified.
```

Verified again through the application, not only the script:

```
count_audit_logs(): 16
get_audit_log(16) fields: {'id': 16, 'timestamp': '2026-09-01T03:23:35Z', 'user_id': 'admin'}
get_audit_log(1) present: True
ids present: [1, 2, ..., 16]          # contiguous, preserved, not regenerated
migrated user: admin / admin / hash len 64
find_user_by_token_hash resolves: True
```

### The 14 rows that were archived rather than migrated

`scripts/migrate_to_turso.py` refuses a non-empty destination and has no `--force`, so exactly one of
the three files could be copied. The volume's file was chosen: newest, largest, and the only one
carrying a `users` row. The other two are **archived, not migrated**, and this is stated rather than
left to be inferred from the deletion:

| Archived file | Rows | sha256 |
|---|---|---|
| `volume-harness_ai.db` (migrated) | 16 `audit_logs`, 1 `users` | `08ad5f62…ead42a9` |
| `root-harness_ai.db` (archived only) | 8 `audit_logs`, 0 `users` | `f55928bb…518c75d` |
| `chat_ui-harness_ai.db` (archived only) | 6 `audit_logs`, no `users` table | `1686d15f…3ea6e96e` |

Those 14 rows are development-era traffic from 2026-08-21 to 2026-08-31. Recovering them would need an
append mode the script deliberately does not have, which is its own story if anyone wants it.

## The build-without-a-database question, answered by experiment

The story asked for the `init_db()`-at-import versus startup-guard interaction to be resolved
deliberately. It was resolved in STORY-008 by `DB_BOOTSTRAP_ENABLED`; this story sets it. Proved by
running the same import twice on `--network none`, changing only the flag:

```
$ docker run --network none ... -e DB_BOOTSTRAP_ENABLED=false harness-ai:cutover \
    python -c "import chat_ui.chat_ui"
imported chat_ui.chat_ui with no network: OK

$ docker run --network none ... harness-ai:cutover python -c "import chat_ui.chat_ui"
app.db.errors.DatabaseUnreachableError: Cannot reach the database at http://127.0.0.1:8080. The
application will not start: PRD-007 removed the local-file fallback deliberately, so there is nothing
to degrade to. Check DATABASE_URL and that the endpoint is reachable from this host.
```

`docker build` itself exited 0 with the libSQL dev server stopped and nothing listening on 8080.
The final image carries **none** of the placeholders — `DATABASE_URL`, `DB_BOOTSTRAP_ENABLED`,
`OPENROUTER_API_KEY` and `ADMIN_TOKEN` are all absent from `docker inspect`'s env, so Plan R3 (the flag
leaking into a running deployment) is closed by inspection, not by assertion.

STORY-008 asked this story's first real deployment to confirm the guard's message text. Confirmed
verbatim above: it names `DATABASE_URL`, states that there is no fallback, and quotes the driver.

## `docker compose down -v` destroys nothing

```
count before down -v : 17
docker compose down -v  →  container removed, network removed
count after up -d    : 17
row written before teardown: audit_id 17, story014-smoke, 2026-09-02T10:33:05Z  (intact)
```

PRD Section 5 story 1's acceptance, in one command.

## The `sqlite` sweep

`grep -rn "sqlite" app/ chat_ui/ docker-compose.yml Dockerfile` — no production-path hits. Every
remaining hit, named as AC 6 requires:

| Hit | Why it is not a production path |
|---|---|
| `chat_ui/.web/` (15 hits) | Reflex's generated `node_modules`; not source, not shipped (`.dockerignore:12`). **Excluded, said out loud.** |
| `app/config.py:11-13,86` | Names the scheme **in order to reject it**. That is the feature. |
| `app/db/database.py:77,180,228,445`, `app/db/errors.py:4,24,27,66,84` | Comments describing what the driver swap replaced, inside `app/db/`, which PRD Section 11 permits explicitly. |
| `app/**/__pycache__/*.pyc` | Compiled bytecode of the above; gitignored. One (`chat_ui/chat_ui/__pycache__/admin_state.cpython-314.pyc`) is **stale** — its current source has no such string. |
| `chat_ui/.env:5` | Now only a comment saying a `sqlite:///` value is a startup error, from Task 7's rewrite. Untracked. |
| `scripts/migrate_to_turso.py:38` | The one `import sqlite3` — the exception this story's own AC 6 sanctions. |

`docker-compose.yml` and `Dockerfile`: zero hits.

The import-level check, which is the meaningful one:

```
$ grep -rn "^import sqlite3\|^from sqlite3" app/ chat_ui/ scripts/ tests/
scripts/migrate_to_turso.py:38:import sqlite3
tests/test_db.py:8:import sqlite3
tests/test_migrate_to_turso_cli.py:17:import sqlite3
```

One production hit, the sanctioned one. `tests/` is outside the AC's scope.

## `harness_ai.db` and git history — a positive finding

Both files are deleted and both ignore rules still fire:

```
$ find . -name "*.db" -not -path "./.git/*" -not -path "./chat_ui/.web/*"
(nothing)
$ git check-ignore -v harness_ai.db chat_ui/harness_ai.db
.gitignore:6:*.db          harness_ai.db
chat_ui/.gitignore:4:*.db  chat_ui/harness_ai.db
$ git status --porcelain          # no deletions staged
```

`.gitignore` needed **no edit** — `*.db` was already at `:6`, so the AC's gitignore half was satisfied
before this story started.

The story's Technical Notes ask whether a committed database file put real audit rows or `users` token
hashes into git history. **It did not, and the question does not arise:**

```
$ git log --all --oneline --diff-filter=A -- '*.db'
(empty)
$ git rev-list --all --objects | grep -c '\.db$'
0
```

Neither file was ever tracked. No history rewrite is needed, and no token hash has ever been in the
repository.

## Findings

### 1. 🔴 The test suite can reach a production database — pre-existing, and it fired here

**This is the most important thing in this report.** PRD Section 7.6 requires the test infrastructure to
be "structurally incapable of reaching a production database", and `tests/conftest.py:129-157`'s
`_never_the_configured_database` docstring promises that "no test can reach another test's rows, or
anyone's real database". Running the README's documented in-container command with the cutover's own
compose stack — which now injects real Turso credentials through `env_file` — one test read the
production database:

```
$ docker compose run --rm -e HARNESS_TEST_LIBSQL_URL=http://host.docker.internal:8080 \
      harness-ai pytest tests/test_db.py -q
E       assert 17 == 1
E        +  where 17 = count_audit_logs()
tests/test_db.py:1816  test_two_init_db_calls_interleaved_between_read_and_alter_both_succeed
1 failed, 96 passed
```

17 is the production row count.

**Mechanism.** `conftest.py:55` uses `os.environ.setdefault("DATABASE_URL", _ENDPOINT)`, which cannot
override a `DATABASE_URL` the container already inherits — and compose's `env_file` supplies the
production one. The autouse fixture still redirects `settings.DATABASE_URL` per test, so the suite is
safe in general. But `tests/test_db.py:1809` calls `monkeypatch.undo()`, and pytest's `monkeypatch` is
**one instance shared by a test and all its fixtures**, so that `undo()` also reverts the safety
fixture's patch. Everything after that line runs against whatever `DATABASE_URL` the process was
configured with.

**Proved by controlled comparison** — same file, same container, only `DATABASE_URL` differing:

| `DATABASE_URL` | Result |
|---|---|
| production Turso (inherited from `env_file`) | 96 passed, **1 failed** (`assert 17 == 1`) |
| `http://host.docker.internal:8080` (forced) | **97 passed** |

**Blast radius here was reads only, and it was verified, not assumed.** After the run, production holds
17 `audit_logs` rows with ids 1–17 and 2 `users` (`admin` plus this story's smoke user) — no test rows,
no test users, no dropped tables. The reachable-but-not-written outcome is luck of which statements
followed the `undo()`, not a guarantee: `_reset_database()` drops every table, and a differently
ordered test would have dropped the production schema.

**Not fixed here, deliberately** — this story's declared blast radius is two infrastructure files, and
the fix belongs with a regression test (`monkeypatch.undo()` must not be able to revert the safety
fixture; `setdefault` should arguably be an unconditional override for the test process). **It needs its
own story, and it should be scheduled before STORY-016**, which runs two instances against one database
and will be handling credentials the same way.

Mitigation until then: run the suite with `DATABASE_URL` explicitly forced to the dev server, which is
how Task 13 was run.

### 2. The README's in-container pytest command is broken — for STORY-015

`Dockerfile:69-71` and `README.md:386` promise `docker-compose run --rm harness-ai pytest tests/ -v`.
As written it now fails, legibly:

```
Exit: The libSQL dev server at http://127.0.0.1:8080 is unreachable (... Connection refused ...).
Start it with: docker run -d --name harness-libsql-dev -p 8080:8080 ...
or point HARNESS_TEST_LIBSQL_URL at another one.
```

Inside the container `127.0.0.1` is the container's own loopback. `conftest.py` already provides the
escape hatch and names it in the message. The documented command needs
`-e HARNESS_TEST_LIBSQL_URL=http://host.docker.internal:8080` (and, on Linux, an `extra_hosts` entry for
`host.docker.internal`) — plus, per Finding 1, an explicit `DATABASE_URL` override. The Dockerfile's
`WORKDIR /app` comment and the README both need this. **STORY-015's, not changed here.**

Also forwarded to STORY-015, from STORY-013: there is no `GET /audit/{id}` route (`GET /audit` is a list
carrying `audit_id`; ids are addressed through `get_audit_log()`), and the suite's known failures are
not all `STREAM_EXPIRED`.

### 3. `docker compose up` silently ran a stale image

The first `up -d` started a container running **pre-STORY-006 code** — it crashed in
`sqlite3.connect(_db_path())`, a line that no longer exists in `app/db/database.py`. Compose reuses an
existing image rather than rebuilding when the `build:` context changes; `up -d --build` was required.
Worth knowing for STORY-016 and for any deployment runbook: after this epic, an `up` without `--build`
can resurrect a pre-migration image that will now fail at boot rather than silently write to a file.

### 4. The host cannot run this project's Python at all

`libsql==0.1.11` publishes no wheel for this machine's Python 3.14 on Windows, and the sdist's Rust
build fails at `link.exe`. Every Python step in this story therefore ran inside `python:3.11`
containers, matching the Dockerfile. Not a defect and not this story's to fix, but it is why no command
in this report runs `python` on the host, and it is worth a line in STORY-015's development-setup notes.

### 5. Two local `.env` observations

`chat_ui/.env` was a **drifted copy**, not a supplement: it carried a stale `sqlite:///harness_ai.db`
and lacked every RBAC and PII setting the root file has. Because Reflex runs with CWD `chat_ui/`,
pydantic-settings reads *that* file, so it silently beats the root one. Both were repointed (Task 7);
consolidating them is a STORY-015 item.

Separately, `Settings` rejects unknown keys (`extra_forbidden`), so a stray `TURSO_DATABASE_URL=` in
`.env` is a hard startup crash, not an ignored line. One was present and was removed. `.env.example`
currently carries a **duplicate** `TURSO_AUTH_TOKEN=` entry (it is already documented near the top);
that edit is not part of this commit and is left for its author to resolve.

## Validation Results

| Check | Result |
|-------|--------|
| `docker compose config` | ✅ parses; no `volumes` key, no `sqlite:` string |
| `docker build` with no database reachable | ✅ exit 0 |
| Import on `--network none` with the flag | ✅ succeeds |
| Import on `--network none` without the flag | ✅ fails with STORY-008's guard (control) |
| Final image env free of all four placeholders | ✅ |
| Migration script against production Turso | ✅ exit 0, all verification layers clean |
| Application-level verification of migrated data | ✅ 16 rows, ids 1–16, user resolves |
| `GET /health` | ✅ 200 `{"status":"ok"}` |
| `POST /query` | ✅ `audit_id: 17`, continuing from migrated id 16 |
| Deactivated token rejected | ✅ 401 |
| Admin console register | ✅ 17 rows render, ids 1–17, no console errors |
| Admin console summary | ✅ all ten figures render |
| `docker compose down -v` | ✅ 17 rows before, 17 after |
| Suite, module by module (42 modules) | ✅ 2 pre-existing collection errors, no new failure |
| `tests/test_db.py` with `DATABASE_URL` forced to the dev server | ✅ 97 passed |
| Blast radius | ✅ `git diff HEAD --stat` names 2 code files |

Suite detail: 40 modules fully green (including `test_db.py` 97, `test_register.py` 178,
`test_admin_state.py` 105, `test_migrate_to_turso_cli.py` 21). `test_pii_badge.py` and
`test_success_metadata_footer.py` fail at collection with `ModuleNotFoundError: No module named
'chat_ui.chat_ui.models'; 'chat_ui.chat_ui' is not a package` — the exact pre-existing packaging error
STORY-013 recorded. `test_chat_state.py` passed here (38), so this run is one better than the recorded
three-failure baseline.

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `docker-compose.yml` | UPDATE | +4/-7 |
| `Dockerfile` | UPDATE | +14/-1 |
| `harness_ai.db` | DELETE | (untracked; 8 rows, archived) |
| `chat_ui/harness_ai.db` | DELETE | (untracked; 6 rows, archived) |
| `.env`, `chat_ui/.env` | UPDATE | (untracked; local dev) |
| `.gitignore`, `.dockerignore` | NO CHANGE | already correct |

## Deviations from Plan

1. **Task 7 was pulled forward, ahead of Task 2.** `.env` still pointed at `sqlite:///`, so the
   migration could not have found a destination. The plan's ordering assumed the env files were only a
   developer-convenience fix; they are a precondition.
2. **All Python ran in containers** rather than on the host — see Finding 4. The plan's commands assumed
   a working host interpreter.
3. **Task 9's `docker volume rm` was not run.** Removing the orphaned `harness-ai_harness_data` volume
   is irreversible and is not required by any acceptance criterion — `down -v` destroying nothing was
   already proved. The operator chose to keep it as a third copy. Outstanding operator step:
   `docker volume rm harness-ai_harness_data`.
4. **A smoke-test user was created and then deactivated.** `POST /query` needs a per-user token;
   `story014-smoke` was created in production, used for one query, and deactivated (its token now
   returns 401). Its audit row (id 17) stays, as an audit trail should.
5. **Task 12's outcome was worse than anticipated.** The plan expected a documentation finding; it also
   produced Finding 1, a test-safety defect that needs its own story.

## Tests Written

None. This story changes two infrastructure files and deletes untracked data files; it adds no Python.
The verification is the E2E checklist above, executed against a real Turso database. Finding 1 names the
regression test that should exist, in the story that fixes it.

## Acceptance Criteria

- [x] `docker-compose.yml` has no `harness_data` volume, no service mount, and no `DATABASE_URL: sqlite:////app/data/harness_ai.db`; the Turso variables arrive through `env_file` (verified by `docker compose config`)
- [x] The Dockerfile's `DATABASE_URL=sqlite:///:memory:` is replaced with a value that satisfies STORY-005's validation
- [x] `docker build` succeeds with no reachable database; the `init_db()`/guard interaction is resolved deliberately by `DB_BOOTSTRAP_ENABLED=false`, and proved by controlled comparison
- [x] `harness_ai.db` is gone from the repository root, and `*.db` is gitignored (no edit was needed)
- [x] The deletion happened **after** the migration and verification were run and recorded — against the volume's file, which is the one that mattered
- [x] `grep -rn "sqlite" app/ chat_ui/ docker-compose.yml Dockerfile` shows no production-path hits; every exception named explicitly
- [x] `docker compose down -v` destroyed no application data — 17 rows before, 17 after
- [x] The stack boots against real Turso credentials, serves `POST /query`, and renders the admin console
- [x] All tasks completed
- [x] Suite shows no new failure against its known baseline
- [x] Follows existing patterns
