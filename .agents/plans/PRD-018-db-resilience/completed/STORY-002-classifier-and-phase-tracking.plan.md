---
story: STORY-002
prd: PRD-018
slug: classifier-and-phase-tracking
title: _classify(exc, phase), FailureClass and per-call phase tracking in _Connection
type: ENHANCEMENT
complexity: LOW
epic_branch: epic/PRD-018-db-resilience        # all stories commit here, no per-story branch
created: 2026-11-17
---

# Plan: Failure classifier and phase tracking (PRD-018 F2, first half)

## Summary

Add the failure taxonomy of PRD Section 6.2 (D2) to `app/db/database.py`, beside `_translated()`. The new pieces are a closed `FailureClass` enum (`not_sent`, `dead_stream`, `outcome_unknown`, `statement`), a closed phase vocabulary, a pure `_classify(exc, phase)`, and a thin phase recorder in `_Connection`, `_Cursor` and `get_connection()`. **The phase travels on the driver's own exception object**, as an attribute set just before a bare `raise`. `_translated()` builds `StorageError(message) from exc`, so the phase is reachable from the raised `StorageError` through `__cause__`, via a small `_phase_of(exc)` reader. `_translated()`, `_is_dead_stream()`, `app/db/errors.py`, every exception type and every message stay byte-identical. Nothing outside tests calls `_classify` yet: STORY-003 wires it into `_unit_of_work`. Tests go in a new non-`db` module, `tests/test_db_resilience_classify.py`. It holds the STORY-001 fixture table (V1 applied), the strings quoted in `database.py`'s comments and `tests/`, and wrapper tests that use fake clients under the real `_Connection` / `_Cursor` / `_translated()`.

## User Story

