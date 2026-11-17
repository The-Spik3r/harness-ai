---
story: STORY-009
prd: PRD-018
slug: journal-drainer
title: Journal drainer thread and lifespan wiring (FastAPI and Reflex)
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-018-db-resilience        # all stories commit here, no per-story branch
created: 2026-11-17
---

# Plan: Drain the journal exactly once (PRD-018 F6 drain half, D11, D17, Risk 7)

## Summary

Add one keyed transaction to `app/db/database.py`, `drain_journal_entry(audit, decisions, *, audit_id=None) -> int`. It runs through `_unit_of_work("drain_journal_entry", StatementKind.IDEMPOTENT, _op)`. `_op` inserts the audit row with the existing `_insert_audit_row` (`ON CONFLICT(write_id) DO NOTHING RETURNING id`, then `SELECT id` on conflict), rebuilds every decision with `dataclasses.replace(d, audit_id=<that id>)`, and inserts them with `_insert_action_decision_rows`. A decisions-only entry uses `entry.audit_id`. Add a new module, `app/db/journal_drainer.py`. It holds `drain_once(journal)`, a pure step with a closed outcome vocabulary and no sleeping; `_run(journal, stop)`, the loop, which takes an injectable stop/wait object; and a reference-counted `start(directory, max_bytes, pipeline_max_workers)` / `stop()` pair. Together they guarantee one journal and one daemon thread per process, even when both lifespans run. `start` opens the journal (an unwritable directory raises `AuditUnavailableError` naming `AUDIT_BUFFER_DIR`), runs `adopt()`, then starts the thread. `app/main.py`'s lifespan calls `start` after `init_db()` and the fail-fast config checks, and on shutdown calls `pipeline_executor.shutdown()` and then `stop()`. `chat_ui/chat_ui/chat_ui.py` registers an `@asynccontextmanager` lifespan task that does the same. It is registered after `authz.check_bootstrap` and before `_pipeline_executor_lifespan`, so Reflex's `AsyncExitStack` tears the pipeline down first. `tests/conftest.py` points `AUDIT_BUFFER_DIR` at a per-test tmp path that is never created unless something opens it, and fails any test that leaks a journal or leaves a drainer thread behind. It also fails any non-`db` test that meets the thread. New tests go in `tests/test_db_resilience_drain.py`, plus the kind-table entry in `tests/test_db_resilience_retry.py` and a probe extension in `tests/test_chat_ui_startup_guard.py`.

## User Story

