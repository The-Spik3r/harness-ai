---
story: STORY-015
prd: PRD-022
slug: providers-status-and-stats
title: GET /providers/status and the /stats fallback figures
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-022-provider-fallback-and-native-adapters
created: 2026-11-20
---

# Plan: GET /providers/status and the /stats fallback figures

## Summary

Two read surfaces. (1) `GET /providers/status` renders `health.providers_status(names)` through new pydantic models, names taken from `provider_registry.current().providers`; no DB, no network. (2) `/stats` gains `fallback_answers`, `failed_attempts`, `answers_by_provider` as three more columns of the existing `_SUMMARY_SQL` statement, so `/stats` still does one `audit_logs` round trip.

- Story: `.agents/stories/PRD-022-provider-fallback-and-native-adapters/STORY-015-providers-status-and-stats.md`
- PRD sections used: 10 (`/providers/status`, `/stats`), F9 (PRD.md:366-372), D12, T10, User story 6, 6.10
- Systems affected: `app/routers/admin.py`, `app/models/schemas.py`, `app/db/database.py` (summary statement), tests that pin the 13-figure snapshot.

## Design Decisions

1. **Wire shape = PRD Section 10 verbatim** (PRD.md:449-459): `{instance, providers: {name: {breaker: {...}}}, counters: {attempts_failed, fallback_answers, skipped, breaker_opens}}`. Models go in `app/models/schemas.py` after `StorageStatusResponse` (:431-437): `ProviderStatusResponse(breaker: StorageBreakerResponse)`, `ProviderCountersResponse(attempts_failed: dict[str,int], fallback_answers: int, skipped: dict[str,int], breaker_opens: int)`, `ProvidersStatusResponse(instance, providers: dict[str, ProviderStatusResponse], counters)`.
2. **`StorageBreakerResponse` is reused**: its five fields (schemas.py:395-402) are exactly `BreakerStatus`'s (circuit_breaker.py:62-76). **Deviation to tell the orchestrator**: the PRD example shows `"since": null` for a closed breaker, but `BreakerStatus.since` is always a UTC string (set at construction, circuit_breaker.py:149) and `StorageBreakerResponse.since` is `str`. Do not change the breaker (PRD-018 contract). The body therefore carries a timestamp (breaker creation) for a never-opened provider; STORY-016 must treat `since` as a string, never null.
3. **Pure read.** Handler: `names = [p.name for p in provider_registry.current().providers]`; `status = health.providers_status(names)`; `ProvidersStatusResponse(**dataclasses.asdict(status))` (as admin.py:228; nested `BreakerStatus` and `ProviderCounters` are dataclasses, so `asdict` recurses). Plain `def` like `/storage/status`. Legacy mode: `current()` derives the implicit provider `openrouter` (provider_registry.py:570-613), so it is listed with a fresh closed breaker. No new import of `app.db`.
4. **T10.** The breaker only holds a `kind` word (health.py:161,169); response models have no message field. `last_failure_class` stays `Optional[str]` (same as storage), not a `Literal`, so a future kind cannot 500 the endpoint; the test pins the vocabulary instead (value in `UPSTREAM_ERROR_KINDS`).
5. **`/stats` columns, inside the one statement.** Append three columns after `blocked_usage_limits` in `_SUMMARY_SQL` (database.py:2380-2383), per the file's own rule that a `?` column goes last (comment :2276-2279):
   - `fallback_answers`: `COUNT(*) FROM audit_logs WHERE success = 1 AND attempt > 1`
   - `failed_attempts`: `COUNT(*) FROM audit_logs WHERE attempt IS NOT NULL AND success = 0`
   - `answers_by_provider`: `json_group_array(json_object('provider', provider, 'count', n))` over `SELECT provider, COUNT(*) AS n FROM audit_logs WHERE success = 1 AND provider IS NOT NULL GROUP BY provider ORDER BY n DESC, provider ASC LIMIT ?`.
   - **Provider column = `audit_logs.provider`** (the registry provider name written by PRD-020/022; database.py `_SUMMARY_SQL` row key `'provider'`, models.py:40). **Success rows only** ("answers"): failure/blocked/exhaustion rows also carry `provider` and must not count. Rows with NULL `attempt` (pre-PRD-022 rows, and the no-attempt exhaustion row) satisfy neither `attempt > 1` nor `attempt IS NOT NULL`, so they count in neither figure; pre-PRD-022 success rows with a PRD-020 `provider` still count in `answers_by_provider` (they were answers).
   - Positional bind tuple becomes `(row_limit, ranked_limit, ranked_limit, ranked_limit, ranked_limit)` (:2498; same N as the top lists = `ranked_limit`, default 5). Update the comment block :2272-2284.
   - Add to `SUMMARY_FIGURES` (:2142, appended last, so 16), `SummarySnapshot` properties (:2197-2247), `_SUMMARY_DECODERS` (:2402; counts use `_decode_count`; `answers_by_provider` a new `_decode_provider_counts` returning `list[dict]`), and the figure-by-figure fallback list (:2437-2451). Standalone reads for the fallback are **private** (`_count_fallback_answers`, `_count_failed_attempts`, `_top_answering_providers(limit)`), each via `_unit_of_work(..., StatementKind.READ, _op)` with the same predicates (share the WHERE strings as module constants like `_BLOCKED_USAGE_LIMITS_WHERE` :2098). Private keeps the census at 42 (test_db_resilience_retry.py:725). If the implementer prefers public ones, register them in `_EXPECTED_KINDS` (:629+) and bump :725.
   - Router: `StatsResponse` (schemas.py:440-459) gains `fallback_answers: int = 0`, `failed_attempts: int = 0`, `answers_by_provider: List[ProviderAnswerCount] = []` (`ProviderAnswerCount(provider: str, count: int)`); `get_stats` (admin.py:287-306) passes the three from `snapshot`. No second statement; `count_action_decisions()` stays the one other query.