As a platform operator
I want every storage failure sorted into "never sent", "dead stream", "outcome unknown" or "statement refused", from both the message text and the driver call that raised it
So that the retry loop (STORY-003) can tell a safe replay from a dangerous one

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-002-classifier-and-phase-tracking.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md`, Sections 6.2 (with the 2026-11-17 amendment, lines 168-170), 6.10, 7 (F2), 11 (Functional), 15 (D1, D2)
- Spike: `.agents/spikes/PRD-018-driver-failure-surface.md`: Captures (:110-134), "Fixture table for STORY-002" (:197-265), Verdicts (:267-279), Recommendation (:281-294)

## Metadata

| Field | Value |
|-------|-------|
| Type | ENHANCEMENT (story `type: technical`) |
| Complexity | LOW (about 80 lines of app code; the care is in the rule order and in leaving `_translated()` untouched) |
| Systems Affected | `app/db/database.py` only; one new test module |
| Story | STORY-002 |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics, read 2026-11-17). Not relevant to a storage classifier. Story `skills: []` | — |

---

## Pre-flight findings (verified by the planner on 2026-11-17)

| Fact | Evidence | Consequence |
|---|---|---|
| **The real driver exception accepts an attribute.** `libsql 0.1.11` raises a plain `builtins.ValueError` (pyo3), and `exc._db_phase = "execute"` works on it | `.venv/Scripts/python -c "import libsql; c=libsql.connect('http://127.0.0.1:1'); ..."` printed `<class 'ValueError'> execute Hrana: `http error: `error trying to connect: tcp connect er...` | The attribute design works on the production object. No guard against `AttributeError` is needed: every `BaseException` instance has a `__dict__`, subclasses with `__slots__` included |
| `_translated()` builds every arm with `from exc` | `app/db/database.py:620-628` (`raise IntegrityError(...) from exc`, `raise MissingRelationError(...) from exc`, `raise StorageError(message) from exc`) | `StorageError.__cause__ is` the driver `ValueError`, so a phase attribute on it is readable from the `StorageError` without touching `_translated()` |
| `_Connection.__exit__` calls the driver directly, not `self.commit()` / `self.rollback()` | `app/db/database.py:351-356` | The wrapper has to cover `__exit__` too. Route `__exit__` through `self.commit()` / `self.rollback()` so there is one recording site per call |
| `_Cursor` holds the driver cursor and forwards `execute`, `fetchone`, `fetchall`, `fetchmany`; `__iter__` goes through `fetchall` | `app/db/database.py:251-308` (`:278-293`) | Record `execute` / `fetchone` / `fetchall` / `fetchmany` in `_Cursor`. `__iter__` is covered through `fetchall` |
| `get_connection()` is where `_shared_client()` (and `_proved()` inside it) is reached, including from `_session()` inside `_translated()` | `app/db/database.py:359-366`, `:631-642`, `:83-132`, `:135-174` | Record `connect` in `get_connection()`. `_proved()` swallows every driver error itself (`:166-173`), so only `libsql.connect` (or a non-driver `ValueError`, re-raised by `_proved()` at `:169-170`) can escape |
| Tests replace `get_connection` with proxies that raise themselves, above `_Connection` | `tests/test_db.py:4582-4587` (`_install`), `:4104-4126` (`_LockedConnection`), `:4414-4447` (`_DyingStream`), `:4386-4411` (`_NoSuchTable`) | Their exceptions never pass the wrapper, so they carry no phase (`_phase_of` → `None`). Nothing in them asserts on a phase, and their behaviour is unchanged |
| Tests that stub the **driver client** under the real `_Connection` | `tests/test_db.py:4252-4276` (`_StandInClient`, set as `database._client`), `tests/test_db_isolation_harness.py:482-513` (`_FakeClient` / `_fake_connect` in a pytester child), `tests/conftest.py:375-415` (`_RecordedClient`) | Each raises a `ValueError` that now gains one attribute. Type, `str()`, `args` and identity are unchanged, so `_translated()`, `_is_dead_stream()`, `_infra_error()` and the `excinfo.value is original` assertion (`tests/test_db_isolation_harness.py:351-363`) all behave as before |
| `_Connection.__slots__ = ("_client",)` and `_Cursor.__slots__ = ("_cursor", "_name_index")` | `app/db/database.py:322`, `:259` | **Unchanged.** The phase lives on the exception, not on the connection, so no slot is added. Nothing constructs a `_Connection` in tests except through `get_connection()`. The proxies wrap one and do not subclass it, so a slot change would not have reached them anyway |
| Non-`db` tests have `database._shared_client` and `libsql.connect` replaced by `_refuse()` | `tests/conftest.py:535-556`, `:661-667` | The new module's tests must build `_Connection(fake)` directly and never call `get_connection()` unpatched. The `connect`-phase test monkeypatches `database._shared_client` itself, which layers over the guard and is restored in the right order (`tests/conftest.py:643-645`). A non-`db` test that reaches real storage fails loudly, which also shows that `_classify` does no I/O |
| `_translated()` calls `_invalidate_client()` on a dead stream, which writes `database._client` / `_client_key` | `app/db/database.py:626-627`, `:177-199` | Wrapper tests that drive `_translated()` must `monkeypatch.setattr(database, "_client", sentinel)` and `"_client_key"` so a client cached by an earlier `db` test is restored afterwards. Asserting `database._client is None` (dead stream) or `is sentinel` (constraint) also re-checks STORY-024 AC 3 / AC 6 at this layer |
| `str(IntegrityError(c, m))`, `str(MissingRelationError(r, m))` and `str(StorageError(m))` all equal `m` | `app/db/errors.py` (`super().__init__(message)`) | `_classify` can read `str(exc)` whether it gets the driver `ValueError` or the translated `StorageError` |
| No `Enum` exists in `app/` yet. Closed vocabularies are `Literal` aliases (`app/models/messages.py:18`, `app/models/v1_schemas.py:89`) | grep | `FailureClass` is a `(str, Enum)`: the story asks for lower-case string values for logs and `storage_status()`, and STORY-003 needs identity comparison. The phase vocabulary is a `Literal` alias (`Phase`) plus a tuple `_PHASES`, which follows the existing style |

---

## Design decision: how the phase reaches `_classify`

**Chosen: an attribute on the driver's exception object, set just before a bare `raise`, and read from `StorageError.__cause__` by `_phase_of()`.**

Against the orchestrator's criteria:

1. **`_translated()`'s contract and docstring are unchanged, and so is its code.** Not one line of `:592-628` changes. The alternative named in the story, "an attribute on the raised `StorageError`, set where it is built", would need an edit inside all three arms of `_translated()` (and a choice about `IntegrityError` / `MissingRelationError`). The brief holds that function fixed (D1).
2. **Exception types and messages that tests assert are unchanged.** The object raised is the driver's own (`raise`, not `raise X from`), so `excinfo.value is original` still holds, and `str()` / `args` / `type()` do not change. The new attribute is private (`_db_phase`) and is not part of `str()`.
3. **The `_RecordedClient` rule (`tests/conftest.py:378-380`) is kept:** same object, same message. One attribute is added, nothing is wrapped or replaced.
4. **Correct under concurrency and nesting, at no cost on the happy path.** The phase is bound to the exception that carries it. A thread-local was rejected for three reasons:
   - It goes stale. A healthy call would have to clear or overwrite it on every driver call, which puts a write on the happy path (PRD 11 Quality: under 0.5 ms).
   - It can disagree with the exception being classified. `find_user_by_token_hash` nests `_translated()` inside `_session()` (`:1576-1584`). `_shared_client()` / `_proved()` run inside `_session()`'s `_translated()`. `chat_ui`'s `asyncio.to_thread` workers share the client. A read on the same thread after a later call could see the wrong phase.
   - STORY-003 would need a protocol for when to read it.

   With the attribute, `try/except` costs nothing when no exception is raised (CPython 3.11+, both the 3.11 image and the 3.12 host).
5. **First mark wins.** `_mark_phase` sets the attribute only if it is not set yet, so the innermost (true) call is kept if the same object ever crosses two recording sites. Today none do: `__iter__` → `fetchall` and `__exit__` → `commit` / `rollback` each record once.

**Why only `ValueError` is caught.** The driver raises nothing else for a failure (`database.py:388-393`). Two other things can pass through: `pytest.fail` from the non-`db` guard, and the driver's `PanicException` after `close()`, which are `BaseException`s, and the test proxies' own exceptions. None of them is classified, so they pass untouched.

**What `_phase_of` returns.** `exc`'s own attribute if set, else `exc.__cause__`'s, else `None`. `None` means "not raised through the wrapper" (a test proxy, or code that calls the raw client). `_classify` treats `None` like a non-`commit` phase. That is safe because the only rule that reads the phase is "dead-stream marker on `commit` → `NOT_SENT`". Every other phase gives `DEAD_STREAM`, which STORY-003 replays for `NON_IDEMPOTENT` only at `execute` (PRD 6.3).

**Rejected: "phase `connect` → `NOT_SENT` whatever the text".** It is tempting, because nothing in the unit ran before `get_connection()` returned. But it breaks the PRD 6.2 rule that unrecognised text is never `NOT_SENT`. It would also be wrong for a nested `get_connection()` inside a session body. `connect` is recorded and the text decides. Today's connect failures carry `tcp connect error` anyway.

## Classification rules (order is load-bearing, mirroring `_translated()`'s)

1. `isinstance(exc, (IntegrityError, MissingRelationError))` → `STATEMENT`.
2. Message matches `_CONSTRAINT`, `_MISSING_RELATION` or `_DUPLICATE_COLUMN` (`:384-386`) → `STATEMENT`. This covers the raw `ValueError`, and the plain `StorageError` that `_translated()` raises for a duplicate column.
3. Message contains `tcp connect error` or `client error (connect)` (case-insensitive) → `NOT_SENT`, **at any phase** (story Technical Notes; spike Recommendation 1). The client is lazy, so these surface on `execute`.
4. `_is_dead_stream(message)` → `NOT_SENT` if `phase == "commit"` (**orchestrator decision, PRD 6.2 amended 2026-11-17, spike Verdict V1**), else `DEAD_STREAM` (this covers `execute`, `fetch*`, `rollback` (spike row 9, flagged), `connect` and `None`).
5. Anything else → `OUTCOME_UNKNOWN`. This covers the 503 / 404 namespace texts, `SQLITE_BUSY` `database is locked`, unrecognised `Hrana:` text, and a non-`Hrana:` message.

**Deviation to flag: `error sending request` alone is NOT a `NOT_SENT` marker.** The story names the older spelling as "`error sending request` / `client error (Connect)`". The older captured text (`tests/test_db.py:4959-4963`, `tests/test_db_isolation_harness.py:474-478`) contains both, plus `tcp connect error`, so it is `NOT_SENT` through rule 3. But `error sending request for url (...)` is reqwest's generic prefix for any request-level failure, and that includes a connection reset or "connection closed before message completed" after the request was written. Treating it as `NOT_SENT` would allow a non-idempotent replay. That is exactly the miss 6.2's first rule forbids. So the marker is the `(Connect)` part. The abbreviated quote in the `database.py:514-515` comment (``error sending request for url (http://127.0.0.1:1/v2/pipeline): ... Connection refused``, with `...` for the elided part) carries neither marker. It is pinned as `OUTCOME_UNKNOWN`, and the test comment says why. If the orchestrator wants the literal reading instead, the change is one tuple entry plus one fixture row.

**Not `STATEMENT`: generic `SQLite error:` text** (syntax errors, `database is locked`). PRD 6.2 lists "SQL error" loosely, but `SQLITE_BUSY` is transient and must not be "never retried". No syntax-error text has been captured either. Such text stays `OUTCOME_UNKNOWN`. The cost is that a buggy statement is retried as a `READ` and counts toward the breaker. That is an open question for STORY-003/005, not something to invent here.

---

## Patterns to Follow

### Naming and the "why" comment above a marker tuple
```python
# SOURCE: app/db/database.py:413-418
# Pinned as literals for the same reason `_MISSING_RELATION` and `_CONSTRAINT`
# are: libSQL raises a bare `ValueError` and there is no type and no code to
# branch on (STORY-001 §3.5). ...
_DEAD_STREAM = ("stream has expired", "stream_expired", "invalid baton")
```

### Error handling: classify by text, re-raise the same object
```python
# SOURCE: app/db/database.py:614-628
    try:
        yield
    except ValueError as exc:
        message = str(exc)
        if _DRIVER_ERROR not in message:
            raise
        constraint = _constraint_of(exc)
        if constraint is not None:
            raise IntegrityError(constraint, message) from exc
        ...
        raise StorageError(message) from exc
