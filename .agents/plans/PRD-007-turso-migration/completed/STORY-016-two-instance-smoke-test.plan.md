---
story: STORY-016
prd: PRD-007
slug: two-instance-smoke-test
title: "Prove two instances share one database: concurrent writes, cross-instance duplicate detection, no lost rows"
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-007-turso-migration
created: 2026-09-02
---

# Plan: Prove two instances share one database

## Summary

Add one new test module, `tests/test_two_instance_smoke.py`, that starts **two real
application processes** against the one libSQL endpoint `tests/conftest.py` already
provisions, and drives them from the parent test through a line-delimited JSON command
protocol on stdin/stdout. The protocol is the design decision that matters: every
ordering this story asserts — write on A *then* read on B, create a user *while* both
are running, deactivate *then* authenticate on both — is sequenced by the parent, so the
proofs are deterministic rather than raced. Concurrency is expressed by writing a batch
of commands to both children before reading either's replies, which is genuine
cross-process concurrency without a `sleep` anywhere in the module. The instances are two
`subprocess.Popen` children built the way `tests/test_admin_shell.py:709` and
`tests/test_chat_ui_startup_guard.py:61` already build probes, upgraded from
`subprocess.run` (one shot) to a long-lived conversation, because this story needs both
processes *alive at the same time* rather than merely both having run.

## User Story

As a platform engineer
I want two application instances proven to run correctly against one database
So that the epic's stated goal — scaling past one container — is demonstrated rather than assumed

## Story Reference

- Story file: `.agents/stories/PRD-007-turso-migration/STORY-016-two-instance-smoke-test.md`
- PRD: `.agents/PRDs/PRD-007-turso-migration/PRD.md` — Section 5 story 2, Section 11 (MVP definition), Section 12 Phase 3 & Phase 4, Section 13

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (test-only) |
| Complexity | MEDIUM |
| Systems Affected | `tests/` only. No production code changes are planned; a production change here would be a **finding**, not a task. |
| Story | STORY-016 |
| PRD | PRD-007 |
| Epic Branch | `epic/PRD-007-turso-migration` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| — | `.agents/skills/` was listed and read in full. It contains exactly one skill, `frontend-design`, scoped by its own `description` to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story adds an integration test and renders nothing. No skill applies, and the story's frontmatter `skills: []` is correct. | none |

---

## Patterns to Follow

### Subprocess probe construction (interpreter, cwd, env)

```python
# SOURCE: tests/test_chat_ui_startup_guard.py:61-72
    proc = subprocess.run(
        [sys.executable, "-c", _CHECK_SCRIPT],
        cwd=str(REPO_ROOT / "chat_ui"),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.fail(f"chat_ui startup-guard probe crashed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])
```

Take from this: `sys.executable` (never `"python"`), an explicit `env`, `text=True`, JSON
on stdout, and a `pytest.fail` that prints **both** streams. Change from it: `Popen` with
`stdin=PIPE` instead of `run`, because the child must outlive one command.

### The child's database environment

```python
# SOURCE: tests/conftest.py:65-78
def child_db_env(url: str) -> dict:
    """The `DATABASE_URL` entry a probe subprocess needs."""
    return {"DATABASE_URL": url}
```

```python
# SOURCE: tests/test_admin_shell.py:697-724
@pytest.fixture(scope="module")
def pages_probe(database_url_factory):
    db_url = database_url_factory("admin_pages")
    ...
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(_PYTHONPATH),
            "ADMIN_TOKEN": os.environ.get("ADMIN_TOKEN", "test-token"),
            "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "test-key"),
            **child_db_env(db_url),
        },
```

`database_url_factory` is **session-scoped and required here**: this module's instance
fixture is module-scoped, and a module-scoped fixture requesting a function-scoped one is
a `ScopeMismatch` (`tests/conftest.py:193-215` says so explicitly).

### Statement counting — the measurement instrument