6. **RBAC.** `dependencies=[Depends(require_permission(PERMISSION_STATS_READ))]` exactly as admin.py:217-221; 403 body `{"detail": "Permission denied: stats:read"}`.
7. **Console blast radius**: `chat_ui/chat_ui/admin_state.py` `_READS` (:382-422) stays at 13 (the console panel for providers is STORY-016); `load()` ignores extra figures. Do not touch `chat_ui/`.

## Skills In Use

None apply (`.agents/skills/` holds only `frontend-design`; no UI here).

## Patterns to Follow

| Category | Source | What to mirror |
|----------|--------|----------------|
| Endpoint | `app/routers/admin.py:217-228` | decorator, `require_permission`, `dataclasses.asdict` |
| Models | `app/models/schemas.py:395-437` | docstring citing PRD section, `dict[str, int]` counters |
| One-statement figure | `app/db/database.py:2380-2383`, `:2098` | scalar subquery + shared WHERE constant + decoder + fallback read |
| Endpoint tests | `tests/test_storage_status.py:138-203` | `_forbid_driver`, `_ADMIN` header, key-set asserts, 401 |
| 403 test | `tests/test_stats_router.py:255-265` | user lacking `stats:read` -> exact detail |
| Health tests | `tests/test_provider_health.py:20-56` | `now` fixture, `_err`, `_fail`; conftest autouse already resets health per test |
| Stats oracle | `tests/test_audit_stats_prd013.py:125-137,323-345` | batched == fallback == oracle |

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `app/models/schemas.py` | UPDATE | provider status models; `StatsResponse` fields |
| `app/routers/admin.py` | UPDATE | `GET /providers/status`; `/stats` passes three figures |
| `app/db/database.py` | UPDATE | three columns, figures, decoders, private fallback reads, bind tuple |
| `tests/test_providers_status.py` | CREATE | endpoint tests (below) |
| `tests/test_stats_router.py` | UPDATE | `_snapshot_of` gets 3 figures; new `/stats` test |
| `tests/test_audit_stats_prd013.py` | UPDATE | `:323` len 13 -> 16 and `[-3:]` -> `[10:13]`; `:414` compare `SUMMARY_FIGURES[:13]`; oracle gets 3 figures |
| `tests/test_db.py`, `tests/test_admin_state.py`, `tests/test_actions_view.py`, `tests/test_storage_view.py`, `tests/test_usage_view.py` | UPDATE (only where they build a `SummarySnapshot` or assert `== SUMMARY_FIGURES`/`len == 13`) | extend fake snapshots with the 3 figures (`test_admin_state.py:574,875`, `test_storage_view.py:162`, `test_usage_view.py:448`); `test_actions_view.py:587` compare with `SUMMARY_FIGURES[:13]`; each edit gets a `# PRD-022 STORY-015: ...` comment. Grep first: `grep -rn "SummarySnapshot(\|SUMMARY_FIGURES" tests` |

These edits are forced by the "inside the existing snapshot" decision (the partition assert at database.py:2184-2190 demands every figure). They only extend fixtures; no assertion is weakened.

## Tasks

