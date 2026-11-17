---
story: STORY-012
prd: PRD-018
slug: storage-status-and-admin-panel
title: GET /storage/status, in-memory counters, and the admin console Storage panel
type: NEW_CAPABILITY
complexity: MEDIUM
epic_branch: epic/PRD-018-db-resilience        # all stories commit here, no per-story branch
created: 2026-11-17
---

# Plan: Storage status endpoint, counters and admin Storage panel (PRD-018 F8, D16, Section 10)

## Summary

Add a process-local, thread-safe counter module (`app/db/storage_counters.py`) and wire each increment at the one place its event happens (`_unit_of_work` retry / exhausted, the breaker's transition to open via a generic hook, `AuditJournal.append` / `mark_drained` / adoption torn tail). Add `database.storage_status() -> StorageStatus` (instance, `BreakerStatus` as is, a journal view, counter snapshot) that reads only in-memory state: zero driver calls, never `_client_lock`. Expose it as `GET /storage/status` (`stats:read`) in `app/routers/admin.py` and register it in the Caddyfile matcher (otherwise production serves a 404 from the static server). Add a Storage view to the admin console (new page `/admin/storage`, fifth masthead peer) that reads `storage_status()` in-process, in the Usage view's style. Route `usage_limits.charge`'s logged driver text through redaction (orchestrator note).

## User Story

As a platform operator
I want to see breaker state, journal depth and retry counters without opening a shell
So that I know whether I am looking at a blip, an outage or a backlog

## Story Reference

- Story file: `.agents/stories/PRD-018-db-resilience/STORY-012-storage-status-and-admin-panel.md`
- PRD: `.agents/PRDs/PRD-018-db-resilience/PRD.md` (F8 :367, Section 10 :435-451, auth :388, D16 :564, zero driver calls :483)

## Metadata

| Field | Value |
|-------|-------|
| Type | NEW_CAPABILITY |
| Complexity | MEDIUM |
| Systems Affected | app/db (database, audit_journal, new storage_counters; journal_drainer read-only), app/services/circuit_breaker (generic hook), app/routers/admin, app/models/schemas, Caddyfile, chat_ui admin console, usage_limits logging |
| Story | STORY-012 |
| PRD | PRD-018 |
| Epic Branch | `epic/PRD-018-db-resilience` (commit directly on this branch) |

Dependencies STORY-005, 008, 009 are `status: done` (checked in their frontmatter).

---

## Skills In Use

| Skill | Why it applies | Tasks affected |
|-------|---------------|----------------|
| frontend-design (`.agents/skills/frontend-design/SKILL.md`) | "Structure is information"; no decoration; copy names what the operator controls; failure and emptiness give direction. The Usage view already applied it (`chat_ui/chat_ui/components/usage.py:1-45`: no meters, bars or accent colours), so Storage keeps that restraint: words and numbers, order that encodes meaning, no charts. The brief says match existing panels rather than invent a style | Tasks 9, 11, 12 |
| Reflex (`chat_ui/AGENTS.md`) | Names the `reflex-docs` skill as required before editing Reflex code. It is not in `.agents/skills/`; the implementer reads the local Usage/Actions components instead and validates with `tests/test_chat_ui_startup_guard.py` | Tasks 9-12 |

---

## Patterns to Follow

### The breaker instance and its test swap
```
// SOURCE: app/db/database.py:299-309
# One per process ... `storage_status()` (STORY-012) reads `.status()`. Tests swap it per test
# (`tests/conftest.py::_fresh_storage_breaker`).
_storage_breaker = CircuitBreaker("storage", _BREAKER_FAILURE_THRESHOLD, _BREAKER_OPEN_SECONDS, probe=_probe_fresh_client)
```
`_storage_breaker` is read at call time everywhere (`_unit_of_work` :1125, `journal_drainer._storage_ready` :87-89); `storage_status()` does the same.

### Log lines the counters sit beside
```
// SOURCE: app/db/database.py:1160-1196 (_unit_of_work)
logger.info("retry op=%s class=%s attempt=%d detail=%s", ...)   -> counters.retry(name, failure.value)
logger.warning("retry exhausted op=%s ...")      } both fall through to the shared
logger.warning("retry refused op=%s ...")        } breaker.record_failure(failure.value) (:1187)
// SOURCE: app/services/circuit_breaker.py:152-164  _emit(): every transition passes here, after the lock is released
// SOURCE: app/db/audit_journal.py:344-347 (append log), :400-419 (mark_drained), :563 (adopt: self._torn_tail_discarded += discarded)
```

### Router and auth style
```
// SOURCE: app/routers/admin.py:180-185
@router.get("/stats", response_model=StatsResponse,
            dependencies=[Depends(require_permission(PERMISSION_STATS_READ))])
def get_stats() -> StatsResponse:
```
`require_permission` returns 403 `Permission denied: stats:read` (`app/middleware/auth.py:34-42`). `ADMIN_TOKEN` is break-glass and resolves with no read (PRD :388), so the endpoint answers during an outage. `PERMISSION_STATS_READ` is `app/services/authz.py:14`.

### Tests
```
// SOURCE: tests/conftest.py:670-686  non-db tests get database._shared_client and libsql.connect replaced by _refuse(); a swallowed access still fails at teardown
// SOURCE: tests/test_stats_router.py:25-60  TestClient(app), ADMIN_TOKEN header, refusal before any read
// SOURCE: tests/test_rbac.py:125  stats:read role matrix (db test: identity read)
// SOURCE: tests/test_caddyfile_routes.py:36-47,121-128  EXPECTED_MATCHER restated; every route in app.routes must be matched
```

### Admin console view (Usage is the precedent)
```
// SOURCE: chat_ui/chat_ui/chat_ui.py:108-110,178-182  admin_usage_page() = admin_page(usage(), VIEW_USAGE); app.add_page(..., context={"sitemap": None})
// SOURCE: chat_ui/chat_ui/admin_state.py:211-222 (state keys), :1062-1082 (usage_state), :1415-1428 (own try/except in load(), own *_error)
// SOURCE: chat_ui/chat_ui/components/admin_shell.py:58-78 (ROUTE_/VIEW_), :465-511 (nav peers), :586-625 (admin_page)
// SOURCE: chat_ui/chat_ui/components/usage.py:1-60 (imports only admin_copy/theme/AdminState/fault_panel/refreshed_stamp)
```

---

## Design decisions (choices flagged in "Open questions")

1. **Counter home: new `app/db/storage_counters.py`**, not `database.py`. `audit_journal.py` must not import `database` (`audit_journal.py:60-80`: only errors/models; PRD: no DB calls) while `database.storage_status()` must read journal state, so counters in `database.py` would force the forbidden edge. A leaf module that imports nothing from `app` breaks the cycle. Contents: a lock; `retries` and `exhausted` dicts keyed `"<op>:<class>"`; ints `breaker_opens`, `journal_appended`, `journal_drained`, `torn_tail_discarded`; functions `retry(op, cls)`, `exhausted(op, cls)`, `breaker_opened()`, `journal_appended()`, `journal_drained()`, `torn_tail_discarded(n)`, `snapshot() -> CounterSnapshot` (frozen, copied dicts), `_reset()` for tests. Key cardinality is bounded (`op` is a literal at each call site, `class` is the closed `FailureClass` vocabulary). No dependency (D16).
2. **`breaker_opens` via a generic hook.** Add an optional kwarg `on_transition: Optional[Callable[[str, str, str], None]] = None` to `CircuitBreaker` (called with `(from, to, class)` from `_emit`, after the lock is released; an exception from the hook is caught and logged so it cannot break the breaker). The class stays storage-ignorant for PRD-022. `database.py` builds the storage instance with a new `_new_storage_breaker()` whose hook calls `storage_counters.breaker_opened()` when `to == "open"`. Counting at `record_failure` in `_unit_of_work` was rejected: it misses a failed half-open probe re-opening the circuit (`circuit_breaker.py:211-243`) and `force_open`. **`breaker_opens` = transitions into `open`, including a re-open after a failed probe.** The conftest `_fresh_storage_breaker` (`tests/conftest.py:705-713`) must use the same factory so per-test breakers count (modified fixture; comment cites PRD-018 STORY-012). `tests/test_db_resilience_breaker.py:59` builds its own breaker with a fake clock and is unaffected.
3. **Refused retries are counted in `counters.exhausted`** (no `refused` map). The PRD's own example is `"exhausted": {"admit_usage:outcome_unknown": 1}` (PRD :445), and `admit_usage` is `NON_IDEMPOTENT`, so that example is a refused retry. A single `storage_counters.exhausted(name, failure.value)` call placed immediately before `breaker.record_failure(...)` (`database.py:1187`) runs exactly once per operation ending in an infrastructure failure (budget exhausted or retry refused) and never on the `continue` path; so `exhausted` equals the number of `record_failure` calls. Docstring says so.
4. **`retries`**: incremented where the INFO `retry ...` line is emitted (`database.py:1160`), once per retry, before the sleep.
5. **`journal_appended`**: in `AuditJournal.append`, after fsync and `_index` succeeded, beside the `journal append` log (`audit_journal.py:344`); a refused or failed append counts nothing. **`journal_drained`**: end of `AuditJournal.mark_drained` (only caller: `journal_drainer.drain_once`, `journal_drainer.py:117`); not on `KeyError`. Counting in the journal keeps the pair symmetric and testable without a database. **`torn_tail_discarded`**: in `_adopt_one` where `self._torn_tail_discarded += discarded` (`audit_journal.py:~563`), call `storage_counters.torn_tail_discarded(discarded)` when `discarded > 0`; a damaged file (`_load` returns `None`) counts nothing. `JournalStatus.torn_tail_discarded` stays per journal object; the counter is process-wide.
6. **`StorageStatus`** (frozen dataclasses in `database.py`): `instance: str = f"{socket.gethostname()}:{os.getpid()}"` (the journal's `_host_tag()` sanitises for file names and is private: do not reuse), `breaker: BreakerStatus` (as is), `journal: JournalView`, `counters: CounterSnapshot`. `JournalView`: `entries, bytes, max_bytes, headroom_bytes, oldest_timestamp, draining, adopted_files, held_back_entries, held_back_files`, plus `open: bool` (my addition over PRD Section 10: tells "no journal in this process" from "empty journal").
   - **No journal open** (`audit_journal.current() is None`): `open=False, entries=0, bytes=0, max_bytes=settings.AUDIT_BUFFER_MAX_BYTES, headroom_bytes=settings.PIPELINE_MAX_WORKERS * 65536, oldest_timestamp=None, draining=False, adopted_files=0, held_back_entries=0, held_back_files=0`. Never raises.
   - **`headroom_bytes`**: the PRD example `2097152` is 32 workers x 65536 (`PIPELINE_MAX_WORKERS` default 32, `app/config.py:264`), i.e. the admission reserve: admission is refused once `bytes > max_bytes - headroom_bytes` (`audit_journal.py:502-505`). It is not "free bytes left". Add `headroom_bytes` to `JournalStatus` (set in `AuditJournal.status()` as `self._workers * _JOURNAL_ENTRY_RESERVE_BYTES`), an additive field on a frozen dataclass built only by `status()`.
   - **`draining` is true iff** `journal_drainer.running()` **and** breaker state is `closed` **and** `entries - held_back_entries > 0`. The PRD example shows `draining: false` with `entries: 3` while the breaker is `open` (PRD :126), so "thread alive and entries > 0" is wrong during an outage (the drainer idles until the breaker lets a probe through, `journal_drainer.py:84-93`); held-back entries are never retried this process (`journal_drainer.py:34-39`), so they are not work. `breaker` and `draining` use one `BreakerStatus` read, so they agree.
   - `held_back_entries = journal_drainer.held_back()`, `held_back_files = JournalStatus.held_back_files`.
7. **Zero driver calls, no `_client_lock`.** Reads: `_storage_breaker.status()` (breaker lock, never held across the probe, per the `circuit_breaker.py` docstring), `AuditJournal.status()` (journal mutex: in-memory work plus an fsync in `append`), `journal_drainer.running()` (lock-free), `held_back()` (drainer `_lock`, never held across a database call, `journal_drainer.py:94-96`), `storage_counters.snapshot()`. `journal_drainer` imports `database` (`journal_drainer.py:53`), so `storage_status()` imports it function-locally with a comment naming the cycle. No `_shared_client`, `get_connection`, `_session` or `_unit_of_work` is reachable.
8. **Endpoint is a plain `def`**, like `/stats` (`admin.py:185`); its dependencies are sync and use the threadpool anyway. Response models `StorageStatusResponse` plus nested `StorageBreakerResponse`, `StorageJournalResponse`, `StorageCountersResponse` in `app/models/schemas.py` (beside `StatsResponse`, `schemas.py:323`), built from `dataclasses.asdict(storage_status())` ("serialize as is", story Technical Notes).
9. **Caddy / route census.** `/storage/status` must be added to `@backend_routes` in `Caddyfile` and to `EXPECTED_MATCHER` in `tests/test_caddyfile_routes.py:36-47` (restated on purpose; modified assertion with a PRD-018 STORY-012 comment). `test_every_harness_route_is_proxied_by_caddy` (`:121`) reads `app.routes` and fails without the Caddyfile edit. `/admin/storage` is a Reflex page, stays static: add it to `STATIC_PATHS` (`:57`). `tests/test_route_reservations.py:30-31` is a `<=` subset and passes unmodified. No other census exists (greps for `app.routes`, `openapi`, `original_router` in `tests/`: `test_admin_shell.py`, `test_caddyfile_routes.py`, `test_route_reservations.py`, `test_v1_*` only; `test_v1_*` are `/v1`-scoped).
10. **Admin console: a new view**, `ROUTE_STORAGE = "/admin/storage"`, `VIEW_STORAGE = "storage"`, fifth masthead peer. Read in `AdminState.load()` as its own `try` with its own `storage_error` (`READ_LABEL_STORAGE = "the storage status"`), **before** the usage read, so an outage that fails the summary read still refreshes it. `storage_status()` makes no DB call, so it is called directly, not via `asyncio.to_thread`. Imported by name from `app.db.database` (read-only by construction, `admin_state.py:1-30` docstring); the console imports no journal, drainer or counters module. State: strings/lists only, the `UsageRow` rule (components compute nothing), a `storage_state` computed var with `STORAGE_STATE_FAULT` / `STORAGE_STATE_READY` (no "empty": the read cannot be empty). `sign_out()` is `reset()`; `tests/test_admin_state.py:318-330` demands every base var default in `("", 0, False, None, [])`, so shape the vars like `usage_rows` (list of pydantic rows + plain str vars), not a pydantic-default var.
    Panel content (copy only in `admin_copy.py`, pure formatting in `admin_formatting.py:to_storage_view`): a one-line verdict in words (reachable / circuit open since `<since>`, requests refused for `<n>` s / probing), then breaker state + `since`, consecutive failures, last failure class, journal entries and bytes of max, oldest, draining, adopted files, **held-back entries and files** (when non-zero, one plain sentence: kept on disk, an operator must look; the orchestrator's decision), then the six counters, the two keyed maps as `<op> / <class> / count` rows. `instance` appears beside the refreshed stamp (counters are per process). Existing Refresh only; no polling.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/db/storage_counters.py` | CREATE | Thread-safe in-memory counters, `CounterSnapshot` |
| `app/services/circuit_breaker.py` | UPDATE | Optional generic `on_transition` hook in `_emit` |
| `app/db/database.py` | UPDATE | `_new_storage_breaker()`, retry/exhausted counts, `StorageStatus`, `JournalView`, `storage_status()` |
| `app/db/audit_journal.py` | UPDATE | `JournalStatus.headroom_bytes`; counters in `append`, `mark_drained`, `_adopt_one` |
| `app/models/schemas.py` | UPDATE | `StorageStatusResponse` + nested models |
| `app/routers/admin.py` | UPDATE | `GET /storage/status` |
| `Caddyfile` | UPDATE | `/storage/status` in `@backend_routes` |
| `app/services/usage_limits.py` | UPDATE | log redacted driver text in `charge` (:217-227) |
| `chat_ui/chat_ui/admin_copy.py` | UPDATE | Storage view copy, `READ_LABEL_STORAGE` |
| `chat_ui/chat_ui/admin_models.py` | UPDATE | string row models |
| `chat_ui/chat_ui/admin_formatting.py` | UPDATE | `to_storage_view` |
| `chat_ui/chat_ui/admin_state.py` | UPDATE | vars, `storage_state`, load() read, by-name import |
| `chat_ui/chat_ui/components/admin_shell.py` | UPDATE | `ROUTE_STORAGE`, `VIEW_STORAGE`, fifth nav peer |
| `chat_ui/chat_ui/components/storage.py` | CREATE | The Storage view |
| `chat_ui/chat_ui/chat_ui.py` | UPDATE | `admin_storage_page`, `app.add_page` |
| `tests/test_storage_status.py` | CREATE | non-`db`: shape, zero-call guard, endpoint, counters, hook |
| `tests/test_storage_view.py` | CREATE | non-`db`: formatting, state, load() isolation, component |
| `tests/conftest.py` | UPDATE | breaker fixture uses the factory; autouse `_fresh_storage_counters` |
| `tests/test_admin_shell.py` | UPDATE | pinned sets `:58-66`, `:157-166`, `:176-182`, probe `:327-340` |
| `tests/test_caddyfile_routes.py` | UPDATE | `EXPECTED_MATCHER`, `STATIC_PATHS` |
| `tests/test_usage_limits.py`, `tests/test_circuit_breaker.py`, `tests/test_audit_journal.py` | UPDATE | additive tests |

Not touched: `docs/api.md` (STORY-014), `/health`, `_translated()`, `tests/test_route_reservations.py`, `tests/test_untouched_app.py`.

---

## Tasks

Execute in order.

### Task 1: Counters module
- **File**: `app/db/storage_counters.py` CREATE per Decision 1. Docstring cites PRD-018 D16 ("process-local, reset on restart, no metrics dependency"). No `app` imports.
- **Mirror**: frozen snapshot style of `audit_journal.JournalStatus` (`audit_journal.py:111-123`).

### Task 2: Breaker hook
- **File**: `app/services/circuit_breaker.py` UPDATE. `on_transition` kwarg, default `None`, documented in the class docstring; called from `_emit` after the log; `except Exception: logger.exception`. No storage default, no new imports.
- **Validate**: `tests/test_circuit_breaker.py` unchanged tests still pass.

### Task 3: Journal counters and headroom
- **File**: `app/db/audit_journal.py` UPDATE per Decision 5; `headroom_bytes` per Decision 6; update the module docstring "Consumers" line (:54).
- **Validate**: `tests/test_audit_journal.py`.

### Task 4: Wire `_unit_of_work` and the breaker factory
- **File**: `app/db/database.py` UPDATE. `_new_storage_breaker()` (current arguments plus the hook); `_storage_breaker = _new_storage_breaker()`; `storage_counters.retry(...)` before `_retry_sleep(delay)`; `storage_counters.exhausted(...)` right before `breaker.record_failure(...)`. One docstring sentence in "Logs (AC 5)". `_translated()` and its docstring untouched.
- **Validate**: `tests/test_db_resilience_retry.py`, `tests/test_db_resilience_breaker.py`.

### Task 5: `storage_status()`
- **File**: `app/db/database.py` UPDATE per Decisions 6-7, function-local `journal_drainer` import. Docstring: zero driver calls, never `_client_lock`, answers during a stall (PRD-018 D16).

### Task 6: Schemas and route
- **Files**: `app/models/schemas.py`, `app/routers/admin.py` UPDATE (Decision 8), keys exactly as PRD :435-451 plus `held_back_entries`, `held_back_files`, `open`. Import `storage_status` by name.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`.

### Task 7: Caddyfile
- **File**: `Caddyfile` UPDATE: add `/storage/status` before `/v1/*`; same position in `EXPECTED_MATCHER` (token order is asserted).

### Task 8: Charge log redaction
- **File**: `app/services/usage_limits.py` UPDATE (`:217-227`, the `error=%s` argument is raw `exc`). Pass `_retry_detail(exc)` (`database.py:1044-1048`: `_redacted` plus echoed-SQL elision, 500 chars), imported by name beside `admit_usage, charge_usage` (`:29`). Comment cites PRD-018 Section 11 / Quality indicators. `tests/test_usage_limits.py:310-325` still holds (`"boom"` stays in the message). Grep `app/` and `chat_ui/chat_ui/` for any other log formatting a `StorageError` raw: the grep I ran found none besides this one. If the orchestrator wants bare `_redacted`, swap one name.
- **Validate**: `tests/test_usage_limits.py` plus a new test: a token in the driver text is `***` in the log.

### Task 9: Console copy, models, formatting
- **Files**: `admin_copy.py`, `admin_models.py`, `admin_formatting.py`. Copy only in `admin_copy.py` (`tests/test_register.py` forbids copy literals elsewhere). Pure formatting from a `StorageStatus` to strings; reuse `format_count`; check for an existing bytes formatter before adding one.
- **Mirror**: `to_usage_rows` (`admin_formatting.py:341`), `UsageRow` (`admin_models.py:93`).

### Task 10: State
- **File**: `admin_state.py` UPDATE per Decision 10: by-name import with a comment beside `usage_snapshot` (`:56`), state constants beside `USAGE_STATES` (`:211-222`), vars beside the usage vars (`:605-611`), `storage_state` beside `usage_state` (`:1062`), read in `load()` before the usage read, `storage_error = ""` reset with the others (`:1385-1388`). Extend the module docstring's read-only paragraph.

### Task 11: Component
- **File**: `components/storage.py` CREATE; imports only `admin_copy`, `theme`, `AdminState`, `fault_panel`, `refreshed_stamp`. Apply the frontend-design rules as `usage.py` did (no charts or accent colours, accessible names, narrow-viewport rules via the existing theme classes).
- **Mirror**: `components/usage.py` (`_head_cell`, `_cell`, grid, `fault_panel` for its own fault).

### Task 12: Shell, page, route
- **Files**: `admin_shell.py` (constants `:58-78`, nav peer pattern `:490-511`), `chat_ui.py` (`admin_storage_page`, `add_page(..., context={"sitemap": None})` like `:178-182`).
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_chat_ui_startup_guard.py tests/test_admin_shell.py -q`.

### Task 13: Conftest and pinned sets
- **Files**: `tests/conftest.py` (breaker fixture via `database._new_storage_breaker()`; autouse `_fresh_storage_counters` calling `storage_counters._reset()` before and after; docstring bullet), `tests/test_admin_shell.py`, `tests/test_caddyfile_routes.py`. Each edited assertion carries a PRD-018 STORY-012 comment.

### Task 14: New tests
- **`tests/test_storage_status.py`** (non-`db`, conftest guard active):
  - shape and AC 1: `instance == f"{socket.gethostname()}:{os.getpid()}"`, `breaker == database._storage_breaker.status()`, the no-journal zero shape, a journal-open snapshot.
  - zero driver calls: patch `libsql.connect`, `database._shared_client`, `database.get_connection` to raise; call with `force_open(30)` and with a journal open; plus hold `database._client_lock` in the test thread and call from a second thread with a join timeout (the 21 s stall case).
  - endpoint: ADMIN_TOKEN 200 with every PRD key; breaker forced open -> 200, `state == "open"`, `retry_after_seconds >= 1`; no token 401; `/health` is exactly `{"status": "ok"}`. The user-token 403/200 matrix needs an identity read: a `db` test (extend the `tests/test_rbac.py:125` matrix with the route, or one `db` test in this file).
  - one test per counter (AC 5), using the non-db fake world and seams of `tests/test_db_resilience_retry.py` (`_retry_sleep/_retry_clock/_retry_jitter`): one retry -> `retries["op:class"] == 1`; budget exhausted -> `exhausted == 1`, `retries == 2`; refused (`NON_IDEMPOTENT` + `OUTCOME_UNKNOWN`) -> `exhausted == 1`, `retries == {}`; `STATEMENT` -> nothing; breaker opens with the factory and a fake clock -> `breaker_opens == 1`, failed probe re-open -> 2, call refused while open -> unchanged; real `AuditJournal` in `tmp_path`: append -> `journal_appended == 1`, over-capacity append -> unchanged; `mark_drained` -> `journal_drained == 1`; adoption of a file with a partial last line -> `torn_tail_discarded == 1`; a damaged file -> 0.
  - `draining` truth table (patch `journal_drainer.running` / `held_back`): not running; breaker open; closed with entries; closed with only held-back entries.
  - pin: `circuit_breaker.py` source mentions neither `database` nor `storage_counters`.
- **`tests/test_storage_view.py`** (non-`db`): `to_storage_view` strings for closed/open/half-open and no-journal; held-back sentence only when non-zero; `AdminState.load()` fills storage and keeps it when the summary read fails; a failing `storage_status` sets only `storage_error`; `sign_out` clears; the console namespace has no `insert_audit_log`, `audit_journal`, `journal_drainer`, `storage_counters` (style of `tests/test_admin_state.py:369-387`); component source has no copy literal (structure of `tests/test_usage_view.py`).
- Additive: `tests/test_circuit_breaker.py` (hook called with `(from, to, class)` after the lock is released; a raising hook leaves the breaker working), `tests/test_audit_journal.py` (`headroom_bytes`).

---

## End-to-End Tests

- [ ] `.venv/Scripts/python -c "from app.main import app; print('OK')"`
- [ ] TestClient `GET /storage/status` with `ADMIN_TOKEN` after `force_open(30)`: 200, `state: "open"`, `retry_after_seconds >= 1`; `GET /health` unchanged.
- [ ] `tests/test_chat_ui_startup_guard.py` passes (its probe imports `chat_ui.chat_ui`, so the new page registers).
- [ ] Optional if cheap: run the console, open `/admin/storage`, press Refresh with the database stopped.

## Validation (one pytest call, `PYTHONUTF8=1`; full suite is GitHub CI)

```
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_storage_status.py tests/test_storage_view.py tests/test_circuit_breaker.py tests/test_audit_journal.py tests/test_usage_limits.py tests/test_admin_shell.py tests/test_admin_state.py tests/test_admin_copy.py tests/test_register.py tests/test_usage_view.py tests/test_caddyfile_routes.py tests/test_route_reservations.py tests/test_stats_router.py tests/test_chat_ui_startup_guard.py tests/test_db_resilience_retry.py tests/test_db_resilience_breaker.py tests/test_db_resilience_drain.py tests/test_conftest_fixtures.py tests/test_untouched_app.py tests/test_pii_redaction_integration.py -q
```
No existing response field changes, so the STORY-010 `audit_id` exclusion grep is not needed. No pre-existing test function is renamed or removed.

## Acceptance Criteria

(From STORY-012; coverage)

- [ ] AC1 `storage_status()` shape, in-memory counters -> shape tests, Decision 6.
- [ ] AC2 `GET /storage/status` with `stats:read`, 403 without, zero driver calls even with the breaker open -> endpoint tests + guard test (403 case is `db`).
- [ ] AC3 breaker open -> 200 `state: "open"`, `retry_after_seconds >= 1`; `/health` unchanged -> endpoint test.
- [ ] AC4 Storage panel reads `storage_status()` in-process, no network call -> `test_storage_view.py` + startup guard.
- [ ] AC5 each counter increments exactly once per event -> one test per counter.
- [ ] Orchestrator notes: charge-log redaction (Task 8), refused retries in `exhausted` (Decision 3), held-back entries/files in journal view and panel (Decisions 6, 10).
- [ ] All tasks completed; server imports; Reflex startup guard passes; follows existing patterns.

## Risks

- **Caddy omission** would 404 the endpoint in production while every in-process test passes: Caddyfile edit plus `test_every_harness_route_is_proxied_by_caddy`.
- **Hook missing on test breakers**: conftest factory change; a test that builds its own breaker passes the hook itself.
- **`sign_out` default census** rejects a pydantic-default var: shape the vars like `usage_rows`.
- **Journal mutex**: `journal.status()` may wait a few ms behind an fsync in `append`; accepted (not `_client_lock`, never a driver stall).
- **Process scope**: counters and panel describe this process only; `instance` makes that visible.

## Open questions for the orchestrator

1. Refused retries counted in `exhausted` (no `refused` map): matches the PRD example. Agree?
2. `draining` = drainer running AND breaker `closed` AND non-held-back entries > 0. Agree?
3. `headroom_bytes` = admission reserve (`workers x 64 KiB`, 2097152 by default), not free bytes. Agree?
4. Extra `journal` keys beyond PRD Section 10: `held_back_entries`, `held_back_files` (requested), `open` (mine). Keep `open`?
5. New leaf module `app/db/storage_counters.py` rather than counters in `database.py`. Agree?
6. Console UI as a new page `/admin/storage` and fifth nav peer (needs the pinned-census updates in `tests/test_admin_shell.py`) rather than a section of an existing view. Agree?
7. `usage_limits.charge` logs through `_retry_detail(exc)` (redacts and elides echoed SQL) rather than bare `_redacted`. Agree?
8. `breaker_opens` counts every transition into `open`, re-opens after a failed probe included. Agree?
