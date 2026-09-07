---
story: STORY-024
prd: PRD-008
slug: stale-client-recovery
title: "Recover the shared libSQL client when its stream dies, so an idle process is not a dead one"
type: REFACTOR
complexity: MEDIUM
epic_branch: epic/PRD-008-chat-sessions
created: 2026-09-06
---

# Plan: Recover the shared libSQL client when its stream dies

## Summary

`app/db/database.py` caches one libSQL client per process forever. Its Hrana stream is server-side
state that the server expires after an idle window (and loses outright across a restart), and nothing
in this module ever sets `_client = None` — so the first request after a quiet period fails, and every
request after it fails the same way until the process is restarted. This plan adds recovery in **two
seams, one primary and one net**, both inside `_shared_client()` / `_translated()` and nowhere else:
(1) **validate-on-acquire, gated by idle time** — past `_IDLE_PROBE_AFTER_SECONDS` of not being
handed out, the cached client is proved with a bare `SELECT 1` *before* the caller's transaction
opens, and a driver-shaped failure there discards it and builds one replacement, once; and (2)
**invalidate-without-retry in `_translated()`** — a statement that fails with one of the two captured
dead-stream messages drops the cached client so the *next* call rebuilds, while the current call still
raises `StorageError` exactly as today. Seam 1 is what makes AC 1 true; seam 2 is what keeps AC 6
true, because a statement that has already run inside an open transaction must never be replayed.
No new exception type, no consumer change, no `app/db/errors.py` change.

## User Story

As an employee
I want the chat to still work after nobody has used it for a while
So that being the first person to open it in the morning is not the same as it being broken.

## Story Reference

- Story file: `.agents/stories/PRD-008-chat-sessions/STORY-024-stale-client-recovery.md`
- PRD: `.agents/PRDs/PRD-008-chat-sessions/PRD.md` (Section 12 Phase 4 — "the whole thing holds under failure")
- Revisits PRD-007 Section 6 Pattern 1 and Section 7.2

## Metadata

| Field | Value |
|-------|-------|
| Type | REFACTOR (reliability; no new capability, no surface change) |
| Complexity | MEDIUM |
| Systems Affected | `app/db/database.py` only, plus new tests in `tests/test_db.py` |
| Story | STORY-024 |
| PRD | PRD-008 |
| Epic Branch | `epic/PRD-008-chat-sessions` (commit directly on this branch) |

---

## Skills In Use

`.agents/skills/` was listed and every `SKILL.md` in it read in full. It contains exactly one skill.

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| `frontend-design` | **Does not apply.** Its `description` scopes it to "distinctive, intentional visual design when building new UI or reshaping an existing one". This story changes one storage module, renders nothing, and adds no string a user can see. | none |

The story's `skills:` frontmatter is empty, and this scan confirms it rather than assuming it.

---

## Prior Evidence (gathered during exploration — this is what the design is built on)

**The failure text, captured live, twice, by two different stories.** The PRD-007 `STORY-009` report
and the PRD-008 `STORY-014` report record the same driver output verbatim:

```
ValueError: Hrana: `api error: `status=400 Bad Request,
    body={"message":"The stream has expired due to inactivity","code":"STREAM_EXPIRED"}``
```

**It is Hrana's behaviour, not the local container's — now documented, not inferred.** The story's
first task was to decide whether the hosted endpoint shares the failure. It does, by construction:
the expiry lives in `libsql-server/src/hrana/http/stream.rs`, which resolves a baton to a stream
handle and returns `StreamExpired` for `Handle::Expired` and `BatonInvalid` when the handle is not
found at all — the same server code Turso runs. `HRANA_3_SPEC.md` states the protocol reason: HTTP is
stateless, so the stream is server-side state addressed by a baton, and a server that has dropped or
forgotten that state cannot be talked back into it by a client that keeps presenting the old baton.
That is why the post-restart message is *"Received an invalid baton"* and not a second expiry notice,
and it is why **no client-side retry on the same client can ever work** — only building a new one,
which starts a new stream with `baton: null`, recovers.

What is *not* verified and must not be claimed: the **length** of the hosted idle window. The server
publishes no constant, PRD-007 STORY-014's `POST /query` against remote Turso worked (short-lived,
never idle), and this repo cannot measure Turso's window without a deployment. The design is written
so the window's length does not matter — the probe threshold is a floor on how often we check, not a
guess at when the server gives up.