As a compliance admin
I want journaled rows drained into the database once it answers again, in order and exactly once
So that the audit trail has no hole and no duplicate after an outage

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-009-journal-drainer.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md`, Sections 6.1 (drainer box, :147-150), 6.5 (breaker, :220-259), 6.8 Drain (:305), 14 Risk 7 (:541), 15 D11, D17 (:559, :565)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY (story `type: technical`, `complexity: medium`) |
| Complexity | MEDIUM: about 60 lines in `database.py`, about 200 lines for the new drainer module, about 25 lines of lifespan wiring, about 50 lines in conftest, about 450 lines of tests |
| Systems Affected | `app/db/database.py`, `app/db/journal_drainer.py` (new), `app/main.py`, `chat_ui/chat_ui/chat_ui.py`, `tests/conftest.py`, `tests/test_db_resilience_drain.py` (new), `tests/test_db_resilience_retry.py`, `tests/test_chat_ui_startup_guard.py` |
| Story | STORY-009 |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| (none) | `.agents/skills/` holds only `frontend-design` (UI aesthetics). The story has `skills: []`, and its only `chat_ui` change is a lifespan registration with no UI | — |

---

## Pre-flight findings (verified by the planner on 2026-11-17)

| Fact | Evidence | Consequence |
|---|---|---|
| `CircuitBreaker.status()` never transitions. Only `before()` moves `open` to `half_open` and runs the storage probe | `app/services/circuit_breaker.py:170-202` (transition inside `before`), `:281-298` (`status` only reads) | **Read only `status().state == "closed"` and an idle instance never drains after an outage.** The window elapses, but nothing calls `before()` until a request arrives. See Design decision D-2 |
| `_retry_after()` is `max(1, ceil(open_until - now))` | `circuit_breaker.py:142-143` | `retry_after_seconds` cannot tell "window elapsed" from "1 s left". The drainer cannot pre-check this and must call `before()` |
| `_unit_of_work` turns every infrastructure failure into `StorageUnavailableError` and records exactly one breaker failure. STATEMENT failures (`IntegrityError`, `MissingRelationError`, driver `StorageError`) and non-driver errors are re-raised and are not counted | `app/db/database.py:1145-1193` | The drainer separates "storage unavailable" (stop the pass, entry stays first) from "this entry is refused" (hold it back). It needs no classification of its own (driver strings stay in `database.py`) |
| `_insert_audit_row` / `_insert_action_decision_rows` are reusable on a `conn` inside a unit and key by `write_id` | `database.py:1428-1478`, `:3023-3075`, `_keyed_row_id` `:1403-1425` | `drain_journal_entry` is about 20 lines: no new SQL |
| The journal guarantees every journaled audit row and decision carries a `write_id` and no `id` | `app/db/audit_journal.py:348-373` (`_validate`) | The drain unit is a literal `StatementKind.IDEMPOTENT`, not `_keyed_kind(...)`. A defensive `ValueError` before the unit covers a hand-built call |
| `_decode` builds decisions with `audit_id=obj["audit_id"]`, which is `None` for an entry that also has an audit row | `audit_journal.py:173-176` | The drain must `dataclasses.replace(d, audit_id=row_id)` and never trust a cached id (story Technical Notes) |
| `mark_drained` tolerates out-of-order marks. The checkpoint advances only over a drained prefix, and compaction runs only when nothing is pending in that file | `audit_journal.py:398-417` | Holding back one entry while later ones drain is safe: the held entry and everything after the checkpoint stay on disk, and a later boot replays them. Replays of drained ones are no-ops by `write_id` |
| Adoption already logs one line per file (`journal adopted file=… entries=… discarded=…`) | `audit_journal.py:568` | AC 5's "each adoption" line exists. The drainer adds `journal drained …` per entry and one `journal drainer started …` summary |
| `open_journal` raises `RuntimeError` when the slot is taken | `audit_journal.py:641-648` | Running both lifespans in one process needs a reference count around it (D-4) |
| The two places `pipeline_executor.shutdown` is registered | `app/main.py:13-23`, `chat_ui/chat_ui/chat_ui.py:257-269`, documented at `app/services/pipeline_executor.py:13-19` | These are the two places to wire the drainer |
| Chat UI runs `init_db()` **at import** (Reflex's `api_transformer` mount bypasses `app.main`'s lifespan). Lifespan tasks run in registration order inside one `AsyncExitStack` | `chat_ui.py:44-49`. Reflex `LifespanMixin._run_lifespan_tasks` (`AsyncExitStack`, `enter_async_context` per `@asynccontextmanager` task) | D17 holds on that path: `init_db()` has already succeeded before any lifespan task. Teardown is the reverse of registration (D-5) |
| `pipeline_executor.shutdown()` waits for in-flight calls (`shutdown(wait=True)`) | `pipeline_executor.py:56-62` | Shut the executor down **before** closing the journal, so an in-flight request that journals its step 8 rows still finds it open |
| Every test that enters a lifespan is already a `db` test: `test_main.py` (`temp_db` / `_DB_NODEIDS`), `test_pattern_default_config_regression.py::booted_client` (`temp_db`), `test_measure_v1_latency.py` (`_DB_NODEIDS`). `test_chat_ui_startup_guard.py` only imports and lists tasks, in a subprocess | `tests/test_main.py:37-172`, `tests/test_pattern_default_config_regression.py:81-92`, `tests/conftest.py:123-138`, `tests/test_chat_ui_startup_guard.py:48-62` | No non-`db` test starts the thread today. A conftest guard keeps it that way (AC 4) |
| `AUDIT_BUFFER_DIR` defaults to `./var/audit-buffer` and is validated only as non-empty | `app/config.py:429`, `:590-601` | Without a conftest override, every lifespan test would write `./var` in the repo. The E2E children run uvicorn with a `tmp_path_factory` cwd (`tests/e2e/test_openai_sdk.py:86`), so their relative default lands in a tmp dir |
| The kind table is pinned at 41 entries and the AST pin requires the literal `StatementKind.X` | `tests/test_db_resilience_retry.py:629-729` | Add `"drain_journal_entry": K.IDEMPOTENT`, make the count 42, and add a PRD-018 comment |

---

## Design decisions

- **D-1. The SQL stays in `database.py`, and the drainer stays in `app/db/`.** The new module is `app/db/journal_drainer.py`. `audit_journal.py` must not call the database (its docstring and the brief's "Pure modules" rule), so the drainer cannot live there. It imports `database` and `audit_journal`, and neither imports it, so there is no import cycle. Nothing runs at import.

- **D-2. Breaker gate: "closed", or let the breaker's own probe close it.** *(Orchestrator ruling requested.)* `drain_once` first checks whether anything is pending. Only then does it call `_storage_ready()`:
  ```python
  breaker = database._storage_breaker          # read at call time: tests swap it
  if breaker.status().state == "closed":
      return True
  try:
      breaker.before()   # open + window elapsed -> storage's own SELECT 1 probe
  except BreakerOpen:
      return False
  return breaker.status().state == "closed"
  ```
  While the window is still open, `before()` raises immediately and touches no client, so the drainer "does nothing while open" (AC 3). While another caller's probe is running, it gets `BreakerOpen`. Once the window has elapsed, the drainer is just the next caller, and the probe is the breaker's own single `SELECT 1` under `_client_lock` (D6). Without this, an idle instance with a non-empty journal would sit `open` forever, because `status()` never transitions (pre-flight row 1). Because the call is gated on a non-empty journal, an idle healthy process never probes. Alternative if the orchestrator prefers: check `state == "closed"` only and document that the drain waits for the next request. This is not recommended.

- **D-3. Failure policy per entry.**
  - `StorageUnavailableError` (an infrastructure class, already recorded in the breaker by `_unit_of_work`) means **stop this pass**. The entry stays first, nothing is marked, and the outcome is `unavailable`. The loop then waits the idle interval. If the failure opened the breaker, the next tick is gated by D-2.
  - **Any other exception from the drain** means **hold back**. That covers a STATEMENT failure (`IntegrityError` on a non-`write_id` constraint, `MissingRelationError`, driver `StorageError`), the `_keyed_row_id` "no row" `StorageError`, and a `ValueError`/`TypeError` from our own code. The entry's `write_id` goes into the drainer's in-process `_held_back` set, and one `ERROR` line is logged: `journal drain held back write_id=… user_id=… error=<ExceptionClassName>`. The line carries no exception text, so neither driver text nor SQL reaches the log. The held-back counter goes up, and the pass **moves on** to the next pending entry on the next tick. The entry is **never deleted or marked drained**. It stays in the file, on disk and in the overlay index, so no row is lost and the duplicate overlay stays truthful. The checkpoint cannot pass it, so the next boot adopts and retries it, by which time `init_db()` may have created a missing table. Everything after it that drained replays as a no-op.
  - Why not "log ERROR and keep it first": one poison entry would wedge every later row forever, which is a hole in the audit trail and a journal that grows to `AUDIT_BUFFER_MAX_BYTES` and starts failing requests closed (D10).
  - Why not "skip and drop": that loses an acknowledged row (D13).
  - A STATEMENT failure never feeds the breaker (D6). `_unit_of_work` already guarantees this.

- **D-4. One journal and one thread per process: a reference-counted `start` / `stop`.** The module keeps `_lock`, `_users`, `_thread`, `_stop_event` and `_journal`.
  - `start(...)` increments `_users`. Only the first user opens the journal (`audit_journal.open_journal`), calls `adopt()` and starts `threading.Thread(target=_run, name="audit-journal-drainer", daemon=True)`. If any of that raises, the count is decremented and `close_journal()` runs before re-raising, so a failed startup leaves nothing behind.
  - `stop()` is a no-op at 0. Otherwise it decrements, and only the last user sets the event, `join`s for `_DRAIN_STOP_JOIN_SECONDS`, logs a WARNING if the thread is still alive (a stalled drain call: the driver has no read timeout), and then calls `close_journal()`.
  - A replay after a close is safe: an entry committed but not marked replays as a no-op at the next boot.
  - The FastAPI app mounted under Reflex does not run its own lifespan (`chat_ui.py:44-49`), so in production exactly one of the two ever calls `start`. The count makes "both ran" (in-process tests, a future mount change) safe instead of a `RuntimeError`.
  - `running()` returns `bool` for tests and STORY-012. `held_back()` returns the count for STORY-012, which decides whether to show it.

- **D-5. Lifespan order.**
  - `app/main.py`: `init_db()` (D17), the config loads, `authz.check_bootstrap()`, then `journal_drainer.start(settings.AUDIT_BUFFER_DIR, settings.AUDIT_BUFFER_MAX_BYTES, settings.PIPELINE_MAX_WORKERS)` **last** before `yield`. A failing fail-fast check therefore never leaks an open journal or a running thread. After `yield`: `pipeline_executor.shutdown()` (waits for in-flight pipeline calls, which may still journal), **then** `journal_drainer.stop()`.
  - `chat_ui.py`: a new `@asynccontextmanager async def _audit_journal_lifespan()` that calls `start(...)`, yields, then calls `stop()`. It is registered right after `app.register_lifespan_task(authz.check_bootstrap)` and before `_pipeline_executor_lifespan`. Startup then runs init_db (import), the loads, the bootstrap check, and then the journal. The reverse-order teardown runs `pipeline_executor.shutdown()` first and the journal stop second. A comment in the existing "Same bypass" style explains this.

- **D-6. Loop and timing, without real sleeping in tests.**
  - Module constants, not settings (O6): `_DRAIN_YIELD_SECONDS = 0.01` (between drained entries, Risk 7: one entry per transaction and the shared client is released between them), `_DRAIN_IDLE_SECONDS = 1.0` (empty, breaker not ready, unavailable, or held back), `_DRAIN_STOP_JOIN_SECONDS = 5.0`.
  - `_run(journal, stop)` is `while not stop.is_set(): outcome = _tick(journal); stop.wait(_DRAIN_YIELD_SECONDS if outcome == "drained" else _DRAIN_IDLE_SECONDS)`.
  - `_tick` wraps `drain_once` in `except Exception`, logging `journal drainer tick failed error=<ClassName>` at ERROR, so the daemon thread never dies (a probe's non-driver `ValueError` is re-raised by `_probe_fresh_client`, `database.py:290-293`).
  - Tests drive `_run` on the test thread with a fake `stop` whose `wait(timeout)` records `timeout` and returns `True` after N calls.

- **D-7. `drain_once(journal) -> DrainOutcome`.** `DrainOutcome` is a `str` Enum with the closed vocabulary `empty`, `breaker_open`, `unavailable`, `held_back`, `drained`.
  - Steps: snapshot `journal.pending()`. Take the first entry whose `write_id` is not in `_held_back`, or return `empty`. Gate with D-2 or return `breaker_open`. Call `database.drain_journal_entry(entry.audit, entry.decisions, audit_id=entry.audit_id)` and apply D-3. On success, `journal.mark_drained(entry.write_id)` (checkpoint and compaction, `audit_journal.py:398-417`), log `journal drained write_id=%s user_id=%s audit_id=%d decisions=%d`, and return `drained`.
  - `user_id` is `entry.audit.user_id`, or the first decision's, as `append` does at `audit_journal.py:311`.
  - Exactly one entry per call.

- **D-8. `drain_journal_entry(audit, decisions, *, audit_id=None) -> int`.** It takes the entry's fields, not a `JournalEntry`, so `database.py` does not import the journal. The return value is the audit row id.
  - Checks before the unit, each a `ValueError` (a programming error, which `drain_once` holds back): exactly one of `audit` / `audit_id`; every row keyed; and `audit_id is None` on a decisions-only call is refused.
  - `_op(conn)`: `row_id = _insert_audit_row(conn, audit) if audit is not None else audit_id`, then `_insert_action_decision_rows(conn, [dataclasses.replace(d, audit_id=row_id) for d in decisions])` when there are decisions, then `return row_id`.
  - The rows are rebuilt inside `_op` from the immutable inputs (the "fn must be re-runnable" rule, `database.py:1100-1104`).
  - The original `timestamp` is carried because `_insert_audit_row` writes `entry.timestamp` (`database.py:1440`).

- **D-9. The conftest guard.** A new autouse fixture, `_isolated_audit_buffer(request, monkeypatch, tmp_path_factory)`, sets `settings.AUDIT_BUFFER_DIR` to `str(tmp_path_factory.getbasetemp() / "audit-buffer" / str(next(_audit_buffer_numbers)))`. The path is not created: `AuditJournal._open_own` creates it on open (`audit_journal.py:252-261`), so a test that never opens a journal costs nothing.
  - At teardown, if `journal_drainer.running()` or `audit_journal.current() is not None`, it force-cleans (`journal_drainer._stop_all()`, then `close_journal()`) and calls `pytest.fail(..., pytrace=False)` naming the leak.
  - A non-`db` test that left a thread named `audit-journal-drainer` alive fails with a message citing PRD-014 D2.
  - Declared after `_fresh_storage_breaker`.
  - `tests/test_audit_journal.py`'s own `_slot_clean` (`:33-37`) is torn down before it, so the two compose.

---

## Patterns to Follow

### Naming and a keyed unit
```python
# SOURCE: app/db/database.py:1481-1497
def insert_audit_log(entry: AuditLog) -> int:
    """Write one audit row and return its id. ... (PRD-018 D4, STORY-004) ..."""

    def _op(conn: _Connection) -> int:
        return _insert_audit_row(conn, entry)

    return _unit_of_work("insert_audit_log", _keyed_kind([entry.write_id]), _op)
