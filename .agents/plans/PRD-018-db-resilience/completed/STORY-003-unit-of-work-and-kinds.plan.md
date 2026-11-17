---
story: STORY-003
prd: PRD-018
slug: unit-of-work-and-kinds
title: _unit_of_work retry boundary, statement kinds on every database.py function, _FaultyClient harness
type: ENHANCEMENT
complexity: HIGH
epic_branch: epic/PRD-018-db-resilience        # all stories commit here, no per-story branch
created: 2026-11-17
---

# Plan: Retry at the unit of work (PRD-018 F2, second half)

## Summary

Add the retry boundary of PRD Section 6.1 to `app/db/database.py`: a closed `StatementKind` enum (`read`, `idempotent`, `non_idempotent`), three module constants (`_RETRY_MAX_ATTEMPTS = 3`, `_RETRY_BACKOFF_CAPS_SECONDS = (0.05, 0.2)`, `_RETRY_START_DEADLINE_SECONDS = 2.0`), three module-level seams for time and randomness (`_retry_sleep`, `_retry_clock`, `_retry_jitter`), a pure `_retryable(kind, cls, phase)`, a `_failure_of(exc)` that applies STORY-002's open rule (classify the rollback's error **and** the body's `__context__`, take the more pessimistic), and `_unit_of_work(name, kind, fn)`. Then a mechanical transformation of all **41** public operational functions: each `with _session() as conn:` body moves verbatim into a local `def _op(conn)` passed to `_unit_of_work("<own name>", StatementKind.<KIND>, _op)`. Signatures and return values do not change. `_translated()` (code and docstring) is untouched; `init_db()` / `check_database_reachable()` keep their direct `_session()` / `get_connection()` (D17). Two existing `tests/test_db.py` tests change, because they pinned "no retry" at the public-function level; each keeps its premise and gets a comment citing PRD-018 D1/D5. New: `tests/db_faults.py` (the reusable `_FaultyClient` harness), a `faulty_db` fixture in `tests/conftest.py`, `tests/test_db_resilience_retry.py` (pure, non-`db`: the loop, the kind x class matrix, the budget, the logs, and the name -> kind pin over the module's function list), and `tests/test_db_resilience_faults.py` (`db`, `_FaultyClient`). No breaker and no `StorageUnavailableError` (STORY-005): the loop has one entry point, one success exit and one failure exit, each marked as the STORY-005 hook.

## User Story

As a platform operator
I want each storage function re-run from the start on a fresh client when the failure proves that is safe
So that a single dead stream mid-request is absorbed instead of becoming a 500

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-003-unit-of-work-and-kinds.md` (Technical Notes carry three orchestrator decisions that supersede parts of AC 2: see "Story-text deviations")
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md`, Sections 6.1 (:130-152), 6.2 as amended (:154-170), 6.3 (:172-201), 6.5 (:229 "counts operations"), 6.6 (:261-265), 12 testing approach (:514-518), 15 D1, D3, D5, D17, D18 (:549-566)
- Spike: `.agents/spikes/PRD-018-driver-failure-surface.md` (Q1 :143-151, Q2 :153-163, Q3 :165-181, captures :110-134)
- STORY-002 report: `.agents/reports/PRD-018-db-resilience/STORY-002-classifier-and-phase-tracking.report.md` ("Open for STORY-003")

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (story `type: technical`, `complexity: large`) |
| Complexity | HIGH: ~150 lines of new app code, 41 mechanical rewrites, a reusable test harness |
| Systems Affected | `app/db/database.py`; `tests/conftest.py` (one fixture); `tests/test_db.py` (two tests); three new test files |
| Story | STORY-003 |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics, read 2026-11-17). Story `skills: []`. Nothing here touches UI | — |

---

## Pre-flight findings (verified by the planner on 2026-11-17)

