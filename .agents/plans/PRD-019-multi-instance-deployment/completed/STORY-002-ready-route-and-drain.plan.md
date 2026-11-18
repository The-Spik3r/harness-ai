---
story: STORY-002
prd: PRD-019
slug: ready-route-and-drain
title: GET /ready with the drain flag, routed through the in-container Caddy
type: NEW_CAPABILITY
complexity: medium
epic_branch: epic/PRD-019-multi-instance-deployment
created: 2026-11-17
---

# Plan: `GET /ready` and the drain flag

## Summary

Add a sync `GET /ready` next to `/health` in `app/main.py`. It checks the drain file first (`os.path.exists(settings.DRAIN_FILE)`, read at call time), then calls `database.check_ready()` (STORY-001) and maps the `ReadyCheck` to the PRD Section 10 bodies with a `JSONResponse`. Every response carries `Cache-Control: no-store`. `/ready` is added as an exact token to `@backend_routes` in the `Caddyfile` and to the restated lists in the two Caddy/route tests. New cases go in `tests/test_main.py`, all non-db (`check_ready` monkeypatched).

- Story: `.agents/stories/PRD-019-multi-instance-deployment/STORY-002-ready-route-and-drain.md` (AC text lives there)
- PRD sections used: 6.3, 7 F1-F2, 10, D3, D4 (D5 as a constraint)
- Systems affected: `app/main.py`, `Caddyfile`, 4 test files. No config change (`DRAIN_FILE` exists, `app/config.py:442`, validator at `:612`).

## Design Decisions (binding, from the orchestrator)

- **Order**: drain file, then `database.check_ready()`. Drained means 503 `{"status":"not_ready","reason":"draining"}` and `check_ready` is NOT called (no breaker/DB read). Read `settings.DRAIN_FILE` inside the handler, never at import.
- **Bodies, exactly Section 10** (tests compare parsed JSON with `==`):
  - `reason is None` -> 200 `{"status":"ready","breaker":"closed"}`.
  - `breaker_open` -> 503 `{"status":"not_ready","reason":"breaker_open","breaker":<ReadyCheck.breaker>}` + `Retry-After: str(retry_after_seconds)`.
  - `database_unreachable` / `database_auth` -> 503 `{"status":"not_ready","reason":<r>}`: no `breaker` key, no `Retry-After`.
  - Every response, 200 and 503: `Cache-Control: no-store`. No endpoint or error text in any body.
- **Sync `def` route**, `@app.get("/ready")`, same decorator style as `/health` (`app/main.py:39-41`; `/health` passes no `include_in_schema`, so `/ready` passes none either). No auth dependency.
- `/health` untouched (D3). Drain affects only `/ready`.
- The route never calls `_unit_of_work`, `record_*` or the driver (D5); it only calls `check_ready()`.
- `READY_REASONS` is at `app/db/database.py:777`; `draining` is the route's own. An unexpected reason (defensive) goes to the no-breaker 503 branch carrying that reason; do not invent a new one.

## Skills In Use

`.agents/skills/` holds only `frontend-design`; it does not apply (no UI). None.

## Patterns to Follow

| Category | Source | What to mirror |
|---|---|---|
| Route | `app/main.py:39-41` | `/health`: sync, plain `@app.get`; put `/ready` right after it with a PRD-019 comment |
| 503 + Retry-After | `app/routers/query.py:76-82` | `JSONResponse(..., headers={"Retry-After": str(retry_after)})` |
| Imports | `app/main.py:1-14` | add `import os`, `from fastapi.responses import JSONResponse`, and `database` to `from app.db import ...` (main.py has `from app.db import journal_drainer` and `from app.db.database import init_db`). Call `database.check_ready()` through the module attribute so a test can monkeypatch it |
| Matcher | `Caddyfile:5` | exact token before `/v1/*` |
| Restated matcher | `tests/test_caddyfile_routes.py:36-47` | one new entry with a `# PRD-019 STORY-002` comment, like `/storage/status` at `:42-44` |
| Test style | `tests/test_main.py:28-34` | module-level `client = TestClient(app)`; `monkeypatch.setattr(settings, ...)` |

## Files to Change

| File | Action | Purpose |
|---|---|---|
| `app/main.py` | UPDATE | `/ready` route + imports |
| `Caddyfile` | UPDATE | `/ready` in `@backend_routes` (line 5) |
| `tests/test_caddyfile_routes.py` | UPDATE | `EXPECTED_MATCHER` + near-miss static paths |
| `tests/test_route_reservations.py` | UPDATE | `/ready` present, no Reflex collision |
| `tests/test_main.py` | UPDATE | `/ready` cases (append; leave the `/health` cases alone) |

`tests/test_untouched_app.py` needs no change. It is PRD-006's guard: it never names `app/main.py` or a route, and it only fails if a test function disappears from the pinned suites (`_UNMODIFIED_SUITES`, `:73-78`, includes `test_route_reservations.py`); adding tests passes.

## Tasks

### Task 1: The route
- **File**: `app/main.py`
- **Implement**: `def ready()` after `health()`, under ~25 lines, comment citing PRD-019 F1/F2, D3, D4, D5. Build every response with `JSONResponse(status_code=..., content=..., headers=...)`; keep the `no-store` header in one place (a dict copied per response, `Retry-After` added only for `breaker_open`).
- **Mirror**: `app/routers/query.py:76-82`.
- **Validate**: `.venv/Scripts/python -c "from app.main import app; print('OK')"`