```

### Error handling: the unit raises `StorageUnavailableError` only for infrastructure classes
```python
# SOURCE: app/db/database.py:1186-1193
                breaker.record_failure(failure.value)
                retry_after = breaker.status().retry_after_seconds or 1
                raise StorageUnavailableError(
                    str(exc), retry_after_seconds=retry_after
                ) from exc
            raise
        breaker.record_success()
        return result
```

### Lifespan task shape (Reflex)
```python
# SOURCE: chat_ui/chat_ui/chat_ui.py:257-269
@asynccontextmanager
async def _pipeline_executor_lifespan():
    yield
    pipeline_executor.shutdown()


app.register_lifespan_task(_pipeline_executor_lifespan)
```

### Module-level, lazily created process resource under a lock
```python
# SOURCE: app/services/pipeline_executor.py:30-42 and audit_journal.py:637-661
_lock = threading.Lock()
_executor: Optional[ThreadPoolExecutor] = None
def _get_executor() -> ThreadPoolExecutor: ...      # never at import
```

### Structured logs
```python
# SOURCE: app/db/audit_journal.py:342-345
logger.info(
    "journal append write_id=%s user_id=%s decisions=%d bytes=%d",
    entry_write_id, user, len(decisions), len(line),
)
```

### Tests: fresh breaker, fake clock, fault script
```python
# SOURCE: tests/conftest.py:682-707 (fresh breaker per test), tests/db_faults.py:86-100 (Fault),
# tests/test_db_resilience_faults.py:98-109 (faulty_db usage)
faulty_db.add(Fault(text, sql=prefix))
```

### Lifespan test
```python
# SOURCE: tests/test_main.py:160-172
def test_lifespan_shuts_down_the_pipeline_executor(monkeypatch, temp_db):
    monkeypatch.setattr(settings, "RBAC_ENABLED", False)
    ...
    with TestClient(app):
        assert calls == []
    assert calls == [1]
