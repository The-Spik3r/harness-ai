---
story: STORY-010
prd: PRD-022
slug: provider-breakers-health
title: health.py — one CircuitBreaker per provider, fault recording rules, providers_status()
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: Provider breakers and providers_status()

## Summary

New `app/services/upstream/health.py`: a process-local registry of one `CircuitBreaker` per provider (`probe=None`), the recording rules of PRD-022 6.2/F6 (`record`), a mapped admit/deny (`admit`), process-local counters and `providers_status()`. It reuses `CircuitBreaker` (no second state machine) and gets two tiny backward-compatible additions to `circuit_breaker.py` (see Design Decisions). No wiring into the pipeline (STORY-011/012 call it; STORY-015 reads `providers_status()`).

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-010-provider-breakers-health.md`
- PRD sections used: 6.10, 6.2, F6, F9, D12, 9.3, User story 6
- Systems affected: `app/services/upstream/` (new module), `app/services/circuit_breaker.py` (additive), `tests/conftest.py` (autouse reset)

## Design Decisions (binding points kept; choices stated)

- **Purity.** `health.py` imports only stdlib + `circuit_breaker` + `upstream.types` (`UpstreamError`); no `settings`, no I/O. `provider_registry.current()` reads settings in legacy mode (`provider_registry.py:661-674`), so health must not call it. **Pruning therefore takes the names as an argument**: `sync(names)` drops every entry whose name is not in `names` (under `_lock`); `providers_status(names)` calls `sync(names)` first. STORY-011/012 call `health.sync({p.name for p in registry.providers})` once per request (O(providers)), so a provider that vanishes from the snapshot loses its breaker at the next request or status read. Deviation from "compares against the registry's current names": the caller supplies them (orchestrator: confirm).
- **State and locks.** `_entries: dict[str, _Entry]` plus counters, all under one module `threading.Lock` `_lock`, held only for dict/counter reads and writes and **never across a breaker call** (a breaker takes its own lock; its `on_transition` hook runs after that lock is released, `circuit_breaker.py:165-179`, and then takes `_lock`). No nesting, so no deadlock. `_Entry = (breaker, record_lock)`; `breaker(name)` returns the `CircuitBreaker` (lazy create under `_lock`, identity-stable). Clock: module var `_clock = time.monotonic`; breakers get `clock=lambda: _clock()` so `reset(clock=fake)` reaches them. `reset(clock=None)` clears entries and counters and restores the clock (tests).
- **Constants.** `_BREAKER_FAILURE_THRESHOLD = 5`, `_BREAKER_OPEN_SECONDS = 10.0`, `_PROVIDER_MISCONFIGURED_OPEN_SECONDS = 300` (comments as `database.py:145-155`). Constructor arg is `failure_threshold`, not `threshold` (`circuit_breaker.py:110`).
- **`record(name, outcome: Optional[UpstreamError])`**, `None` = success. Runs under the entry's `record_lock`:
  - `None` -> `record_success()`.
  - not `fallback_eligible` (4xx status, `shape`, `incompatible`, `refusal`) -> breaker untouched (still counted in `attempts_failed`).
  - eligible, `kind != "misconfigured"` -> `record_failure(kind)`; if `kind == "status"`, `retry_after_seconds` is set and `status().state == "open"` -> `_extend(max(retry_after, 10))`.
  - `misconfigured` -> `record_failure(kind)` then `_extend(300)`.
  - `_extend(s)`: `st = status()`; if `st.state != "open"` or `s > st.retry_after_seconds` -> `force_open(s, failure_class=kind)`, else no-op. Never shortens: a 300 s window survives a later 429. `retry_after_seconds` is a whole-second ceil, so a sub-second extension may be skipped: acceptable.
  - Eligible with `kind None` (bare retryable 5xx) counts with class `"unclassified"`. The class is always a `kind` or that word, never message text (T10).
- **Race record_failure / force_open.** The two calls are separately atomic. `record_lock` makes read-status-then-force_open one critical section against other `record()` calls, so two concurrent extends cannot interleave a stale read into a shortening. The residual race is with `admit()`/`before()` only (window elapses or a trial is claimed between the calls): worst case `force_open` re-opens a just-half-open breaker, which is the intended outcome of a 401/429 and matches the probe case already tested (`tests/test_circuit_breaker.py:162`). `record_lock` is held across breaker calls and log emission; nothing else takes it and `_lock` is never held while waiting for it.
- **`admit(name) -> Admission`**, frozen dataclass `(admitted: bool, reason: Optional[str], retry_after_seconds: Optional[int])`; `reason` is `"open"` or `"half_open_busy"` (already PRD skip words). Built on `breaker.before()` + `BreakerOpen`; no state machine copied. The first caller after the window is the trial (`:195-199`) and **must report through `record()`**; a trial that reports nothing is replaced after `open_seconds` (`:204-210`). STORY-011 should call `admit` last among the per-candidate checks so a claimed trial is always followed by an attempt.
- **`BreakerOpen` cannot say which refusal it is**: open (`:194`) and half-open (`:211`) both raise, both may carry retry_after 1; peeking `status()` afterwards is racy. Additive fix: `BreakerOpen(name, retry_after, state="open")`; the half-open site passes `"half_open"`; `admit` maps `exc.state`.
- **Counters** (like `storage_counters.py:25-60`; process-lifetime and monotonic; **not pruned with the breaker**, only `reset()` clears; cardinality bounded by closed vocabularies): `attempts_failed["provider:kind"]` (incremented inside `record()` for every failed attempt, incl. non-eligible; `kind None` -> `unclassified`), `skipped["provider:reason"]` via `count_skipped(provider, reason)` (reason validated against `SKIP_REASONS = (open, half_open_busy, forbidden, capability, byok, redaction_limit, deadline)`, PRD 6.7, else `ValueError`), `fallback_answers` via `count_fallback_answer()`. **`breaker_opens` is counted by the breaker's own `on_transition` hook** (storage's way, `database.py:311-314`), `to == "open"` only: it catches closed->open, a failed trial's half_open->open and force-open from closed, with no detection logic in `record`. Extending an already-open window is not a transition and is not counted. STORY-011/012 call `count_skipped` for every skip (admit denials included) and `count_fallback_answer` once per answer with `attempt > 1`; `admit` itself counts nothing.
- **`providers_status(names) -> ProvidersStatus`** (STORY-015 contract, keep stable): `ProvidersStatus(instance: str, providers: Mapping[str, BreakerStatus], counters: ProviderCounters)`; `instance = f"{socket.gethostname()}:{os.getpid()}"` (same as `storage_status`, `database.py:1341+`, a local syscall); `providers` has one entry per name in `names`, in order (breaker created lazily so an untouched provider shows `closed`); `ProviderCounters(attempts_failed: dict[str,int], fallback_answers: int, skipped: dict[str,int], breaker_opens: int)` are copies. `BreakerStatus` is PRD-018's (`circuit_breaker.py:61-75`), `last_failure_class` = the `kind`. No DB, no network.
- **Transition log (checked).** The breaker logs `breaker name=<n> from=<s> to=<s> class=<c>` after releasing its lock (`:165-174`), WARNING for `to == "open"`, INFO otherwise; it never sees message text. Two gaps vs the AC: (1) recoveries (`half_open`, `closed`) are INFO, not WARNING. **Orchestrator decision (binding):** the PRD (F9 AC, §10) requires one WARNING per transition, so add an additive constructor keyword `transition_log_level: Optional[int] = None` to `CircuitBreaker` (None keeps today's WARNING-for-open / INFO-otherwise, so storage and PRD-018 tests are unchanged); health passes `logging.WARNING`, making every provider transition exactly one WARNING line. (2) `force_open` from closed logs `class=forced` (`:288`, asserted by `tests/test_circuit_breaker.py:274-277`), so a 401 would log `forced`, not `misconfigured`. Minimal fix: `force_open(seconds, failure_class="forced")` (default keeps the old line and the test); health passes the kind. A 429 that opens through `record_failure` already logs `class=status`; the later extension is not a transition and logs nothing, so exactly one line per transition.

## Skills In Use

None (`.agents/skills/` only has `frontend-design`; no UI here).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Counters | `app/db/storage_counters.py:25-60` | module lock, frozen snapshot dataclass, `_reset()`, closed-vocab keys |
| Status | `app/db/database.py:1341-1400` | `instance` string, no I/O, frozen dataclass |
| Breaker hook | `app/db/database.py:311-324` | `on_transition` counter hook, factory |
| Constants | `app/db/database.py:145-155` | constant comments citing PRD decisions |
| Module state | `app/services/upstream/chain_config.py:308-362` | `reset()` reads no setting |
| Autouse reset | `tests/conftest.py:706-740` | fixture restoring module state around each test |
| Breaker tests | `tests/test_circuit_breaker.py:24-47,352-370` | `now` list clock, barrier race helper, caplog capture |
| Purity test | `tests/test_circuit_breaker.py:416-428` | AST allow-list of imports |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/services/upstream/health.py` | CREATE | everything above |
| `app/services/circuit_breaker.py` | UPDATE | `BreakerOpen.state` (default `"open"`), `force_open(seconds, failure_class="forced")` |
| `tests/test_provider_health.py` | CREATE | story tests |
| `tests/test_circuit_breaker.py` | UPDATE (add only) | tests for the two additions; no existing assertion changes |
| `tests/conftest.py` | UPDATE | autouse `_fresh_provider_health`: `health.reset()` before and after each test |