### Task 2: Caddyfile
- **File**: `Caddyfile`
- **Implement**: insert `/ready` between `/storage/status` and `/v1/*` on line 5. Nothing else changes.

### Task 3: Caddy matcher test
- **File**: `tests/test_caddyfile_routes.py`
- **Implement**: add `"/ready"` to `EXPECTED_MATCHER` after `/storage/status` with `# PRD-019 STORY-002: GET /ready (readiness probe); exact token, so a near-miss such as /readyx stays static.` Near-miss list: `STATIC_PATHS` (`:62-65`) is the only one; the `/storage/status` precedent is just a comment, no `/storage/statusx` entry exists. Add `"/readyx"`, `"/ready/"` and `"/readiness"` there with a `# PRD-019 STORY-002` comment. Optionally add `assert not _caddy_path_matches("/ready", "/readyx")` to `test_the_path_model_matches_caddy_semantics` (`:147`). `test_every_harness_route_is_proxied_by_caddy` picks `/ready` up from `app.routes` by itself.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_caddyfile_routes.py`

### Task 4: Route reservation test
- **File**: `tests/test_route_reservations.py`
- **Implement**: new `test_ready_route_present_and_not_reserved`: `"/ready" in _harness_route_paths()` and `"/ready" not in REFLEX_RESERVED_ROUTES`. Leave the existing `test_expected_harness_routes_present` (`:31`) untouched: it sits in the unmodified-suites census.

### Task 5: `/ready` tests
- **File**: `tests/test_main.py` (append after `test_health_returns_ok`, `:31-34`)
- **Implement**: a fixture points `settings.DRAIN_FILE` at `str(tmp_path / "drain")` (absent) via `monkeypatch.setattr`; a helper patches `database.check_ready` with a stub that records calls. Cases:
  1. ready `ReadyCheck(None, "closed")` -> 200, body `== {"status":"ready","breaker":"closed"}`, `Cache-Control == "no-store"`, no auth header sent.
  2. drain file present -> 503 `{"status":"not_ready","reason":"draining"}`, no-store, no `Retry-After`, stub call count 0; unlink the file -> 200 again.
  3. `breaker_open`, parametrized `open` / `half_open`, `retry_after_seconds=7` -> body `{"status":"not_ready","reason":"breaker_open","breaker":<state>}`, `Retry-After == "7"`, no-store.
  4. `database_unreachable` and `database_auth` (parametrized) -> body has exactly `status` and `reason`; no `retry-after` header; no-store.
  5. No-leak guard on every body: no `://`, `libsql`, `Traceback`.
  6. Drain affects only `/ready`: with the file present, `/health` returns the same status and the same bytes as without; one harness route that needs no DB (read `app/routers/query.py` / `app/routers/v1.py` for a real unauthenticated status, e.g. `/v1/models` 401) returns the same `(status, body)` with and without the file.
  7. Read at call time: repoint `settings.DRAIN_FILE` between two calls on the same client and see the response change.
- **Mirror**: `tests/test_main.py:28-34`.
- **Validate**: `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_main.py -k "ready or health or drain"`

## End-to-End Tests

- [ ] `TestClient(app).get("/ready")` with `check_ready` stubbed: status, body and headers for every class (Task 5, cases 1-4, 6).
- [ ] Optional: one unstubbed `GET /ready` against the dev libSQL server returning 200 `{"status":"ready","breaker":"closed"}`, only if a `temp_db`-style fixture in `test_main.py` makes it a few lines; STORY-001 already tests the real classifier.

## Validation

```bash
.venv/Scripts/python -c "from app.main import app; print('OK')"
PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider tests/test_main.py tests/test_caddyfile_routes.py tests/test_route_reservations.py tests/test_untouched_app.py
```
`tests/test_main.py` has db tests: if many error at fixture setup, `docker restart harness-libsql-dev`. Full suite: GitHub CI.

## Acceptance Criteria -> Tasks -> Tests

| AC | Task(s) | Test that proves it |
|---|---|---|
| AC1 ready 200 + no-store | 1, 5 | `tests/test_main.py::test_ready_returns_200_when_ready` |
| AC2 drain 503, no `check_ready`, only `/ready` affected, removal restores | 1, 5 | `test_ready_draining_*`, `test_drain_file_leaves_health_and_other_routes_unchanged` |
| AC3 breaker/db 503 bodies, headers, no leak | 1, 5 | `test_ready_breaker_open_*`, `test_ready_database_*` |
| AC4 `/health` unchanged | 1 (untouched) | existing `test_health_returns_ok` + the drain case |
| AC5 Caddy matcher + reservations | 2, 3, 4 | `test_the_matcher_is_exactly_the_expected_list`, `test_every_harness_route_is_proxied_by_caddy`, `test_ready_route_present_and_not_reserved` |

Test names are suggestions; the implementer may rename the new ones.

## Risks

- The monkeypatch only works if `main.py` calls `database.check_ready()` via the module attribute, not `from ... import check_ready`.
- `/ready` appears in `/openapi.json` like `/health`; harmless.
- `/ready/` (trailing slash) is a static 404 under Caddy, as `/health/` is.