```python
# SOURCE: tests/test_db.py:967-1002
class _RecordingConnection:
    def __init__(self, conn, statements):
        self._conn = conn
        self._statements = statements

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._conn.__exit__(*exc_info)

    def execute(self, sql, *parameters):
        self._statements.append(sql)
        return self._conn.execute(sql, *parameters)

    def cursor(self):
        return self._conn.cursor()


def _count_statements(monkeypatch) -> list:
    statements: list = []
    real_get_connection = database.get_connection
    monkeypatch.setattr(
        database,
        "get_connection",
        lambda: _RecordingConnection(real_get_connection(), statements),
    )
    return statements
```

The child has no `monkeypatch`, so the worker script sets and restores
`database.get_connection` by hand around a measured operation. The recorded shape is
unchanged, so the numbers this story reports are comparable to the ones STORY-010 and
STORY-011 already recorded in the index. `__enter__` / `__exit__` are **not optional
decoration**: `app/db/database.py:441-451`'s `_session()` does `with conn:`, and a proxy
without them turns every measured write into an `AttributeError` rather than a measurement.

### Faking OpenRouter without touching the network

```python
# SOURCE: tests/test_integration.py:46-48
def _fake_call_openrouter(prompt, model="gpt-4", api_key=None):
    return OpenRouterResult(response="mock response", model_used=model, tokens_used=7)
```

Patched at `app.routers.query.call_openrouter` (`tests/test_integration.py:53`). In the
child this is a plain module attribute assignment. **PII redaction is deliberately left
real**, exactly as `tests/test_integration.py` leaves it: this is a smoke test of the
deployed pipeline, and `redact()` loads its analyzer lazily (`app/services/pii_redactor.py:29-33`),
so the cost is one model load per instance, once.

### Concurrency assertion style

```python
# SOURCE: tests/test_db.py:1866-1883
def test_concurrent_init_db_on_an_empty_database_converges(database_url):
    failures = _run_concurrently(8, init_db)
    assert not failures, f"a concurrent init_db() raised: {failures}"
```

This story is the **end-to-end form** of that thread-level test, as its AC 1 says. The
assertion style carries over: collect every child's failure and report them all, rather
than letting the first one mask the rest.

---

## Design

### Why a long-lived worker rather than N one-shot subprocesses

Every existing probe in the suite is `subprocess.run` — start, answer one question, exit.
That shape cannot express this story. "Instance B detects a duplicate written by instance
A" is only evidence if B was **already running** when A wrote: a fresh process that starts
afterward proves the database persisted a row, which is STORY-006's claim, not this one.
The failure modes named in the story's Technical Notes — a per-process client cache, a
per-process schema assumption — are all properties of a process that has *already booted*.
So the child becomes a loop:

```
parent                          child A                child B
  Popen ────────────────────────► import, init_db()  ◄──────── Popen  (simultaneous)
  read "ready" ◄──────────────── {"ready": {...schema...}}
  write {"cmd": "query", ...} ──►
  read ◄──────────────────────── {"status_code": 200, "audit_id": 1, ...}
  write {"cmd": "query", same} ─────────────────────────────►
  read ◄──────────────────────────────────────────────────── {"status": "BLOCKED"}
```

Blocking `readline()` on a pipe is the synchronization primitive; there is no polling and
no timeout to tune, which is what AC 7 asks for.

### The command protocol

One JSON object per line in, one JSON object per line out, strictly one reply per command.
Commands:

| Command | Payload | Reply | Serves |
|---|---|---|---|
| `init_db` | — | `{"ok": true}` or `{"error": "..."}` | AC 1 |
| `schema` | — | tables, `audit_logs` columns, `users` columns (from `PRAGMA table_info`) | AC 1 |
| `query` | `prompt`, `token` | `status_code`, `body`, `elapsed_ms`, `statements` | AC 2, 3, 8 |
| `authenticate` | `token` | `status_code` of a real authenticated request | AC 4, 5 |
| `plant_audit_row` | `prompt_hash`, `timestamp` | `audit_id` | AC 2 (window control) |
| `rows` | — | every `audit_logs` row via `list_audit_logs()` | AC 3, 6 |
| `console_load` | — | `elapsed_ms`, `statements` for one `summary_snapshot()` | AC 8 |
| `stop` | — | — (child exits 0) | teardown |