### Task 1: Response models
- **File**: `app/models/schemas.py`. **Action**: UPDATE. Add the models in Decision 1 and the `StatsResponse` fields (Decision 5).
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Summary statement and snapshot
- **File**: `app/db/database.py`. **Action**: UPDATE. Decision 5 (SQL columns, bind tuple + comment, `SUMMARY_FIGURES`, properties, decoders, private reads, fallback list). Keep `"rows"` first and the existing 4 `?` order; the new `?` is last.
- **Mirror**: `database.py:2121-2128` (`count_blocked_usage_limits`) for the private reads.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_audit_stats_prd013.py`

### Task 3: Router
- **File**: `app/routers/admin.py`. **Action**: UPDATE. Add `get_providers_status` after `/storage/status`; imports `dataclasses` (present), `provider_registry`, `health` (`from app.services.upstream import health`, as test_provider_health.py:14), the three schemas. Extend `get_stats`.
- **Mirror**: `admin.py:217-228`.

### Task 4: Fix the pinned tests (Files table), then create `tests/test_providers_status.py`
Tests (admin token header from `test_storage_status.py:172`):
- `test_the_full_body_is_pinned`: patch `circuit_breaker._wall_clock` to a fixed datetime and `health.socket.gethostname`/`os.getpid` (or compare `instance` to `health.providers_status([]).instance`); load a two-provider registry with `tests/_providers.py` (`provider_file`); fail one provider 5x with `timeout` and record some counters; assert `response.json() == {...}` for the whole body (PRD 10 shape, nested keys included).
- `test_status_makes_no_database_or_network_call`: monkeypatch `database._unit_of_work`, `database.get_connection`/`_session` and `httpx.Client.send`/`socket.create_connection` to raise (mirror `_forbid_driver`, test_storage_status.py:138); 200 anyway; also with the storage breaker open.
- `test_legacy_deployment_lists_the_legacy_provider_closed`: `PROVIDERS_FILE=""`, reload; body `providers` keys == `{"openrouter"}`, `state == "closed"`, `consecutive_failures == 0`, `retry_after_seconds is None`.
- `test_a_401_force_open_reports_misconfigured_and_leaks_no_text` (T10): `health.record("anthropic-direct", UpstreamError("CANARY-sk-leak-123", kind="misconfigured", upstream_status=401))`; `last_failure_class == "misconfigured"`, `state == "open"`, `290 <= retry_after_seconds <= 300`; `"CANARY" not in response.text`; also no `message`/`detail` keys inside any breaker.
- `test_a_pruned_provider_is_not_listed`: a name removed from the registry disappears (health `sync` inside `providers_status`).
- `test_status_requires_stats_read`: no token 401; user without `stats:read` -> 403 `{"detail": "Permission denied: stats:read"}` (compare with `/storage/status` for the same identity, as test_stats_router.py:255).
- `/stats` tests (in `tests/test_stats_router.py`, `temp_db`): seed rows: success attempt 1 (provider A), success attempt 2 (provider B, fallback), failure attempt 1 (B, success 0), failure attempt 2, a NULL-attempt success (pre-PRD-022, provider A), a NULL-attempt exhaustion failure; assert `fallback_answers == 1`, `failed_attempts == 2`, `answers_by_provider == [{"provider":"A","count":2},{"provider":"B","count":1}]` (failure rows excluded; NULL-attempt rows in neither count figure), more than 5 providers -> truncated to 5; empty table -> `0, 0, []`. Plus the existing one-statement guard (`test_stats_issues_one_database_round_trip_for_its_figures`, :360) must still pass with no change in the `audit_logs` statement count.
- In `test_audit_stats_prd013.py`: extend the batched-vs-fallback-vs-oracle agreement to the three new figures (non-trivial seed).

## End-to-End Tests

- [ ] `TestClient(app)` GET `/providers/status` with the admin token -> 200, the pinned full body; `/stats` -> 200 with the three new keys.
- [ ] A 401 force-open then GET shows `misconfigured` and ~300 s, canary absent.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
# one pytest call; local libSQL is ~3 s per DB test, so keep it narrow
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_providers_status.py tests/test_stats_router.py tests/test_audit_stats_prd013.py tests/test_provider_health.py tests/test_storage_status.py tests/test_actions_view.py tests/test_admin_state.py tests/test_storage_view.py tests/test_usage_view.py tests/test_untouched_app.py
# plus, narrow: the summary and census tests in the big files
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_db.py -k "summary or snapshot" tests/test_db_resilience_retry.py -k "public or kind or census or session"
```
(Run the two `-k` selections as separate pytest calls if `-k` applies to both; never concurrently.) `tests/test_pii_redaction_integration.py` only if a test is renamed.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|----|---------|---------------------|
| AC1 shape, no I/O, 403 | 1, 3, 4 | `test_providers_status.py::test_the_full_body_is_pinned`, `::test_status_makes_no_database_or_network_call`, `::test_status_requires_stats_read` |
| AC2 401 -> misconfigured ~300, no text | 3, 4 | `::test_a_401_force_open_reports_misconfigured_and_leaks_no_text` |
| AC3 `/stats` figures in one snapshot | 1, 2, 3, 4 | `test_stats_router.py` new figures test + `test_audit_stats_prd013.py` agreement test + existing one-round-trip test |
| AC4 legacy provider closed | 3, 4 | `::test_legacy_deployment_lists_the_legacy_provider_closed` |

## Risks

- **PRD example `since: null` vs real `since: str`** (Decision 2): follow the code; orchestrator to confirm, STORY-016 to be told.
- Widening `SUMMARY_FIGURES` to 16 touches fixtures in ~6 test files (pre-PRD-022 tests, extended not weakened). Grep first, then run only those files.
- The bind tuple is positional; a column inserted before the last silently shifts `LIMIT`s. The new column must be last.
- `/stats` `answers_by_provider` ties break on provider name for determinism.
