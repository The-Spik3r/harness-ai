---
story: STORY-011
prd: PRD-007
plan: .agents/plans/PRD-007-turso-migration/completed/STORY-011-stats-endpoint-batched.plan.md
epic_branch: epic/PRD-007-turso-migration
commit: 94fdf4a
status: COMPLETE
completed: 2026-09-02
---

# Implementation Report — STORY-011: GET /stats consumes the batched read instead of nine sequential calls

**Plan**: `.agents/plans/PRD-007-turso-migration/completed/STORY-011-stats-endpoint-batched.plan.md`
**Epic Branch**: `epic/PRD-007-turso-migration`
**Commit**: `94fdf4a`

## Summary

`get_stats()` fills the same `StatsResponse` from one `summary_snapshot(row_limit=0)` where it made nine sequential database calls. Nothing else about the endpoint moved: the response schema, its field order, the success-rate formula, the empty-database path and the `stats:read` gate are all unchanged, and `get_audit` — which shares the file and reads similarly — was not touched. Seven imports left `app/routers/admin.py`; `count_audit_logs` and `list_audit_logs` stayed, because `get_audit`'s scoped reads still use them.

This is the last of PRD-007 Phase 3 and the second half of Section 6 Pattern 3: STORY-012 adopted the batched read in the admin console, this story adopts it in the endpoint, and the two callers the PRD named as the fan-out sites are now both on one round trip.

## The two questions the story asked by name

### 1. Can a caller skip a figure it does not want?