`query` and `authenticate` go through `TestClient(app)` — the real router, the real
`require_permission` dependency, the real `run_query` pipeline — not through helper
functions. `authenticate` must be an HTTP call, because AC 5's claim is about what an
instance *serves*, and a direct `resolve()` call would skip the dependency chain that
turns a resolved identity into a 401.

`TestClient` is used **without** its context manager, so FastAPI's lifespan does not run
and the child controls `init_db()` itself. That is deliberate: the boot ordering is what
AC 1 measures, and it must be observable rather than hidden inside a lifespan.

### Schema evidence is captured at boot, not asserted later

`tests/conftest.py:129-176`'s autouse `_never_the_configured_database` drops every table
before **every** test. The instances are module-scoped, so they boot before the first
test's reset and their tables are dropped out from under them moments later. This is not a
problem to work around — it is the reason the child reports its post-`init_db()` schema in
its `ready` line. AC 1's assertion then runs against a record of what was true at boot,
which no later reset can erase. Each test afterwards opens with an `init_db` command to
both instances (sent to both before reading either reply — concurrent by construction),
which re-creates the schema and doubles as the warm-up ping described under Risks.

### Credential hygiene in the child's environment

STORY-014's Finding 1 and STORY-015's Finding 1 are both about inherited environment
reaching a real database, and this module spawns processes that build their own
`Settings()` where `monkeypatch` cannot reach — the exact shape of both findings. The child
env is therefore built as `{**os.environ, **child_db_env(url), "TURSO_AUTH_TOKEN": ""}`:
the URL comes from the session fixture, and the token is explicitly blanked so an
inherited production credential cannot travel into a child even if the parent run has one.
The README already documents this same triple for the in-container suite
(`README.md:456-472`); this module enforces it in code rather than trusting the invocation.

### What is measured, and what the numbers mean

AC 8 closes PRD Section 12 Phase 3's "Measured round-trip counts" deliverable, so the
figures must be commensurable with the ones already in the index (1 vs 10 statements,
2.7 ms vs 21.2 ms for the summary; 1 vs 9, 11.0 ms vs 19.1 ms for `/stats`). Two figures:

- **`POST /query`** — wall-clock for the whole request and the count of statements issued
  against the database. The expected count is **two** (PRD Section 5 story 6: one
  duplicate-check read, one audit write); a third would be a finding worth naming.
- **An admin console load** — one `summary_snapshot()`, which is what `AdminState.load()`
  reduces to since STORY-012 (`chat_ui/chat_ui/admin_state.py:1056-1058`). Expected: **one**
  statement.

Both are measured against a same-host local libSQL server, which understates the gap
against a remote endpoint — the index says exactly this about STORY-011's numbers, and the
report must repeat the caveat rather than present these as production latencies.

### Risks + mitigations