## Tasks

### Task 1: additive `CircuitBreaker` changes
- **File**: `app/services/circuit_breaker.py`; **Mirror**: `:78-86`, `:211`, `:281-292`
- **Implement**: `BreakerOpen.__init__(name, retry_after_seconds, state="open")` stores `.state`; `:211` raises with `"half_open"`; `force_open(seconds, failure_class="forced")` passes it to `_open`; constructor keyword `transition_log_level: Optional[int] = None` used by `_emit` when set (orchestrator decision). Docstring touch only where the log class is described.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_circuit_breaker.py tests/test_db_resilience_breaker.py`

### Task 2: `health.py`
- **File**: `app/services/upstream/health.py` (CREATE); module docstring cites PRD-022 6.10, F6, F9, D12 and states the purity and lock rules.
- **Implement**: constants, `SKIP_REASONS`, `_Entry`, `_clock`/`reset`/`sync`/`breaker`, breaker factory with `on_transition=_count_open`, `Admission`/`admit`, `record`/`_extend`, `count_skipped`/`count_fallback_answer`, `ProviderCounters`/`ProvidersStatus`/`providers_status`.
- **Mirror**: patterns table. **Validate**: Task 3 tests.

### Task 3: tests (injected clock `now=[0.0]`, no real sleeps)
- **Files**: `tests/test_provider_health.py` (new), conftest fixture, two additions to `tests/test_circuit_breaker.py`.
- `breaker()`: constants; identity; 16 threads at a barrier get one object; `sync` drops absent names and keeps others; a re-added name gets a fresh closed breaker.
- `record` table: success resets; timeout/transport/5xx/unclassified count and open at the 5th for 10 s; 4xx, shape, incompatible, refusal change nothing (also from half-open); misconfigured opens at once for 300 with `last_failure_class == "misconfigured"` and log `class=misconfigured`; 429 retry 30 opens at the 5th for 30, retry 3 -> 10, no retry_after -> 10, below threshold no force; misconfigured then 429 keeps 300; 429(30) then misconfigured extends to 300; half-open trial 429 reopens for `max(retry,10)`. Two threads recording misconfigured and a 429 on an open breaker, 200 iterations: final window always 300.
- `admit`: closed admits; open -> `("open", n)` (ceil); at the window the first caller is the trial and the second gets `half_open_busy`; two threads at a barrier: exactly one admitted; trial success closes, failure reopens; a silent trial is replaced after `open_seconds`.
- `providers_status`: shape and types (instance equals the `storage_status` expression), only the requested names, others pruned; no network/DB (monkeypatch `socket.socket.connect` and `database.get_connection` to raise); counters (attempts_failed keys, skipped validation, fallback_answers, `breaker_opens` for closed->open, failed trial, force-open; not for extension or close); `reset()` zeros all.
- Logs: caplog shows WARNING for opens with provider, from, to, kind; `UpstreamError("SECRET text")` appears in no log line and no status value; recoveries (half_open, closed) are WARNING too (orchestrator decision); plus a `test_circuit_breaker.py` test that `transition_log_level` overrides and that the default is unchanged.
- Purity: AST import allow-list (`logging, math, os, socket, threading, time, dataclasses, typing`, `app.services.circuit_breaker`, `app.services.upstream.types`), no `settings`/`open`/`httpx`/`database` names; works with `app.config.settings` unreachable.
- Additions to `test_circuit_breaker.py`: half-open refusal `.state == "half_open"`, open refusal `"open"`; `force_open(5, failure_class="x")` logs `class=x`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_provider_health.py tests/test_circuit_breaker.py`