| Fact | Evidence | Consequence |
|---|---|---|
| **41** public functions open `with _session() as conn:`; the only other public functions are `get_connection`, `check_database_reachable`, `init_db` | `grep -n "^def \|with _session()" app/db/database.py` (list in the kinds table below) | The orchestrator's "~60" is 41 in the code. The pin test enumerates the module, so the exact count is asserted, not assumed |
| `database.py` has no logger at all | no `logging` import in `app/db/database.py:1-47` | Add `import logging` + `logger = logging.getLogger(__name__)` (house style: `app/services/usage_limits.py:33`, `app/services/query_pipeline.py:63`) |
| `_session()` is `_translated()` around `get_connection()` + `with conn:` | `app/db/database.py:817-828` | `_unit_of_work` opens a **new** `_session()` per attempt; `_translated()` stays the inner seam and never retries (D1) |
| On a body exception `_Connection.__exit__` calls `rollback()`; a failing rollback replaces the body's error, which stays on `__context__` | `app/db/database.py:396-405`; pinned by `tests/test_db_resilience_classify.py:338-350` | `_failure_of` reads `exc.__cause__.__context__` when the phase is `rollback` (Design D-4) |
| A dead-stream `rollback()` raises the same baton text | spike F4a (`.agents/spikes/...:121`, rids 566/590/614) | The rollback-masks-body case is real, not hypothetical |
| **DML is not durable before `commit()`** | spike Q1 (`:143-151`) | An "after forwarding" fault on `execute` is undone by `__exit__`'s forwarded rollback, so it cannot model "the effect landed". Only an "after forwarding" fault on **`commit`** can. AC 4's admit test uses `op="commit", when="after"` (Design D-7) |
| `commit()`/`rollback()` with no open transaction never touch the network | spike Q2 (`:153-163`) | After a before-forward `execute` fault on a fresh statement, `__exit__`'s rollback is a harmless no-op on the real client |
| An abandoned stream holding a write lock makes a fresh writer wait ~2.1 s | spike Q3 (`:165-181`) | The harness must roll the **real** transaction back when it fakes a dead-stream `commit`/`rollback`, or every such test pays 2 s and leaves a lock (Design D-7) |
| `find_user_by_token_hash` nests `_translated()` inside the block and folds `MissingRelationError` into `None` | `app/db/database.py:1762-1773` | The nested arm stays inside `_op` verbatim. A dead stream there arrives at `_unit_of_work` as the inner `StorageError` (or, if the rollback also fails, as the outer one with the inner on `__context__`); `_phase_of` reads either through `__cause__` (`:744-757`) |
| `summary_snapshot` catches `StorageError` around its one `_session()` and falls back figure by figure | `app/db/database.py:1707-1723`, `:1636-1681` | Wrap only the one statement; the `except StorageError` stays outside the unit, so the fallback runs once, after the batch's budget is spent. Decoding stays outside too (`test_summary_snapshot_isolation_of_one_bad_decode`, `tests/test_db.py:1804-1823`, must still see a decode `ValueError` as one bad figure) |
| `insert_action_decisions` loops inside one block and accumulates `ids` declared **before** the `with` | `app/db/database.py:2455-2488` | `ids = []` must move **into** `_op`, or a replay appends a second set of ids |
| `count_action_decisions` initialises `counts` before the `with` and fills it after | `app/db/database.py:2564-2571` | `_op` returns the fetched rows; the counting loop stays after the unit (mutated only once, after success) |
| `create_chat_session`, `insert_user`, `touch_chat_session`, `append_chat_message` mint `session_id` / `now` / `created_at` **before** the `with` | `:2070-2071`, `:1798-1800`, `:2173`, `:2324-2326` | Keep them before the unit: every attempt writes the same values. That is what makes `create_chat_session`'s "IntegrityError on a retry is success" rule sound (the retry re-sends the same `uuid4`) |
| `append_chat_message` raises `StorageError("chat session not available for this owner")` from inside the block | `app/db/database.py:2361-2362` | That is our own refusal, not a driver failure: no `Hrana:` prefix. `_unit_of_work` re-raises any `StorageError` without the prefix untouched, exactly as `_translated()` treats a non-driver `ValueError` (`:675-676`) |
| `set_user_limits` raises `ValueError` before opening a session | `app/db/database.py:1869-1870` | Stays before the unit |
| No public function returns a generator; every result is materialised (`fetchone`/`fetchall`, list comprehensions) inside the block | all 41 bodies | `_op`'s return value is safe to carry past the transaction |
| Async callers run storage in `asyncio.to_thread` workers | `chat_ui/chat_ui/state.py:359-360, 695, 766, 862, 918, 933, 940, 1046`; `chat_ui/chat_ui/admin_state.py:1312, 1419, 1435, 1455` | `_retry_sleep` (`time.sleep`, at most 0.25 s per operation) blocks a worker thread, not the event loop. `ChatState`'s inline `resolve(token)` (`state.py:967`) still runs on the loop, as today (STORY-007's scope); noted as a risk |
| In a `db` test `libsql.connect` is already `_recorded_connect(libsql.connect)` when the test body runs, and a test patching it "layers over the wrapper" | `tests/conftest.py:653-663`, docstring `:645-651` | `_FaultyClient` wraps whatever `libsql.connect` is at install time, so PRD-014's recorder still sees every forwarded call and `libsql diagnostics` still works |
| `_shared_client()` caches a client across tests; `temp_db`'s `init_db()` builds it before the test body | `app/db/database.py:122-133`, `tests/conftest.py:739-747` | The fixture must `database._invalidate_client()` after installing (or the cached, unfaulty client is lent) and again at teardown (or the next test inherits a faulty proxy) |
| `tests/test_db_isolation_harness.py` copies `tests/conftest.py`'s text into child pytest runs | `tests/test_db_isolation_harness.py:520-525` (`_run_child`) | The new fixture imports `tests.db_faults` **lazily, inside the fixture body**, so the copied conftest still imports in a child that never uses it |
| A test module may import a helper module from `tests/` | `tests/test_reports_service.py:18` (`from tests.reports_fixture import build_agents_tree`); `tests/__init__.py` exists | `tests/db_faults.py` is importable as `from tests.db_faults import ...` by STORY-004/005/013 |
| The `db` marker follows the fixture closure | `tests/conftest.py:103-105`, `:192-195` | A test requesting `faulty_db` (which requests `temp_db`) is `db` automatically. **No `_DB_NODEIDS` entry is needed.** The pure retry tests request no storage fixture, so they stay non-`db` and PRD-014's guard (`:664-671`) proves they reach no driver |
| Two existing tests pin "no retry" through a public function | `tests/test_db.py:4322-4343` (`len(built) == 1`), `:4414-4450` (`executes == [one]`) | Modified, premise kept (Task 7). Every other failure-injecting test raises a **persistent** failure (`:2597-2606`, `:4104-4134`), a `STATEMENT` (`:4386-4411`), or a non-`Hrana:` `StorageError` (`tests/test_action_audit.py:142-145, 465-476`): they still pass, a persistent infrastructure one after 3 attempts |
| The guard test `test_init_db_fails_fast_against_an_unreachable_endpoint` goes through `check_database_reachable()` only | `tests/test_db.py:5067-5084`; `_DB_NODEIDS` `tests/conftest.py:119` | Unchanged; `init_db()` never meets `_unit_of_work` (pinned by the AST test too) |
| `test_chat_sessions.py` inspects function bodies with `ast.unparse` and looks for SQL fragments | `tests/test_chat_sessions.py:91-102, 214, 613, 623-637` | Still passes: the nested `_op` is part of the unparsed body. `_op` gets no docstring, so no prose fragment can leak into the check |
| `test_summary_snapshot_leaves_the_ten_standalone_signatures_unchanged` pins `inspect.signature` | `tests/test_db.py:1916-...` | Local `_op` changes no signature (no decorator) |

---

## Story-text deviations (to confirm with the orchestrator; all follow the code or a recorded decision)

1. **AC 2's "`DEAD_STREAM`@`commit` is not retried" is superseded** (Technical Notes, orchestrator decision from STORY-001): a dead stream on `commit` classifies `NOT_SENT` (`app/db/database.py:810-812`), so a `NON_IDEMPOTENT` op **is** retried after it. Tests pin the new rule.
2. **`insert_audit_log` and `insert_action_decisions` are `NON_IDEMPOTENT` in this story**, not `IDEMPOTENT`. PRD 6.3 rows #6, #8, #9 say "`IDEMPOTENT` (after D4)", and D4 lands in STORY-004, whose own Technical Notes say a call "whose rows lack a `write_id` ... runs as `NON_IDEMPOTENT`". Until STORY-004 no row has a `write_id`, so marking them `IDEMPOTENT` now would let an `OUTCOME_UNKNOWN` commit replay an audit row twice between the two commits. STORY-004 switches the kind per call. The pin test row carries that comment.
3. **AC 4's "OUTCOME_UNKNOWN raised after forwarding on `admit_usage`" is tested on `commit`, not `execute`.** Spike Q1: an increment forwarded on `execute` and then failed is rolled back by `__exit__`, so `requests` would move by 0, and only a *wrong* retry would make it 1: the assertion would pass for the wrong reason. The honest "effect landed, response lost" is a forwarded `commit` whose response is replaced by `OUTCOME_UNKNOWN` text (`Fault(op="commit", when="after")`). A companion test does the `execute`-after case and pins `requests == 0` and one forwarded INSERT.
4. **`delete_chat_session` (`IDEMPOTENT`, PRD 6.3) can return `False` on a retry after a landed `OUTCOME_UNKNOWN` commit** (the rows are gone, so the second attempt matches 0). The state is correct, the bool is not. Recorded as a known residual; fixing it needs a read-back design, not this story.
5. **`_RETRY_BACKOFF_CAPS_SECONDS = (0.05, 0.2)`** is a third constant beside the two the story names. The caps are D5's numbers; naming them keeps them out of the loop body and lets a test pin `len(caps) == _RETRY_MAX_ATTEMPTS - 1`.

---

## Design

### D-1. Vocabulary, constants and seams (no settings, O6)

```python
class StatementKind(str, Enum):
    """How safe it is to run a unit of work twice (PRD-018 D3, Section 6.3)."""
    READ = "read"
    IDEMPOTENT = "idempotent"
    NON_IDEMPOTENT = "non_idempotent"
```

`(str, Enum)` like `FailureClass` (`app/db/database.py:695-712`). Constants go right after `_IDLE_PROBE_AFTER_SECONDS` (`:62-81`), with a comment block in the same voice: what D5 measured, why so small (6.6), "a deployment knob whose wrong value silently restores the defect is not a knob worth having", and the fact that the deadline gates *starting* an attempt and cannot cut one already running (spike Q3: a contended first write takes ~2.1 s; no driver read timeout, spike F3a).

```python
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_CAPS_SECONDS = (0.05, 0.2)   # full jitter: uniform(0, cap) before attempt 2, 3
_RETRY_START_DEADLINE_SECONDS = 2.0
```

