---
story: STORY-005
prd: PRD-018
slug: circuit-breaker-and-storage-unavailable
title: Reusable CircuitBreaker class, the storage instance, StorageUnavailableError
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-018-db-resilience        # all stories commit here, no per-story branch
created: 2026-11-17
---

# Plan: Circuit breaker and StorageUnavailableError (PRD-018 F4, D6, D7)

## Summary

Add a pure, reusable `CircuitBreaker` state machine in a new `app/services/circuit_breaker.py` (`BreakerStatus`, `BreakerOpen`, `CircuitBreaker`). It takes an injected monotonic clock and a pluggable half-open probe, and it is shaped as the contract PRD-022 (one breaker per provider, `probe=None`, `force_open`) and PRD-019 (`/ready` reads `status().state` and `retry_after_seconds`) consume. Add `StorageUnavailableError(StorageError)` with `retry_after_seconds: int` to `app/db/errors.py`. In `app/db/database.py`, add `_BREAKER_FAILURE_THRESHOLD = 5`, `_BREAKER_OPEN_SECONDS = 10.0`, a `_probe_fresh_client()` that runs one `SELECT 1` on a brand-new client under `_client_lock` and caches it on success, and exactly one `_storage_breaker`. Then wire the three STORY-003 hooks in `_unit_of_work`. **Rule chosen for this story: every infrastructure-class failure that leaves `_unit_of_work` is a `StorageUnavailableError`,** whether the retry budget ran out or a `NON_IDEMPOTENT` unit was refused a retry. It is raised `from` the original `StorageError` and keeps its message. `STATEMENT` failures and our own errors keep their exact type. A new autouse fixture in `tests/conftest.py` gives every test a fresh breaker, so no breaker state leaks between tests. Tests: `tests/test_circuit_breaker.py` (pure, threaded) and `tests/test_db_resilience_breaker.py` (a non-`db` part under PRD-014's guard and a `db` part on `faulty_db`). Two assertions in `tests/test_db_resilience_retry.py` change, each with a PRD-018 D7 comment.

## User Story

As a security admin
I want a process-local breaker that stops sending traffic to a database that is down and fails fast with a `StorageError` subclass
So that an outage is refused by the existing fail-closed arms and never waved through

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-005-circuit-breaker-and-storage-unavailable.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md`: Sections 6.1 (:130-152), 6.5 (:220-259, amended :229), 6.7 `Retry-After` rule (:279), 9.2 T1/T10 (:394, :403), 9.3 constants (:413), 10 Internal API (:448-460), 12 testing approach (:515-519), 15 D6/D7/D17 (:554-555, :565), Cross-PRD consumers (:637-641)
- STORY-003 hooks: `app/db/database.py:1063-1064` (entry), `:1117-1118` (failure), `:1120` (success)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (story `type: technical`, `complexity: medium`) |
| Complexity | MEDIUM: ~170 lines of new app code, mostly the state machine; ~25 lines of wiring |
| Systems Affected | `app/services/circuit_breaker.py` (new), `app/db/errors.py`, `app/db/database.py`, `tests/conftest.py` (one autouse fixture), `tests/test_db_resilience_retry.py` (two assertions), two new test files |
| Story | STORY-005 |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics). The story has `skills: []` and touches no UI | — |

---

## Pre-flight findings (verified by the planner on 2026-11-17)

| Fact | Evidence | Consequence |
|---|---|---|
| `_unit_of_work` has three marked hooks. The failure hook already runs once per operation for both "retry exhausted" and "retry refused" (the `raise` at :1119 follows both arms), and not for `STATEMENT` (the `if failure is not FailureClass.STATEMENT` at :1078 encloses both arms) | `app/db/database.py:1063-1121` | A `NON_IDEMPOTENT` refusal on `OUTCOME_UNKNOWN` counts **once**, as the amended PRD 6.5 (:229) requires. The record goes inside the `if` block, after both arms, never per attempt |
| A driver-free `StorageError` (e.g. `append_chat_message`'s ownership refusal) re-raises at :1075-1076 before any classification | `app/db/database.py:1074-1076` | It never records on the breaker and keeps its type |
| `_proved()` probes on the raw client under `_client_lock`, never through `get_connection()` (non-reentrant lock) | `app/db/database.py:193-232`, rule at :203-209 | `_probe_fresh_client()` follows the same rule: raw `libsql.connect` + `SELECT 1` inside `with _client_lock:` |
| No code path holds `_client_lock` while it calls anything outside `_shared_client`/`_proved`/`_invalidate_client` | `:181-190`, `:254-257`. `_unit_of_work` calls `_invalidate_client(stale)` (:1079) outside any lock | If the breaker never holds its own lock while it calls the probe, **no thread ever holds both locks**, so a deadlock cannot happen (Design D-3) |
| `app/services/__init__.py` is empty. `database.py` imports only `app.config`, `app.db.errors`, `app.db.models` | `app/db/database.py:26-61` | `from app.services.circuit_breaker import BreakerOpen, CircuitBreaker` adds no import cycle, provided `circuit_breaker.py` imports nothing from `app` |
| Pure service modules define their own `_TIMESTAMP_FORMAT` | `app/services/usage_limits.py:35` | `circuit_breaker.py` declares its own copy and does not import `database` |
| `check_duplicate` and `admit` catch `StorageError`. `find_user_by_token_hash` catches only `MissingRelationError`, inside the unit | `app/services/duplicate_checker.py:32-35`, `app/services/usage_limits.py:161-162`, `app/db/database.py:2196-2207` | AC 4 needs no change in those modules. The breaker-open raise happens at `_unit_of_work` entry, outside `_op`, so the narrow arm can never see it |
| Non-`db` tests replace `database._shared_client` and `libsql.connect` with `_refuse()` | `tests/conftest.py:667-674` | A non-`db` test with the breaker forced open proves "no call to `_shared_client()`" for free: reaching it fails the test |
| Conftest restores a module global with direct assignment, not `monkeypatch`, because `tests/test_db.py` calls `monkeypatch.undo()` | `tests/conftest.py:677-700` (`_default_pattern_policy`) | The breaker reset uses the same save, assign and restore idiom |
| Non-`db` retry tests exhaust budgets many times per module, each a recorded failure on the module breaker | `tests/test_db_resilience_retry.py:273-296, 507-551` | The reset must be autouse for **every** test, not only `db` ones. Without it, the 5th failing test in a module would open the breaker for the 6th |

---

## Design decisions

**D-1. Every infrastructure failure out of `_unit_of_work` is a `StorageUnavailableError`, including a refused `NON_IDEMPOTENT` retry.** PRD 6.1 (:141) says "raise (`StorageUnavailableError` if cls is infrastructure)", with no exception for a refusal. AC 4 names only exhaustion, but the reasons below point the same way:
- PRD user story 3 (:110-111): `admit_usage` with `OUTCOME_UNKNOWN` "fails closed with **503**". STORY-006's mapping is "`UsageLimitError` caused by `StorageUnavailableError` → 503; non-transient causes keep 500" (PRD :70). A refusal that raised a plain `StorageError` would map to **500**, which contradicts that story.
- The rule "`StorageUnavailableError` ⇔ the failure was an infrastructure class" is the one STORY-006 (503 vs 500), STORY-008/010 (journal on exhausted-or-open) and STORY-012 (counters) can each test with one `isinstance`. "Exhausted, but not refused" would make every consumer re-classify.
- It is still a `StorageError`. `check_duplicate`, `admit`, `charge` (fail open, `usage_limits.py:214-227`), the chat UI arms and `manage_users` (catches `IntegrityError` only) behave exactly as before.

`retry_after_seconds`: `record_failure` runs first. Then `retry_after_seconds = _storage_breaker.status().retry_after_seconds or 1`. That gives `1` while closed (PRD 6.7 :279), and `10` when this failure is the one that opened the breaker.

**D-2. The message and the chain are preserved: `raise StorageUnavailableError(str(exc), retry_after_seconds=...) from exc`.** `str()` is unchanged, so every existing assertion on the text (`tests/test_db_resilience_retry.py:280`, `:394`; `tests/test_db.py:4147` `"locked" in str(...)`) and today's `/query` 500 `detail` still hold. STORY-006 replaces that `detail` with fixed copy. No new driver text reaches a client that did not reach it before. `__cause__` is the translated `StorageError`, so `_failure_of(exc.__cause__)` and `_phase_of(exc.__cause__)` still work. The breaker-open raise carries fixed text with no driver text: `f"Storage unavailable: the {name} circuit breaker is open; retry after {n} s."`, raised `from` the `BreakerOpen`. `StorageUnavailableError` is never re-raised for `STATEMENT` failures or for non-driver errors, which keep their exact object (`tests/test_db_resilience_retry.py:462-492` stay green).

**D-3. Lock order: the breaker never holds its own lock while it runs the probe or logs.** The AC says the probe runs "under the breaker's own lock" so that only one runs. This plan meets that by claiming the probe under the lock, not by holding the lock while the probe runs:
- `before()` takes `self._lock`, sees `open` with the window elapsed, moves to `half_open`, sets `self._probing = True` and `self._generation += 1`, records the generation, and **releases the lock**. Then it runs `probe()`.
- Every other caller that arrives while `_probing` is set takes the lock, sees `half_open` + probing, and raises `BreakerOpen(1)` at once. It does not wait behind a probe that may stall for 21 s (PRD Risk 2). `status()` never blocks behind a probe either, which PRD-019's `/ready` depends on.
- `_probe_fresh_client()` takes `_client_lock`. `_shared_client` / `_proved` / `_invalidate_client` take only `_client_lock` and never touch the breaker. `_unit_of_work` calls breaker methods only outside `with _session()`, so outside `_client_lock`. **No thread ever holds both locks**, so no lock-order cycle can exist. A threaded test pins this (Task 6, test N6).
- The result is applied under the lock only if `self._generation` is still the claimed one and the state is still `half_open`. A `force_open()` during the probe wins, and a stale result is dropped.
- Transitions are computed under the lock and logged after it is released, so a slow log handler never extends the critical section.
- Deviation, stated in the code comment: the probe is claimed under the lock, not run under it, for the two reasons above (callers would block instead of being refused, and `/ready` would hang).

**D-4. Full transition table** (the pure tests pin every row):

| State | Event | Result | Log |
|---|---|---|---|
| closed | `record_failure(c)` | `consecutive_failures += 1`, `last_failure_class = c`. At `>= failure_threshold`: open, `open_until = now + open_seconds` | on open: `from=closed to=open class=c` (WARNING) |
| closed | `record_success()` | `consecutive_failures = 0` | none |
| closed | `before()` | returns | none |
| open | `before()`, `now < open_until` | `BreakerOpen(max(1, ceil(open_until - now)))` | none |
| open | `before()`, `now >= open_until` | half_open, this caller claims the trial | `from=open to=half_open class=none` (INFO) |
| half_open (probe set) | claimer runs `probe()`: True / False / raises | True → closed, count 0, `before()` returns. False → open for `open_seconds`, `BreakerOpen`. Raises → open for `open_seconds` and the exception propagates (try/finally, so the breaker can never stick in `_probing`) | `from=half_open to=closed class=none` (INFO) / `to=open class=probe` (WARNING) |
| half_open, trial claimed | `before()` from anyone else | `BreakerOpen(1)` | none |
| half_open (`probe=None`) | claimer's `before()` | returns; the claimer is the live trial | (the open→half_open line) |
| half_open (`probe=None`) | `record_success()` | closed, count 0 | `to=closed` |
| half_open (`probe=None`) | `record_failure(c)` | open for `open_seconds`, count += 1, class c | `to=open class=c` |
| half_open (`probe=None`), trial claimed more than `open_seconds` ago | `before()` | a new trial is admitted (a lease), so a trial that never reports, such as a `STATEMENT` failure, cannot wedge the breaker for PRD-022 | none |
| open | `record_success()` / `record_failure(c)` from a straggler that started before the open | success: no change. Failure: `last_failure_class = c` only, the window is not extended | none |
| any | `force_open(s)` | open, `open_until = now + s`, `_generation += 1`, count unchanged | only when the state changes: `to=open class=forced` |

`last_failure_class` is a free string and stays as is on a probe failure (it remains the D2 class of the outage). `retry_after_seconds` is `None` while closed, `max(1, ceil(remaining))` while open, and `1` while half_open. `since` is wall-clock UTC in `_TIMESTAMP_FORMAT` at the last transition (construction time at first), read through a module seam `_wall_clock` so tests can pin it. The state machine itself reads only `clock`.

**D-5. The constructor has no storage defaults and validates its arguments.** Signature: `CircuitBreaker(name: str, failure_threshold: int, open_seconds: float, clock: Callable[[], float] = time.monotonic, probe: Optional[Callable[[], bool]] = None)`. `failure_threshold < 1` or `open_seconds <= 0` raises `ValueError` naming the breaker and the rule (house style: errors name the thing and the rule).

**D-6. Logging lives in the class**, `logging.getLogger(__name__)`, format `"breaker name=%s from=%s to=%s class=%s"`. The `name=` field is why: PRD-022's per-provider breakers get the same line for free. The stdlib logger is the only side effect. The module imports no settings and opens no file or socket, which an AST pin asserts (Task 5).

**D-7. Test isolation: an autouse `_fresh_storage_breaker` fixture in `tests/conftest.py`**, declared right after `_storage_policy`. It saves `database._storage_breaker`, assigns a new `CircuitBreaker("storage", database._BREAKER_FAILURE_THRESHOLD, database._BREAKER_OPEN_SECONDS, probe=database._probe_fresh_client)`, yields, and restores the original by direct assignment (the `_default_pattern_policy` idiom, safe against `monkeypatch.undo()`). It applies to every test, `db` or not, and the module-level instance is never driven by a test. **How a test gets an open breaker:**
- (a) `database._storage_breaker.force_open(10.0)`, the simplest, for ingress tests in STORY-006/007.
- (b) For clock control: `monkeypatch.setattr(database, "_storage_breaker", CircuitBreaker("storage", database._BREAKER_FAILURE_THRESHOLD, database._BREAKER_OPEN_SECONDS, clock=lambda: now[0], probe=database._probe_fresh_client))`. `_unit_of_work` reads the global once per call.
- (c) Drive five real failing operations.

The isolation-harness child runs copy `conftest.py` (`tests/test_db_isolation_harness.py:520-525`) and get the fixture too. That is harmless, because they never run a unit of work.

---

## Patterns to Follow

### Naming / module constants
```python
# SOURCE: app/db/database.py:118-123
# Module constants rather than settings (O6) for the reason `_IDLE_PROBE_AFTER_SECONDS`
# is one: a deployment knob whose wrong value silently restores the defect is not
# a knob worth having.
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_CAPS_SECONDS = (0.05, 0.2)
_RETRY_START_DEADLINE_SECONDS = 2.0
```

### Probe on a raw client under the lock
```python
# SOURCE: app/db/database.py:224-232 (_proved)
    try:
        client.execute("SELECT 1").fetchone()
    except ValueError as exc:
        if _DRIVER_ERROR not in str(exc):
            raise
        return libsql.connect(key[0], auth_token=key[1])
    return client
```

### Error type with an attribute
```python
# SOURCE: app/db/errors.py:94-96 (DatabaseUnreachableError)
    def __init__(self, endpoint: str, message: str) -> None:
        self.endpoint = endpoint
        super().__init__(message)
```

### Frozen dataclass, Literal vocabulary
```python
# SOURCE: app/services/usage_limits.py:39, 52-63
UsageLimit = Literal["requests", "tokens"]

@dataclass(frozen=True)
class UsageRefusal:
    limit: UsageLimit
    ...
    resets_at: str  # UTC, _TIMESTAMP_FORMAT
```

### Autouse save/restore of a module global
```python
# SOURCE: tests/conftest.py:696-700
    original = pattern_config._policy
    yield
    pattern_config._policy = original
```

### Tests: fake world under the real seams
```python
# SOURCE: tests/test_db_resilience_retry.py:111-139 (_World), 206-230 (matrix)
world = _World(monkeypatch, {op: text})
with pytest.raises(StorageError) as raised:
    world.run(kind)
```
Cross-module import of test helpers has precedent (`tests/test_pattern_config.py:58`, `tests/test_action_corpus.py:125`), so `tests/test_db_resilience_breaker.py` imports `_World` from `tests.test_db_resilience_retry`.

### Threads released together
```python
# SOURCE: tests/test_db.py:4627-4645 (_run_concurrently: threading.Barrier(count, timeout=30))
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/circuit_breaker.py` | CREATE | `BreakerStatus`, `BreakerOpen`, `CircuitBreaker` (pure, reusable by PRD-022/019) |
| `app/db/errors.py` | UPDATE | `StorageUnavailableError(StorageError)` with `retry_after_seconds: int` |
| `app/db/database.py` | UPDATE | constants, `_probe_fresh_client`, `_storage_breaker`, the three hooks in `_unit_of_work`, docstring update |
| `tests/conftest.py` | UPDATE | autouse `_fresh_storage_breaker`; module docstring bullet |
| `tests/test_db_resilience_retry.py` | UPDATE | two assertions (matrix type check for refused infrastructure rows; `_phase_of` on `__cause__`), each with a PRD-018 D7 comment |
| `tests/test_circuit_breaker.py` | CREATE | pure state-machine tests, injected clock, both probe modes threaded, purity pin |
| `tests/test_db_resilience_breaker.py` | CREATE | non-`db` (guard, consumers, wiring, lock order) and `db` (`faulty_db`: open after 5, probe, statement-neutral, boot bypass) |

No change to `duplicate_checker.py`, `usage_limits.py`, `identity.py`, routers or the chat UI (AC 4 and the story's "stops at the exception").

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: `StorageUnavailableError`

- **File**: `app/db/errors.py`
- **Action**: UPDATE (append after `DatabaseAuthError`)
- **Implement**: `class StorageUnavailableError(StorageError)` with `__init__(self, message: str, retry_after_seconds: int)`. Set `self.retry_after_seconds = retry_after_seconds`, then `super().__init__(message)`. Docstring: PRD-018 D7 / Section 6.5. Raised only by `database._unit_of_work`: breaker open, or an infrastructure-class failure (exhausted or refused a retry). A `StorageError` on purpose ("subclass, don't widen", PRD 6.10), so `check_duplicate` / `admit` fail closed with no change, while `MissingRelationError`'s arm stays narrow and never reads an outage as a bad credential. `retry_after_seconds` is ≥ 1: seconds to the breaker's next half-open, or 1 when only this operation's budget ran out (PRD 6.7). The message may carry driver text (it is the original failure's). STORY-006 shows clients fixed copy. Do **not** add `AuditUnavailableError` (STORY-008).
- **Mirror**: `app/db/errors.py:74-96`
- **Validate**: `.venv/Scripts/python -c "from app.db.errors import StorageUnavailableError, StorageError; e=StorageUnavailableError('x', retry_after_seconds=1); assert isinstance(e, StorageError) and e.retry_after_seconds == 1 and str(e) == 'x'; print('OK')"`

### Task 2: `app/services/circuit_breaker.py`

- **File**: `app/services/circuit_breaker.py`
- **Action**: CREATE
- **Implement**:
  - Module docstring: PRD-018 Section 6.5, D6/D7. One class, storage holds one instance and PRD-022 one per provider (cross-PRD consumers, PRD :637-641). Pure (no settings, no I/O beyond the stdlib logger). Explain the D-3 claim-don't-hold rule and why (callers refused rather than blocked, `/ready` never blocks).
  - Imports: stdlib only (`logging`, `math`, `threading`, `time`, `dataclasses`, `datetime`, `typing`).
  - `_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"` (copy, `usage_limits.py:35` precedent). `_wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)` as a seam, written as a `def`.
  - `BreakerState = Literal["closed", "open", "half_open"]`.
  - `@dataclass(frozen=True) class BreakerStatus`: `state: BreakerState`, `since: str`, `consecutive_failures: int`, `last_failure_class: Optional[str]`, `retry_after_seconds: Optional[int]`. Docstring: a contract with PRD-019 `/ready` and PRD-022 `/providers/status`. Contains no lock, client or callable, so it serializes as is.
  - `class BreakerOpen(Exception)`: `__init__(self, name: str, retry_after_seconds: int)`, attributes `name` and `retry_after_seconds`, message `f"{name} circuit breaker is open; retry after {retry_after_seconds} s"`.
  - `class CircuitBreaker` per D-4 and D-5. Private state: `_lock = threading.Lock()`, `_state`, `_since`, `_failures`, `_last_class`, `_open_until`, `_probing`, `_trial_claimed_at`, `_generation`. Public: `before()`, `record_success()`, `record_failure(failure_class: str)`, `force_open(seconds: float)`, `status() -> BreakerStatus`, plus a read-only `name` property. A private `_transition(to, cls) -> tuple` runs under the lock and returns the log tuple. A private `_emit(transitions)` logs after the lock is released. `_retry_after(now)` returns `max(1, math.ceil(self._open_until - now))`.
  - `before()` probe path: claim under the lock (D-3), then `try: ok = bool(self._probe())` and `except BaseException:` reopen under the lock (if the generation still matches), emit, re-raise. Then apply the result under the lock if the generation matches and the state is half_open, emit, and on failure `raise BreakerOpen(self._name, retry_after)`. If the generation no longer matches (a `force_open` won), compute from the current state: still open → `BreakerOpen`.
  - Log levels: `to=open` WARNING, everything else INFO.
- **Mirror**: `app/services/usage_limits.py:23-82` (module docstring style, frozen dataclasses, Literal)
- **Validate**: `.venv/Scripts/python -c "import app.services.circuit_breaker as m; print('OK')"`

### Task 3: Storage instance and probe in `database.py`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  1. Import: `from app.services.circuit_breaker import BreakerOpen, CircuitBreaker` (after the `app.db.models` import block, :34-61). Add `StorageUnavailableError` to the `app.db.errors` import (:27-33).
  2. After the retry seams (:136-138), add the constants with a comment block in house style: PRD-018 D6, Section 6.5. Five consecutive infrastructure-failed **operations** (not attempts), 10 s open. Constants, not settings (O6, the `_IDLE_PROBE_AFTER_SECONDS` sentence). They are the storage instance's arguments, never the class's defaults (PRD :232).
     `_BREAKER_FAILURE_THRESHOLD = 5`, `_BREAKER_OPEN_SECONDS = 10.0`.
  3. After `_invalidate_client` (:235-257), add `def _probe_fresh_client() -> bool:`. Docstring: the half-open probe (PRD 6.5 :231). One `SELECT 1` on a **brand-new** client, under `_client_lock`, never through `get_connection()` (the `_proved()` rule, :203-209: re-entering `_shared_client()` would deadlock on the non-reentrant lock). Never through `check_database_reachable()` (boot-only, D17). On success the new client replaces the cached one, so the first request after recovery does not pay a second handshake. On a driver failure it returns `False` and leaves the cache alone. A non-`Hrana:` `ValueError` is re-raised (the `_proved()` rule). It is called only by the breaker, which never holds its own lock while calling it (lock order, D-3). Body:
     ```python
     global _client_key, _client, _client_used_at
     key = (settings.DATABASE_URL, settings.TURSO_AUTH_TOKEN)
     with _client_lock:
         client = libsql.connect(key[0], auth_token=key[1])
         try:
             client.execute("SELECT 1").fetchone()
         except ValueError as exc:
             if _DRIVER_ERROR not in str(exc):
                 raise
             return False
         _client, _client_key, _client_used_at = client, key, time.monotonic()
         return True
     ```
     (`libsql.connect` is lazy, so a connect failure surfaces on `execute`: spike F1. If `connect` itself raises a driver `ValueError`, catch it the same way. Put it inside the `try`.)
  4. Immediately after it, exactly one assignment:
     `_storage_breaker = CircuitBreaker("storage", _BREAKER_FAILURE_THRESHOLD, _BREAKER_OPEN_SECONDS, probe=_probe_fresh_client)`
     The comment says: one per process, matching the one client per process (`_shared_client` docstring). `/query`, `/v1` and the chat UI share it in a Reflex deployment (PRD :228). `storage_status()` (STORY-012) reads `.status()`. Tests swap it per test (`tests/conftest.py::_fresh_storage_breaker`).
- **Mirror**: `app/db/database.py:193-232`, `:99-123`
- **Validate**: `.venv/Scripts/python -c "from app.db import database as d; print(d._storage_breaker.status())"` prints `state='closed'` and makes no network call (the probe runs only in half_open).

### Task 4: Wire the hooks in `_unit_of_work`

- **File**: `app/db/database.py:1015-1121`
- **Action**: UPDATE
- **Implement**:
  - Entry (replace the comment at :1063-1064):
    ```python
    breaker = _storage_breaker  # read once: a test may swap the instance
    try:
        breaker.before()
    except BreakerOpen as refused:
        raise StorageUnavailableError(
            f"Storage unavailable: the {refused.name} circuit breaker is open; "
            f"retry after {refused.retry_after_seconds} s.",
            retry_after_seconds=refused.retry_after_seconds,
        ) from refused
    ```
    This sits before `first_started` and before any `_session()`, so an open breaker never reaches `_shared_client()` (PRD :230).
  - Failure (replace the comment at :1117-1118). **Inside** the `if failure is not FailureClass.STATEMENT:` block, after the exhausted/refused `if/else`:
    ```python
    breaker.record_failure(failure.value)
    retry_after = breaker.status().retry_after_seconds or 1
    raise StorageUnavailableError(str(exc), retry_after_seconds=retry_after) from exc
    ```
    The bare `raise` at :1119 stays for `STATEMENT`, so `IntegrityError` / `MissingRelationError` propagate as the same object and the count is unchanged. Do not add any new log line here; the breaker logs transitions itself.
  - Success (replace the comment at :1120): `breaker.record_success()` before `return result`.
  - Docstring: add a **Breaker (D6, D7)** paragraph. `before()` first: open → `StorageUnavailableError` with no client touched. One `record_failure` per operation whose final failure is an infrastructure class, exhausted **or refused** (PRD 6.5 as amended: counted once). `STATEMENT` and our own errors leave it alone. Every infrastructure failure leaves as `StorageUnavailableError(str(exc)) from exc` (D-1, D-2). Update the sentence "The last attempt's exception is what propagates, same type and message as before this story" to: same message, now as `StorageUnavailableError` chained `from` it. Keep the D17 sentence. **Do not touch `_translated()` or its docstring** (D1).
- **Mirror**: the existing structure of `:1074-1121`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_retry.py -q` (it fails on exactly the two assertions Task 7 updates until then; any other failure is a wiring bug)

### Task 5: Pure tests, `tests/test_circuit_breaker.py`

- **File**: `tests/test_circuit_breaker.py`
- **Action**: CREATE (non-`db`, imports only `app.services.circuit_breaker` + stdlib + pytest)
- **Implement** (fake clock `now = [0.0]`, `clock=lambda: now[0]`, `caplog` on `app.services.circuit_breaker`):
  - P1 `closed → open` after exactly `failure_threshold` consecutive `record_failure` calls (threshold 3 and 5). At threshold−1 it is still closed.
  - P2 `record_success()` resets the count: 4 failures, 1 success, 4 failures → still closed.
  - P3 `before()` while open raises `BreakerOpen` with `retry_after_seconds` rounded up and ≥ 1: open_seconds 10 at t=0 → 10; t=0.8 → 10; t=9.2 → 1; t=9.99 → 1. Parametrize.
  - P4 `open → half_open` exactly at `open_seconds`: at t=9.999 still `BreakerOpen`; at t=10.0 the probe runs.
  - P5 probe True → closed, count 0, `before()` returns. Probe False → open for another `open_seconds` (retry_after 10 measured from the probe time), and `last_failure_class` keeps the D2 class. A probe that raises → reopened, the exception propagates, and the next `before()` after the window probes again (not stuck).
  - P6 `force_open(30)` from closed with count 0 → open, retry_after 30. A `force_open` during a running probe (the probe calls `force_open` itself) → the probe's True result is dropped and the state stays open.
  - P7 `status()`: frozen (`dataclasses.FrozenInstanceError` on assignment). Field names exactly `("state","since","consecutive_failures","last_failure_class","retry_after_seconds")`. `json.dumps(dataclasses.asdict(status))` works. No field value is callable, a lock or anything but `str`/`int`/`None`. `retry_after_seconds is None` while closed, `1` while half_open. `since` matches `^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$` and changes on a transition (patch `circuit_breaker._wall_clock`).
  - P8 Contract with PRD-022: `inspect.signature(CircuitBreaker)` has `failure_threshold` and `open_seconds` with **no** default, `clock` defaults to `time.monotonic`, `probe` defaults to `None`. `failure_threshold=0` / `open_seconds=0` raise `ValueError` naming the breaker.
  - P9 Logs: drive closed→open→half_open→closed, then →open→half_open→open (probe False). Assert exactly one record per transition, matching `^breaker name=storage from=closed to=open class=not_sent$` and so on. No record for a failure below the threshold, a refused `before()`, or `record_success` while closed.
  - P10 Stragglers: `record_failure` while open does not extend `open_until` and does not log. `record_success` while open does not close.
  - P11 **Threaded, probe mode**: the probe blocks on `threading.Event` `release` and counts its calls. Eight threads released by `threading.Barrier(8, timeout=5)` call `before()` at t ≥ open_seconds. Assert: within a short `join(timeout=2)` the seven non-claimers have all finished with `BreakerOpen` **while the probe is still blocked**. `status()` returns `half_open` from the main thread without blocking. Then `release.set()`: the claimer returns normally, probe calls == 1, state closed. Repeat with the probe returning False: claimer gets `BreakerOpen`, state open. No `time.sleep` anywhere; every wait is an event/barrier/join with a timeout.
  - P12 **Threaded, `probe=None`**: at t ≥ open_seconds, eight barrier-released threads call `before()`. Exactly one returns (the trial), seven get `BreakerOpen`. Further `before()` calls keep getting `BreakerOpen` until the trial calls `record_success()` (→ closed, then everyone is admitted) or, in a second case, `record_failure("x")` (→ open). Lease: with the trial silent, at t = claim + open_seconds a new single trial is admitted.
  - P13 Purity pin: parse `app/services/circuit_breaker.py` with `ast`. Every `Import`/`ImportFrom` is in the stdlib set above (no `app.*`, no `libsql`). The source contains no `open(`, `socket`, `settings`.
- **Mirror**: `tests/test_db_resilience_retry.py:173-180` (caplog filter), `tests/test_db.py:4627-4645` (barrier)
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_circuit_breaker.py -q`

### Task 6: Storage wiring tests, `tests/test_db_resilience_breaker.py`

- **File**: `tests/test_db_resilience_breaker.py`
- **Action**: CREATE. The module docstring says which tests are non-`db` (guarded by PRD-014: any driver call fails them) and which are `db` (request `faulty_db`).
- **Implement**: helper fixture `breaker_clock(monkeypatch)` that installs a clock-injected storage instance (D-7 (b)) and yields `now`.

  *Non-`db`:*
  - N1 Single instance: AST over `database.py` finds exactly one `CircuitBreaker(` call, assigned to `_storage_breaker`, with args `("storage", _BREAKER_FAILURE_THRESHOLD, _BREAKER_OPEN_SECONDS)` and `probe=_probe_fresh_client`. `database._BREAKER_FAILURE_THRESHOLD == 5`, `database._BREAKER_OPEN_SECONDS == 10.0`. `_storage_breaker.name == "storage"`.
  - N2 Open breaker, no driver call (T1): `database._storage_breaker.force_open(7.0)`, then `database.find_duplicate_timestamp("u", "k", "2026-01-01T00:00:00Z")` raises `StorageUnavailableError` with `retry_after_seconds == 7`. The PRD-014 guard proves `_shared_client` was never reached (also patch `database._shared_client` with a counting stub that raises, and assert 0 calls, so the claim does not rest on the guard alone). The message contains no `Hrana`.
  - N3 Consumers, no code change (AC 4), each with the breaker forced open: `check_duplicate("u", "k")` raises `DuplicateCheckError` whose `__cause__` is a `StorageUnavailableError`. `usage_limits.admit(Identity("u1", "user"), charges_budget=True)` raises `UsageLimitError`, cause `StorageUnavailableError`. `database.find_user_by_token_hash("h")` **raises** `StorageUnavailableError` (does not return `None`), so `identity.resolve` cannot read an outage as a bad credential.
  - N4 Wiring with `_World` (imported from `tests.test_db_resilience_retry`) and a `breaker_clock` instance: a READ exhausting 3 attempts → `StorageUnavailableError`, `retry_after_seconds == 1`, `__cause__` is a `StorageError` whose `str` is the text, `status().consecutive_failures == 1` (one per operation, not 3). Five such operations → the fifth raises with `retry_after_seconds == 10` and the state is open. A sixth builds **no** client (`len(world.clients)` unchanged).
  - N5 `STATEMENT` is neutral: five `_UNIQUE`/`_NO_TABLE` failures → `IntegrityError`/`MissingRelationError` (exact types), count 0, still closed. Our own `StorageError("chat session not available ...")` → same object, count 0. Refused `NON_IDEMPOTENT` on `OUTCOME_UNKNOWN` (`NAMESPACE_SHUTDOWN_503` on execute) → exactly one `world.runs`, `StorageUnavailableError`, `consecutive_failures == 1`, `last_failure_class == "outcome_unknown"`. A success after four failures → count 0.
  - N6 **Lock order (deadlock test)**: `breaker_clock` at t ≥ 10 after `force_open(10)`. Patch `libsql.connect` (overriding the guard for this test) with a fake whose `execute("SELECT 1")` waits on `threading.Event` `go` and records `database._client_lock.locked()`. Thread A calls `database._storage_breaker.before()`, which runs the probe and holds `_client_lock`. Once A is inside `execute` (an `entered` event), from other threads: `status()` returns `half_open` at once, `before()` raises `BreakerOpen` at once (both `join(timeout=1)`), and a thread calling `database._invalidate_client()` is still alive (blocked on `_client_lock`). `go.set()`, then every thread joins within 2 s (no deadlock), state closed, `database._client is` the fake client. The idle gate is satisfied (`_client_used_at` refreshed). Use `monkeypatch.setattr` on `database._client`/`_client_key`/`_client_used_at` first so they are restored. `_shared_client` stays the guard's refusal throughout: the probe went through neither `get_connection()` nor `_shared_client()`.
  - N7 Probe failure keeps the cache: the fake raises `ValueError(CONNECT_REFUSED)` → `before()` raises `BreakerOpen`, the state is open again, and `database._client` is unchanged. A fake raising `ValueError("not the driver's")` propagates that exact object, and the breaker is open (not stuck half_open).
  - N8 Boot bypass pin: `test_the_boot_path_never_meets_the_unit_of_work` already pins the AST (`tests/test_db_resilience_retry.py:751-755`). Add an AST check that `_storage_breaker` is referenced in no function but `_unit_of_work` (`storage_status` joins in STORY-012).

  *`db` (request `faulty_db`; patch `database._retry_sleep` to a no-op):*
  - B1 Open after 5 real operations: `faulty_db.add(Fault(CONNECT_REFUSED, sql="SELECT COUNT(*) AS N FROM AUDIT_LOGS", times=15))`. Five `count_audit_logs()` calls each raise `StorageUnavailableError`. After the fifth the state is open. A sixth raises immediately, `faulty_db.forwarded(...)` and `len(faulty_db.fired)` unchanged, `faulty_db.connects` unchanged.
  - B2 Recovery through the real probe (`breaker_clock`): after B1's setup, advance to t=10. The next `count_audit_logs()` succeeds. `faulty_db.connects` rose by exactly 1 (the probe's client), and `database._client` is that client (no further connect on the following call). Variant: `faulty_db.add(Fault(CONNECT_REFUSED, sql="SELECT 1"))` → the probe fails, `StorageUnavailableError` with `retry_after_seconds == 10`, the state is open.
  - B3 Statement-neutral against the real server: `DROP TABLE audit_logs`, then six `count_audit_logs()` → `MissingRelationError` every time, `status().state == "closed"`, count 0.
  - B4 `NON_IDEMPOTENT` counted once: `faulty_db.add(Fault(NAMESPACE_SHUTDOWN_503, op="commit", when="after"))`, then `admit_usage("dana")` raises `StorageUnavailableError` with `retry_after_seconds == 1`, `consecutive_failures == 1`, and the counter row moved exactly once (the effect landed: `_usage_row`, mirror `tests/test_db_resilience_faults.py:176-187`).
  - B5 D17: with `database._storage_breaker.force_open(10)`, `init_db()` and `check_database_reachable()` succeed against the healthy server, and the state is still open. Then `faulty_db.add(Fault(CONNECT_REFUSED, sql="SELECT 1", times=5))` on a fresh closed breaker: `init_db()` raises `DatabaseUnreachableError` and `status().consecutive_failures == 0`.
  - B6 Logs: B1+B2 produce exactly `from=closed to=open class=not_sent`, `from=open to=half_open class=none`, `from=half_open to=closed class=none` on `app.services.circuit_breaker`, and no line contains `SELECT` or the auth token.
- **Mirror**: `tests/test_db_resilience_faults.py:60-110` (seeding, `faulty_db.add`, `forwarded`), `tests/test_usage_limits.py:296-307`, `tests/test_duplicate_checker.py:131-133`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_breaker.py -q`

### Task 7: Conftest reset and the two pinned assertions

- **File**: `tests/conftest.py`
- **Action**: UPDATE
- **Implement**: import `from app.services.circuit_breaker import CircuitBreaker` with the other app imports (:86-91). Add after `_storage_policy` (:599-674):
  ```python
  @pytest.fixture(autouse=True)
  def _fresh_storage_breaker():
      """Every test starts with a closed storage breaker of its own (PRD-018 STORY-005). ..."""
      original = database._storage_breaker
      database._storage_breaker = CircuitBreaker(
          "storage", database._BREAKER_FAILURE_THRESHOLD, database._BREAKER_OPEN_SECONDS,
          probe=database._probe_fresh_client,
      )
      yield
      database._storage_breaker = original
  ```
  The docstring explains: module state that every unit of work records into, so without this the fifth test that exhausts a retry would open it for the sixth. It applies to every test, not only `db` ones (the non-`db` retry tests record failures too). Direct assignment for the `_default_pattern_policy` reason (`monkeypatch.undo()` in `tests/test_db.py`). How a test gets an open breaker: `force_open(seconds)`, or `monkeypatch.setattr(database, "_storage_breaker", CircuitBreaker(..., clock=...))`. Add one bullet to the module docstring list (:23-37): "**The breaker.** ...".
- **File**: `tests/test_db_resilience_retry.py`
- **Action**: UPDATE (two assertions; no test renamed, so nothing for `_DELIBERATELY_SUPERSEDED_TESTS`)
  1. `test_the_kind_by_class_matrix` (:225): the not-retried branch now separates `STATEMENT` rows from infrastructure rows refused a retry (`dead_stream_on_fetch`, `outcome_unknown_on_execute`, `outcome_unknown_on_commit`, `unrecognised_text` × `NON_IDEMPOTENT`). For the latter: `type(raised.value) is StorageUnavailableError`, `type(raised.value.__cause__) is type(direct.value)`, `raised.value.retry_after_seconds == 1`. `str(...) == text` still holds for both. Comment: `# PRD-018 D7 / PRD 6.1 (STORY-005): an infrastructure failure leaves _unit_of_work as StorageUnavailableError raised from today's exception; the message is unchanged.`
  2. `test_a_rollback_that_masks_the_body_is_judged_pessimistically` (:395): `_phase_of(raised.value)` becomes `_phase_of(raised.value.__cause__)`, with the same comment.
  - Nothing else in that file needs a change: `pytest.raises(StorageError)` matches the subclass, `str(...)` is preserved, and `raised.value.__cause__ is not None` (:281) holds.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_retry.py tests/test_db_isolation_harness.py -q`

### Task 8: Regression sweep (targeted, never two pytest processes at once)

- Check every test that reads the exact type of a persistent infrastructure failure. Verified by the planner, all expected green with no edit:
  - `tests/test_db.py:4127-4147` (SQLITE_BUSY → `OUTCOME_UNKNOWN`, READ, exhausted): `pytest.raises(StorageError)`, `not isinstance(MissingRelationError)`, `"locked" in str`.
  - `:4339-4361` (`test_a_second_connection_failure_surfaces_rather_than_looping`): `pytest.raises(StorageError)`, construction count, `_client is None`.
  - `:2598-2607` `mark_audit_log_failed` typed error.
  - `:4462-4470` drives `_session()` directly.
  - `tests/test_db_resilience_classify.py:394-449` drives `_translated()` directly; `type is StorageError` is unaffected.
  - `tests/test_query_router.py:210` (`MissingRelationError` → `STATEMENT` → unchanged 500).
  - `tests/test_chat_sessions.py:1734`, `tests/test_query_pipeline_tools.py:858` assert `isinstance(__cause__, StorageError)`, still true.
  - `tests/test_db.py:5090` / `tests/test_main.py:174` (boot path, no unit of work).
- A test that runs **five or more** infrastructure-failing units in one test body would now see the breaker open from the sixth (fast `StorageUnavailableError` instead of a network attempt). None was found in `test_db_resilience_faults.py` (one fault per test). The 8-thread `test_many_threads_finding_the_stream_dead_together_build_one_client` asserts `failures == []`, so it never fails 5 times. If such a test appears in the run, keep its premise and either raise its breaker's threshold via `monkeypatch.setattr(database, "_storage_breaker", CircuitBreaker("storage", 1000, 10.0, probe=...))` with a PRD-018 D6 comment, or assert the new fast-fail. Report it.
- **Validate** (sequentially):
  1. `.venv/Scripts/python -c "from app.main import app; print('OK')"`
  2. `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_circuit_breaker.py tests/test_db_resilience_breaker.py tests/test_db_resilience_retry.py tests/test_db_resilience_faults.py tests/test_db_resilience_classify.py tests/test_db_resilience_write_id.py tests/test_duplicate_checker.py tests/test_usage_limits.py tests/test_identity.py tests/test_db_isolation_harness.py tests/test_untouched_app.py tests/test_query_router.py -q`
  3. `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db.py -q -k "stream or probe or client or connection_failure or token_hash or unreachable or locked or mark_audit_log_failed or no_driver_exception or add_missing_columns"`
  4. Full suite: GitHub CI on push (user decision).

---

## End-to-End Tests

- [ ] With the app imported, `database._storage_breaker.status()` is `closed`, `retry_after_seconds=None`, and making it costs no network call.
- [ ] B1/B2 (`db`): five real `NOT_SENT` operations open the breaker; the sixth issues no driver call; after 10 s (injected clock) one `SELECT 1` on a new client closes it and that client is the cached one.
- [ ] N2/N3 (non-`db`, PRD-014 guard): open breaker → `StorageUnavailableError` / `DuplicateCheckError` / `UsageLimitError`, zero `_shared_client` calls.
- [ ] N6: the probe holds `_client_lock` while `status()` and `before()` answer immediately from other threads; all threads finish once the probe is released (no deadlock).

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_circuit_breaker.py tests/test_db_resilience_breaker.py tests/test_db_resilience_retry.py -q
# then the Task 8 list, one pytest process at a time
```

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| The breaker leaks state between tests and opens on an unrelated test | Autouse `_fresh_storage_breaker` for every test, with a direct-assignment restore (D-7) |
| Deadlock between the breaker lock and `_client_lock` | Never held together (D-3), pinned by N6 with timeouts so a regression fails rather than hangs |
| A stalled probe (21 s connect) blocks other callers | Claim, don't hold: others get `BreakerOpen(1)` immediately (P11, N6). Stragglers already inside `_shared_client` wait on `_client_lock`, as they would behind `_proved()` today |
| Changing the propagated type breaks a consumer that compares types exactly | Grepped `app/`, `chat_ui/`, `scripts/`: no `type(exc) is StorageError` and no arm narrower than `StorageError` except `MissingRelationError` / `IntegrityError` (STATEMENT, unchanged). Message preserved (D-2) |
| PRD-022 needs a `probe=None` trial that may never report | Trial lease of `open_seconds` (D-4), pinned in P12 |
| The healthy-path overhead (PRD :486, < 0.5 ms p50) | Two uncontended lock acquisitions per operation (`before`, `record_success`), sub-microsecond. No I/O on the happy path |

## Deviations / decisions for the orchestrator

1. **A refused `NON_IDEMPOTENT` retry raises `StorageUnavailableError`** (D-1). It follows PRD 6.1 literally, and STORY-006 needs it for user story 3's 503. AC 4 names only exhaustion, so this is a superset of it.
2. **The probe is claimed under the breaker's lock but runs outside it** (D-3). The AC wording "runs the probe (under the breaker's own lock)" is read as "the lock makes the single run exclusive". Holding the lock across a network call would block every other caller and `status()` (PRD-019 `/ready`) for up to 21 s.
3. **A trial lease in `probe=None` mode** (D-4) is not in the PRD. It is needed so a silent trial cannot wedge PRD-022's breaker. Storage (probe mode) is unaffected.
4. Log `class=` values for non-failure transitions: `none`. For a failed probe: `probe`. For `force_open`: `forced`.

