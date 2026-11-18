---
story: STORY-001
prd: PRD-019
slug: readiness-settings-and-check-ready
title: Readiness settings and database.check_ready() — a bounded, breaker-neutral SELECT 1
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-019-multi-instance-deployment
created: 2026-11-17
---

# Plan: Readiness settings and `database.check_ready()`

## Summary

Add two settings (`DRAIN_FILE`, `READY_DB_TIMEOUT_SECONDS`) with validators in `app/config.py`, and a non-raising `database.check_ready() -> ReadyCheck` in `app/db/database.py`. It reads the breaker in memory only; while `closed` it runs one `SELECT 1` on a process-wide single-slot executor with a deadline, abandoning a stuck future. It never touches the breaker's mutating API. The `/ready` route, drain file check, Caddyfile and docs are STORY-002 / 005 / 011, not here.

- Story: `.agents/stories/PRD-019-multi-instance-deployment/STORY-001-readiness-settings-and-check-ready.md`
- PRD sections used: §4 Readiness, §6.3, §7 F1, §9.3, §11, D3, D5
- Systems affected: `app/config.py`, `app/db/database.py`, tests

## Design Decisions (binding, from the orchestrator)

- **Contract.** `ReadyCheck` frozen dataclass in `database.py`: `reason: Optional[str]` (None = ready), `breaker: str` (state read), `retry_after_seconds: Optional[int]` (only for `breaker_open`: `max(1, status.retry_after_seconds or 1)`). Module constant `READY_REASONS = ("breaker_open", "database_unreachable", "database_auth", "draining")` (closed vocabulary; the route adds `draining` in STORY-002). Never raises: the whole body sits in one `try/except Exception`; an unexpected error classifies as `database_unreachable` (`breaker` is `"unknown"` if it could not be read).
- **Breaker first, no driver call.** `_storage_breaker.status()` read once (same reading as `storage_status()`, database.py:1266). `open`/`half_open` -> `breaker_open`, return at once. Never `before()`, `record_success()`, `record_failure()`, never `_unit_of_work`, never retry. Read `_storage_breaker` at call time (a test may swap it, cf. database.py:1145).
- **Verified: `get_connection()` and `_shared_client()` do not touch the breaker.** `get_connection` (database.py:534-547) only calls `_shared_client()` and wraps it. `_storage_breaker` appears only at database.py:326 (definition), 1132/1145 (`_unit_of_work`) and 1266 (`storage_status`). `_shared_client` (:156) goes through `_proved` / `_invalidate_client` and no breaker call; the breaker calls `_probe_fresh_client`, not the reverse. No design conflict. Caveat: `_shared_client` may rebuild a stale client and take `_client_lock` (can stall), which is why the call runs on the executor under a deadline.
- **Bounded statement.** Lazily created `ThreadPoolExecutor(max_workers=1, thread_name_prefix="ready-probe")` + module-level in-flight `Future` guarded by a `threading.Lock`. Under one lock hold: if the previous future is not `done()` -> `database_unreachable`, no submit; else submit `lambda: get_connection().execute("SELECT 1").fetchone()` (as `check_database_reachable`, database.py:750-772). Release the lock, then `future.result(timeout=settings.READY_DB_TIMEOUT_SECONDS)`. Timeout -> `database_unreachable`, future left in flight (abandoned, still holding the slot). Exception -> `_classify_startup_failure(exc, _safe_endpoint(settings.DATABASE_URL))` (:720): `DatabaseAuthError` -> `database_auth`, else `database_unreachable`. One WARNING with the classified (already redacted) message; no token. Settings are read at call time so tests can monkeypatch.
- **Test-only reset** `_reset_ready_probe_for_tests()`: under the lock, `executor.shutdown(wait=False, cancel_futures=True)` if any; set executor and future to None.
- **Edges.** Done-check and submit share one lock hold, so two concurrent callers cannot both submit. A finished-with-exception old future counts as done. Reading `half_open` returns `breaker_open` (PRD §7 F1.2).
- **Not implemented here:** the rule `READY_DB_TIMEOUT_SECONDS < balancer health_timeout (3 s)` cannot be validated in settings; STORY-005's static test asserts the default against the Caddyfile.

## Skills In Use