**Injection without settings: three module-level seams**, read at call time (the same mechanism every existing test uses to patch `database._shared_client` / `database.get_connection`):

```python
def _full_jitter(cap: float) -> float:
    return random.uniform(0.0, cap)

_retry_sleep: Callable[[float], None] = time.sleep
_retry_clock: Callable[[], float] = time.monotonic   # separate from the idle gate's time.monotonic()
_retry_jitter: Callable[[float], float] = _full_jitter
```

Tests `monkeypatch.setattr(database, "_retry_sleep", fake.sleep)` etc. `_retry_jitter` receives the **cap**, so a test can return `cap` (worst case), `0.0`, or record the caps it was asked for. Separate from `time.monotonic` so a fake clock never disturbs `_shared_client()`'s idle gate. `import random` is stdlib (no new dependency).

### D-2. The retry rule (pure)

```python
_RETRIED_ON: Mapping[StatementKind, frozenset[FailureClass]] = {
    READ: {NOT_SENT, DEAD_STREAM, OUTCOME_UNKNOWN},
    IDEMPOTENT: {NOT_SENT, DEAD_STREAM, OUTCOME_UNKNOWN},
    NON_IDEMPOTENT: {NOT_SENT, DEAD_STREAM},
}

def _retryable(kind, failure, phase) -> bool:
    if failure not in _RETRIED_ON[kind]:
        return False          # STATEMENT never; NON_IDEMPOTENT never on OUTCOME_UNKNOWN
    if kind is NON_IDEMPOTENT and failure is DEAD_STREAM:
        return phase == "execute"   # 6.3: "DEAD_STREAM on execute only" (a fetch-phase one is not proof)
    return True
```

`NOT_SENT` covers the commit-phase dead stream (orchestrator decision), so `NON_IDEMPOTENT` retries it.

### D-3. What `_unit_of_work` classifies

`except StorageError as exc` only (so `IntegrityError` / `MissingRelationError` arrive here too and classify `STATEMENT`). Then:

1. `if _DRIVER_ERROR not in str(exc): raise` — our own `StorageError` (the `append_chat_message` ownership refusal, a test's `StorageError("injected failure")`) is not a driver failure: not classified, not retried, not logged, client kept. Same rule `_translated()` applies to a non-driver `ValueError`.
2. `failure, phase = _failure_of(exc)` (D-4).
3. Non-`StorageError` exceptions (our `ValueError`, `KeyError`, pytest's `Failed` from the PRD-014 guard, a `BaseException`) are not caught at all.

### D-4. `_failure_of(exc) -> tuple[FailureClass, Optional[str]]` (the rollback `__context__` rule)

Lives directly after `_classify` (classification stays beside `_translated()`, PRD 6.10).

```text
phase = _phase_of(exc); result = (_classify(exc, phase), phase)
if phase == "rollback":
    driver = exc.__cause__ or exc            # the rollback's own ValueError
    body = driver.__context__                 # what the body raised before __exit__ rolled back
    if body is not None:
        if isinstance(body, StorageError) or (isinstance(body, ValueError) and _DRIVER_ERROR in str(body)):
            body_phase = _phase_of(body); body_result = (_classify(body, body_phase), body_phase)
        else:
            body_result = (OUTCOME_UNKNOWN, None)   # our own exception mid-block: nothing is proven
        result = the more pessimistic of (body_result, result); a tie goes to body_result
return result
```

Rank, least to most pessimistic: `NOT_SENT` < `DEAD_STREAM` < `OUTCOME_UNKNOWN` < `STATEMENT` (the story's order, with `STATEMENT` on top because "never retried" is the safe end). A tie goes to the **body** so its phase decides `NON_IDEMPOTENT`'s "`DEAD_STREAM` on `execute` only": body `DEAD_STREAM`@`execute` + rollback `DEAD_STREAM`@`rollback` -> `(DEAD_STREAM, "execute")` -> retried; body `DEAD_STREAM`@`fetchone` + rollback baton -> not retried. The exception that propagates is unchanged: the rollback's `StorageError`, exactly as today. The nested `_translated()` in `find_user_by_token_hash` is covered: the body is then the inner `StorageError`, whose phase `_phase_of` reads through `__cause__`.

### D-5. `_unit_of_work(name, kind, fn)`

```python
T = TypeVar("T")

def _unit_of_work(name: str, kind: StatementKind, fn: Callable[[_Connection], T]) -> T:
    # PRD-018 STORY-005 hook (entry): _storage_breaker.before() goes here, before
    # _session() can reach _shared_client().
    first_started = _retry_clock()
    attempt = 1
    while True:
        stale = None
        try:
            with _session() as conn:
                stale = getattr(conn, "_client", None)   # getattr: tests install proxies without it
                result = fn(conn)
        except StorageError as exc:
            if _DRIVER_ERROR not in str(exc):
                raise
            failure, phase = _failure_of(exc)
            if failure is not FailureClass.STATEMENT:
                # Fresh client next time, whatever the infrastructure class: _translated()
                # already dropped a dead stream; NOT_SENT / OUTCOME_UNKNOWN leave a client
                # that may be half-dead. Never inside _translated() (D1). The identity
                # guard keeps a client another thread already rebuilt.
                _invalidate_client(stale)
            delay = None
            if _retryable(kind, failure, phase):
                if attempt >= _RETRY_MAX_ATTEMPTS:
                    reason = "max_attempts"
                else:
                    delay = _retry_jitter(_RETRY_BACKOFF_CAPS_SECONDS[attempt - 1])
                    if _retry_clock() + delay - first_started > _RETRY_START_DEADLINE_SECONDS:
                        delay, reason = None, "deadline"
                if delay is None:
                    logger.warning("retry exhausted op=%s class=%s attempts=%d reason=%s detail=%s", ...)
            if delay is None:
                # PRD-018 STORY-005 hook (failure): record_failure(failure) when failure is not
                # STATEMENT -- exactly once per operation, here and nowhere else.
                raise
            logger.info("retry op=%s class=%s attempt=%d detail=%s", name, failure.value, attempt, _retry_detail(exc))
            _retry_sleep(delay)
            attempt += 1
            continue
        # PRD-018 STORY-005 hook (success): record_success().
        return result
```

- **Retry boundary = the start of the `_session()` block** (D1): every attempt is a new `_session()`, a new `get_connection()`, a new transaction, and `fn` runs from its first statement. `_translated()` is not touched.
- **`attempt=<n>` in the INFO line is the attempt that just failed** (1 or 2). One INFO line per retry, one WARNING per exhausted budget, nothing for a non-retryable refusal (the exception carries it; STORY-005/012 count it).
- **Deadline**: no attempt *starts* more than 2.0 s after the first started; the check projects `now + delay` so the loop never sleeps into a start it would then refuse. `>` so exactly 2.0 s is allowed.
- **Exhausted / refused** re-raises the last attempt's exception: same type and message as today (AC 2).
- `_retry_detail(exc)` = `_redacted(str(exc))` with SQLite's only statement-echoing form, `near "<token>"`, replaced by `near "<elided>"`, cut to 500 characters. Infrastructure texts quote no SQL and no parameters (spike captures), and `STATEMENT` failures are never logged here; the elision covers a syntax error, which STORY-002 left `OUTCOME_UNKNOWN`.
- The docstring states D1/D3/D5, the "re-runnable `_op`" contract (no state survives an attempt except values minted before the unit), the deadline-cannot-cut-a-call fact, and that `init_db()` / `check_database_reachable()` never come here (D17).

### D-6. The mechanical transformation (one template, three exceptions)

```python
def get_user(user_id: str) -> Optional[User]:
    """(docstring unchanged)"""

    def _op(conn: _Connection) -> Optional[User]:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_user(row)

    return _unit_of_work("get_user", StatementKind.READ, _op)
```

Rules: (1) everything before the `with` stays before the unit; (2) the `with` body moves verbatim into `_op`, comments included, re-indented by zero (the `with` line becomes the `def _op` line); (3) anything after the `with` stays after the unit, using `_op`'s return value; (4) `_op` gets no docstring; (5) the name literal is the enclosing function's name. Exceptions:

- `insert_action_decisions`: `ids = []` moves **into** `_op` (rule 1 would replay-append).
- `create_chat_session`: a `nonlocal attempts` counter in `_op`; around the unit, `except IntegrityError as exc: if attempts > 1 and exc.constraint == "chat_sessions.session_id": return session_id; raise` (PRD 6.3 #11: on a retry the constraint means the first attempt landed; the retry re-sent the same `uuid4`, so the row is ours). The counter counts `_op` runs, so an attempt that failed before reaching `execute` (connect) is not counted. On attempt 1 an `IntegrityError` is raised as today.
- `summary_snapshot`: `_op` returns the fetched `row`; `try: row = _unit_of_work(...) except StorageError as exc: return _summary_figure_by_figure(...)`; decoding unchanged after it.

### D-7. `_FaultyClient` and its script (reused by STORY-004, 005, 013)

`tests/db_faults.py` (new helper module; importable as `from tests.db_faults import ...`):

```python
@dataclass(frozen=True)
class Fault:
    text: str                                   # raised as a NEW ValueError(text) each time (phase marks ride on the instance)
    op: Literal["execute", "commit", "rollback"] = "execute"
    sql: str = ""                               # execute only: prefix of the whitespace-normalised, upper-cased SQL
    nth: int = 1                                # 1-based, among calls this fault matches, counted across every client the script built
    times: int = 1                              # consecutive matching calls that fail, starting at nth
    when: Literal["before", "after"] = "before"
```

Semantics, stated in the module docstring with the spike rows that justify them:

| op / when | What the proxy does | Models |
|---|---|---|
| `execute` / `before` | raises without forwarding | `NOT_SENT` (connect text) or `DEAD_STREAM` (baton/expired): the request did not run |
| `execute` / `after` | forwards, then raises | a response lost **inside an open transaction**: `__exit__`'s forwarded rollback undoes it (spike Q1), so nothing lands |
| `commit` / `before` | `real.rollback()`, then raises | a server that dropped the stream and its transaction (spike V1: 9/9 dead-stream commits landed nothing). The real rollback also releases the write lock, so the retry does not wait 2 s (spike Q3) |
| `commit` / `after` | `real.commit()`, then raises | **the effect landed and the response was lost**: the only honest `OUTCOME_UNKNOWN`-landed case |
| `rollback` / either | `real.rollback()`, then raises | a dead-stream rollback masking the body's error (spike F4a) |

`FaultScript(*faults)`: holds the faults, per-fault match counters under a `threading.Lock` (STORY-013 drives concurrent requests), `calls: list[tuple[str, str]]` (op, first 60 characters of the normalised SQL), `fired: list[Fault]`, `connects: int`, and helpers `forwarded(sql_prefix) -> int` (how many matching executes reached the real client). `install(monkeypatch)` wraps the **current** `libsql.connect` (the PRD-014 recorder in a `db` test) so `connect(*a, **kw)` returns `_FaultyClient(previous(*a, **kw), self)`, then calls `database._invalidate_client()` so the next `_shared_client()` builds through it. `add(*faults)` appends mid-test.

`_FaultyClient(real, script)`: `execute(sql, *parameters)`, `commit()`, `rollback()` as above; `__getattr__` forwards everything else (`cursor`, `in_transaction`, ...), the `_RecordedClient` idiom (`tests/conftest.py:375-414`). It raises a real `ValueError`, never a wrapper, so `_Connection` marks the phase and `_translated()` translates exactly as for the driver. Cursor-level `execute` is forwarded unscripted (no `database.py` function uses `conn.cursor()`); documented as the extension point.

Captured-text library, each constant with its spike row and expected class: `CONNECT_REFUSED` (row 1, `NOT_SENT`), `STREAM_EXPIRED` (rows 5/6), `INVALID_BATON` (rows 7-9), `NAMESPACE_SHUTDOWN_503` and `NAMESPACE_MISSING_404` (rows 10/11, `OUTCOME_UNKNOWN`, captured), `UNRECOGNISED` (row 15, synthetic), `UNIQUE_SESSION_ID` (the `chat_sessions.session_id` constraint text, `STATEMENT`).

Fixture in `tests/conftest.py`, beside `temp_db`:

```python
@pytest.fixture
def faulty_db(temp_db, monkeypatch):
    """A `db` database whose driver is wrapped by an empty FaultScript (PRD-018 STORY-003, D18)..."""
    from tests.db_faults import FaultScript   # lazy: test_db_isolation_harness copies this file into child runs
    script = FaultScript()
    script.install(monkeypatch)
    yield script
    database._invalidate_client()   # the next test must not inherit a faulty proxy
```

It does not touch `_retry_sleep` (real backoff, at most 0.25 s per operation, keeps the fault tests honest about timing; a test may patch it).

### D-8. The name -> kind pin (so a future function cannot skip `_unit_of_work`)

In `tests/test_db_resilience_retry.py` (pure): `_EXPECTED_KINDS: dict[str, StatementKind]` = the 41 rows of the table below, each commented with its PRD 6.3 statement number; `_EXEMPT = {"get_connection", "check_database_reachable", "init_db"}` (D17). Four assertions:

1. **Module enumeration**: `{n for n, o in vars(database).items() if inspect.isfunction(o) and o.__module__ == database.__name__ and not n.startswith("_")} == set(_EXPECTED_KINDS) | _EXEMPT`. A new public function fails here until it is given a kind; a renamed one fails too.
2. **Call-site kinds (AST over `Path(database.__file__)`)**: each expected function contains exactly one `_unit_of_work(...)` call, whose first argument is the string literal of its own name and whose second unparses to `StatementKind.<expected>`.
3. **No bypass**: the top-level functions containing a `_session()` call are exactly `{"_unit_of_work", "init_db"}`, and those calling `get_connection()` are exactly `{"_session", "check_database_reachable"}`. A future function that opens its own session fails here even if it is private.
4. `init_db` and `check_database_reachable` contain no `_unit_of_work` call (D17).

---

## Kinds of every public function (PRD Section 6.3 plus the admin/CLI reads)

| # | Function | `app/db/database.py` | Kind | 6.3 row / reason | Special handling |
|---|---|---|---|---|---|
| 1 | `insert_audit_log` | :988 | `NON_IDEMPOTENT` | #6, #8: `IDEMPOTENT` only after D4 (STORY-004); no `write_id` yet | — |
| 2 | `find_duplicate_timestamp` | :1043 | `READ` | #5 | — |
| 3 | `mark_audit_log_failed` | :1088 | `IDEMPOTENT` | #10 (sets fixed values) | — |
| 4 | `get_audit_log` | :1156 | `READ` | admin read | — |
| 5 | `count_audit_logs` | :1166 | `READ` | admin/summary read | — |
| 6 | `list_audit_logs` | :1178 | `READ` | admin/summary read | — |
| 7 | `count_blocked_duplicates` | :1197 | `READ` | summary read | — |
| 8 | `count_blocked_suspicious` | :1218 | `READ` | summary read | — |
| 9 | `count_unique_users` | :1226 | `READ` | summary read | — |
| 10 | `count_successful_queries` | :1234 | `READ` | summary read | — |
| 11 | `top_models` | :1242 | `READ` | summary read | — |
| 12 | `top_users` | :1257 | `READ` | summary read | — |
| 13 | `count_pii_detected_queries` | :1271 | `READ` | summary read | — |
| 14 | `top_pii_entities` | :1282 | `READ` | summary read | — |
| 15 | `sum_input_tokens` | :1343 | `READ` | summary read | — |
| 16 | `sum_output_tokens` | :1351 | `READ` | summary read | — |
| 17 | `count_blocked_usage_limits` | :1359 | `READ` | summary read | — |
| 18 | `summary_snapshot` | :1684 | `READ` | summary read | fallback and decode stay outside the unit |
| 19 | `get_user` | :1738 | `READ` | CLI read | — |
| 20 | `find_user_by_token_hash` | :1750 | `READ` | #1 | nested `_translated()` stays inside `_op` |
| 21 | `list_users` | :1776 | `READ` | CLI/admin read | — |
| 22 | `count_active_users` | :1785 | `READ` | admin read | — |
| 23 | `insert_user` | :1793 | `NON_IDEMPOTENT` | 6.3 prose: a replay could misreport a created user as a duplicate | `created_at` minted before the unit |
| 24 | `deactivate_user` | :1818 | `IDEMPOTENT` | 6.3 prose | rowcount counts matched rows, so a replay still returns `True` |
| 25 | `set_user_token_hash` | :1829 | `IDEMPOTENT` | 6.3 prose | same |
| 26 | `set_user_limits` | :1845 | `IDEMPOTENT` | 6.3 prose | the `ValueError` guard stays before the unit |
| 27 | `admit_usage` | :1926 | `NON_IDEMPOTENT` | #4 (O3) | — |
| 28 | `charge_usage` | :1947 | `NON_IDEMPOTENT` | #7 | — |
| 29 | `usage_snapshot` | :2011 | `READ` | 6.3 prose | — |
| 30 | `create_chat_session` | :2051 | `IDEMPOTENT` | #11 | `IntegrityError(chat_sessions.session_id)` after attempt 1 = success |
| 31 | `get_chat_session` | :2084 | `READ` | #2, #14 | — |
| 32 | `list_chat_sessions` | :2110 | `READ` | rail read | — |
| 33 | `rename_chat_session` | :2143 | `IDEMPOTENT` | 6.3 prose | — |
| 34 | `touch_chat_session` | :2166 | `IDEMPOTENT` | #13 | `now` minted before the unit |
| 35 | `delete_chat_session` | :2182 | `IDEMPOTENT` | 6.3 prose | two statements, one unit; see deviation 4 |
| 36 | `append_chat_message` | :2263 | `NON_IDEMPOTENT` | #12 | own `StorageError` passes through unclassified |
| 37 | `list_chat_messages` | :2366 | `READ` | #3 | — |
| 38 | `count_chat_sessions` | :2413 | `READ` | rail read | — |
| 39 | `insert_action_decisions` | :2439 | `NON_IDEMPOTENT` | #9: `IDEMPOTENT` only after D4 (STORY-004) | `ids` reset inside `_op`; empty `rows` still returns before any unit |
| 40 | `list_action_decisions` | :2515 | `READ` | admin read | clause building stays before the unit |
| 41 | `count_action_decisions` | :2557 | `READ` | admin read | counting loop stays after the unit |
| — | `get_connection` | :408 | exempt | raw transaction handle (13 test modules open one) | — |
| — | `check_database_reachable` | :624 | exempt | D17, boot path | — |
| — | `init_db` | :831 | exempt | D17, boot path | keeps its direct `_session()` |

---

## Patterns to Follow

### Module constant with the "no knob" rationale
```python
# SOURCE: app/db/database.py:62-81
# PRD-008 STORY-024. How long the client may go without being handed out before
# it is proved rather than trusted. A **floor on how often we check**, not a
# model of the server's timeout, ...
# A module constant rather than a setting on purpose: a deployment knob whose
# wrong value silently restores the defect is not a knob worth having.
_IDLE_PROBE_AFTER_SECONDS = 5.0
```

### Closed vocabulary as a `str` Enum with a docstring per value
```python
# SOURCE: app/db/database.py:695-712
class FailureClass(str, Enum):
    """What a storage failure says about whether the statement ran (PRD 6.2).
    ...
    """
    NOT_SENT = "not_sent"
```

### Error handling: re-raise anything that is not the driver's, untouched
```python
# SOURCE: app/db/database.py:671-685
    except ValueError as exc:
        message = str(exc)
        if _DRIVER_ERROR not in message:
            raise
```

### Drop a client with an identity guard
```python
# SOURCE: app/db/database.py:178-200
def _invalidate_client(stale: Optional[Any] = None) -> None:
    ...
    with _client_lock:
        if stale is None or _client is stale:
            _client = None
            _client_key = None
```

### Log call style
```python
# SOURCE: app/services/usage_limits.py:217-227
        logger.error(
            "usage charge failed: user_id=%s day=%s input_tokens=%s output_tokens=%s"
            " total_tokens=%s error=%s",
```

### Forwarding proxy that re-raises the original exception
```python
# SOURCE: tests/conftest.py:375-414
class _RecordedClient:
    """Forwards every attribute to the real client, timing each method call.

    **The original exception, re-raised.** ...
    """
    def __getattr__(self, name):
        attr = getattr(self._real, name)
```

### Pure test over the real `_Connection` with a fake client and a restored cache
```python
# SOURCE: tests/test_db_resilience_classify.py:252-280, 387-393
class _FakeClient:
    """A driver client that raises one pre-built exception from the chosen calls."""

@pytest.fixture
def _client_sentinel(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(database, "_client", sentinel)
    monkeypatch.setattr(database, "_client_key", "sentinel-key")
    return sentinel
```

### Test module header (non-`db`)
```python
# SOURCE: tests/test_db_resilience_classify.py:1-24
"""PRD-018 STORY-002 (D2, Section 6.2 as amended 2026-11-17): the failure classifier.
...
Every test here is non-`db`: fake driver clients stand under the real
`_Connection` / `_Cursor` / `_translated()`, and no storage fixture is requested,
so nothing reaches a database and the module runs with Docker stopped.
"""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```

### Statement inspection through `ast`
```python
# SOURCE: tests/test_chat_sessions.py:91-102
    tree = ast.parse(inspect.getsource(getattr(database, name)))
    body = tree.body[0].body
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | `logging`/`random`/`Callable`/`TypeVar` imports, `logger`; retry constants + seams after `:81`; `StatementKind`, `_RETRIED_ON`, `_retryable`, `_failure_of`, `_retry_detail`, `_unit_of_work` after `_classify`/`_session`; 41 functions rewritten through `_unit_of_work`; two stale "nothing calls `_classify` yet" sentences (`:688-692`, `:777-779`) and the `__exit__` comment (`:397-400`) updated to name the caller. `_translated()` untouched |
| `tests/db_faults.py` | CREATE | `Fault`, `FaultScript`, `_FaultyClient`, captured-text constants (D-7) |
| `tests/conftest.py` | UPDATE | `faulty_db` fixture (lazy import), one docstring line in the module header naming it |
| `tests/test_db_resilience_retry.py` | CREATE | pure: loop, kind x class matrix, budget, deadline, jitter, fresh client, rollback rule, logs, `create_chat_session` rule, name -> kind pin |
| `tests/test_db_resilience_faults.py` | CREATE | `db`: one function per kind under before-forward faults, the landed `OUTCOME_UNKNOWN` on `admit_usage`, the batch replay, `create_chat_session` after a landed commit, logs |
| `tests/test_db.py` | UPDATE | two tests (Task 7), each modified assertion commented with PRD-018 D1/D5 |

No change to `app/db/errors.py`, `app/config.py`, any service, router or `chat_ui/` module. No new dependency.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: Vocabulary, constants, seams, logger

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: imports (`logging`, `random`; `Callable`, `TypeVar` from `typing`); `logger = logging.getLogger(__name__)` after `_TIMESTAMP_FORMAT` (`:49`); the three constants and the three seams (D-1) directly after `_IDLE_PROBE_AFTER_SECONDS` (`:81`) with a D5 / O6 / spike Q3 comment block; `StatementKind` (D-1) after `FailureClass` (`:695-712`).
- **Mirror**: `app/db/database.py:62-81`, `:695-712`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: `_retryable`, `_failure_of`, `_retry_detail`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: `_failure_of` (D-4) directly after `_classify` (`:774-814`); `_RETRIED_ON` + `_retryable` (D-2) and `_retry_detail` (D-5 bullet) next to it. Update the two "Nothing calls `_classify` yet" sentences (`:688-692`, `:777-779`) to "Its caller is `_failure_of()`, which `_unit_of_work` uses" and the `__exit__` comment (`:397-400`) to "for `_failure_of()` to read". Do not touch `_translated()` (`:649-685`).
- **Mirror**: `_classify`'s docstring style (`:774-798`): pure, order load-bearing, decisions cited
- **Validate**: import check; `git diff app/db/database.py` shows no hunk inside `_translated()`

### Task 3: `_unit_of_work`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: D-5, placed after `_session()` (`:817-828`) and before `init_db()` (`:831`). Docstring: D1 boundary, D3 rule, D5 budget and deadline (cannot cut a running call; spike F3a/Q3), the fresh-client rule and why it is here and not in `_translated()`, the non-`Hrana:` pass-through, the rollback rule, the re-runnable `_op` contract, the three STORY-005 hook comments (entry, success, failure), and "`init_db()` / `check_database_reachable()` never come here (D17)".
- **Mirror**: `_shared_client()` docstring (`:84-121`) for the narrative register
- **Validate**: import check

### Task 4: Rewrite the 41 functions

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: D-6 template, in file order, one function at a time, kinds from the table. The three exceptions (`insert_action_decisions` `ids`, `create_chat_session` counter + `IntegrityError` arm with a comment citing PRD 6.3 #11 and D3, `summary_snapshot` wrapper) and the "stays before / stays after" notes in the table. Docstrings unchanged, except one added sentence on `create_chat_session` (the retry rule), `insert_audit_log`/`insert_action_decisions` ("`NON_IDEMPOTENT` until STORY-004's `write_id`, PRD-018 D4") and `summary_snapshot` ("the batch is one unit; the fallback runs after its budget is spent").
- **Mirror**: D-6 `get_user` example
- **Validate**: import check; `grep -c "with _session() as conn" app/db/database.py` -> 2 (`_unit_of_work`, `init_db`); `grep -c "_unit_of_work(\"" app/db/database.py` -> 41

### Task 5: `_FaultyClient` harness and fixture

- **Files**: `tests/db_faults.py` (CREATE), `tests/conftest.py` (UPDATE)
- **Implement**: D-7. Module docstring: what each op/when models and the spike rows behind it, the lazy-install rule (wraps the current `libsql.connect`, so PRD-014's recorder stays underneath), "a new `ValueError` per fire, never a wrapper", "commit/rollback faults match by occurrence only", "the idle probe's `SELECT 1` goes through the proxy: use a specific `sql` prefix". `faulty_db` fixture beside `temp_db` (`tests/conftest.py:739-747`), lazy import; one line in the module docstring's bullet list (`:23-34`).
- **Mirror**: `tests/conftest.py:375-434` (`_RecordedClient`, `_recorded_connect`)
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_conftest_fixtures.py tests/test_db_isolation_harness.py -q -p no:cacheprovider`

### Task 6: `tests/test_db_resilience_retry.py` (new, non-`db`)

Header as `tests/test_db_resilience_classify.py:1-18`. A local `_ScriptedClient` (per-op failure text: `execute`, `fetchone`, `commit`, `rollback`), a `_clients(monkeypatch, *scripts)` helper that patches `database._shared_client` to hand out one new client per attempt and records them, a `_FakeTime` (`sleep(d)` advances `now`, records `sleeps`; `clock()` returns `now`; a fn can advance `now` to simulate a slow attempt), jitter patched to `lambda cap: cap` unless a test says otherwise, `_client`/`_client_key` restored via `monkeypatch`, `caplog` on `"app.db.database"`.

- **Matrix (AC 1, AC 2)**: parametrize kind x (text, failing op) -> expected attempts:
  - `NOT_SENT`@`execute` (`CONNECT_REFUSED`): all three kinds retried, success on attempt 2
  - `NOT_SENT` via dead stream @`commit` (`STREAM_EXPIRED` on commit): all three retried (orchestrator decision; supersedes AC 2's commit case)
  - `DEAD_STREAM`@`execute` (`INVALID_BATON`): all three retried
  - `DEAD_STREAM`@`fetchone`: `READ`/`IDEMPOTENT` retried, `NON_IDEMPOTENT` raised on attempt 1
  - `OUTCOME_UNKNOWN`@`execute` and @`commit` (`NAMESPACE_SHUTDOWN_503`): `READ`/`IDEMPOTENT` retried, `NON_IDEMPOTENT` raised on attempt 1
  - `STATEMENT` (`UNIQUE`, `NO_TABLE`): every kind raised on attempt 1 as `IntegrityError` / `MissingRelationError`, client not invalidated
  - each raised case asserts the exception type and message equal what `_session()` alone raises for the same fault (same type as today)
- `_retryable` over the full cartesian product of kinds x classes x phases (pure table)
- **Budget**: a persistent `DEAD_STREAM` runs `fn` exactly 3 times, raises the third attempt's `StorageError`; `sleeps == [0.05, 0.2]` with worst-case jitter; `len(_RETRY_BACKOFF_CAPS_SECONDS) == _RETRY_MAX_ATTEMPTS - 1`; the constants' values (3, (0.05, 0.2), 2.0)
- **Full jitter**: default `_retry_jitter` over 1000 draws stays in `[0, cap]` and is not constant; a recording jitter is asked for caps `[0.05, 0.2]` in order
- **Deadline**: attempt 1 advances the clock to 1.99 s with jitter 0 -> attempt 2 starts; to 2.01 s -> no attempt 2, raised, WARNING `reason=deadline`; 1.96 s + delay 0.05 -> not started (the projected start is checked); a 21 s first attempt (the connect stall) is never followed by a retry
- **Fresh client**: for `NOT_SENT`, `DEAD_STREAM` and `OUTCOME_UNKNOWN`, a spy on `database._invalidate_client` is called with the failed attempt's client before attempt 2, and attempt 2 runs on a different client object; for `STATEMENT` it is not called
- **Rollback rule (D-4)**: body `OUTCOME_UNKNOWN`@`execute` + rollback baton -> `NON_IDEMPOTENT` raised once, `READ` retried; body `DEAD_STREAM`@`execute` + rollback baton -> `NON_IDEMPOTENT` retried; body `DEAD_STREAM`@`fetchone` + rollback baton -> `NON_IDEMPOTENT` not retried; body `KeyError` + rollback baton -> `OUTCOME_UNKNOWN`; in every case the raised exception is the rollback's `StorageError`, as today; direct `_failure_of` unit tests for the tie and for the nested-`_translated()` shape (inner `StorageError` on `__context__`)
- **Pass-through**: a `fn` raising `StorageError("chat session not available for this owner")` runs once, no log, client kept; a `fn` raising `KeyError` / a non-driver `ValueError` propagates as the same object after one run
- **Logs (AC 5)**: exactly one INFO record per retry matching `^retry op=<name> class=<value> attempt=<n> detail=` with `n` = the failed attempt; a persistent failure -> 2 INFO + 1 WARNING `retry exhausted op=... attempts=3 reason=max_attempts`; a non-retryable refusal -> no record; `TURSO_AUTH_TOKEN` patched to a sentinel that appears in the text -> `***` in the record; a `near "SELECT secret_column": syntax error` text -> `near "<elided>"`; no record contains the `fn`'s SQL
- **`create_chat_session` rule**: with fake clients through the real function: attempt 1 commit raises `NAMESPACE_SHUTDOWN_503`, attempt 2 execute raises the `chat_sessions.session_id` UNIQUE text -> returns the id minted on attempt 1 (both executes carry the same id parameter); `IntegrityError` on attempt 1 -> raised; `IntegrityError` on a different constraint on attempt 2 -> raised
- **The pin (AC 3)**: D-8, the 41-row `_EXPECTED_KINDS` table copied from this plan with 6.3 row comments
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_retry.py -q -p no:cacheprovider` (runs with Docker stopped; PRD-014's guard fails any driver call)

### Task 7: The two `tests/test_db.py` tests that pinned "no retry" at the function level

- **File**: `tests/test_db.py`
- **Action**: UPDATE (names unchanged, so `_DELIBERATELY_SUPERSEDED_TESTS` is not touched)
- `test_a_second_connection_failure_surfaces_rather_than_looping` (`:4322-4343`): `assert len(built) == 1` -> `assert len(built) == database._RETRY_MAX_ATTEMPTS` with a comment: "PRD-018 D5: `count_audit_logs` is a `READ` unit retried at most three times, each attempt on a freshly built client (one from the idle probe's replacement, two from `_unit_of_work`'s rebuilds). Still bounded, still a `StorageError`: the premise holds." Optionally patch `database._retry_sleep` to a no-op to keep it fast. Expected count verified by trace: probe replaces (1), attempts 2 and 3 rebuild after `_translated()` dropped the client (2, 3).
- `test_a_dead_stream_mid_statement_invalidates_without_retrying` (`:4414-4450`): call through `with database._session() as conn: conn.execute("SELECT COUNT(*) AS n FROM audit_logs")` instead of `count_audit_logs()`; assertions unchanged; comment: "PRD-018 D1: the no-retry contract belongs to `_translated()` / `_session()`, and that is what this pins. The public read now retries at `_unit_of_work`, which `tests/test_db_resilience_retry.py` covers."
- **Validate**: the two tests by nodeid

### Task 8: `tests/test_db_resilience_faults.py` (new, `db`)

Header: PRD-018 STORY-003 D18, "every test requests `faulty_db`, so it is `db` by fixture closure; no `_DB_NODEIDS` entry". Fault texts from `tests.db_faults`.

- **AC 4, READ**: seed a user; `Fault(text, sql="SELECT * FROM USERS WHERE TOKEN_HASH")` for `text` in (`STREAM_EXPIRED`, `INVALID_BATON`, `CONNECT_REFUSED`) -> `find_user_by_token_hash` returns the seeded user (equal to a fault-free call), `script.forwarded(...) == 1`, `script.connects` grew (fresh client)
- **AC 4, IDEMPOTENT**: same three texts on `UPDATE CHAT_SESSIONS SET UPDATED_AT` -> `touch_chat_session` returns `True` and `updated_at` moved; and `create_chat_session` with a before-forward fault on `INSERT INTO CHAT_SESSIONS` -> one row, owned
- **AC 4, NON_IDEMPOTENT**: same three texts on `INSERT INTO USAGE_DAILY` -> `admit_usage("u-fault")` equals `admit_usage("u-clean")` on `day`, `window_requests`, `tokens_today`, and `usage_daily.requests == 1` for both; plus `Fault(STREAM_EXPIRED, op="commit")` (dead stream on commit = `NOT_SENT`) -> retried, `requests == 1`, two INSERTs forwarded
- **AC 4, landed OUTCOME_UNKNOWN on `admit_usage`**: `Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after")` -> `StorageError` propagates, `requests == 1` (moved by exactly 1), `script.forwarded("INSERT INTO USAGE_DAILY") == 1`, no INFO `retry` record. Companion: the same text on `execute`/`after` -> `StorageError`, `requests` row absent (rolled back), one INSERT forwarded (deviation 3)
- **Batch replay**: `Fault(INVALID_BATON, sql="INSERT INTO ACTION_DECISIONS", nth=2)` on a 3-row `insert_action_decisions` -> exactly 3 rows, 3 ids in input order, matching the table's ids (proves `ids` resets per attempt and rows 1..k-1 did not survive)
- **`create_chat_session` after a landed commit**: `Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after")` -> returns an id, exactly one `chat_sessions` row with that id, owned by the caller (the IntegrityError-on-retry rule against the real driver's constraint text)
- **AC 5 logs**: one retry -> exactly one INFO `retry op=find_user_by_token_hash class=dead_stream attempt=1`; `times=3` -> two INFO + one WARNING; `caplog.text` contains no `SELECT`, no `usage_daily`, no seeded token hash
- **AC 5 boot**: `init_db()` after `faulty_db` performs no retry: a `CONNECT_REFUSED` fault on `CREATE TABLE IF NOT EXISTS AUDIT_LOGS` -> one forwarded attempt, `StorageError`, no `retry` record (the existing `test_init_db_fails_fast_against_an_unreachable_endpoint` stays unchanged and is in the run)
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_faults.py -q -p no:cacheprovider`

### Task 9: Targeted regression run (one pytest process, never two at once; under ~10 minutes)

One call. `-k` matches module names as keywords, so the module-name terms keep every other file whole while the remaining terms select the `tests/test_db.py` subset:

```bash
K="test_db_resilience or test_conftest_fixtures or test_db_isolation_harness or test_usage_storage or test_chat_sessions or test_action_audit or test_identity or test_duplicate_checker or test_manage_users_cli or test_untouched_app or stream or second_connection or busy_client or constraint_violation or missing_table or summary_snapshot or token_hash or mark_audit_log or unreachable or guard or usage or chat_session or chat_message or insert_user or deactivate or set_user or action_decision or duplicate_timestamp"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider -k "$K" \
  tests/test_db_resilience_retry.py tests/test_db_resilience_faults.py tests/test_db_resilience_classify.py \
  tests/test_conftest_fixtures.py tests/test_db_isolation_harness.py \
  tests/test_usage_storage.py tests/test_chat_sessions.py tests/test_action_audit.py \
  tests/test_identity.py tests/test_duplicate_checker.py tests/test_manage_users_cli.py \
  tests/test_untouched_app.py tests/test_db.py
```

Planner collection on 2026-11-17, before the two new files existed: **564 of 707** collected. That is all 466 tests of the ten other files plus **98 of 241** `test_db.py` tests. The subset holds both modified tests, the STORY-024 section (`tests/test_db.py:4296-4495`), the summary-snapshot tests (`:1275-1930`), the boot-guard tests (`:5038-5160`, `test_init_db_fails_fast_against_an_unreachable_endpoint` included) and every user, usage, session and decision storage test. `test_pii_redaction_integration.py` is not needed because no test is renamed or removed. Record exact pass/fail/skip counts. Full suite: GitHub CI on push (user decision). If many `db` tests error at fixture setup, `docker restart harness-libsql-dev` and rerun.

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints OK
- [ ] `git diff app/db/database.py` has no hunk inside `_translated()` (`:649-685`) and none in `init_db()`'s body or `check_database_reachable()`
- [ ] `grep -n "with _session() as conn" app/db/database.py` -> exactly `_unit_of_work` and `init_db`
- [ ] `tests/test_db_resilience_retry.py` passes with Docker stopped (or `-m "not db"`): no driver call
- [ ] `tests/test_db_resilience_faults.py` passes; a failing case shows a `libsql diagnostics` section (recorder still under the proxy)
- [ ] `test_init_db_fails_fast_against_an_unreachable_endpoint` passes unchanged
- [ ] `grep -rn "_classify\|FailureClass\|StatementKind" app chat_ui scripts --include=*.py` finds them only in `app/db/database.py`

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest <Task 9 set> -q -p no:cacheprovider
PYTHONIOENCODING=utf-8 .venv/Scripts/python .agents/scripts/gen_index.py PRD-018   # after frontmatter edits: "errors: none"
```

No frontend, no npm lint in this repo.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| A mechanical rewrite drops or reorders a statement in one of 41 functions | Verbatim move rule (D-6); every function already has `tests/test_db.py` / module coverage in the Task 9 set; the AST pin catches a missing or mislabelled unit |
| `_op` closure state survives an attempt (double ids, double counts) | Only three functions keep state around the block; each handled explicitly (D-6) and the batch replay is tested against the real driver |
| A retry replays a landed non-idempotent effect | `NON_IDEMPOTENT` retries only `NOT_SENT` and `DEAD_STREAM`@`execute`; rollback masking resolved pessimistically (D-4); the landed `OUTCOME_UNKNOWN` test on `admit_usage` uses a real committed effect (D-7) |
| An unrecognised text is retried for `READ`/`IDEMPOTENT` and costs up to 0.25 s of sleep | Accepted by D5; the deadline bounds starts at 2 s; a persistent `SQLITE_BUSY` (`tests/test_db.py:4104-4134`) now takes 3 attempts and still raises the same type |
| The summary fallback multiplies attempts during an outage (1 batch + 13 figures, each up to 3 attempts) | Each unit stops starting attempts after 2 s, and a stall is never followed by a retry; STORY-005's breaker short-circuits the fan-out after 5 failed operations. Behaviour (partition, attribution) unchanged |
| Retry sleep on the event loop | Only for storage calls already made on the loop (`ChatState` `resolve()`, `state.py:967`, STORY-007's scope); all other async callers use `asyncio.to_thread` |
| Logs leak SQL or a credential | Only infrastructure classes are logged; `_redacted()` plus `near "..."` elision; tests assert the token and SQL are absent |
| `usage_limits.charge` already logs `str(exc)` raw (`app/services/usage_limits.py:217-227`) | Pre-existing, outside `app/db/`; flagged for STORY-012's log audit, not changed here |
| The faulty proxy leaks into the next test | `faulty_db` invalidates the cached client at install and at teardown |
| The copied conftest in `test_db_isolation_harness` children breaks | Lazy import inside `faulty_db`; that module is in the Task 9 run |
| `delete_chat_session` returns `False` after a landed retry | Deviation 4, recorded for the orchestrator |

---

## Open questions for the orchestrator

1. Confirm deviation 2 (`insert_audit_log` / `insert_action_decisions` `NON_IDEMPOTENT` until STORY-004). The alternative, `IDEMPOTENT` now, opens a duplicate-row window between the two commits.
2. Confirm deviation 3 (landed `OUTCOME_UNKNOWN` modelled on `commit`/`after`).
3. Should a non-retryable infrastructure refusal (`NON_IDEMPOTENT` on `OUTCOME_UNKNOWN`) also write a WARNING line? This plan writes none (AC 5 defines only the retry and the exhausted lines); STORY-005/012 count it at the marked failure hook.

---

## Acceptance Criteria

(Copied from story `STORY-003`, with the orchestrator decisions applied)

- [ ] `_unit_of_work(name, kind, fn)` retries a retryable class for its kind (`READ`/`IDEMPOTENT` on `NOT_SENT`, `DEAD_STREAM`, `OUTCOME_UNKNOWN`; `NON_IDEMPOTENT` on `NOT_SENT` and `DEAD_STREAM` on `execute` only) inside a fresh `_session()`, at most `_RETRY_MAX_ATTEMPTS = 3`, full jitter (<= 50 ms, <= 200 ms), no attempt started more than `_RETRY_START_DEADLINE_SECONDS = 2.0` after the first; pure tests with fake `fn`s, injected sleep, clock and randomness cover each kind x class cell -> Task 6
- [ ] `STATEMENT`, and `NON_IDEMPOTENT` on `OUTCOME_UNKNOWN`, raise on the first attempt with today's exception type; a dead stream on `commit` is `NOT_SENT` and **is** retried (orchestrator decision) -> Task 6 matrix
- [ ] All 41 public operational functions run through `_unit_of_work` with the kinds above, signatures and return values unchanged, `create_chat_session`'s retry `IntegrityError(chat_sessions.session_id)` is success, and a test pins name -> kind against the module's function list -> Tasks 4, 6 (D-8), 8
- [ ] `_FaultyClient` (monkeypatched `libsql.connect`, over PRD-014's recorder): before-forward `DEAD_STREAM`/`NOT_SENT` on a `READ`, an `IDEMPOTENT` and a `NON_IDEMPOTENT` function returns the fault-free result; a landed `OUTCOME_UNKNOWN` on `admit_usage` moves `usage_daily.requests` by exactly 1 and propagates -> Tasks 5, 8
- [ ] One INFO `retry op=<name> class=<class> attempt=<n>` per retry, one WARNING per exhausted budget, redacted, no SQL or parameters; `init_db()` still fails fast (`test_init_db_fails_fast_against_an_unreachable_endpoint` unchanged) -> Tasks 3, 6, 8, 9
- [ ] `_translated()` code and docstring unchanged; no breaker and no `StorageUnavailableError`; the three STORY-005 hooks are marked
- [ ] Backend imports; targeted run green (Task 9 counts recorded); full suite: GitHub CI on push (user decision)
- [ ] Follows existing patterns