| Risk | Mitigation |
|---|---|
| **`STREAM_EXPIRED` on the shared client** — the index records that an idle long-lived client makes `POST /query` return 500 and does not recover, and that this "should be scheduled before STORY-016". This module holds two clients open across a whole test module. | Every test opens by sending `init_db` to both instances, which is also a keep-warm statement, and the module is written to run in well under a minute. If it fires anyway, it is **the finding this story is best placed to characterize** — it would mean the two-instance claim is bounded by an idle window — and it belongs in the report and in a new story, not in a retry loop hidden in the test. |
| **Cost of two spaCy model loads.** `redact()` loads `en_core_web_lg` lazily on the first query in each process. | Module-scoped instances pay it twice for the whole module, not per test. If it proves intolerable, the fallback is to patch `app.services.query_pipeline.redact` in the child — recorded here as a deliberate second choice, because it trades realism for speed and this is a smoke test. |
| **A hung child deadlocks the suite.** A blocking `readline()` against a child that died mid-command never returns. | Every read checks `proc.poll()` first and fails with both captured streams; stderr is drained on failure. A child that crashes produces a legible `pytest.fail`, not a hang. |
| **Windows cannot run this at all.** `libsql==0.1.11` has no wheel for Python 3.14 on Windows, so every step of the last three stories ran in `python:3.11` containers. | Validation commands below are written for the container, per `README.md:439-465`. This is an execution constraint, not a design one. |
| **A flaky duplicate test gets deleted in six months** (the story says so). | No timing race exists to be flaky: ordering is parent-sequenced, and the 24-hour window (`app/services/duplicate_checker.py:28`) is controlled by planting a row with a chosen timestamp rather than by waiting. |

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `tests/test_two_instance_smoke.py` | CREATE | The entire story: worker script, instance harness, and the eight assertions the ACs name |
| `.agents/stories/PRD-007-turso-migration/STORY-016-two-instance-smoke-test.md` | UPDATE | `plan`, `status`, `updated` frontmatter (Phase 5, done by this command) |
| `.agents/PRDs/PRD-007-turso-migration/index.md` | UPDATE | Story row: status + plan link (Phase 5, done by this command) |
| `.agents/reports/PRD-007-turso-migration/STORY-016-two-instance-smoke-test.report.md` | CREATE | Written by `/implement`; carries AC 8's measured numbers |