## End-to-End Tests

- [ ] Fake-clock flow: 5 x `record(p, UpstreamError(..., kind="timeout", retryable=True))` -> `admit` denies `("open", 10)` -> clock +10 -> one trial admitted, a second thread gets `half_open_busy` -> `record(p, None)` -> closed.
- [ ] `from app.main import app` still imports (nothing wired).

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_provider_health.py tests/test_circuit_breaker.py tests/test_db_resilience_breaker.py tests/test_upstream_error_fields.py tests/test_untouched_app.py
```
No test is renamed or removed (no `test_pii_redaction_integration.py`); no `database.py` change (no census guard).

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 lazy, thread-safe, constants, pruning | 2, 3 | `test_provider_health.py::test_breaker_*`, `::test_sync_prunes_absent_providers` |
| AC2 recording rules | 2, 3 | `::test_record_*`, `::test_a_300s_window_survives_a_429`, `::test_concurrent_extends_never_shorten` |
| AC3 admit incl. two threads | 1, 2, 3 | `::test_admit_*`, `test_circuit_breaker.py::test_half_open_refusal_carries_its_state` |
| AC4 `providers_status()` shape, counters, no I/O | 2, 3 | `::test_providers_status_*`, `::test_counters_*` |
| AC5 transition log | 1, 3 | `::test_transition_log_names_kind_never_text`, `test_circuit_breaker.py::test_force_open_names_the_failure_class` |

## Risks / open questions
- Caller supplies registry names (purity); every provider transition WARNING via `transition_log_level` (decided); two additive `circuit_breaker.py` edits: orchestrator to confirm.
- A trial admitted and then never attempted, or ended by a non-eligible fault, blocks the provider until the lease (`open_seconds`) expires: STORY-011 calls `admit` last and always `record`s.
- Later stories wiring health into pipeline fixtures need nothing more than the conftest autouse reset.