---

## Acceptance Criteria

(Copied from story STORY-005)

- [ ] Given `app/services/circuit_breaker.py`, when `CircuitBreaker(name, failure_threshold, open_seconds, clock=time.monotonic, probe=None)` is driven with an injected clock, then pure tests cover `closed → open` after `failure_threshold` consecutive `record_failure()` calls, `before()` raising `BreakerOpen(retry_after_seconds)` while open (≥ 1, rounded up), `open → half_open` after `open_seconds`, and closing or reopening on the probe result. `record_success()` resets the count. `force_open(seconds)` opens immediately. `status()` returns a frozen `BreakerStatus(state, since, consecutive_failures, last_failure_class, retry_after_seconds)` with no lock, client or callable in it. **(P1-P10)**
- [ ] Given `probe` set, when half-open, then exactly one caller runs the probe (under the breaker's own lock) while every other caller gets `BreakerOpen`. Given `probe=None`, when half-open, then exactly one live caller is admitted as the probe and the others get `BreakerOpen` until it records success or failure. A threaded test pins each mode. **(P11, P12)**
- [ ] Given `database.py`, when it imports, then it holds exactly one `_storage_breaker = CircuitBreaker("storage", _BREAKER_FAILURE_THRESHOLD=5, _BREAKER_OPEN_SECONDS=10.0, probe=_probe_fresh_client)`. `_unit_of_work` calls `before()` first (open → `StorageUnavailableError(retry_after_seconds=...)` with **no** call to `_shared_client()`), `record_success()` on success, and `record_failure(cls)` once per **operation** that exhausted its retries on an infrastructure class. A `STATEMENT` failure leaves the count unchanged. A `NON_IDEMPOTENT` op refused a retry on `OUTCOME_UNKNOWN` counts exactly **once**. **(N1, N2, N4, N5, B1, B3, B4)**
- [ ] Given `app/db/errors.py`, when imported, then `StorageUnavailableError(StorageError)` carries `retry_after_seconds: int`, and exhausting the retry budget on an infrastructure class raises it with `retry_after_seconds=1` while the breaker is closed. With the breaker open, `check_duplicate` raises `DuplicateCheckError`, `usage_limits.admit` raises its fail-closed error, and `find_user_by_token_hash`'s `MissingRelationError` arm does not catch it, all with no code change in those modules. **(Task 1, N3, N4)**
- [ ] Given the half-open probe, when it runs, then it issues one `SELECT 1` on a brand-new client under `_client_lock`, never through `get_connection()`. On success the new client replaces the cached one. `init_db()` and `check_database_reachable()` bypass retry and breaker (D17). Every breaker transition writes exactly one structured log line (`breaker name=storage from=<s> to=<s> class=<c>`). **(N6, N7, B2, B5, B6, P9)**
- [ ] All tasks completed
- [ ] `from app.main import app` succeeds
- [ ] Targeted tests (Task 8) green; full suite on GitHub CI
- [ ] Follows existing patterns (constants not settings, frozen dataclass, docstrings citing PRD-018 decisions, `_translated()` untouched)