No production file is on this list. If implementation finds one that must change, that is
a finding to raise before changing it — the story's whole value is that it tests the
system the other fifteen stories built, unaltered.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Module prologue and the worker script

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: CREATE
- **Implement**: Module docstring stating what this file is (the epic's exit criterion) and
  why the instances are processes rather than threads. The `os.environ.setdefault`
  prologue for `OPENROUTER_API_KEY` / `ADMIN_TOKEN` and the `sys.path.insert` +
  `from tests.conftest import child_db_env` import, verbatim from
  `tests/test_chat_ui_startup_guard.py:27-32`. Then `_INSTANCE_SCRIPT`, a module-level raw
  string: the child imports `app.main`, `app.db.database as database`,
  `app.routers.query`, and `app.services.authz`; assigns a local fake over
  `app.routers.query.call_openrouter`; calls `authz.load()` and `init_db()`; builds
  `TestClient(app)` (no context manager); prints one `{"ready": {...}}` line carrying the
  `PRAGMA table_info` schema record and the instance name; then loops on
  `sys.stdin.readline()` dispatching the eight commands, printing one JSON line per
  command with `flush=True`. Any exception inside a command is caught and returned as
  `{"error": "<Type>: <message>"}` so the parent reports it rather than hanging.
- **Mirror**: `tests/test_chat_ui_startup_guard.py:37-58` (script-as-string, JSON-on-stdout,
  errors folded into the payload); `tests/test_integration.py:46-48` (the fake).
- **Validate**: `python -c "import ast,pathlib; ast.parse(pathlib.Path('tests/test_two_instance_smoke.py').read_text())"` parses, and the script string parses too.

### Task 2: The `Instance` harness and the simultaneous-start fixture

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: An `Instance` class wrapping `Popen([sys.executable, "-c", _INSTANCE_SCRIPT], stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True, cwd=REPO_ROOT, env=...)` with
  `send(**command)`, `recv()`, `call(**command)` (send + recv), and `stop()`. `recv()`
  checks `proc.poll()` before reading and `pytest.fail`s with both streams if the child is
  gone. Env is `{**os.environ, **child_db_env(url), "TURSO_AUTH_TOKEN": "", "RBAC_ENABLED": "true"}`.
  Then a module-scoped `instances` fixture taking `database_url_factory` that constructs
  **both** `Instance`s before reading **either** ready line — that ordering is AC 1's
  "start simultaneously" — yields `(a, b)`, and stops both in teardown.
- **Mirror**: `tests/test_admin_shell.py:697-724` for the env dict and the module scope;
  `tests/conftest.py:193-215` for why the factory is the session-scoped one.
- **Validate**: `pytest tests/test_two_instance_smoke.py --collect-only -q` collects with no error.

### Task 3: A `fresh_schema` fixture, and AC 1 — both boot, schema correct

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: A function-scoped autouse `fresh_schema(instances)` fixture that sends
  `init_db` to both instances before reading either reply, then asserts neither returned
  an error — restoring the schema conftest's autouse reset just dropped, concurrently, and
  warming both clients. Then `test_both_instances_boot_against_one_database`, asserting on
  the captured `ready` records: both booted, both report `audit_logs` and `users`, and both
  report the full `AUDIT_LOGS_ADDED_COLUMNS` set — imported from `app.db.models` rather
  than spelled out, so a future column cannot make this test quietly weaker. A second
  assertion that the two schema records are **equal to each other**: two instances that
  each booted fine but converged on different schemas is the failure AC 1 actually guards.
- **Mirror**: `tests/test_db.py:1866-1883` — the thread-level statement of the same claim.
- **Validate**: `pytest tests/test_two_instance_smoke.py -k boot -v` passes.

### Task 4: AC 2 — cross-instance duplicate detection, inside and outside the window

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: A `seeded_user` fixture creating one `user`-role user (via `insert_user` in
  the parent, `tests/test_integration.py:26-34`'s shape) and returning its plaintext token.
  `test_a_prompt_answered_by_instance_a_is_blocked_by_instance_b`: `query` a distinctive
  prompt on A (expect `SUCCESS` and an `audit_id`), then the identical prompt on B, and
  assert B returns the blocked outcome with `first_query_at` pointing at A's row. Then
  `test_a_prompt_outside_the_window_is_not_blocked_by_the_other_instance`: `plant_audit_row`
  on A with a timestamp 25 hours old, then the matching prompt on B, and assert it
  succeeds — proving the block in the first test came from the window and the shared table,
  not from any prompt hash matching anything ever.
- **Mirror**: `tests/test_integration.py:71-82` for the duplicate assertion shape;
  `app/services/duplicate_checker.py:28` for the 24-hour cutoff being computed, not configured.
- **Validate**: `pytest tests/test_two_instance_smoke.py -k duplicate -v` passes.

### Task 5: AC 3 and AC 6 — concurrent writes, every row present exactly once, ids unique

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: `test_concurrent_queries_from_both_instances_lose_no_rows`. Build `2N`
  distinct prompts (N = 10, each carrying its instance name and index so a row can be
  traced to its writer), `send` all N to A and all N to B **before** reading any reply —
  interleaved at the pipe level, so both processes have work in flight simultaneously —
  then drain both. Assert: every reply is a success; `rows` from either instance returns
  exactly `2N` rows; the set of `prompt_preview` values equals the set of prompts sent; no
  `prompt_hash` appears twice; `audit_logs.id` values are unique and number `2N`; and every
  row's `user_id`, `model_used` and `success` match what was submitted, which is AC 6's
  "no row is corrupted" stated as a comparison rather than as a vibe. Read the rows from
  **B** after writing from both, so the assertion also re-proves the shared view.
- **Mirror**: `tests/test_integration.py:37-40` (`_count_audit_rows`) and `tests/test_db.py:1723-1746`
  (collect all failures, report them together).
- **Validate**: `pytest tests/test_two_instance_smoke.py -k concurrent -v` passes; run it
  three times consecutively and confirm identical results (AC 7).

### Task 6: AC 4 — a CLI-created user authenticates against both instances

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: `test_a_user_created_by_the_cli_resolves_on_both_running_instances`. With
  both instances already running, `subprocess.run` `scripts/manage_users.py create-user
  --user-id ... --role user` with the same child env, parse the plaintext token from its
  stdout (`scripts/manage_users.py:45` prints `Token (save this now -- it cannot be
  recovered): <token>`), then issue an authenticated request with that token to **each**
  instance and assert both accept it. The point is the negative: neither instance restarted,
  so a per-process identity cache would fail here.
- **Mirror**: `tests/test_manage_users_cli.py` for CLI invocation; `app/services/identity.py:58`
  (`find_user_by_token_hash`) for what is being proved to be uncached.
- **Validate**: `pytest tests/test_two_instance_smoke.py -k created_by_the_cli -v` passes.

### Task 7: AC 5 — a CLI-deactivated user is rejected by both instances

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: `test_a_deactivated_user_is_rejected_by_both_running_instances`. Reuse the
  CLI-created user, confirm it authenticates on both, then run `manage_users.py
  deactivate-user`, then authenticate again against **both** and assert both return 401.
  Assert against both explicitly and separately, with the instance name in the assertion
  message: the story is emphatic that revocation taking effect on one instance only is a
  security failure, so a test that checked one instance would be the bug.
- **Mirror**: `app/services/identity.py:44-58` — `resolve()` folds deactivated into `None`,
  and `app/middleware/auth.py:15-19` turns that into 401.
- **Validate**: `pytest tests/test_two_instance_smoke.py -k deactivated -v` passes.

### Task 8: AC 8 — the measured numbers

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: In the worker, a `_RecordingConnection` and a `_measured()` helper that
  swaps `database.get_connection` for the duration of one operation and restores it in a
  `finally` — the child's hand-rolled equivalent of `tests/test_db.py:994-1002`. Wire it
  into the `query` and `console_load` commands so each reply carries `elapsed_ms` and
  `statements`. Then `test_round_trip_cost_is_measured_and_reported`: run one warm
  `POST /query` and one `console_load` on instance A, assert the console load issues
  exactly **one** statement and `POST /query` exactly **two** (the duplicate-check read and
  the audit write PRD Section 5 story 6 names), and print the four numbers through
  `pytest`'s output so `/implement` can transcribe them into the report. An unexpected
  count fails the test with the recorded SQL attached, because "we issue two round trips
  per query" is a claim the PRD makes and this is where it is checked.
- **Mirror**: `tests/test_db.py:1136-1152` (`test_summary_snapshot_issues_one_round_trip`),
  whose numbers these must be comparable to.
- **Validate**: `pytest tests/test_two_instance_smoke.py -k round_trip -v -s` passes and
  prints the figures.

### Task 9: Determinism pass (AC 7)

- **File**: `tests/test_two_instance_smoke.py`
- **Action**: UPDATE
- **Implement**: Audit the finished module for anything that could make it non-deterministic
  and remove it: no `time.sleep`, no wall-clock threshold asserted as a pass/fail bound
  (the measurements are *recorded*, and only the **statement counts** are asserted), no
  dependence on which instance wins a race, no hosted-Turso reference. Confirm the endpoint
  comes only from `database_url_factory` and that a `HARNESS_TEST_LIBSQL_URL` override
  reaches the children. Add a short comment block recording these constraints for the next
  reader.
- **Mirror**: `tests/conftest.py:1-33` — the module docstring convention of stating the
  invariant and why the mechanism behind it was chosen.
- **Validate**: `grep -n "sleep\|turso.io\|libsql://" tests/test_two_instance_smoke.py` returns nothing.

### Task 10: Full-suite regression

- **File**: — (no file)
- **Action**: VERIFY
- **Implement**: Run the whole suite in the container with the three documented overrides
  and confirm the new module is additive: the recorded baseline is **1113 passed, 20
  skipped, 0 failed** (STORY-015 report, Finding 2), so the expected result is that count
  plus this module's tests. A pre-existing failure that reappears is reported, not fixed
  here.
- **Validate**: the command in **Validation** below.

---

## End-to-End Tests

- [ ] Both instances start simultaneously against one empty database; both boot, and their post-`init_db()` schema records are identical and complete
- [ ] Prompt P → instance A returns `SUCCESS`; the same P → instance B returns blocked, citing A's timestamp
- [ ] A row planted 25 hours old does **not** cause the matching prompt to be blocked on the other instance
- [ ] 20 concurrent queries across both instances → exactly 20 `audit_logs` rows, 20 distinct ids, 20 distinct prompt hashes, every field matching its submission
- [ ] `manage_users.py create-user` run while both instances are live → the new token authenticates against both without a restart
- [ ] `manage_users.py deactivate-user` → 401 from **both** instances
- [ ] One `POST /query` measured: 2 statements, wall-clock recorded
- [ ] One admin console load measured: 1 statement, wall-clock recorded
- [ ] The module passes three consecutive runs with identical results, against the local libSQL dev server, with no Turso account present

## Validation

```bash
# The shared endpoint both instances and the parent use (README.md:440-444)
docker run -d --name harness-libsql-dev -p 8080:8080 -e SQLD_NODE=primary \
  ghcr.io/tursodatabase/libsql-server@sha256:6dd3eb276d9d3604e4a48ac4a999a2e267814732d57d7e94c04ba71482333a67

# This module (this host cannot run the project's Python: libsql has no
# Windows wheel for 3.14, so every step runs in the container -- STORY-015 Finding 5)
docker-compose run --rm \
  -e HARNESS_TEST_LIBSQL_URL=http://host.docker.internal:8080 \
  -e DATABASE_URL=http://host.docker.internal:8080 \
  -e TURSO_AUTH_TOKEN= \
  harness-ai pytest tests/test_two_instance_smoke.py -v -s

# The full suite -- baseline 1113 passed, 20 skipped, 0 failed
docker-compose run --rm \
  -e HARNESS_TEST_LIBSQL_URL=http://host.docker.internal:8080 \
  -e DATABASE_URL=http://host.docker.internal:8080 \
  -e TURSO_AUTH_TOKEN= \
  harness-ai pytest tests/ -q
```

All three overrides are mandatory and non-negotiable: `README.md:467` records that
without `DATABASE_URL` an in-container run **can reach a production database**, which
STORY-014 demonstrated by accident.

---

## Acceptance Criteria

(Copied from story `STORY-016`)

- [ ] Given two application instances against one database, when both start simultaneously, then both boot successfully and the schema is correct — the end-to-end form of STORY-007's convergent `init_db()`.
- [ ] Given a prompt submitted to instance A, when the same prompt is submitted to instance B inside the detection window, then B blocks it as a duplicate.
- [ ] Given concurrent query traffic to both instances, when it completes, then every query produced exactly one `audit_logs` row — none lost, none duplicated.
- [ ] Given a user created through `scripts/manage_users.py` while both instances are running, when that user authenticates against either instance, then the credential resolves.
- [ ] Given a user deactivated through the CLI, when they attempt to authenticate against **both** instances, then both reject them.
- [ ] Given concurrent writes from both instances, when the audit trail is read afterward, then `audit_logs.id` values are unique and no row is corrupted.
- [ ] Given the test, when it runs in CI, then it is deterministic and does not depend on a hosted Turso database.
- [ ] Given the results, when they are recorded, then the report states the measured round-trip cost of a `POST /query` and an admin console load, closing PRD Section 12 Phase 3's "Measured round-trip counts" deliverable with real numbers.
- [ ] All tasks completed
- [ ] The full suite passes at or above its 1113-passed baseline
- [ ] No production file changed (any need to change one is raised as a finding first)
- [ ] Follows existing patterns