**No — but it can empty one, and that is what matters here.** The endpoint needs nine of the ten figures; `rows` (the register's audit rows) has no field in `StatsResponse`.

`_SUMMARY_SQL` is a fixed ten-column `SELECT`. There is no per-figure projection and adding one would reopen STORY-010's design — the column names are what carry Risk 6's attribution, so the ten columns are the mechanism, not an accident. What *is* available is the rows subquery's trailing `LIMIT ?`, bound to `row_limit`. Passing `0` empties it.

Measured against the live endpoint before the code was written, on a six-row table:

| Question | Answer |
|---|---|
| Where does `rows` land with `row_limit=0`? | `figures["rows"] == []` — `json_group_array` over zero rows returns `'[]'`, not `NULL`, so the decode succeeds and nothing lands in `errors` |
| Do the other nine figures change? | No. All nine identical to `summary_snapshot()`'s unlimited call, figure for figure |
| Is it still one round trip? | Yes — 1 statement |
| Empty database? | `errors == {}`, `rows == []`, `total_recorded == 0` |

So `row_limit=0` is the answer, and it is not merely tidiness. Left at the default 100, `/stats` would pull up to 100 fully serialized audit rows — nineteen fields each, two of them preview strings — across the network on every call, with nothing reading them. That is exactly the transfer cost Section 6 Pattern 4 exists to remove, reintroduced by a different door.

The absence of `ranked_limit` is deliberate and is now pinned by a test. Until this story the three `top_*` figures were read through each function's own default of 5, which is also `summary_snapshot()`'s default. Passing nothing keeps the two defaults tracking each other exactly as before; hard-coding a 5 here would silently freeze one of them.

### 2. The measured round-trip count

PRD Section 12 Phase 3 asks for counts, not prose.

| Path | Statements against `audit_logs` | `/stats` wall clock (7-row table, best of 6, live HTTP) |
|---|---|---|
| `get_stats()` after this story | **1** | 11.0 ms |
| The nine figures read the old way | **9** | 19.1 ms |

Both counts come from the same instrument in the same test — `tests/test_stats_router.py::test_stats_issues_one_database_round_trip_for_its_figures` wraps the connection in a recording proxy, counts the endpoint's statements, then counts the nine standalone calls under the same proxy. The contrast is measured, not assumed.

**Only statements touching `audit_logs` are counted, and that is not a convenience.** A `/stats` request has never been one statement end to end: `require_permission` → `require_identity` resolves the bearer token against the `users` table first, and it did so before this story too. Counting everything would pin an unrelated auth read into a performance assertion. What this story changed is the endpoint's *figure* reads, and that is what the count is scoped to.

The timing is context rather than the claim, and it understates the real gain: both servers talked to a libSQL container on the same host, where a round trip is nearly free. The eight round trips removed are worth far more against a remote Turso endpoint — which is the entire premise of PRD-007.

## What the batched read did *not* cost here

No error handling was added, because none was replaced. `SummarySnapshot`'s named properties re-raise the exception recorded against a figure (`app/db/database.py:823-828`), so a broken read still raises out of `get_stats()` and still becomes a 500, in the same place, as it did with nine direct calls. The `errors` partition exists for the caller that wants per-figure attribution — the admin console, STORY-012 — and `/stats` deliberately never inspects it. `/stats` wants the value or nothing; that is what the properties give it.

The function also stayed a plain `def`. FastAPI dispatches it to a threadpool and `summary_snapshot()` blocks; as `async def` that blocking call would sit on the event loop, which would be worse than the nine reads it replaces.

## Tasks Completed

| # | Task | File | Status |
|---|------|------|--------|
| 1 | Verify `row_limit=0` empties `rows` and leaves the other nine alone | — | ✅ |
| 2 | `get_stats()` reads one snapshot; seven imports removed | `app/routers/admin.py` | ✅ |
| 3 | `_guard_all_aggregates` retargeted onto `summary_snapshot` | `tests/test_stats_router.py` | ✅ |
| 4 | Round-trip count pinned (1, against 9 the old way) | `tests/test_stats_router.py` | ✅ |
| 5 | `row_limit=0` and the absent `ranked_limit` pinned | `tests/test_stats_router.py` | ✅ |
| 6 | Full validation + untouched-callers proof | — | ✅ |
| 7 | This report | `.agents/reports/…` | ✅ |

## Validation Results

| Check | Result |
|-------|--------|
| `tests/test_stats_router.py` | ✅ 9 passed (7 pre-existing, assertions unchanged, + 2 new) |
| `tests/test_admin_auth.py`, `tests/test_main.py` | ✅ 28 passed (with the stats suite) |
| `tests/test_db.py` | ✅ 97 passed — `summary_snapshot()` itself untouched |
| `tests/test_audit_router.py` | ✅ 10 passed — AC 7, `GET /audit` unaffected |
| Backend import (`from app.main import app`) | ✅ |
| E2E | ✅ 9/9 (below) |
| Diff confined to two source files | ✅ `app/routers/admin.py`, `tests/test_stats_router.py` |
| `get_audit` untouched | ✅ the router diff is exactly two hunks — the import block and `get_stats` |

### Negative controls

A test that cannot fail proves nothing, so both new tests were made to fail on purpose:

- Changing `summary_snapshot(row_limit=0)` to `summary_snapshot()` → `test_stats_does_not_fetch_the_register_rows` **FAILED**, the other 8 passed. Restored and re-verified.
- The round-trip test carries its own positive control: the same proxy that counts 1 for the endpoint counts 9 for the nine standalone calls in the same test body, so an instrument that had silently stopped recording would fail the second assertion.

### End-to-End Verification

Real `uvicorn` servers over HTTP, not `TestClient`. Two of them: the working tree on `:8001`, and a git worktree of the epic tip **before this story** (`3124a16`) on `:8002` — the nine-sequential-read version — both pointed at the same seeded libSQL database, so byte-identity is a comparison of two live servers rather than of a recorded fixture.

| # | Check | Result |
|---|---|---|
| 1 | Both servers boot | ✅ `/health` 200 on both |
| 2 | `/stats` with no token | ✅ 401 |
| 3 | `/stats` with a wrong token | ✅ 401 |
| 4 | `/stats` seeded, new vs pre-change | ✅ **byte-identical** |
| 5 | `/stats` on an empty database | ✅ byte-identical, `success_rate == "0.0%"`, no division by zero |
| 6 | `/stats` as `auditor` | ✅ 200, same shape and values |
| 7 | `/stats` as a `user` lacking `stats:read` | ✅ 403 `{"detail":"Permission denied: stats:read"}` |
| 8 | `/audit` as admin (`audit:read:all`), new vs pre-change | ✅ byte-identical (2077 bytes) |
| 9 | `/audit` as auditor (scoped), new vs pre-change | ✅ byte-identical |

The seeded body, identical from both servers:

```json
{"total_queries":7,"blocked_duplicates":1,"blocked_suspicious":1,"unique_users":3,"success_rate":"57.1%","top_models":["gpt-4","claude"],"top_users":["a","c","b"],"pii_detected_queries":2,"top_pii_entities":["EMAIL_ADDRESS","PERSON"]}
```

## Files Changed

| File | Action | Lines |
|------|--------|-------|
| `app/routers/admin.py` | UPDATE | +44/-17 |
| `tests/test_stats_router.py` | UPDATE | +189/-11 |

## Deviations from Plan

| Deviation | Why |
|---|---|
| E2E 4's baseline is the epic tip (`3124a16`), not `main` | The AC says "compared to `main`'s output for the same data", but `main`'s `app/db/database.py` still uses stdlib `sqlite3` against a file path — it cannot read the libSQL database at all, so it cannot produce output for the *same data*. The epic tip is the honest baseline: the same storage layer, the same rows, nine sequential reads instead of one. This is the same correction STORY-010's report made about `git diff main` on an accumulating epic branch. |
| The E2E servers ran with `PII_REDACTION_ENABLED=false` | Startup otherwise downloads a 400 MB spaCy model per container. It changes nothing under test: `/stats`' two PII figures are counted from stored `audit_logs` columns, and the flag only governs redaction on `POST /query`. Both servers ran with it set, so the byte comparison is unaffected either way. |
| `_guard_all_aggregates` was edited | Unavoidable and anticipated by the plan. It patched seven names on `app.routers.admin` that no longer exist, and `monkeypatch.setattr` raises `AttributeError` on a missing attribute — the two auth tests would have failed for a reason unrelated to what they assert. Only the helper's target changed; every assertion in the file is byte-identical. See below. |
| The pre-existing `STREAM_EXPIRED` fault appeared during E2E | Both servers 500'd on their first request after idling through the model download — the known Hrana idle-expiry issue recorded in `index.md`, present since STORY-006 and owned by no story. It hit the baseline server identically, so it is not this story's. Restarting the servers immediately before the checks cleared it. |
| Docker Desktop's daemon stopped mid-run and was restarted | Environmental. No effect on results; every suite and every E2E check above was run after it came back. |

## On AC 6's "assertions unchanged"

The AC asks that `tests/test_stats_router.py` pass with its assertions unchanged. It does — all seven pre-existing tests keep every assertion byte for byte. One **helper** changed: `_guard_all_aggregates` now patches the single name `app.routers.admin.summary_snapshot` instead of seven names the router no longer imports.

Worth recording that the replacement is the *stricter* guard, not a weakened one. The old list named seven functions but the endpoint read nine figures — `count_pii_detected_queries` and `top_pii_entities` were never guarded, so two reads could have run behind a refused gate without failing the test. All ten figures now sit behind the one name.

## Tests Written

| Test File | Test Cases |
|-----------|------------|
| `tests/test_stats_router.py` | `test_stats_issues_one_database_round_trip_for_its_figures`, `test_stats_does_not_fetch_the_register_rows` |

Supporting helpers added alongside them: `_count_audit_log_statements` (the recording-connection proxy, mirroring `tests/test_db.py::_count_statements`), `_seed_four_rows`, and `_snapshot_of` (a complete ten-figure `SummarySnapshot`, which `__post_init__` refuses unless `figures` and `errors` partition `SUMMARY_FIGURES` exactly).

## Acceptance Criteria

- [x] `GET /stats` issues **one** database round trip for all its figures, using STORY-010's batched read — counted (1, against 9 the old way), not asserted in prose
- [x] The response is byte-identical to the pre-change server's for the same data; `StatsResponse`'s field set, types and ordering are unchanged — verified by two live servers against one database
- [x] The success-rate figure is still `successful / total` with the same semantics; `success = 1` still includes blocked-but-recorded queries, and was not "fixed" here. The formula moved operand for operand, the `total > 0` guard and the `"0.0%"` literal verbatim
- [x] The empty-database path behaves exactly as before — `"0.0%"`, no division by zero, byte-identical to the baseline server
- [x] The `stats:read` gate is unchanged: 401 without a token, 401 on a bad token, 403 naming `stats:read` for an authenticated caller lacking it, 200 for `auditor`
- [x] `tests/test_stats_router.py` passes with its assertions unchanged, plus new assertions pinning the single round trip (and the emptied tenth figure). One helper retargeted — see above
- [x] `GET /audit` is untouched. Its `count_audit_logs(user_id=scope_user_id)` and `list_audit_logs(..., user_id=...)` remain standalone scoped calls, both imports kept; the router diff is two hunks and neither is in `get_audit`, and `/audit` is byte-identical from both servers for both an `audit:read:all` and a scoped caller