None. `.agents/skills/` holds only `frontend-design`, unrelated; story `skills: []`.

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Settings field + validator | `app/config.py:429` (field), `:493-503` (`OPENROUTER_TIMEOUT_SECONDS`), `:590-601` (`AUDIT_BUFFER_DIR`) | `@field_validator` + `@classmethod`, one-line docstring citing PRD, message names the setting and the rule |
| Frozen dataclass / docstring | `app/services/circuit_breaker.py:62-78` (`BreakerStatus`), `database.py:1252-1264` | frozen, plain values, PRD/decision citations |
| Boot twin | `database.py:750-772` | `get_connection().execute("SELECT 1").fetchone()`; classify with `_safe_endpoint(settings.DATABASE_URL)` |
| Config tests | `tests/test_config.py:93-97` (`_settings()`), `:1496-1509` | `_settings(X=bad)` + `pytest.raises(ValidationError)`, assert the setting name in the message |
| Breaker tests | `tests/test_db_resilience_breaker.py:57-75` (`_new_breaker`, `breaker_clock`), `:131-147` | injected-clock breaker; `monkeypatch.setattr(database, "_shared_client", counting_stub)` |
| Isolation | `tests/conftest.py:657-700`, `:707` | non-`db` tests get a refusing `_shared_client` (so unit tests patch it themselves; that is the spy). `db` tests (by fixture closure on `database_url` / `temp_db`) get the real libSQL server. A fresh breaker per test |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/config.py` | UPDATE | `DRAIN_FILE`, `READY_DB_TIMEOUT_SECONDS` + two validators (after the `AUDIT_BUFFER_*` fields / `_validate_audit_buffer_dir`) |
| `app/db/database.py` | UPDATE | `ReadyCheck`, `READY_REASONS`, probe executor state, `check_ready()`, `_reset_ready_probe_for_tests()` (after `check_database_reachable`, :772) |
| `tests/test_config.py` | UPDATE | validator + default tests (new "PRD-019 STORY-001" section) |
| `tests/test_db_check_ready.py` | CREATE | `check_ready()` tests |

No `.env.example` / docs change (STORY-011); no test asserts that every Settings field appears in `.env.example` (only per-variable lists, test_config.py:64-71). No pre-existing test is renamed.

## Tasks

### Task 1: Settings
- **File**: `app/config.py`
- **Implement**: `DRAIN_FILE: str = "/tmp/harness-drain"` and `READY_DB_TIMEOUT_SECONDS: float = 2.0` with a PRD-019 §9.3 comment block. Validator 1: strip; empty -> error; accept iff `PurePosixPath(v).is_absolute() or PureWindowsPath(v).is_absolute()` (STORY-002 tests use Windows `tmp_path`; `C:foo` and `rel/x` are rejected). Message: "DRAIN_FILE must be a non-empty absolute path, got ...". Validator 2: `if not (0 < value <= 10)` (also rejects NaN) -> "READY_DB_TIMEOUT_SECONDS must be greater than 0 and at most 10, got {value}. ...". Import `PurePosixPath`, `PureWindowsPath` from `pathlib` if absent.
- **Mirror**: `app/config.py:493-503`, `:590-601`
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_config.py`

### Task 2: `check_ready()`
- **File**: `app/db/database.py`
- **Implement**: per Design Decisions. Add `from concurrent.futures import Future, ThreadPoolExecutor` and `TimeoutError as FutureTimeout` (imports at :1-25; no clash seen). Docstring cites PRD-019 D3/D5 and states: zero driver calls while not closed, never moves the breaker, never raises. Use the module's existing logger at WARNING with the classified exception's message; the stuck-slot path logs a short WARNING without driver text.
- **Mirror**: `database.py:750-772`, `:1252-1266`
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 3: Config tests (`tests/test_config.py`, append section)
- Defaults (`/tmp/harness-drain`, `2.0`). `DRAIN_FILE` rejects `""`, `"   "`, `"relative/x"`, `"C:rel"` with `DRAIN_FILE` in the message; accepts `/tmp/x`, a Windows `C:\tmp\x`-style path and a UNC path. `READY_DB_TIMEOUT_SECONDS` rejects `0`, `-1`, `10.01`, `nan`, `"abc"`; accepts `0.5` and `10`; message names the setting and the rule.
- **Mirror**: `tests/test_config.py:1496-1509`