**The blast radius is every request, not the storage layer.** The PRD-007 index records it plainly:
after the app idled through its spaCy model load, `POST /query` returned 500 from
`find_user_by_token_hash`, two further requests failed identically, and `docker-compose restart` did
not clear it while a short-lived process read the same rows instantly. Identity resolution goes
through this client, so a dead stream is a signed-out application.

**The suite cannot see it and never could.** `tests/conftest.py`'s autouse reset queries before every
test, so the client is never idle. That is why every AC below is written against a simulated dead
stream, and why the one wall-clock assertion is manual (AC 9).

---

## Patterns to Follow

### The cache, the lock, and what the lock is for

```python
# SOURCE: app/db/database.py:38-71
_client_lock = threading.Lock()
_client_key: Optional[tuple[str, str]] = None
_client: Optional[Any] = None


def _shared_client() -> Any:
    """The process-wide libSQL client, constructed once and reused.
    ...
    **One client for the whole process, not one per thread.** STORY-006 measured
    both against the local server with eight threads writing concurrently: the
    shared client completed all 200 writes with no error, while a client per
    thread lost 169 of them to `TRANSACTION_TIMEOUT`.
    ...
    """
    global _client_key, _client
    key = (settings.DATABASE_URL, settings.TURSO_AUTH_TOKEN)
    with _client_lock:
        if _client is None or _client_key != key:
            # Not closing the previous client: close() discards uncommitted work
            # (STORY-001 §2.2) and the key only changes under test.
            _client = libsql.connect(key[0], auth_token=key[1])
            _client_key = key
        return _client
```

Two rules this story inherits: **every mutation of `_client` happens under `_client_lock`** (or two
threads discovering a dead client together rebuild two, which is the 169-of-200 configuration), and
**a discarded client is dropped, never closed** (`close()` discards uncommitted work).

### The translation seam, and how it discriminates by message text

```python
# SOURCE: app/db/database.py:425-446
@contextmanager
def _translated() -> Iterator[None]:
    try:
        yield
    except ValueError as exc:
        message = str(exc)
        if _DRIVER_ERROR not in message:
            raise
        constraint = _constraint_of(exc)
        if constraint is not None:
            raise IntegrityError(constraint, message) from exc
        relation = _MISSING_RELATION.search(message)
        if relation is not None:
            raise MissingRelationError(relation.group(1), message) from exc
        raise StorageError(message) from exc
```

```python
# SOURCE: app/db/database.py:255-259 -- the precedent for pinning driver text as a literal
_MISSING_RELATION = re.compile(r"no such table: (\w+)")
_CONSTRAINT = re.compile(r"constraint failed: ([\w.]+)")
_DUPLICATE_COLUMN = re.compile(r"duplicate column name: (\w+)")
```

### The one-statement, no-transaction read this module already trusts

```python
# SOURCE: app/db/database.py:399-421 -- check_database_reachable()
    """One statement, no transaction, no commit: a read needs neither, and
    `_Connection.close()` is already a no-op because the client is shared."""
    try:
        get_connection().execute("SELECT 1").fetchone()
    except Exception as exc:  # noqa: BLE001 -- every failure is classified below
        raise _classify_startup_failure(exc, endpoint) from exc
```

The probe borrows the *statement*, and deliberately **not** the function — see Design Decision 4.

### Test idioms to mirror

```python
# SOURCE: tests/test_db.py:2292-2311
def _install(monkeypatch, make_proxy) -> None:
    """Points `database.get_connection` at a proxy over the real connection."""
    real_get_connection = database.get_connection
    monkeypatch.setattr(
        database, "get_connection", lambda: make_proxy(real_get_connection())
    )


def _driver_error(message: str) -> ValueError:
    """The driver's real failure shape, captured from the live endpoint. ..."""
    return ValueError(
        'Hrana: `stream error: `Error { message: "SQLite error: '
        + message
        + '", code: "SQLITE_UNKNOWN" }`'
    )
```

```python
# SOURCE: tests/test_db.py:2586-2596
@pytest.fixture
def _restore_shared_client():
    """Drops the process-wide client after a test repoints DATABASE_URL. ..."""
    yield
    database._client = None
    database._client_key = None