```

### Same-object re-raise in a forwarding wrapper
```python
# SOURCE: tests/conftest.py:404-410 (_RecordedClient.timed)
            try:
                return attr(*args, **kwargs)
            except Exception as exc:
                error = _infra_error(str(exc))
                raise
```

### Narrow predicate with a docstring that names the story and the consequence
```python
# SOURCE: app/db/database.py:421-433
def _is_dead_stream(message: str) -> bool:
    """True when the driver is reporting that the server no longer has the stream.

    Deliberately **narrow**, ...
    """
    haystack = message.lower()
    return any(marker in haystack for marker in _DEAD_STREAM)
```

### Tests: same-object assertion and a fake driver client
```python
# SOURCE: tests/test_db_isolation_harness.py:351-363
def test_the_proxy_reraises_the_drivers_own_exception_and_records_it(monkeypatch):
    """`_translated()` and `_is_dead_stream()` read the message of the very object raised."""
    ...
    original = ValueError(_STREAM_EXPIRED)
    client = _RecordedClient(_FakeReal(raises=original))
    with pytest.raises(ValueError) as excinfo:
        client.execute("SELECT 1")
    assert excinfo.value is original
```
```python
# SOURCE: tests/test_db_isolation_harness.py:482-506 (_FakeCursor / _FakeClient)
class _FakeClient:
    def execute(self, sql, *parameters):
        if _FAIL["text"] is not None:
            raise ValueError(_FAIL["text"])
        return _FakeCursor()
    def commit(self): pass
    def rollback(self): pass