```

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/database.py` | UPDATE | Add `drain_journal_entry` (D-8) beside `insert_action_decisions` (after `:3107`), in the existing keyed-insert docstring style |
| `app/db/journal_drainer.py` | CREATE | `DrainOutcome`, `drain_once`, `_storage_ready`, `_tick`, `_run`, `start`, `stop`, `running`, `held_back`, `_stop_all` (tests only). Constants (D-6). Module docstring citing PRD-018 6.8 Drain, D11, D17, Risk 7, PRD-014 D2, and the D-2/D-3 rulings |
| `app/main.py` | UPDATE | Import `journal_drainer`. `start(...)` last before `yield`, then `pipeline_executor.shutdown()` and `journal_drainer.stop()` after it (D-5) |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | Add `journal_drainer` and `settings` imports and an `_audit_journal_lifespan` task registered between `authz.check_bootstrap` and `_pipeline_executor_lifespan`, with a "Same bypass" comment (D-5) |
| `tests/conftest.py` | UPDATE | `_isolated_audit_buffer` autouse fixture (D-9), plus one docstring bullet in the module docstring's list |
| `tests/test_db_resilience_drain.py` | CREATE | The AC tests below |
| `tests/test_db_resilience_retry.py` | UPDATE | `_EXPECTED_KINDS["drain_journal_entry"] = K.IDEMPOTENT`, `len == 42`, each with a `# PRD-018 STORY-009 (D11)` comment |
| `tests/test_chat_ui_startup_guard.py` | UPDATE | The probe also reports `journal_lifespan_registered`, its order (after `check_bootstrap`, before `_pipeline_executor_lifespan`) and `journal_open_at_import = audit_journal.current() is not None`. Add one test asserting registration and order, and that nothing opened at import. Update the module docstring's list |