```

```python
# SOURCE: tests/test_db.py:2177-2187 -- identity is the assertion, because a module that
# quietly rebuilds passes every other test in the file
def test_the_shared_client_is_reused_across_calls(temp_db):
    first = database._shared_client()
    count_audit_logs()
    assert database._shared_client() is first
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | Idle tracking + probe-on-acquire in `_shared_client()`; `_is_dead_stream()` / `_invalidate_client()`; invalidate-without-retry arm in `_translated()`; docstrings recording all of it |
| `tests/test_db.py` | UPDATE | New section: seven tests driving the recovery, the no-retry bound, the two captured messages, and the two negative cases |
| `app/db/errors.py` | **UNCHANGED** | AC 7 — asserted, not assumed (Task 8) |

Nothing else. No `app/services/`, no `chat_ui/`, no `app/config.py` (Design Decision 5), no consumer.

---

## Design Decisions

**1 — Two seams, and why neither alone is enough.** The story offered three placements. Chosen:
*validate-on-acquire* as the primary, plus a *narrow invalidate* in `_translated()`.

- **Validate on acquire (primary).** Runs before `_session()` opens its transaction, so it cannot
  replay partial work — AC 6 is satisfied *structurally*, not by care. It costs nothing on a busy
  path because it is gated on idle time. It is the only placement that can make AC 1 true ("the call
  **succeeds**"), because it is the only one that acts before the caller's statement is issued.
- **Invalidate in `_translated()` (net, no retry).** A stream can die in the window between the probe
  and the statement, or during a long transaction. Without this arm, that client stays cached and the
  *next* call is dead too. With it, the current call still raises `StorageError` — nothing is
  retried, nothing is replayed — and the next call rebuilds. This is the deliberate answer to the
  story's warning about `_translated()`: the hazard there is in *retrying*, not in *invalidating*.
- **Rejected: a decorator on each public function.** Thirty-odd decorators is thirty-odd places for
  the thirty-first to be forgotten — the failure mode `_wrapped()` in `app/services/chat_sessions.py`
  was written to avoid ("nine copies of a three-line `except` is nine places for the ninth to be
  forgotten").

**2 — The probe's failure rule is broader than the invalidation's, on purpose.** A `SELECT 1` cannot
fail for a *statement* reason: there is no table to be missing and no constraint to violate. So on
the probe, **any** driver-shaped `ValueError` (carrying `_DRIVER_ERROR`) means the client is not
usable and is discarded — which keeps working if the server ever grows a third way of saying the
stream is gone. Inside `_translated()`, where real statements fail for real statement reasons, the
rule must be narrow: only the captured dead-stream markers invalidate, and `UNIQUE constraint failed`
/ `no such table` leave the cache untouched (AC 3).

**3 — One rebuild per call, and the second failure is allowed to be a failure.** If the probe fails,
the client is dropped and exactly one replacement is built, and that replacement is **not** probed.
A genuinely dead endpoint therefore surfaces through the caller's own statement as `StorageError`
(AC 2) instead of looping. The invariant to hold: `libsql.connect` is called at most twice per
`_shared_client()` call, and there is no `while` and no `for` anywhere in this path.

**4 — The probe must not call `check_database_reachable()` and must not call `get_connection()`.**
Two independent reasons, both hard failures if ignored:

- `get_connection()` calls `_shared_client()`, and `_client_lock` is a plain non-reentrant
  `threading.Lock` — a probe routed through it **deadlocks the process**. The probe issues
  `client.execute("SELECT 1")` on the raw driver client it is already holding.
- `tests/test_db.py::test_guard_does_not_run_outside_init_db` is a booby trap for exactly this: it
  patches `database.check_database_reachable` to raise and then runs an ordinary insert, pinning
  STORY-008's AC 7 ("startup, not liveness"). Reusing that function would spring it. The distinction
  is real and worth keeping: `check_database_reachable()` classifies a *boot* failure for an operator
  and must keep failing loudly; the probe recovers an *operational* client and says nothing.

**5 — The threshold is a module constant, not a setting.** `_IDLE_PROBE_AFTER_SECONDS = 5.0`. A
setting would put a reliability invariant behind a deployment knob whose wrong value silently
restores the defect, and it would pull `app/config.py` and its tests into a story whose Technical
Notes say "one storage module". Five seconds is chosen as a floor well below any observed window
(the shortest gap that has produced the failure in evidence is a ~40 s model load), not as an
estimate of the server's timeout — the probe is cheap and its cost is bounded by Decision 6.

**6 — What the probe costs, stated so it can be checked.** One extra `SELECT 1` round trip on a call
that follows ≥5 s of the client not being handed out. Against the measured local endpoint that is
~1–4 ms (STORY-010 measured 2.7 ms for a ten-subquery SELECT). On a busy path — the
20-concurrent-query smoke test, an admin console load — it never fires. On the chat path it fires at
most once per user action after a pause, against a request that already spends two Presidio
`redact()` calls and an upstream model call. The suite pays it only between slow modules, which is
precisely where it is needed.

**7 — "Last used" is recorded at acquire, and the imprecision is in the safe direction.** The
timestamp is `time.monotonic()` stamped when the client is handed out, not when the last statement
completed, so a long transaction makes the *next* call look idler than it is. That over-probes
slightly and can never under-probe. `monotonic()` and not `time.time()`: a clock adjustment must not
be able to suppress a probe forever.

**8 — Invalidation is identity-guarded where it can be, and tolerant where it cannot.**
`_invalidate_client(stale)` drops the cache only when `_client is stale`, so a thread holding a
client another thread has already replaced cannot throw away the good one. `_translated()` has no
client reference (it is used standalone in `_add_missing_columns()` and `find_user_by_token_hash()`),
so it calls `_invalidate_client()` with no argument and drops whatever is cached. The cost of that
rare over-drop is one extra construction on the next call — not a correctness problem, and not the
client-per-thread configuration, because construction stays serialized under the lock.

**9 — Still no `close()` on the discarded client.** `_shared_client()` already declines to and says
why: `close()` discards uncommitted work rather than flushing it (STORY-001 §2.2). A dead stream
needs dropping, not closing. The existing comment stays and is extended rather than replaced.

---

## Tasks

Execute in order. Each task is atomic + verifiable.

### Task 1: Start the libSQL dev server and establish a green baseline

- **File**: none (environment)
- **Action**: RUN
- **Implement**: `docker start harness-libsql-dev` (or the `docker run` in `tests/conftest.py`'s
  module docstring if it does not exist). Then record the baseline: `pytest tests/test_db.py -q`.
- **Why first**: every later task's "it passes" claim is worthless without it, and this endpoint
  degrades under repeated suite runs — a wall of fixture errors means **restart the container**, not
  bisect the change.
- **Validate**: `pytest tests/test_db.py -q` → green; write the count down.

### Task 2: Add the dead-stream classifier and the invalidation helper

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: below `_DRIVER_ERROR` (~line 265), add the captured markers and the predicate:

  ```python
  # The stream is server-side state (HRANA_3_SPEC: HTTP is stateless, so a stream
  # is addressed by a baton). Both messages mean the server no longer has it, and
  # neither can be talked back into existence by the client holding the old baton
  # -- only a new client, which opens a stream with `baton: null`, recovers.
  #   idle expiry, captured live (PRD-007 STORY-009 report, PRD-008 STORY-014 report):
  #     Hrana: `api error: `status=400 Bad Request,
  #       body={"message":"The stream has expired due to inactivity","code":"STREAM_EXPIRED"}``
  #   after a server restart (PRD-008 STORY-014):
  #     Received an invalid baton
  # Pinned as literals for the same reason `_MISSING_RELATION` and `_CONSTRAINT`
  # are: libSQL raises a bare ValueError and there is no type and no code to
  # branch on (STORY-001 §3.5).
  _DEAD_STREAM = ("stream has expired", "STREAM_EXPIRED", "invalid baton")
  ```

  and `_is_dead_stream(message: str) -> bool` matching case-insensitively on any marker.
  Then `_invalidate_client(stale: Optional[Any] = None) -> None`: takes `_client_lock`, and if
  `stale is None or _client is stale`, sets `_client = None` and `_client_key = None`. Its docstring
  carries Design Decisions 8 and 9 — the identity guard, and **not** closing.
- **Mirror**: `app/db/database.py:249-266` for the literal-pinning comment style;
  `app/db/database.py:43-71` for lock discipline.
- **Validate**: `python -c "from app.db import database; print(database._is_dead_stream('...STREAM_EXPIRED...'), database._is_dead_stream('no such table: users'))"` → `True False`

### Task 3: Probe on acquire in `_shared_client()`, gated by idle time

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: add `import time` to the stdlib block, a third module global
  `_client_used_at: float = 0.0` beside `_client` / `_client_key`, and
  `_IDLE_PROBE_AFTER_SECONDS = 5.0` with Design Decisions 5 and 6 in a comment above it.
  Inside the existing `with _client_lock:` block, after the build-if-needed branch and before the
  `return`:
  - if the client was **just built**, stamp `_client_used_at = time.monotonic()` and return it — a
    brand-new client is never probed (which is also what keeps `init_db()`'s boot path at exactly one
    statement, Task 7);
  - otherwise, if `time.monotonic() - _client_used_at >= _IDLE_PROBE_AFTER_SECONDS`, run
    `_client.execute("SELECT 1")` inside `try/except ValueError as exc:`; on a message carrying
    `_DRIVER_ERROR`, rebuild **once** (`_client = libsql.connect(key[0], auth_token=key[1])`, no
    close, no second probe — Decisions 2, 3, 9); a `ValueError` without the prefix re-raises
    untouched, exactly as `_translated()` treats one;
  - stamp `_client_used_at` and return.

  Extend the `_shared_client()` docstring with a paragraph naming: what the probe is for, that it is
  idle-gated, that it must not route through `get_connection()` / `check_database_reachable()`
  (Decision 4, both reasons, deadlock named), and that one rebuild is the bound.
- **Mirror**: `app/db/database.py:399-421` for the statement itself; `app/db/database.py:66-69` for
  the do-not-close comment.
- **Validate**: `pytest tests/test_db.py -q` → same count as Task 1's baseline, no new failures.

### Task 4: Invalidate — but never retry — in `_translated()`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: in `_translated()`, after the `_DRIVER_ERROR` guard and **after** the constraint and
  missing-relation branches have had their chance (so a statement-level failure can never reach it),
  add: if `_is_dead_stream(message)`, call `_invalidate_client()` and then raise `StorageError` as
  the fall-through already does. The comment must say explicitly why there is no retry here: the
  generator has already yielded, the caller's statement may have run inside an open transaction, and
  replaying partial work is a worse defect than the one being fixed (AC 6). Ordering matters and the
  comment should say so — the constraint and relation branches come first so an `IntegrityError` can
  never be reclassified.
- **Mirror**: `app/db/database.py:425-446`.
- **Validate**: `pytest tests/test_db.py -q` → baseline count, unchanged.

### Task 5: Test the recovery itself (AC 1, AC 4)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: a new section header `# PRD-008 STORY-024: recovering a dead stream` after the
  STORY-006 shared-client section (~line 2205), and:
  - module-level `_STREAM_EXPIRED_TEXT` and `_INVALID_BATON_TEXT` holding the two captured driver
    strings verbatim, beside the existing `_REAL_UNREACHABLE_TEXT` idiom;
  - a `_DeadThenAlive` stand-in whose `execute()` raises `ValueError(_STREAM_EXPIRED_TEXT)` on its
    first call and delegates to a real client afterwards;
  - `test_a_dead_stream_is_discarded_and_the_call_is_served` — install the stand-in as
    `database._client`, force the idle gate (`database._client_used_at = 0.0`), count constructions
    by wrapping `database.libsql.connect`, call `count_audit_logs()`, and assert the **result** is a
    normal integer **and** that exactly one new client was constructed and `database._client is not`
    the stand-in.
- **Mirror**: `tests/test_db.py:2107-2136` (proxy raising the driver's real shape),
  `tests/test_db.py:2586-2596` (`_restore_shared_client`, which every test in this section takes so a
  stubbed global cannot leak into the next test).
- **Validate**: `pytest tests/test_db.py -q -k "dead_stream"` → passes.

### Task 6: Test the bound and the two negatives (AC 2, AC 3, AC 5, AC 6)

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**:
  - `test_a_second_connection_failure_surfaces_rather_than_looping` — a stand-in that always raises
    the expiry text; assert `pytest.raises(StorageError)` **and** that `libsql.connect` was called
    exactly once (the single rebuild), so a future retry loop fails this test rather than hanging it;
  - `test_both_captured_dead_stream_messages_are_recognised` — `@pytest.mark.parametrize` over the
    two literals against `database._is_dead_stream`, plus a third case asserting the constraint text
    from `_driver_error("UNIQUE constraint failed: users.token_hash")` is **not** recognised;
  - `test_a_constraint_violation_does_not_discard_the_client` — insert a duplicate `user_id` through
    `insert_user()`, assert `IntegrityError` **and** `database._client is` the same object as before;
  - `test_a_missing_table_does_not_discard_the_client` — induce `no such table` through the existing
    proxy idiom, assert the exception type is what it is today and the client identity is unchanged;
  - `test_a_dead_stream_mid_statement_invalidates_without_retrying` — a `get_connection` proxy that
    raises the expiry text at `execute()` time inside a `_session()`; assert `StorageError` was
    raised (not swallowed, not retried — the proxy counts its `execute()` calls and must see
    **one**) and that `database._client is None` afterwards, i.e. the next call rebuilds.
- **Mirror**: `tests/test_db.py:2292-2311` (`_install`, `_driver_error`), `tests/test_db.py:2599-2612`
  for the parametrize style.
- **Validate**: `pytest tests/test_db.py -q` → baseline + 6 new tests, all green.

### Task 7: Prove the probe stays off the hot path and off the boot path

- **File**: `tests/test_db.py`
- **Action**: UPDATE
- **Implement**: `test_a_busy_client_is_not_probed` — wrap the cached client in a statement-recording
  stand-in, issue two ordinary reads back to back, and assert no `SELECT 1` was recorded between them
  (Decision 6's claim, made falsifiable). Then confirm, by running them rather than by reading them,
  that `test_guard_issues_exactly_one_extra_statement` and `test_guard_does_not_run_outside_init_db`
  still pass **unmodified** — the first because a freshly built client is never probed, the second
  because the probe does not route through `check_database_reachable()` (Decision 4).
- **Mirror**: `tests/test_db.py:2707-2740`.
- **Validate**: `pytest tests/test_db.py -q -k "guard or busy_client"` → all pass, with no edits to
  the two existing tests.

### Task 8: Assert the untouched surface (AC 7, AC 8)

- **File**: none (verification)
- **Action**: RUN
- **Implement**: `git diff --stat` must show exactly two files. `git diff -- app/db/errors.py` must be
  empty. `git diff -- tests/test_chat_sessions.py tests/test_chat_state.py` must be empty. Run
  `pytest tests/test_chat_sessions.py tests/test_chat_state.py tests/test_untouched_app.py -q` and
  confirm the degraded arms STORY-014 built on `StorageError` still fire.
- **Validate**: two files in `--stat`, empty diffs, three suites green.

### Task 9: The live idle boot (AC 9) — the assertion no fresh-process suite can make

- **File**: none (manual E2E)
- **Action**: RUN
- **Implement**: boot the Reflex server against the dev container, do not touch the app while the
  production build runs (well past 5 s, and past whatever the container's real window is), then sign
  in with a valid token. The sign-in must succeed. Then reproduce the *other* half:
  `docker restart harness-libsql-dev` under the running app and issue a request — the invalid-baton
  path — and confirm the app recovers rather than staying dead. Record both outcomes, including the
  observed idle window if it can be narrowed, for the report.
- **Fallback if it cannot be run**: say so explicitly in the report the way STORY-014 did, and do not
  mark AC 9 met. Do not substitute a shortened threshold or a `sleep` in a test for it.
- **Validate**: sign-in succeeds after idle; the app serves a request after the server restart.

### Task 10: Full suite, then commit

- **File**: none
- **Action**: RUN
- **Implement**: `pytest -q` as one process — which, if the fix works, should be *more* stable than
  baseline, since the probe is exactly what the suite's slow modules were missing. Note the
  before/after in the report rather than claiming it. Then commit on `epic/PRD-008-chat-sessions`.
- **Validate**: `pytest -q`; `git commit`

---

## End-to-End Tests

- [ ] Boot the app, idle past the stream window, sign in → succeeds (AC 9; Task 9)
- [ ] Restart the libSQL server under a booted app, issue a request → the app recovers on the next
      request rather than requiring a process restart (the invalid-baton half of AC 5)
- [ ] Send a chat turn immediately after a successful idle recovery → the turn persists and the rail
      moves it to the front (STORY-013/014 behaviour unchanged by the rebuild)
- [ ] Load the admin console after an idle period → all ten summary figures render, none in a fault
      state
- [ ] Point `DATABASE_URL` at a dead endpoint and boot → `init_db()` still fails loudly with
      `DatabaseUnreachableError`, not a green start behind a retry

## Validation

```bash
docker start harness-libsql-dev
pytest tests/test_db.py -q
pytest tests/test_chat_sessions.py tests/test_chat_state.py tests/test_untouched_app.py -q
pytest -q
git diff --stat                     # exactly two files
git diff -- app/db/errors.py        # empty
```

## Risks + Mitigations

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | **Deadlock**: a probe routed through `get_connection()` re-enters `_shared_client()` and blocks on the non-reentrant `_client_lock`, hanging every request. | Decision 4 is a hard rule in Task 3: the probe executes on the raw client already held. Reviewable in one line of the diff. |
| 2 | **Two clients**: invalidating outside the lock lets two threads rebuild concurrently — STORY-006's client-per-thread configuration, which lost 169 of 200 writes. | Every mutation of `_client` happens under `_client_lock`; `_invalidate_client()` takes it itself and is identity-guarded (Decision 8). |
| 3 | **A retried partial transaction** — the defect AC 6 says would be worse than the one being fixed. | Structural: the only retry is in `_shared_client()`, before any transaction opens. `_translated()` invalidates and re-raises, and Task 6's mid-statement test counts `execute()` calls to prove the statement ran once. |
| 4 | The lock is now held across a network round trip on the idle path, blocking other threads for its duration. | Bounded by one `SELECT 1` (~1–4 ms measured locally), only on the idle path, and those threads would serialize on the single client anyway. Probing outside the lock was rejected because it reopens Risk 2. |
| 5 | A third dead-stream message shape appears and the narrow `_translated()` arm misses it. | Degrades to today's behaviour, not worse — and the probe's broad rule (Decision 2) still recovers the client on the next idle acquire. The failure mode of a miss is the status quo. |
| 6 | The dev container degrades under repeated suite runs and produces a wall of fixture errors that reads like a defect in this change. | Restart `harness-libsql-dev` and re-run; do not bisect the diff. Task 1's baseline count is what any later run is compared against. |
| 7 | `_IDLE_PROBE_AFTER_SECONDS = 5.0` turns out to be above the hosted window. | The probe is a floor on checking, not a model of the server; the `_translated()` net still recovers by the following call. If a deployment measures a shorter window, the constant is one number in one module. |
| 8 | Timing-sensitive tests: one that manipulates `_client_used_at` leaks its stub into the next test. | Every test in the new section takes `_restore_shared_client`, and the new global is reset there alongside `_client` / `_client_key`. |

---

## Acceptance Criteria

(Copied from story STORY-024)

- [ ] Given a cached client whose stream has expired, when any function in `app/db/database.py` is called, then the call **succeeds** — the dead client is discarded, a new one is built, and the caller sees a normal result rather than a `StorageError`.
- [ ] Given the same, when the recovery is observed, then the reconnect happens **at most once per call**. A second consecutive connection-level failure surfaces as `StorageError` and is not retried again.
- [ ] Given a **query-level** failure — `UNIQUE constraint failed`, `no such table` — when it is raised, then **no reconnect is attempted and the cached client is not discarded**, and the exception is still `IntegrityError` / `MissingRelationError` exactly as today.
- [ ] Given `tests/test_db.py`, when it runs, then a test drives the recovery with a stand-in client that raises the connection error on its first call and succeeds on the second, asserting both the successful result and that a new client was constructed.
- [ ] Given the two connection-level messages this defect actually produces, when each is fed to the classifier, then both are recognised: `STREAM_EXPIRED` and the post-restart *"Received an invalid baton"*, both present in the test as literals.
- [ ] Given a write already issued inside an open transaction, when the connection dies mid-transaction, then the operation is **not** silently retried.
- [ ] Given `app/db/errors.py`, when the story is complete, then it is **unchanged** — no new exception type.
- [ ] Given the existing error-surface tests in `tests/test_db.py` and `tests/test_chat_sessions.py`, when they run, then they pass **unmodified**.
- [ ] Given a manual verification, when the app is booted and left idle past the stream timeout and a user then signs in, then the sign-in succeeds.
- [ ] All tasks completed
- [ ] Full suite green, or the delta explained against Task 1's recorded baseline
- [ ] Follows existing patterns