```

### Test module header (non-`db`)
```python
# SOURCE: tests/test_identity.py:1-4
import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")
```

### Verbatim fixtures as named module constants with provenance comments
```python
# SOURCE: tests/test_db.py:4214-4233 (_STREAM_EXPIRED_TEXT / _INVALID_BATON_TEXT)
# SOURCE: .agents/spikes/PRD-018-driver-failure-surface.md:220-265 (_BATON, _EXPIRED, _FIXTURES)
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | `FailureClass`, `Phase` / `_PHASES`, `_PHASE_ATTRIBUTE`, `_mark_phase`, `_phase_of`, `_CONNECT_FAILURE`, `_classify` after `_translated()`. Phase recording in `_Cursor.execute/fetchone/fetchall/fetchmany`, `_Connection.execute/commit/rollback/__exit__`, `get_connection()`. Docstring paragraphs on `_Connection` and `get_connection()` |
| `tests/test_db_resilience_classify.py` | CREATE | Non-`db`: the classifier table test (AC 1-3), vocabulary tests, wrapper and same-object tests at every phase (AC 4), and the `_translated()` no-second-`execute` test (AC 4, PRD 11) |

No change to `app/db/errors.py`, `_translated()`, `_is_dead_stream()`, `_DEAD_STREAM`, `_shared_client()`, `_proved()`, `tests/conftest.py`, `tests/test_db.py` or `tests/test_db_isolation_harness.py`. No pre-existing test is renamed or modified, so `_DELIBERATELY_SUPERSEDED_TESTS` is untouched.

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: The vocabulary and the phase helpers

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**:
  - Imports: add `from enum import Enum` (stdlib, beside `import uuid`, `:5`) and `Literal` to the `typing` import (`:9`).
  - Insert one block **directly after `_translated()` (after `:628`, before `_session()` at `:631`)**, under a `# PRD-018 STORY-002 (D2, Section 6.2)` comment header that says why this is the one seam (PRD 6.10, PRD-007 Section 7.2):
    - `class FailureClass(str, Enum)` with `NOT_SENT = "not_sent"`, `DEAD_STREAM = "dead_stream"`, `OUTCOME_UNKNOWN = "outcome_unknown"`, `STATEMENT = "statement"`. The docstring gives the "did the statement run?" column of 6.2 for each member, in one line each. It says the values are the names logs and `storage_status()` use, and that `STATEMENT` is never retried and never counts toward the breaker (6.2 rule 2; wiring is STORY-003/005).
    - `Phase = Literal["connect", "execute", "fetchone", "fetchall", "fetchmany", "commit", "rollback"]` and `_PHASES: tuple[str, ...] = ("connect", "execute", "fetchone", "fetchall", "fetchmany", "commit", "rollback")`. Comment: `fetchmany` is added to the story's six because `_Cursor.fetchmany` (`:289-290`) is a driver call too, and an unrecorded call would classify as `None`.
    - `_PHASE_ATTRIBUTE = "_db_phase"`.
    - `def _mark_phase(exc: BaseException, phase: Phase) -> None`: `if getattr(exc, _PHASE_ATTRIBUTE, None) is None: setattr(exc, _PHASE_ATTRIBUTE, phase)`. The docstring says "first mark wins (innermost call)" and gives the same-object rule: the attribute is the **only** change. Type, message, `args` and identity stay as raised, so `_translated()` and `_is_dead_stream()` behave as before (PRD 6.2 last bullet; the PRD-014 `_RecordedClient` rule, `tests/conftest.py:378-380`).
    - `def _phase_of(exc: BaseException) -> Optional[str]`: own attribute, then `exc.__cause__`'s, else `None`. The docstring explains `__cause__`: `_translated()` raises `... from exc` in all three arms, so the phase is reachable without changing it (D1). It also explains why not a thread-local, in two sentences from the decision above.