### Task 4: `check_ready()` tests (`tests/test_db_check_ready.py`)
Helpers: a clock-injected breaker (copy the shape of test_db_resilience_breaker.py:57-75); an autouse fixture calling `database._reset_ready_probe_for_tests()` before and after; a stub client whose `execute(sql)` records calls and can raise or block on a `threading.Event`; a fixture that releases the Event in teardown (ordered so release runs before `_shared_client` is restored) and then resets the executor.
Non-`db` tests patch `database._shared_client` to return the stub:
1. `test_breaker_open_returns_breaker_open_with_zero_driver_calls`: `force_open(7.0)`; `reason == "breaker_open"`, `breaker == "open"`, `retry_after_seconds == 7`; `_shared_client` and `libsql.connect` spy counts 0; executor never created.
2. `test_half_open_is_breaker_open_with_retry_after_one`: force open, advance the clock to 10, confirm `status().state == "half_open"` through `.status()` only (`_half_open_ready`, test_db_resilience_breaker.py:265, may use `before()`, which runs the probe; do not copy it blindly); zero spy calls.
3. `test_retry_after_is_at_least_one`: fractional remaining -> `>= 1`.
4. `test_a_hundred_failing_calls_leave_consecutive_failures_unchanged`: stub raises `ValueError("boom")`; 2 failures pre-recorded via `record_failure`; 100 calls all `database_unreachable`; `consecutive_failures == 2`, state `closed`.
5. `test_a_successful_probe_with_the_breaker_open_keeps_it_open`: open breaker, succeeding stub -> `breaker_open`, still `open`, stub calls 0. Also closed with 3 failures + successful probe -> `consecutive_failures == 3` (no `record_success`).
6. `test_closed_breaker_and_success_is_ready`: `reason is None`, `breaker == "closed"`, `retry_after_seconds is None`, exactly one `SELECT 1`.
7. `test_deadline_returns_within_timeout_plus_half_a_second`: `READY_DB_TIMEOUT_SECONDS` = 0.2 via monkeypatch; stub blocks on the Event; elapsed `< 0.7`; `database_unreachable`.
8. `test_second_call_while_stuck_does_not_submit`: after 7, a second call returns `database_unreachable` quickly and the stub's `execute` count stays 1; after releasing the Event and the future finishing, a third call submits and returns ready (slot recovers).
9. `test_auth_text_is_classified_database_auth`: stub raises text containing `401 Unauthorized` -> `database_auth`; `ValueError("connection refused")` -> `database_unreachable`.
10. `test_it_never_raises`: a breaker whose `status()` raises, and a `_shared_client` raising `RuntimeError`; both return a `ReadyCheck` with `database_unreachable`.
11. `test_the_warning_never_carries_the_token`: `caplog`; error text containing `auth_token=<sentinel>`; exactly one WARNING, sentinel absent from `caplog.text`.
12. `test_ready_check_is_frozen_and_reasons_are_closed`: `FrozenInstanceError` on assignment; `READY_REASONS` equals the four strings; every returned reason is in it or None.
13. `db` test `test_happy_path_against_the_libsql_dev_server(temp_db)`: real `check_ready()` -> `ReadyCheck(None, "closed", None)`; breaker status unchanged (`consecutive_failures == 0`).
- A real blackholed-endpoint test is deliberately absent (the Event stub is deterministic); STORY-007/008 cover blackholing end to end.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_db_check_ready.py`

## End-to-End Tests

- [ ] Task 4 test 13 against the real libSQL dev server (`harness-libsql-dev`, :8080).
- [ ] No route exists yet (STORY-002 adds `/ready`), so no `TestClient` check; no `chat_ui/` change.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_db_check_ready.py tests/test_config.py tests/test_circuit_breaker.py tests/test_db_resilience_breaker.py tests/test_untouched_app.py
```
Full suite: GitHub CI on push. `tests/test_pii_redaction_integration.py` only if a test is renamed (none planned).

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 settings + validators | 1, 3 | new PRD-019 STORY-001 tests in `tests/test_config.py` |
| AC2 open/half_open -> breaker_open, retry >= 1, no driver call | 2, 4 | `test_breaker_open_returns_breaker_open_with_zero_driver_calls`, `test_half_open_is_breaker_open_with_retry_after_one`, `test_retry_after_is_at_least_one` |
| AC3 closed: one SELECT 1, classification, never raises, WARNING without token | 2, 4 | `test_closed_breaker_and_success_is_ready`, `test_auth_text_is_classified_database_auth`, `test_it_never_raises`, `test_the_warning_never_carries_the_token`, `test_happy_path_against_the_libsql_dev_server` |
| AC4 stuck probe: no second statement; within timeout + 0.5 s | 2, 4 | `test_deadline_returns_within_timeout_plus_half_a_second`, `test_second_call_while_stuck_does_not_submit` |
| AC5 breaker neutral | 2, 4 | `test_a_hundred_failing_calls_leave_consecutive_failures_unchanged`, `test_a_successful_probe_with_the_breaker_open_keeps_it_open` |

Plus: all tasks done, validation passes, follows existing patterns.

## Risks

- An abandoned thread on a stalled shared client keeps the slot busy until the driver returns: intended (§7 F1.3); say so in the docstring.
- Test thread leaks: release every blocking stub and reset the executor in teardown; confirm at implement time that conftest's thread guards do not flag `ready-probe`.
- Story AC1 says "POSIX path"; the binding design point (POSIX or Windows absolute) wins. Record the deviation in the report.