---

## Tasks

Execute in order. Each task is atomic and verifiable.

### Task 1: `database.drain_journal_entry`

- **File**: `app/db/database.py`
- **Action**: UPDATE
- **Implement**: Per D-8, placed after `insert_action_decisions` (`:3078-3107`). The docstring states: one transaction per entry (D11); the audit id is resolved by `write_id` inside the unit, never cached; decisions-only entries use the given `audit_id`; the original `timestamp` is kept; a replay is a no-op; the kind is a literal `IDEMPOTENT` because the journal refuses unkeyed rows (`audit_journal._validate`). `database.py:9` imports only `from dataclasses import dataclass, field`: extend it with `replace` (and call `replace(d, audit_id=row_id)`).
- **Mirror**: `insert_audit_log` (`database.py:1481-1497`), `insert_action_decisions` (`:3078-3107`)
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Kind table pin

- **File**: `tests/test_db_resilience_retry.py`
- **Action**: UPDATE
- **Implement**: Add `"drain_journal_entry": K.IDEMPOTENT,  # PRD-018 D11 (STORY-009): every journaled row is keyed` to `_EXPECTED_KINDS` (`:629-675`). Change `assert len(_EXPECTED_KINDS) == 41` to `42` (`:712`) with a comment citing PRD-018 STORY-009. `_PER_CALL_KIND` is unchanged (the literal `StatementKind.IDEMPOTENT`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_retry.py -q -k "kind or table or unit"`

### Task 3: `app/db/journal_drainer.py`

- **File**: `app/db/journal_drainer.py`
- **Action**: CREATE
- **Implement**: D-2, D-3, D-4, D-6 and D-7.
  - `from app.db import audit_journal, database` (module objects, so `database._storage_breaker` and `database.drain_journal_entry` are read at call time and tests can monkeypatch them). Plus `from app.db.errors import StorageUnavailableError` and `from app.services.circuit_breaker import BreakerOpen`.
  - No settings import: `start` takes the three values.
  - `_held_back: set[str]` and `_held_back_count` are guarded by `_lock`. `_stop_all()` resets the count and set to zero and stops, for the conftest guard.
  - `stop()` clears `_held_back` after the last user, so a re-start in the same process retries them.
  - `start` logs `journal drainer started adopted=%d pending=%d`, and `stop` logs `journal drainer stopped`.
- **Mirror**: the module slot in `audit_journal.py:637-661`, and the docstring density of `audit_journal.py:1-54`
- **Validate**: `.venv/Scripts/python -c "import app.db.journal_drainer as d, threading; assert not d.running(); assert not [t for t in threading.enumerate() if t.name == 'audit-journal-drainer']; print('OK')"`

### Task 4: FastAPI lifespan

- **File**: `app/main.py`
- **Action**: UPDATE
- **Implement**: D-5. `from app.db import journal_drainer`. After `authz.check_bootstrap()`, call `journal_drainer.start(settings.AUDIT_BUFFER_DIR, settings.AUDIT_BUFFER_MAX_BYTES, settings.PIPELINE_MAX_WORKERS)`. After `yield`, call `pipeline_executor.shutdown()` and then `journal_drainer.stop()`. Add a short comment citing PRD-018 D11/D17 and the order's reason.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 5: Reflex lifespan task

- **File**: `chat_ui/chat_ui/chat_ui.py`
- **Action**: UPDATE
- **Implement**: D-5. Import `from app.config import settings` and `from app.db import journal_drainer`. Add:
  ```python
  @asynccontextmanager
  async def _audit_journal_lifespan():
      journal_drainer.start(settings.AUDIT_BUFFER_DIR, settings.AUDIT_BUFFER_MAX_BYTES, settings.PIPELINE_MAX_WORKERS)
      yield
      journal_drainer.stop()
  ```
  Register it right after `app.register_lifespan_task(authz.check_bootstrap)` (`:255`), before the `_pipeline_executor_lifespan` block. The comment explains: same bypass; after `init_db()` at import (D17); before the executor's task so the `AsyncExitStack` teardown shuts the executor down first; the reference count makes a mounted `app.main` lifespan harmless.
- **Validate**: run `tests/test_chat_ui_startup_guard.py` (Task 8), which is the probe form from the brief

### Task 6: conftest isolation and leak guard

- **File**: `tests/conftest.py`
- **Action**: UPDATE
- **Implement**: D-9. `_audit_buffer_numbers = itertools.count(1)` (itertools is already imported, `:59`). Import `audit_journal` and `journal_drainer` from `app.db` beside the other `app` imports (`:90-96`). Add a module docstring bullet: "**The audit journal.** `_isolated_audit_buffer` …".
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_audit_journal.py tests/test_conftest_fixtures.py -q`

### Task 7: `tests/test_db_resilience_drain.py`

- **File**: `tests/test_db_resilience_drain.py`
- **Action**: CREATE
- **Implement**: Module docstring as in the sibling files (`tests/test_db_resilience_retry.py:1-14`), naming which tests are `db`. Helpers: `_audit(write_id=…, timestamp=…)` and `_decision(write_id, i)`, mirroring `tests/test_audit_journal.py`'s builders, plus a `journal` fixture building `AuditJournal(str(tmp_path / "buf"), 1 << 20, 2)` and closing it.

  **Non-`db`** (real `AuditJournal` on `tmp_path`, `database.drain_journal_entry` monkeypatched with a recording fake, breaker from conftest or an injected `CircuitBreaker` with a fake clock and fake probe):
  1. Empty journal: `drain_once` returns `empty`, and neither the fake drain nor the breaker probe runs.
  2. FIFO with one entry per call: with three entries appended, three calls drain them in append order. After the last, the own file is 0 bytes and there is no checkpoint sidecar (AC 1, AC 5 compaction).
  3. Breaker open with the window running (`force_open(10)` on a fake-clock breaker): `breaker_open`, no drain, no probe, entry still first (AC 3).
  4. Window elapsed (advance the fake clock): the probe runs once, closes the breaker, and the same call drains (D-2).
  5. Probe fails: `breaker_open`, the entry stays first, and the drain is not called.
  6. `StorageUnavailableError` from the fake: `unavailable`, `pending()[0].write_id` unchanged, nothing marked, file size unchanged (AC 3).
  7. `IntegrityError` from the fake for entry A: `held_back`, one ERROR line with A's `write_id` and no exception text (assert the message does not appear in `caplog.text`). The next call drains B. A stays pending, the file is not compacted, `held_back() == 1`, and a third call returns `empty` (A is skipped this process) (D-3).
  8. The loop yields between entries: `_run` with a fake stop runs two entries, then empty. The recorded waits are `[_DRAIN_YIELD_SECONDS, _DRAIN_YIELD_SECONDS, _DRAIN_IDLE_SECONDS]`, with one drain call per tick (Risk 7, AC 3).
  9. The loop survives a crash in a tick: `drain_once` patched to raise `RuntimeError` once. The ERROR log names the class, and the loop keeps going.
  10. A drained log line exists for each entry: `journal drained write_id=… user_id=…` (AC 5).
  11. Nothing starts at import: `subprocess` runs `-c "import app.main, app.db.journal_drainer as d, app.db.audit_journal as j, threading; print(d.running(), j.current() is None, any(t.name == 'audit-journal-drainer' for t in threading.enumerate()))"` and expects `False True False` (AC 4). The child env comes from `os.environ` with `DATABASE_URL` set. A subprocess, because this test process already imported `app.main`.

  **`db`** (`temp_db` / `faulty_db`; the real `database.drain_journal_entry`):
  12. Audit and decisions: `drain_journal_entry(audit, decisions)` returns the row id. `get_audit_log(id).timestamp` is the original. `list_action_decisions` rows have `audit_id == id` and their own `write_id`s (AC 1).
  13. Decisions only: first `insert_audit_log(audit)`, then `drain_journal_entry(None, decisions, audit_id=that_id)` inserts the decisions with that id (AC 1).
  14. Replay is a no-op: drain the same entry twice. Same id, `SELECT COUNT(*) FROM audit_logs WHERE write_id = ?` is 1, and the decision count is unchanged (AC 2).
  15. **Crash between commit and checkpoint** (simulated, the cheaper honest choice):
      - Journal A in `tmp_path/buf` holds one entry.
      - Monkeypatch `A.mark_drained` to raise `SystemExit`-like `RuntimeError("crash")`.
      - `drain_once(A)` raises out of it (call `drain_once` directly, not `_tick`), after the unit committed.
      - `A.close()`, which leaves the files and releases the lock.
      - Journal B opens in the same dir and `B.adopt() == 1`. The entry is pending again.
      - `drain_once(B)` returns `drained`.
      - Assertions: `COUNT(*) WHERE write_id = ?` is 1, the row's `timestamp` is the original, A's file is deleted (adopted file drained, `audit_journal.py:443-449`) and B's own file is 0 bytes (AC 2).
  16. A drain failure feeds the breaker: `faulty_db.add(Fault(CONNECT_REFUSED, sql="INSERT INTO AUDIT_LOGS", times=3))`. `drain_once` returns `unavailable`, `database._storage_breaker.status().consecutive_failures == 1`, and the entry is still first (AC 3).
  17. A STATEMENT failure does not feed the breaker: `Fault(UNIQUE_SESSION_ID, sql="INSERT INTO ACTION_DECISIONS")` (`tests/db_faults.py:75-78`, a UNIQUE failure on a non-`write_id` column) gives `held_back`, and `consecutive_failures == 0`. Also check that the audit row did **not** land, because the unit rolled back (D-3).
  18. Lifespan opens, adopts and drains (`TestClient(app)`, `RBAC_ENABLED=False`, `_DRAIN_IDLE_SECONDS` monkeypatched to `0.01`):
      - Before entering, write an orphan journal into `settings.AUDIT_BUFFER_DIR` with a standalone `AuditJournal`, then close it.
      - Inside: `audit_journal.current()` is not None, `journal_drainer.running()`, and a thread named `audit-journal-drainer` is alive and a daemon. Poll at most 5 s, in 0.05 s steps, until the row count is 1.
      - After exit: `running()` is False, `current()` is None, the thread is gone (AC 4).
  19. Unwritable dir (`AUDIT_BUFFER_DIR = str(tmp_path / "a-file" / "sub")`, where `a-file` is a regular file, so this works on Windows and POSIX): `pytest.raises(AuditUnavailableError, match="AUDIT_BUFFER_DIR")` around `with TestClient(app): pass`. Afterwards `running()` is False and `current()` is None (AC 4).
  20. Both lifespans in one process: `journal_drainer.start(...)` twice gives one journal (`current()` identity) and exactly one drainer thread. The first `stop()` keeps it running and the second stops and closes it. A third `stop()` is a no-op (D-4). This is `db` because it starts the real thread. Request `temp_db`.
  21. Startup order: in a `TestClient(app)` lifespan, `init_db` is monkeypatched to record a call order with a wrapped `journal_drainer.start`, giving `["init_db", "journal_start"]`. On exit, the order is `["pipeline_shutdown", "journal_stop"]` (D17, D-5).
- **Mirror**: `tests/test_audit_journal.py` (builders, tmp_path), `tests/test_db_resilience_faults.py:98-109` (faulty_db), `tests/test_main.py:160-172` (lifespan)
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_drain.py -q`

### Task 8: Chat UI probe

- **File**: `tests/test_chat_ui_startup_guard.py`
- **Action**: UPDATE
- **Implement**: In `_CHECK_SCRIPT`, after `tasks = ...` (`:58`), add `result["journal_lifespan_registered"] = chat_ui_module._audit_journal_lifespan in tasks`. Add `result["journal_lifespan_order_ok"]`, which is check_bootstrap index < journal index < pipeline-executor index. Add `result["journal_open_at_import"] = __import__("app.db.audit_journal", fromlist=["x"]).current() is not None`. Add `test_audit_journal_lifespan_registered_after_bootstrap_before_executor_shutdown` asserting registered, order OK, and `journal_open_at_import is False`, with a `# PRD-018 STORY-009 (D11, D17)` header comment in the file's block style. Add the drainer to the module docstring's list of duplicated concerns. No existing assertion changes.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_chat_ui_startup_guard.py -q`

### Task 9: Targeted run (one pytest process)

- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_db_resilience_drain.py tests/test_db_resilience_retry.py tests/test_audit_journal.py tests/test_main.py tests/test_chat_ui_startup_guard.py tests/test_pattern_default_config_regression.py tests/test_conftest_fixtures.py tests/test_db_resilience_faults.py tests/test_untouched_app.py -q`
- If a test is renamed or removed (none planned), also run `tests/test_pii_redaction_integration.py`. Full suite: GitHub CI on push (user decision).

---

## End-to-End Tests

- [ ] `from app.main import app` imports with no thread named `audit-journal-drainer` and `audit_journal.current() is None` (Task 7 #11)
- [ ] `TestClient(app)` boots against `temp_db`, adopts an orphan journal, drains it into `audit_logs` with its original timestamp, and leaves nothing running after exit (Task 7 #18)
- [ ] An unwritable `AUDIT_BUFFER_DIR` refuses startup with a message naming `AUDIT_BUFFER_DIR` (Task 7 #19)
- [ ] The chat UI probe shows the journal lifespan task between `check_bootstrap` and `_pipeline_executor_lifespan`, and no journal opened at import (Task 8)

---

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_chat_ui_startup_guard.py -q
PYTHONUTF8=1 .venv/Scripts/python -m pytest <Task 9 file list> -q
```

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| The drainer's probe nudge (D-2) is read as violating "does nothing while open" | It never touches a client while the window runs. Once the window elapses, it is the same single breaker-owned `SELECT 1` any request would trigger, gated on a non-empty journal. It is flagged for the orchestrator, with the fallback named |
| A stalled drain call (no driver read timeout, up to about 21 s) delays shutdown | `join(_DRAIN_STOP_JOIN_SECONDS)`, a WARNING, then close. The daemon thread does not block exit. An entry that committed but was not marked replays as a no-op next boot |
| `mark_drained` racing `close_journal()` after a timed-out join | The journal's own compaction catches `OSError`/`ValueError` and logs (`audit_journal.py:429-449`). The process is exiting, and replay is a no-op. No change to STORY-008's module |
| Lifespan tests now write files | The conftest path is under pytest's basetemp, never `./var`, and is created only on open |
| A test leaks a journal and breaks the next test's `open_journal` with `RuntimeError` | The D-9 teardown guard force-cleans and fails the leaking test by name |
| Poison entry wedges the queue | The D-3 hold-back keeps the row on disk, skips it for the rest of the process, and retries on the next boot |
| The thread competes with live traffic (Risk 7) | One entry per transaction, a 10 ms yield between entries, and draining only while the breaker admits |
| Reflex teardown order assumption | Taken from Reflex's `AsyncExitStack` in `LifespanMixin._run_lifespan_tasks` (reverse of registration). Task 8 pins the registration order |

---

## Deviations / decisions for the orchestrator

1. **D-2 (probe nudge)**: the story says "only drains while the breaker is closed". `status()` never leaves `open` without a `before()` call, so a literal reading leaves an idle instance's journal undrained indefinitely. The plan calls `before()` only when the journal is non-empty, which lets the breaker's own probe run once the window elapses. Please confirm, or rule "closed only, wait for traffic".
2. **D-3 (statement failure)**: hold the entry back in-process (never delete it or mark it drained), skip it for the rest of the process, log ERROR with the exception class only, count it, and retry it on the next boot through adoption. `StorageUnavailableError` stops the pass with the entry still first.
3. **D-4 (both lifespans)**: a reference count in `journal_drainer` instead of catching `open_journal`'s `RuntimeError`, so the second `start` shares the first's journal and the last `stop` closes it.
4. **Signature**: `drain_journal_entry(audit, decisions, *, audit_id=None)` takes fields, not a `JournalEntry`, so `database.py` never imports the journal module.
5. `held_back()` / `running()` are exposed for STORY-012. No status endpoint work is done here.

---

## Acceptance Criteria

(Copied from story `STORY-009`)

- [ ] Given a non-empty journal and a closed breaker, when the drainer runs, then it takes the oldest entry and runs one `_unit_of_work(IDEMPOTENT)` transaction: insert the audit row with `ON CONFLICT(write_id) DO NOTHING`, select its id by `write_id`, insert the decisions with that `audit_id` (`ON CONFLICT DO NOTHING`), commit, then advance the checkpoint and drop the row from the pending index. Decisions-only entries (`audit: null`, `audit_id` known) insert the decisions alone. *(Task 1, 7 #2, #12, #13)*
- [ ] Given a crash between drain commit and checkpoint (simulated by raising after commit and reloading the journal), when the drainer runs again, then the replay is a no-op and `SELECT COUNT(*) FROM audit_logs WHERE write_id = ?` is 1, and the drained row keeps its original `timestamp`. *(Task 7 #14, #15)*
- [ ] Given the breaker open or a drain failure, when the drainer ticks, then it does nothing while open, a drain failure feeds the breaker like any other operation, and the entry stays first in line. It yields between entries (Risk 7). *(Task 7 #3-#6, #8, #16, #17)*
- [ ] Given `app/main.py`'s lifespan and `chat_ui/chat_ui/chat_ui.py`'s lifespan task, when the app starts after a successful `init_db()`, then the journal is opened (unwritable directory → startup error naming `AUDIT_BUFFER_DIR`), orphaned journals are adopted, and the daemon drainer thread starts. On shutdown it stops. Nothing starts at import: a non-`db` test never meets the thread. *(Tasks 4-6, 8; Task 7 #11, #18-#21; conftest guard)*
- [ ] Given each drain and each adoption, when it happens, then one structured log line is written (`journal drained write_id=… user_id=…`), and when the journal is fully drained it is compacted to zero bytes. *(Task 7 #2, #10, #15; adoption line at `audit_journal.py:568`)*
- [ ] All tasks completed
- [ ] `from app.main import app` imports cleanly, and the chat UI probe passes
- [ ] Follows existing patterns