- **Mirror**: `app/db/database.py:413-433` (constant + narrow predicate + docstring house style)
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: `_classify(exc, phase)`

- **File**: `app/db/database.py`
- **Action**: UPDATE (same block, after Task 1's helpers)
- **Implement**:
  - `_CONNECT_FAILURE = ("tcp connect error", "client error (connect)")` (lower-case, matched against `message.lower()`). The comment quotes today's text and the older one verbatim (spike Captures row F1, `tests/test_db.py:4959-4963`). It says that `os error 110` / `10060` / `10061` / `111` all share the `tcp connect error` tail, and gives the reqwest reason why `error sending request` alone is **not** a marker (see the Classification rules section above).
  - `def _classify(exc: BaseException, phase: Optional[str]) -> FailureClass`, implementing rules 1-5 above in that order. It reuses `_CONSTRAINT`, `_MISSING_RELATION`, `_DUPLICATE_COLUMN` and `_is_dead_stream()`. It does not duplicate `_DEAD_STREAM`.
  - Docstring, in house style:
    - **Pure**: a function of the exception and the phase. No I/O, no settings, no client, no logging.
    - Not wired yet: STORY-003's `_unit_of_work` is the only intended caller.
    - **Unrecognised → `OUTCOME_UNKNOWN`, never `NOT_SENT`**: a miss costs a retry that was skipped, never a replay that should not have happened.
    - **Order is load-bearing**, as in `_translated()`: statement first, so a constraint can never be read as infrastructure.
    - **Dead stream on `commit` → `NOT_SENT`**: the orchestrator decision of 2026-11-17, PRD 6.2 amended. Cite spike Verdict V1: Q1 says DML is not durable before `commit()`. Q2 says `commit()` with no open transaction is a local no-op, so a commit-phase dead stream always means an open transaction that was lost. 9/9 dead-stream commits left nothing landed. State that a reset, a timeout or unrecognised text on `commit` stays `OUTCOME_UNKNOWN`.
    - **Dead stream on `rollback` → `DEAD_STREAM`**: spike row 9, flagged. Nothing to replay.
    - The two restart-window texts stay `OUTCOME_UNKNOWN` (spike Recommendation 3).
    - `phase=None` is safe: only the `commit` rule reads the phase.
  - Do **not** add a `Hrana:` gate. `_classify` is reached only with a `StorageError`, which `_translated()` already gated. Text-only rules also keep `DatabaseUnreachableError`'s embedded `Driver said: ... tcp connect error` meaningful.
- **Mirror**: `app/db/database.py:592-628` (branch order and comment style), `:537-564` (`_classify_startup_failure`: a fail-safe default with the asymmetry spelled out)
- **Validate**: `.venv/Scripts/python -c "from app.db.database import _classify, FailureClass; print(_classify(ValueError('Hrana: x'), 'execute'))"` → `FailureClass.OUTCOME_UNKNOWN`

### Task 3: Phase recording in `_Cursor`, `_Connection` and `get_connection()`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: at each site, wrap **only the driver call** in `try: ... except ValueError as exc: _mark_phase(exc, "<phase>"); raise`. Use a bare `raise`, never `raise exc` and never `from`, so the traceback stays as it was too.
  - `_Cursor.execute` (`:278-281`) → `"execute"`. `_Cursor.fetchone` (`:283-284`) → `"fetchone"`. `_Cursor.fetchall` (`:286-287`) → `"fetchall"`. `_Cursor.fetchmany` (`:289-290`) → `"fetchmany"`. Bind the driver result to a local inside the `try`, then `_wrap` it outside, so a `_Row` bug is never labelled a driver phase.
  - `_Connection.execute` (`:327-328`) → `"execute"`. `_Connection.commit` (`:333-334`) → `"commit"`. `_Connection.rollback` (`:336-337`) → `"rollback"`.
  - `_Connection.__exit__` (`:351-356`): call `self.commit()` / `self.rollback()` instead of `self._client.commit()` / `self._client.rollback()`. Same calls, same order, same `return False`; one recording site per call. A rollback failure during an exception exit propagates as today, with the body's exception as `__context__`. Note this in the docstring: it is STORY-003's concern, see Risks.
  - `_Connection.cursor()` (`:330-331`) and `close()` stay unrecorded: `client.cursor()` is local, and `close()` is a no-op.
  - `get_connection()` (`:359-366`) → `"connect"` around `_shared_client()`. Add one docstring sentence: this covers `libsql.connect` and anything `_proved()` re-raises.
  - `_Connection` docstring (`:312-320`): add one paragraph, "PRD-018 STORY-002 (D2): each driver call labels a `ValueError` it raises with the call's name (`_mark_phase`) and re-raises the same object ...". It points at `_classify` / `_phase_of`, and says `__slots__` is unchanged because the phase rides on the exception. Same for one sentence in `_Cursor`'s docstring.
- **Mirror**: `tests/conftest.py:404-410` (forward, catch, record, bare `raise`)
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`, then `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_isolation_harness.py -q` (the `_RecordedClient` same-object test, the pytester `_FakeClient` children with `CONNECT_TIMEOUT`, and the guard)

### Task 4: `tests/test_db_resilience_classify.py` (new, non-`db`)

- **File**: `tests/test_db_resilience_classify.py`
- **Action**: CREATE
- **Implement**: a module docstring that cites PRD-018 STORY-002, D2, Section 6.2 (amended), and the spike path. It says every test here is non-`db` and that fake driver clients stand under the real `_Connection` / `_Cursor` / `_translated()`. Use the `os.environ.setdefault` header (`tests/test_identity.py:1-4`). Use **no storage fixture**: requesting one would make the test `db` (`tests/conftest.py:100-101, 192-195`).
  1. **Constants**: `_BATON` and `_EXPIRED` copied verbatim from the spike block (`:222-226`), the connect texts, the namespace texts, and `_LOCKED` = the `SQLITE_BUSY` text from `tests/test_db.py:4119-4122`. Each gets a provenance comment (spike rid / `file:line`).
  2. **`_FIXTURES` table test (AC 1)**: `@pytest.mark.parametrize("message, phase, expected", _FIXTURES)` over the spike's 16 rows, with **V1 applied**: rows 6 and 8 (`_EXPIRED`/`_BATON` @ `commit`) become `NOT_SENT`, with a comment `# PRD-018 6.2 amended 2026-11-17 (orchestrator, spike V1)`. Add these rows:
     - spike row 4: the `tcp connect error` text at `commit` and at `rollback` → `NOT_SENT`.
     - `_EXPIRED` / `_BATON` at `fetchone`, `fetchall`, `fetchmany`, `connect` and `None` → `DEAD_STREAM`. `_EXPIRED` at `rollback` → `DEAD_STREAM`.
     - `database.py` comment strings:
       - the STREAM_EXPIRED and baton texts at `:406-411`, which are the same as `_EXPIRED` / `_BATON`;
       - the three `stream error` texts at `:372-379` → `STATEMENT`;
       - the abbreviated unreachable quote at `:514-515` → `OUTCOME_UNKNOWN`, with the comment explaining the reqwest reason.
     - test-quoted strings: `tests/test_db.py:4959-4963` → `NOT_SENT`; `tests/test_db_isolation_harness.py:474-478` (`os error 10060`, old spelling) → `NOT_SENT`; `_LOCKED` → `OUTCOME_UNKNOWN`; the bare `"Received an invalid baton"` (`tests/test_db.py:4351`) at `execute` → `DEAD_STREAM`.
     - `"Hrana: \`api error\`: boom"` (`tests/test_db.py:2602`) → `OUTCOME_UNKNOWN`.

     Expected values are written as `FailureClass` members, not strings. Each row runs twice, as the raw `ValueError(message)` and as `StorageError(message)`, so `_classify` is shown to read either shape.
  3. **AC 2**: an unrecognised `Hrana:` text at **every** phase in `_PHASES` plus `None` → `OUTCOME_UNKNOWN`, and never `NOT_SENT`, as an explicit `!=` assertion. The 503 and 404 texts at `commit` → `OUTCOME_UNKNOWN`. A dead stream at `commit` → `NOT_SENT`, with a docstring that cites the PRD 6.2 amendment and spike V1. A parametrize over `_PHASES` asserts that only `commit` yields `NOT_SENT` for `_EXPIRED` and `_BATON`.
  4. **AC 3**: `IntegrityError("users.token_hash", <constraint text>)`, `MissingRelationError("users", <no such table text>)` and the duplicate-column `StorageError` → `STATEMENT` at every phase, `commit` included. Also `IntegrityError(None, "Hrana: \`x\`")`: the type wins even when the text does not parse.
  5. **Vocabulary**: `{c.value for c in FailureClass} == {"not_sent", "dead_stream", "outcome_unknown", "statement"}`, `FailureClass.NOT_SENT == "not_sent"` (the str mixin), and `set(_PHASES) == set(typing.get_args(Phase))`, with the seven names.
  6. **Wrapper, same object, every phase (AC 4)**: local `_FakeCursor` / `_FakeClient` classes whose methods raise a **pre-built** `original = ValueError(_EXPIRED)` on demand (mirror `tests/test_db_isolation_harness.py:482-506`). For each of these, assert `excinfo.value is original`, `_phase_of(original) == <phase>`, `str(original) == _EXPIRED`, `original.args == (_EXPIRED,)`:
     - `_Connection(fake).execute(...)` → `"execute"`;
     - `_Connection(fake).cursor().execute(...)` → `"execute"`;
     - `.fetchone()` / `.fetchall()` / `.fetchmany(2)` / `list(cursor)` on a returned cursor → the fetch phase (`"fetchall"` for iteration);
     - `with _Connection(fake): pass` where `commit` raises → `"commit"`;
     - `with _Connection(fake): raise KeyError` where `rollback` raises → `"rollback"`, with `isinstance(excinfo.value.__context__, KeyError)`;
     - `get_connection()` with `monkeypatch.setattr(database, "_shared_client", raiser)` → `"connect"`.

     Also check that a non-`ValueError` raised by the fake (e.g. `RuntimeError`) passes through without the attribute. A healthy fake returns rows through `_Row` unchanged, with `fetchone()` giving `(1,)`, which shows the happy path is untouched.
  7. **`_translated()` contract (AC 4, PRD 11 "re-raises without a second `execute`")**. `monkeypatch.setattr(database, "_client", sentinel)` and `"_client_key"`. Then `with pytest.raises(StorageError) as excinfo: with database._translated(): with _Connection(fake) as conn: conn.execute("SELECT 1")`, where the fake records each `execute` and raises `original` (`_EXPIRED`). Assert:
     - `fake.executes == ["SELECT 1"]` (exactly one);
     - `type(excinfo.value) is StorageError`, `str(excinfo.value) == _EXPIRED` and `excinfo.value.__cause__ is original`;
     - `database._client is None` (invalidated, as STORY-024 AC 6);
     - `_classify(excinfo.value, _phase_of(excinfo.value)) is FailureClass.DEAD_STREAM`.

     Companion cases:
     - the constraint text gives `IntegrityError`, `database._client is sentinel` (STORY-024 AC 3 at this layer), and `STATEMENT`;
     - a non-`Hrana:` `ValueError("decode exploded")` passes out of `_translated()` as the very object (`is`). That is PRD 11 "A non-`Hrana:` `ValueError` propagates untouched";
     - a commit-phase baton gives `StorageError` and `_classify(...)` is `NOT_SENT`.
  8. **`_phase_of`**: `None` for a fresh `ValueError` and for a `StorageError` with no cause. It reads through `__cause__`. First mark wins: calling `_mark_phase(exc, "commit")` after `"execute"` leaves `"execute"`.
  9. **Purity**: a test that calls `_classify` over all fixtures with `monkeypatch.setattr(database, "settings", None)`. Any settings read would raise. The conftest guard already refuses a client in this non-`db` module.

  Every test docstring names the AC it covers, house style (`tests/test_db.py:4296-4306`). No pre-existing assertion is modified.
- **Mirror**: `tests/test_db_isolation_harness.py:351-363, 482-506`; `tests/test_db.py:4214-4233, 4345-4370, 4414-4447`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_classify.py -q -p no:cacheprovider` (all pass, 0 skipped; it runs with Docker stopped because no test is `db`)

### Task 5: Regression run (one pytest process, never two at once)

- **Action**: run in **one** call (needs `harness-libsql-dev` on :8080; `docker restart harness-libsql-dev` if many `db` tests error at setup):
  ```
  PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_classify.py tests/test_db_isolation_harness.py tests/test_untouched_app.py "tests/test_query_router.py::test_duplicate_check_storage_failure_returns_500" tests/test_db.py -k "test_db_resilience_classify or test_db_isolation_harness or test_untouched_app or duplicate_check_storage_failure or dead_stream or stream_messages or constraint_violation or missing_table or second_connection_failure or many_threads or busy_client or unreachable or guard or not_a_missing_table or mark_audit_log_failed or duplicate_column or bootstrap or safe_endpoint" -q
  ```
  (`-k` matches module names, so the first three files run in full. In `tests/test_db.py` it selects the `_translated` / STORY-024 / boot-guard / duplicate-column subset.) Record the exact pass/fail/skip counts. If the `-k` expression turns out awkward, run instead `tests/test_db.py -k "<subset>"` together with the other files given by node id, still in one process.
- **Validate**: 0 failed. "Full suite: GitHub CI on push (user decision)".

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"` prints `OK`
- [ ] `tests/test_db_resilience_classify.py` passes with Docker **stopped or running** (non-`db` only)
- [ ] `tests/test_db_isolation_harness.py` passes unchanged (same-object proxy test, the pytester `_FakeClient` children, the guard)
- [ ] The STORY-024 subset of `tests/test_db.py` passes unchanged: `test_a_dead_stream_is_discarded_and_the_call_is_served`, `test_a_second_connection_failure_surfaces_rather_than_looping`, `test_the_captured_dead_stream_messages_are_told_from_statement_failures`, `test_a_constraint_violation_does_not_discard_the_client` (AC 3), `test_a_missing_table_does_not_discard_the_client`, `test_a_dead_stream_mid_statement_invalidates_without_retrying`, `test_many_threads_finding_the_stream_dead_together_build_one_client`, `test_a_busy_client_is_not_probed`
- [ ] `test_init_db_fails_fast_against_an_unreachable_endpoint` and `test_duplicate_check_storage_failure_returns_500` pass unchanged (PRD 11)
- [ ] `git diff --stat` shows only `app/db/database.py`, the new test file, and the plan/report/story/index files. `git diff app/db/database.py` shows **no** hunk inside `_translated()` (`:592-628`), `_is_dead_stream()` or `_DEAD_STREAM`
- [ ] `grep -rn "_classify(" app/ chat_ui/ scripts/` finds only the definition (not wired: STORY-003)

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_classify.py -q
# then the single combined run of Task 5
git diff -U0 app/db/database.py | grep -n "^@@"   # no hunk in the _translated() range
```

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| A rollback failure during an exception exit replaces the body's exception (Python `with` semantics, unchanged today). A body `OUTCOME_UNKNOWN` followed by a baton on `rollback` would surface as `DEAD_STREAM`@`rollback` | Not this story's decision. `DEAD_STREAM`@`rollback` is not replayable for `NON_IDEMPOTENT` (6.3 says "on `execute` only"), so it cannot cause a double effect. **STORY-003 should classify `exc.__context__` too when the phase is `rollback`** and take the more pessimistic class. A wrapper test pins the `__context__` here so STORY-003 can rely on it |
| `error sending request` interpreted narrowly (deviation) | Documented in code and plan. The captured older text still classifies `NOT_SENT` through its `client error (Connect)` / `tcp connect error` parts. The orchestrator can widen it with one tuple entry |
| Generic `SQLite error:` (syntax, `SQLITE_BUSY`) is `OUTCOME_UNKNOWN`, not `STATEMENT` | Conservative toward replay safety. STORY-003/005 decide whether a syntax error should count toward the breaker. No capture exists to justify a rule today |
| Exceptions raised by test proxies above `_Connection` carry no phase | `_phase_of` → `None` → classified as non-`commit`. Only the dead-stream-on-`commit` rule reads the phase, so the worst case is `DEAD_STREAM` where `NOT_SENT` was right. Both mean "did not run" |
| Healthy-path overhead | One `try` per driver call: zero-cost when nothing is raised (CPython 3.11+). No allocation, no lock, no global write. `__exit__` gains one method call, which is negligible against a network round trip |
| Someone later "simplifies" the wrapper into `raise StorageError(...) from exc` | `_Connection` docstring and the `is original` assertions at every phase in the new test module |

## Open questions for the orchestrator

1. Accept the narrow reading of the older connect spelling (`client error (Connect)` yes, `error sending request` alone no)?
2. Adding `fetchmany` as a seventh phase name (`_Cursor.fetchmany` exists at `database.py:289-290`; nothing calls it today)?

---

## Acceptance Criteria

(Copied from story `STORY-002`, with the Technical Notes' orchestrator decisions applied)

- [ ] Given every verbatim string in the STORY-001 report and in `database.py`'s comments, when `_classify(exc, phase)` runs, then a table test asserts the expected `FailureClass` (`NOT_SENT`, `DEAD_STREAM`, `OUTCOME_UNKNOWN`, `STATEMENT`) for each `(message, phase)` pair. → Task 4 item 2
- [ ] Given an unrecognised `Hrana:` message, when classified, then the result is `OUTCOME_UNKNOWN`, never `NOT_SENT`. Given a dead-stream marker on `commit`, the result is **`NOT_SENT`** (orchestrator decision, PRD 6.2 amended 2026-11-17, spike V1, which supersedes AC 2's hedge), and every other `commit` failure stays `OUTCOME_UNKNOWN`. → Task 4 item 3
- [ ] Given `IntegrityError` or `MissingRelationError` (or a duplicate-column failure), when classified, then the result is `STATEMENT`. → Task 4 item 4
- [ ] Given a statement on the shared client, when the driver raises, then `_Connection` (and `_Cursor` for `fetch*`) records the failing call as the phase and re-raises the same exception object, so `_translated()` and `_is_dead_stream()` behave exactly as now. A test asserts `_translated()` still re-raises with no second `execute` (PRD Section 11). → Task 3; Task 4 items 6-7
- [ ] Given the healthy path, when the existing storage tests run (the `tests/test_db.py` subset that covers `_translated`, the idle probe and STORY-024's AC 3), then they pass unchanged. → Task 5
- [ ] All tasks completed
- [ ] Backend imports without error (`from app.main import app`)
- [ ] Follows existing patterns (no change to `_translated()`, `_is_dead_stream()`, `app/db/errors.py`; docstrings cite PRD-018 D2 / STORY-002)
